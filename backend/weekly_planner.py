"""
周计划调度器 - AI自动分配每日任务
家长选择本周任务池 → AI计算每日任务 → 家长确认 → 生效
"""
import sqlite3
import json
from datetime import datetime, timedelta


def get_db():
    return sqlite3.connect('/home/ubuntu/zlzp-dictation/dictation.db')


def create_weekly_plan(child_id: int, week_start: str, week_end: str) -> int:
    """创建新周计划，返回 plan_id"""
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
                  unit_name: str = None, content: str = None, total_chars: int = 0):
    """添加任务到周计划任务池"""
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        INSERT INTO weekly_plan_item (weekly_plan_id, task_type, unit_id, unit_name, content, total_chars)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (plan_id, task_type, unit_id, unit_name, content, total_chars))
    db.commit()
    item_id = cur.lastrowid
    db.close()
    return item_id


def get_wrongbook_chars(child_id: int) -> list:
    """获取错题本内容"""
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
    """获取某课的所有字词"""
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "SELECT char, word, pinyin FROM words WHERE unit_id = ?",
        (unit_id,)
    )
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


def ai_distribute_tasks(plan_id: int, week_start: str, week_end: str) -> dict:
    """
    AI 自动分配算法：
    - 听写：按课分，每天 15-25 字
    - 错题：每天 3-5 个，循环清除
    - 背诵：每天全量
    """
    db = get_db()
    cur = db.cursor()

    # 取周计划所有任务
    cur.execute("SELECT * FROM weekly_plan_item WHERE weekly_plan_id = ?", (plan_id,))
    items = cur.fetchall()  # (id, weekly_plan_id, task_type, unit_id, unit_name, content, total_chars, status, created_at)

    # 计算天数
    start_dt = datetime.strptime(week_start, "%Y-%m-%d")
    end_dt = datetime.strptime(week_end, "%Y-%m-%d")
    days_count = (end_dt - start_dt).days + 1

    # 分离任务类型
    dictation_items = [i for i in items if i[2] == 'dictation']
    wrongbook_items = [i for i in items if i[2] == 'wrongbook']
    recite_items = [i for i in items if i[2] == 'recite']

    # 取错题本内容
    child_id = 1  # 目前固定
    wrongbook_chars = get_wrongbook_chars(child_id)
    total_wrong_chars = len(wrongbook_chars)

    # 构建每天的任务预览
    daily_preview = {}
    for i in range(days_count):
        date = (start_dt + timedelta(days=i)).strftime("%Y-%m-%d")
        daily_preview[date] = {
            "dictation": [],
            "wrongbook": [],
            "recite": []
        }

    # --- 听写分配：均分到每天，不超过每天上限，但保证每天都有量 ---
    daily_dict_target = 18  # 每天目标 18 字左右
    day_idx = 0
    for item in dictation_items:
        unit_id = item[3]
        unit_name = item[4]
        chars = get_unit_chars(unit_id)
        total = len(chars)

        if total == 0:
            continue

        # 每课均分到每天（最少每天 2 字，最多每天 25 字）
        chars_per_day = max(2, min(25, total // days_count + 1))
        distributed = 0
        while distributed < total:
            date = (start_dt + timedelta(days=day_idx)).strftime("%Y-%m-%d")
            batch_size = min(chars_per_day, total - distributed)
            batch = chars[distributed:distributed + batch_size]
            daily_preview[date]["dictation"].append({
                "unit_id": unit_id,
                "unit_name": unit_name,
                "words": batch,
                "count": batch_size
            })
            distributed += batch_size
            day_idx = (day_idx + 1) % days_count

    # --- 错题分配：每天 3-5 个，循环 ---
    daily_wrong_count = 4  # 默认每天 4 个
    if total_wrong_chars > 0:
        for i in range(days_count):
            date = (start_dt + timedelta(days=i)).strftime("%Y-%m-%d")
            start_pos = (i * daily_wrong_count) % total_wrong_chars
            batch = []
            for j in range(daily_wrong_count):
                idx = (start_pos + j) % total_wrong_chars
                batch.append(wrongbook_chars[idx])
            daily_preview[date]["wrongbook"] = batch[:daily_wrong_count]

    # --- 背诵：每天全量 ---
    for item in recite_items:
        content = item[5]
        for i in range(days_count):
            date = (start_dt + timedelta(days=i)).strftime("%Y-%m-%d")
            daily_preview[date]["recite"].append({
                "content": content,
                "note": "不熟则明天继续"
            })

    db.close()

    return {
        "plan_id": plan_id,
        "days_count": days_count,
        "items_summary": {
            "dictation": [(i[3], i[4]) for i in dictation_items],  # (unit_id, unit_name)
            "wrongbook_count": total_wrong_chars,
            "recite_count": len(recite_items)
        },
        "daily_preview": daily_preview
    }


def confirm_weekly_plan(plan_id: int) -> dict:
    """确认周计划，生成正式每日任务"""
    db = get_db()
    cur = db.cursor()

    cur.execute("SELECT * FROM weekly_plan WHERE id = ?", (plan_id,))
    plan = cur.fetchone()
    if not plan:
        return {"error": "plan not found"}

    week_start = plan[2]
    week_end = plan[3]

    # 先删除已有的每日任务（草稿）
    cur.execute("DELETE FROM daily_task WHERE weekly_plan_id = ?", (plan_id,))

    # 获取 AI 分配预览
    preview = ai_distribute_tasks(plan_id, week_start, week_end)

    # 写入每日任务
    child_id = 1
    for date, tasks in preview["daily_preview"].items():
        # 听写
        for d_item in tasks["dictation"]:
            cur.execute("""
                INSERT INTO daily_task (child_id, weekly_plan_id, date, task_type, unit_id, unit_name, words, status)
                VALUES (?, ?, ?, 'dictation', ?, ?, ?, 'pending')
            """, (child_id, plan_id, date, d_item["unit_id"], d_item["unit_name"],
                  json.dumps(d_item["words"], ensure_ascii=False)))

        # 错题
        if tasks["wrongbook"]:
            cur.execute("""
                INSERT INTO daily_task (child_id, weekly_plan_id, date, task_type, words, status)
                VALUES (?, ?, ?, 'wrongbook', ?, 'pending')
            """, (child_id, plan_id, date, json.dumps(tasks["wrongbook"], ensure_ascii=False)))

        # 背诵
        for r_item in tasks["recite"]:
            cur.execute("""
                INSERT INTO daily_task (child_id, weekly_plan_id, date, task_type, content, status)
                VALUES (?, ?, ?, 'recite', ?, 'pending')
            """, (child_id, plan_id, date, r_item["content"]))

    cur.execute("UPDATE weekly_plan SET status = 'confirmed' WHERE id = ?", (plan_id,))
    db.commit()
    db.close()

    return {"success": True, "plan_id": plan_id}


def get_today_tasks(child_id: int = 1) -> list:
    """获取今日任务"""
    today = datetime.now().strftime("%Y-%m-%d")
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        SELECT id, task_type, unit_id, unit_name, content, words, status, completed_at
        FROM daily_task
        WHERE child_id = ? AND date = ? AND status != 'cancelled'
        ORDER BY FIELD(task_type, 'dictation', 'recite', 'wrongbook'), id
    """, (child_id, today))
    rows = cur.fetchall()
    db.close()

    tasks = []
    for r in rows:
        tasks.append({
            "id": r[0],
            "task_type": r[1],
            "unit_id": r[2],
            "unit_name": r[3],
            "content": r[4],
            "words": json.loads(r[5]) if r[5] else [],
            "status": r[6],
            "completed_at": r[7]
        })
    return tasks


def get_week_summary(child_id: int = 1) -> dict:
    """获取本周完成情况概览"""
    today = datetime.now()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    db = get_db()
    cur = db.cursor()
    cur.execute("""
        SELECT date, COUNT(*), SUM(status='completed')
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
