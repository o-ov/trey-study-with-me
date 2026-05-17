"""
english_setup.py — 每周英语内容配置脚本
用法: python english_setup.py --week 2026-05-18 --pdf /path/to/pdf

PDF 结构已知：
- Page 1: L30 (1-12) + L31 开头 (1-7: could~noon)
- Page 2: L31 续 (8-12: house~mouth) + Irregular Verbs Set.3
- Page 3: PEP Unit 5 Words + Key Dialogues
- Page 4: Tense 语法（不取）
"""

import os, sys, json, re, sqlite3, argparse
import fitz
from datetime import date, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "dictation.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_week_monday(week_date_str):
    d = date.fromisoformat(week_date_str)
    diff = d.weekday()
    return d - timedelta(days=diff)

# ─── 按页解析 PDF ────────────────────────────────────────────────

def extract_all(pdf_path):
    doc = fitz.open(pdf_path)
    pages = [page.get_text() for page in doc]
    doc.close()

    # Page 0: L30 (1-12) + L31 (1-7)
    l30 = extract_spelling_page0_l30(pages[0])
    l31_part1 = extract_spelling_page0_l31(pages[0])

    # Page 1: L31 (8-12) + Irregular Verbs
    l31_part2 = extract_spelling_page1_l31(pages[1])
    irregular = extract_irregular_page1(pages[1])

    # Page 2: PEP Words
    pep = extract_pep_page2(pages[2])

    l31 = l31_part1 + l31_part2
    return l30, l31, irregular, pep


def extract_spelling_page0_l30(text):
    """Page 0: L30，12个词，每词占5行（中间有空格）"""
    lines = [l.strip() for l in text.split('\n')]
    words = []
    l30_positions = [i for i, l in enumerate(lines) if re.match(r'^L30\s*$', l)]
    if not l30_positions:
        return words
    idx = l30_positions[0] + 1
    # 跳过空白行，找第一个编号行
    while idx < len(lines) and not re.match(r'^\d+$', lines[idx]):
        idx += 1
    for j in range(12):
        base = idx + j * 5
        if base + 4 < len(lines):
            no = lines[base].strip()
            word = lines[base+1].strip()
            pos = lines[base+3].strip()
            meaning = lines[base+4].strip()
            if re.match(r'^\d+$', no) and re.match(r'^[a-zA-Z]+$', word):
                words.append({'word': word.lower(), 'pos': pos, 'meaning': meaning})
    return words


def extract_spelling_page0_l31(text):
    """Page 0: L31 第1-7个词"""
    lines = [l.strip() for l in text.split('\n')]
    words = []
    for i, l in enumerate(lines):
        if re.match(r'^L31\s*$', l):
            idx = i + 1
            # 跳过空白行，找第一个编号行
            while idx < len(lines) and not re.match(r'^\d+$', lines[idx]):
                idx += 1
            for j in range(7):  # 前7个
                base = idx + j * 5
                if base + 4 < len(lines):
                    no = lines[base].strip()
                    word = lines[base+1].strip()
                    pos = lines[base+3].strip()
                    meaning = lines[base+4].strip()
                    if re.match(r'^\d+$', no) and re.match(r'^[a-zA-Z]+$', word):
                        words.append({'word': word.lower(), 'pos': pos, 'meaning': meaning})
            break
    return words


def extract_spelling_page1_l31(text):
    """Page 1: L31 第8-12个词 (5个)"""
    lines = [l.strip() for l in text.split('\n')]
    words = []
    # 第一行是 '2'（章编号），第二行是空，然后是 '8' 开始
    # 找编号8的位置
    start = -1
    for i, l in enumerate(lines):
        if l == '8' and i + 4 < len(lines) and re.match(r'^[a-zA-Z]+$', lines[i+1]):
            start = i
            break
    if start < 0:
        return words
    for j in range(5):
        base = start + j * 5
        if base + 4 < len(lines):
            no = lines[base].strip()
            word = lines[base+1].strip()
            pos = lines[base+3].strip()
            meaning = lines[base+4].strip()
            if re.match(r'^\d+$', no) and re.match(r'^[a-zA-Z]+$', word):
                words.append({'word': word.lower(), 'pos': pos, 'meaning': meaning})
    return words


def extract_irregular_page1(text):
    """Page 1: Irregular Verbs Set.3"""
    lines = [l.strip() for l in text.split('\n')]
    verbs = []
    start = -1
    for i, l in enumerate(lines):
        if 'Irregular Verbs' in l:
            start = i
            break
    if start < 0:
        return verbs

    # 从 Irregular Verbs 之后开始，收集所有动词
    # 每个动词: present(小写) / past / meaning，然后若干example行（以大写开头或含句子）
    i = start + 3  # 跳过表头3行 (Present Tense / Past Tense / Chinese Meaning)
    while i + 2 < len(lines):
        present = lines[i].strip()
        past = lines[i+1].strip()
        meaning = lines[i+2].strip()
        # 判断是否为有效动词行: present和past都是纯小写英文
        if re.match(r'^[a-z]+$', present) and re.match(r'^[a-z]+$', past):
            verbs.append({'word': f"{present}/{past}", 'pos': 'v.', 'meaning': meaning})
            i += 3
            # 跳过例句行（包含大写字母或包含完整句子的行）
            while i < len(lines):
                nxt = lines[i].strip()
                # 如果下一行是空行或下一个还是小写单词(下一个动词)，停止跳过
                if not nxt:
                    i += 1
                    continue
                # 例句通常以大写字母开头或包含多个单词
                if nxt and nxt[0].isupper() and ' ' in nxt:
                    i += 1
                    continue
                break
        else:
            i += 1
    return verbs


def extract_pep_page2(text):
    """Page 2: PEP Unit 5 Words，两列交替布局"""
    lines = [l.strip() for l in text.split('\n')]
    words = []
    # 找 'pass' 作为第一个词（Word表头的下一行开始就是pass）
    start = -1
    for i, l in enumerate(lines):
        if l == 'pass':
            start = i
            break
    if start < 0:
        return words

    # 从pass开始，两列交替：English, Chinese, English, Chinese...
    # 每4行是一对（两个词）
    i = start
    while i + 1 < len(lines):
        w1 = lines[i].strip()
        c1 = lines[i+1].strip()
        if i + 3 < len(lines):
            w2 = lines[i+2].strip()
            c2 = lines[i+3].strip()
            # 遇到对话/段落标题停止
            if any(h in w1 for h in ['Key Dialogues', 'Paragraphs']):
                break
            # 检查w1是否是纯英文单词
            w1_clean = re.sub(r'\s*\([^)]*\)', '', w1).strip().lower()
            w2_clean = re.sub(r'\s*\([^)]*\)', '', w2).strip().lower()
            # 左列
            if re.match(r'^[a-z]+$', w1_clean) and c1 and not re.match(r'^[a-z]', c1[0]):
                words.append({'word': w1_clean, 'pos': '', 'meaning': c1})
            # 右列
            if re.match(r'^[a-z]+$', w2_clean) and c2 and not re.match(r'^[a-z]', c2[0]):
                words.append({'word': w2_clean, 'pos': '', 'meaning': c2})
            i += 4
        else:
            break
    return words


def run(pdf_path, week_date_str):
    monday = get_week_monday(week_date_str)
    week_str = monday.isoformat()

    l30, l31, irregular, pep = extract_all(pdf_path)

    print(f"L30: {len(l30)} words → {', '.join(w['word'] for w in l30[:3])}...")
    print(f"L31: {len(l31)} words → {', '.join(w['word'] for w in l31[:3])}...")
    print(f"Irregular: {len(irregular)} verbs → {', '.join(v['word'] for v in irregular[:3])}...")
    print(f"PEP: {len(pep)} words → {', '.join(w['word'] for w in pep[:5])}...")

    db = get_db()
    cur = db.cursor()

    # 清除旧数据
    cur.execute("DELETE FROM english_words WHERE week_date=?", (week_str,))
    cur.execute("DELETE FROM english_articles WHERE week_date=?", (week_str,))
    cur.execute("DELETE FROM english_schedule WHERE child_id=1 AND date>=? AND date<?",
                (week_str, (monday + timedelta(days=7)).isoformat()))

    # 写入 Spelling L30
    for w in l30:
        cur.execute(
            "INSERT INTO english_words (word, pos, meaning, lesson, week_date, word_type) VALUES (?,?,?,?,?,?)",
            (w['word'], w['pos'], w['meaning'], 'L30', week_str, 'spelling')
        )
    # 写入 Spelling L31
    for w in l31:
        cur.execute(
            "INSERT INTO english_words (word, pos, meaning, lesson, week_date, word_type) VALUES (?,?,?,?,?,?)",
            (w['word'], w['pos'], w['meaning'], 'L31', week_str, 'spelling')
        )
    # 写入 Irregular
    for w in irregular:
        cur.execute(
            "INSERT INTO english_words (word, pos, meaning, lesson, week_date, word_type) VALUES (?,?,?,?,?,?)",
            (w['word'], w['pos'], w['meaning'], 'Set.3', week_str, 'irregular')
        )
    # 写入 PEP
    for w in pep:
        cur.execute(
            "INSERT INTO english_words (word, pos, meaning, lesson, week_date, word_type) VALUES (?,?,?,?,?,?)",
            (w['word'], w['pos'], w['meaning'], 'Unit5', week_str, 'pep')
        )

    # 生成调度
    all_spelling = l30 + l31
    schedule = [
        # Monday: L30 + irregular前4 + PEP前7
        {'date': monday.isoformat(), 'type': 'spelling', 'lesson': 'L30', 'count': len(l30)},
        {'date': monday.isoformat(), 'type': 'irregular', 'lesson': 'Set.3-1', 'count': min(4, len(irregular))},
        {'date': monday.isoformat(), 'type': 'pep', 'lesson': 'Unit5-1', 'count': min(7, len(pep))},
        # Tuesday: L30复习 + irregular后4 + PEP后8
        {'date': (monday+timedelta(1)).isoformat(), 'type': 'spelling', 'lesson': 'L30-review', 'count': len(l30)},
        {'date': (monday+timedelta(1)).isoformat(), 'type': 'irregular', 'lesson': 'Set.3-2', 'count': min(4, len(irregular))},
        {'date': (monday+timedelta(1)).isoformat(), 'type': 'pep', 'lesson': 'Unit5-2', 'count': min(8, len(pep))},
        # Wednesday: L31 + irregular混合 + PEP前7
        {'date': (monday+timedelta(2)).isoformat(), 'type': 'spelling', 'lesson': 'L31', 'count': len(l31)},
        {'date': (monday+timedelta(2)).isoformat(), 'type': 'irregular', 'lesson': 'Set.3-mix', 'count': min(4, len(irregular))},
        {'date': (monday+timedelta(2)).isoformat(), 'type': 'pep', 'lesson': 'Unit5-1', 'count': min(7, len(pep))},
        # Thursday: L31复习 + irregular混合复习 + PEP后8
        {'date': (monday+timedelta(3)).isoformat(), 'type': 'spelling', 'lesson': 'L31-review', 'count': len(l31)},
        {'date': (monday+timedelta(3)).isoformat(), 'type': 'irregular', 'lesson': 'Set.3-mix', 'count': min(4, len(irregular))},
        {'date': (monday+timedelta(3)).isoformat(), 'type': 'pep', 'lesson': 'Unit5-2', 'count': min(8, len(pep))},
        # Friday: 全部复习
        {'date': (monday+timedelta(4)).isoformat(), 'type': 'spelling', 'lesson': 'ALL', 'count': len(all_spelling)},
        {'date': (monday+timedelta(4)).isoformat(), 'type': 'irregular', 'lesson': 'ALL', 'count': len(irregular)},
        {'date': (monday+timedelta(4)).isoformat(), 'type': 'pep', 'lesson': 'ALL', 'count': len(pep)},
    ]

    for s in schedule:
        cur.execute(
            "INSERT INTO english_schedule (child_id, date, task_type, lesson, task_data) VALUES (?,?,?,?,?)",
            (1, s['date'], s['type'], s['lesson'], json.dumps({'lesson': s['lesson'], 'count': s['count']}))
        )

    db.commit()

    # 验证
    cur.execute("SELECT word_type, COUNT(*) FROM english_words WHERE week_date=? GROUP BY word_type", (week_str,))
    print("\n📊 DB 验证:")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]}")
    db.close()

    print(f"\n✅ 已写入 {week_str}")
    return {'l30': l30, 'l31': l31, 'irregular': irregular, 'pep': pep}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--week', required=True)
    parser.add_argument('--pdf', required=True)
    args = parser.parse_args()
    run(args.pdf, args.week)
