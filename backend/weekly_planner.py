"""
周计划调度器 - 基于 MiniMax LLM 智能分配
家长选择本周任务池 → LLM理解内容 → 智能分配每日任务 → 家长确认 → 生效
"""
import sqlite3
import json
import os
import requests
from datetime import datetime, timedelta


MINIMAX_KEY = os.environ.get(
    "MINIMAX_CN_API_KEY",
    os.environ.get("MINIMAX_API_KEY", "")
)
MINIMAX_URL = "https://api.minimaxi.com/anthropic/v1/messages"
MODEL = "MiniMax-M2.7-highspeed"


def get_db():
    return sqlite3.connect('/home/ubuntu/zlzp-dictation/dictation.db')


# ─── MiniMax LLM 调用 ────────────────────────────────────────

def call_minimax(system: str, user: str, max_tokens: int = 10000) -> str:
    """调用 MiniMax LLM，返回文本内容"""
    key = MINIMAX_KEY
    if not key:
        # 尝试从 .env 读取（仅本地文件，不上传 GitHub）
        env_file = os.path.expanduser("~/.hermes/.env")
        if os.path.exists(env_file):
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("MINIMAX_API_KEY=") or line.startswith("MINIMAX_CN_API_KEY="):
                        key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if key:
                            break

    if not key:
        raise ValueError("MiniMax API key not found")

    headers = {
        "x-api-key": key,
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01"
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": f"{system}\n\n{user}"}
        ],
        "max_tokens": max_tokens
    }

    resp = requests.post(MINIMAX_URL, headers=headers, json=payload, timeout=90)
    data = resp.json()

    if data.get("type") == "error":
        raise RuntimeError(f"MiniMax error: {data['error']['message']}")

    # 解析 content blocks（可能有 thinking + text）
    content_blocks = data.get("content", [])
    text = ""
    for block in content_blocks:
        if isinstance(block, dict) and block.get("type") == "text":
            text += block.get("text", "")

    if not text:
        # fallback：直接返回原始 data
        raise RuntimeError(f"MiniMax returned no text content: {str(data)[:200]}")
    return text


# ─── 任务数据获取 ──────────────────────────────────────────

def get_wrongbook_chars(child_id: int) -> list:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "SELECT char, word, pinyin FROM wrongbook WHERE child_id = ? ORDER BY wrong_count DESC",
        (child_id,)
    )
    rows = cur.fetchall()
    db.close()
    return [{"char": r[0], "word": r[1], "pinyin": r[2]} for r in rows]


def get_unit_chars(unit_id: str) -> list:
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT char, word, pinyin FROM words WHERE unit_id = ?", (unit_id,))
    rows = cur.fetchall()
    db.close()
    return [{"char": r[0], "word": r[1], "pinyin": r[2]} for r in rows]


def get_unit_chars_count(unit_id: str) -> int:
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT COUNT(*) FROM words WHERE unit_id = ?", (unit_id,))
    count = cur.fetchone()[0]
    db.close()
    return count


# ─── 周计划基础操作 ────────────────────────────────────────

def get_plan_items(plan_id: int) -> list:
    """获取计划的所有任务项"""
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        SELECT id, task_type, unit_id, unit_name, content, total_chars, chars
        FROM weekly_plan_item WHERE weekly_plan_id = ?
    """, (plan_id,))
    rows = cur.fetchall()
    db.close()
    import json
    return [
        {"id": r[0], "task_type": r[1], "unit_id": r[2],
         "unit_name": r[3], "content": r[4], "total_chars": r[5],
         "chars": json.loads(r[6]) if r[6] else []}
        for r in rows
    ]


def create_weekly_plan(child_id: int, week_start: str, week_end: str) -> int:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "INSERT INTO weekly_plan (child_id, week_start, week_end) VALUES (?, ?, ?)",
        (child_id, week_start, week_end)
    )
    db.commit()
    plan_id = cur.lastrowid
    db.close()
    return plan_id


def add_plan_item(plan_id: int, task_type: str, unit_id: str = None,
                  unit_name: str = None, content: str = None,
                  total_chars: int = 0, chars: list = None):
    import json
    db = get_db()
    cur = db.cursor()
    chars_json = json.dumps(chars or [], ensure_ascii=False)
    cur.execute("""
        INSERT INTO weekly_plan_item (weekly_plan_id, task_type, unit_id, unit_name, content, total_chars, chars)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (plan_id, task_type, unit_id, unit_name, content, total_chars, chars_json))
    db.commit()
    item_id = cur.lastrowid
    db.close()
    return item_id


# ─── LLM 智能分配 ─────────────────────────────────────────

def simple_distribute_tasks(plan_id: int, week_start: str, week_end: str) -> dict:
    """
    规则均分（无需 LLM）：
    - 听写：按天数均分，每天 15~25 字
    - 错题：每天全量
    - 背诵：每天全量
    """
    db = get_db()
    cur = db.cursor()

    cur.execute("SELECT * FROM weekly_plan_item WHERE weekly_plan_id = ?", (plan_id,))
    items = cur.fetchall()

    start_dt = datetime.strptime(week_start, "%Y-%m-%d")
    end_dt = datetime.strptime(week_end, "%Y-%m-%d")
    days_count = (end_dt - start_dt).days + 1

    # 收集每天的日期字符串
    dates = [(start_dt + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days_count)]

    dictation_details = []
    recite_details = []
    has_wrongbook = False

    import json
    for item in items:
        task_type = item[2]
        if task_type == 'dictation':
            unit_id = item[3]
            unit_name = item[4]
            chars_json = item[9] if len(item) > 9 else None
            chars = json.loads(chars_json) if chars_json and chars_json.strip() else []
            # 如果没有存储的字（兼容旧数据），从words表读全量
            if not chars:
                chars = get_unit_chars(unit_id)
            dictation_details.append({"unit_id": unit_id, "unit_name": unit_name, "chars": chars})
        elif task_type == 'recite':
            recite_details.append({"name": item[4] or "背诵", "content": item[5]})
        elif task_type == 'wrongbook':
            has_wrongbook = True

    db.close()

    # ── 均分听写 ──
    all_chars = []
    for d in dictation_details:
        chars = d["chars"]
        if isinstance(chars, list) and len(chars) > 0:
            # get_unit_chars 返回的是 list of dict {char, word, pinyin}
            for c in chars:
                if isinstance(c, dict):
                    all_chars.append({**c, "unit_id": d["unit_id"], "unit_name": d["unit_name"]})
                else:
                    all_chars.append({"char": str(c), "word": "", "pinyin": "", "unit_id": d["unit_id"], "unit_name": d["unit_name"]})

    chars_per_day = max(15, min(25, len(all_chars) // days_count)) if all_chars else 0
    daily_preview = {}
    char_idx = 0

    for i, date in enumerate(dates):
        # 今天分完所有剩余的字（往前天数不够均分时，最后一天兜底）
        remaining = len(all_chars) - char_idx
        if remaining <= 0:
            chars_for_today = 0
        elif remaining < chars_per_day and i < days_count - 1:
            # 剩余不多，提前结束，后面的天留到最后的兜底日
            chars_for_today = 0
        else:
            chars_for_today = chars_per_day

        day_chars = []
        for _ in range(chars_for_today):
            if char_idx < len(all_chars):
                c = all_chars[char_idx]
                day_chars.append({"unit_id": c.get("unit_id"), "unit_name": c.get("unit_name"),
                                  "char": c["char"], "word": c.get("word", ""), "pinyin": c.get("pinyin", "")})
                char_idx += 1

        # 最后一天兜底：把剩余字全塞进去
        if i == days_count - 1:
            while char_idx < len(all_chars):
                c = all_chars[char_idx]
                day_chars.append({"unit_id": c.get("unit_id"), "unit_name": c.get("unit_name"),
                                  "char": c["char"], "word": c.get("word", ""), "pinyin": c.get("pinyin", "")})
                char_idx += 1

        daily_preview[date] = {
            "dictation": [{"unit_id": c["unit_id"], "unit_name": c["unit_name"],
                           "char": c["char"], "word": c.get("word", ""), "pinyin": c["pinyin"]} for c in day_chars] if day_chars else [],
            "wrongbook": [{"char": c["char"], "word": c["word"], "pinyin": c["pinyin"]}
                          for c in get_wrongbook_chars(1)] if has_wrongbook else [],
            "recite": [{"name": r["name"], "content": r["content"]} for r in recite_details]
        }

    return {
        "plan_id": plan_id,
        "days_count": days_count,
        "daily_preview": daily_preview,
        "llm_reasoning": "规则均分：听写每天约" + str(chars_per_day) + "字，错题/背诵每天全量"
    }


# ─── 确认周计划 ──────────────────────────────────────────

def confirm_weekly_plan(plan_id: int) -> dict:
    """确认周计划，生成正式每日任务（规则均分，不调用 LLM）"""
    db = get_db()
    cur = db.cursor()

    cur.execute("SELECT * FROM weekly_plan WHERE id = ?", (plan_id,))
    plan = cur.fetchone()
    if not plan:
        return {"error": "plan not found"}

    week_start = plan[2]
    week_end = plan[3]

    cur.execute("DELETE FROM daily_task WHERE weekly_plan_id = ?", (plan_id,))

    preview = simple_distribute_tasks(plan_id, week_start, week_end)

    child_id = 1
    for date, tasks in preview["daily_preview"].items():
        # 听写：每天一个 task，多个字打包在一起
        dict_items = tasks.get("dictation", [])
        if dict_items:
            # 把每天所有字合并成一个 dictation task
            all_words = []
            for d_item in dict_items:
                ch = d_item.get("char", "")
                if ch:
                    all_words.append({"char": ch, "word": d_item.get("word", ""), "pinyin": d_item.get("pinyin", "")})
            if all_words:
                # 取第一条的 unit 作为代表
                first = dict_items[0]
                words_json = json.dumps(all_words, ensure_ascii=False)
                cur.execute("""
                    INSERT INTO daily_task (child_id, weekly_plan_id, date, task_type, unit_id, unit_name, words, status)
                    VALUES (?, ?, ?, 'dictation', ?, ?, ?, 'pending')
                """, (child_id, plan_id, date, first.get("unit_id"), first.get("unit_name"), words_json))

        # 错题
        for w_item in tasks.get("wrongbook", []):
            cur.execute("""
                INSERT INTO daily_task (child_id, weekly_plan_id, date, task_type, words, status)
                VALUES (?, ?, ?, 'wrongbook', ?, 'pending')
            """, (child_id, plan_id, date, json.dumps(w_item, ensure_ascii=False)))

        # 背诵
        for r_item in tasks.get("recite", []):
            cur.execute("""
                INSERT INTO daily_task (child_id, weekly_plan_id, date, task_type, content, status)
                VALUES (?, ?, ?, 'recite', ?, 'pending')
            """, (child_id, plan_id, date, r_item.get("content", "")))

    cur.execute("UPDATE weekly_plan SET status = 'confirmed' WHERE id = ?", (plan_id,))
    db.commit()
    db.close()

    return {"success": True, "plan_id": plan_id, "llm_reasoning": preview.get("llm_reasoning", "")}


# ─── 查询接口 ─────────────────────────────────────────────

def get_today_tasks(child_id: int = 1) -> list:
    today = datetime.now().strftime("%Y-%m-%d")
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        SELECT id, task_type, unit_id, unit_name, content, words, status, completed_at
        FROM daily_task
        WHERE child_id = ? AND date = ? AND status != 'cancelled'
        ORDER BY CASE task_type
            WHEN 'dictation' THEN 1
            WHEN 'recite' THEN 2
            WHEN 'wrongbook' THEN 3
            ELSE 4 END, id
    """, (child_id, today))
    rows = cur.fetchall()
    db.close()

    tasks = []
    for r in rows:
        words = r[5]
        if words:
            try:
                words = json.loads(words)
            except:
                words = []
        else:
            words = []
        tasks.append({
            "id": r[0],
            "task_type": r[1],
            "unit_id": r[2],
            "unit_name": r[3],
            "content": r[4],
            "words": words,
            "status": r[6],
            "completed_at": r[7]
        })
    return tasks


def get_week_summary(child_id: int = 1) -> dict:
    today = datetime.now()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    db = get_db()
    cur = db.cursor()
    cur.execute("""
        SELECT date, COUNT(*), SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END)
        FROM daily_task
        WHERE child_id = ? AND date >= ? AND date <= ?
        GROUP BY date
        ORDER BY date
    """, (child_id, week_start.strftime("%Y-%m-%d"), week_end.strftime("%Y-%m-%d")))
    rows = cur.fetchall()
    db.close()

    return {
        "week_start": week_start.strftime("%Y-%m-%d"),
        "week_end": week_end.strftime("%Y-%m-%d"),
        "daily": [{"date": r[0], "total": r[1], "done": r[2]} for r in rows]
    }
