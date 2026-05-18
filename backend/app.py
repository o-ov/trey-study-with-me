"""
app.py — 听写 App 后端 API（Flask · 8080）
"""

import os, json, uuid, sqlite3, base64, subprocess, urllib.request
from datetime import datetime, date, timedelta
from functools import wraps
from flask import Flask, send_from_directory, jsonify, request, send_file
from werkzeug.utils import secure_filename
from flask_cors import CORS

app = Flask(__name__)
CORS(app, origins=["http://47.243.65.57:3000", "http://47.243.65.57:3001", "http://43.160.222.242:3000", "http://43.160.222.242:3001"])
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DB_PATH     = os.path.join(BASE_DIR, "..", "dictation.db")
UPLOAD_DIR  = os.path.join(BASE_DIR, "uploads")
SESSION_DIR = os.path.join(BASE_DIR, "sessions")

os.makedirs(UPLOAD_DIR,  exist_ok=True)
os.makedirs(SESSION_DIR, exist_ok=True)

# ─── 勋章种子数据（启动时保证存在） ──────────────────────────
BADGE_DEFS = [
    ("first_practice",       "初次练习",   "🌱", "完成第1次练习",              0),
    ("streak_3",             "连续3天",     "🔥", "连续练习3天",               0),
    ("perfect_10",           "十全十美",    "💯", "单次练习10字全对",           0),
    ("neat_writer",          "整洁书写",    "✍️", "单次练习连续5字全对",         0),
    ("wrongbook_cleared_20", "错字清道夫", "🧹", "累计复习20个错字",           0),
    ("streak_7",             "连续7天",     "📆", "连续练习7天",               0),
    ("hundred_perfect",      "百分达人",    "🏆", "累计100字全对",             0),
    ("monthly_practitioner", "月度练习家", "📅", "累计练习30天",              0),
    ("lv10",                 "全能小王",    "👑", "达到Lv10",                 0),
]

def seed_badges():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    for key, name, icon, cond, pts in BADGE_DEFS:
        cur.execute(
            "INSERT OR IGNORE INTO badges (badge_key, name, icon, condition, points) VALUES (?,?,?,?,?)",
            (key, name, icon, cond, pts)
        )
    conn.commit()
    conn.close()

seed_badges()


# ─── 数据库工具 ──────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def row_to_dict(row):
    return dict(row) if row else None


# ─── 等级计算（按完成 session 数） ──────────────────────────
# Lv1-5: 每完成1个session升1级
# Lv6-20: 每完成2个session升1级
# Lv21+: 每完成3个session升1级

def calc_level_from_sessions(session_count):
    if session_count < 5:
        return session_count + 1  # Lv1 needs 0 sessions, Lv5 needs 4
    elif session_count < 5 + 8 * 2:  # Lv6 needs 5 sessions (4+1), up to Lv20
        return 5 + (session_count - 4) // 2
    else:
        return 20 + (session_count - (4 + 16 * 2)) // 3

LEVEL_NAMES = {
    1: "识字小童", 2: "书写新手", 3: "错字克星", 4: "听写达人",
    5: "文字小博士", 6: "词语大师", 7: "书法小将",
    8: "语文小标兵", 9: "文字小精灵", 10: "全能小王",
    11: "勤学小将", 12: "汉字小博士", 13: "词汇小达人",
    14: "书写小高手", 15: "听写小专家", 16: "错字终结者",
    17: "满分小达人", 18: "连续作战小能手", 19: "词语小博士",
    20: "全能小学霸", 21: "语文小状元", 22: "汉字小冠军",
    23: "词汇小大师", 24: "书写小艺术家", 25: "语文小天才"
}

def calc_level(points):
    # 兼容旧接口，通过 session 数反推 level
    conn = get_db()
    cur = conn.cursor()
    session_count = cur.execute(
        "SELECT COUNT(*) FROM sessions WHERE child_id=1 AND status='submitted'"
    ).fetchone()[0]
    conn.close()
    return calc_level_from_sessions(session_count)

def level_name(level):
    return LEVEL_NAMES.get(level, "全能小王")

def next_threshold(level):
    # 返回升到下一级所需的 session 数
    current_sessions = (level - 1) if level <= 5 else (4 + (level - 5) * 2)
    if level <= 5:
        next_sessions = level  # Lv N 需要 N sessions
    elif level < 20:
        next_sessions = 4 + (level - 4) * 2
    else:
        next_sessions = 4 + 16 * 2 + (level - 20) * 3
    return next_sessions  # 简化：返回所需session数，实际前端用 progress 计算百分比


# ─── 飞书通知 ────────────────────────────────────────────────

FEISHU_CHAT_ID = "oc_7c2b51a013b7408f6cb978c3f44cf48c"

def feishu_notify(text):
    try:
        import subprocess
        subprocess.run(
            ["lark-cli", "im", "+messages-send",
             "--chat-id", FEISHU_CHAT_ID,
             "--text", text],
            capture_output=True, text=True, timeout=15
        )
    except Exception:
        pass  # 非关键，失败静默


# ─── 静态资源 ───────────────────────────────────────────────

@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    resp = send_from_directory(UPLOAD_DIR, filename)
    resp.headers["Access-Control-Allow-Origin"] = "http://47.243.65.57:3001"
    resp.headers["Access-Control-Allow-Credentials"] = "true"
    return resp


@app.route("/api/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "no file"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "empty filename"}), 400
    filename = secure_filename(file.filename)
    file.save(os.path.join(UPLOAD_DIR, filename))
    return jsonify({"url": "/uploads/" + filename})


# ─── 健康检查 ───────────────────────────────────────────────

@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})


# ════════════════════════════════════════════════════════════
#  字库
# ════════════════════════════════════════════════════════════

@app.route("/api/words", methods=["GET"])
def list_words():
    unit_id = request.args.get("unit")
    conn = get_db()
    cur = conn.cursor()
    if unit_id:
        rows = cur.execute(
            "SELECT * FROM words WHERE unit_id=? ORDER BY id", (unit_id,)
        ).fetchall()
    else:
        rows = cur.execute("SELECT * FROM words ORDER BY id").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/words/units", methods=["GET"])
def list_units():
    conn = get_db()
    cur = conn.cursor()
    rows = cur.execute(
        "SELECT DISTINCT unit_id, unit_name FROM words ORDER BY id"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/words/daily", methods=["GET"])
def daily_words():
    """返回今日练习字（优先错题，避开已掌握）"""
    child_id = request.args.get("child_id", 1, type=int)
    conn = get_db()
    cur = conn.cursor()
    # 已掌握的错字
    mastered = [
        r["char"] for r in cur.execute(
            "SELECT char FROM wrongbook WHERE child_id=? AND reviewed=1", (child_id,)
        ).fetchall()
    ]
    placeholders = "NULL" if not mastered else ",".join(["?"] * len(mastered))
    rows = cur.execute(
        f"SELECT * FROM words WHERE char NOT IN ({placeholders}) ORDER BY RANDOM() LIMIT 20",
        mastered or []
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# ════════════════════════════════════════════════════════════
#  Session（练习）
# ════════════════════════════════════════════════════════════

@app.route("/api/sessions", methods=["POST"])
def create_session():
    data = request.get_json()
    mode     = data.get("mode", "dictation")
    unit_ids = data.get("unit_ids", [])
    child_id = data.get("child_id", 1)

    conn = get_db()
    cur = conn.cursor()

    # 收集字：优先用前端传入的 words（复习/错题专用），否则按 unit_ids 查库
    incoming_words = data.get("words", [])
    if incoming_words:
        words = incoming_words if isinstance(incoming_words, list) else [incoming_words]
    elif unit_ids:
        placeholders = ",".join(["?"] * len(unit_ids))
        rows = cur.execute(
            f"SELECT * FROM words WHERE unit_id IN ({placeholders}) ORDER BY id",
            unit_ids
        ).fetchall()
        words = [dict(r) for r in rows]
    else:
        rows = cur.execute("SELECT * FROM words ORDER BY RANDOM() LIMIT 10").fetchall()
        words = [dict(r) for r in rows]
    total = len(words)

    session_key = uuid.uuid4().hex[:8]
    cur.execute(
        "INSERT INTO sessions (child_id, session_key, mode, unit_ids, status, total_chars) "
        "VALUES (?,?,?,?,?,?)",
        (child_id, session_key, mode, json.dumps(unit_ids), "draft", total)
    )
    session_id = cur.lastrowid

    # 写入 session_chars，同时收集其真实 PK
    char_ids = []
    for w in words:
        char   = w["char"] or ""
        word   = w.get("word") or ""
        pinyin = w.get("pinyin") or ""
        cur.execute(
            "INSERT INTO session_chars (session_id, char, word, pinyin) VALUES (?,?,?,?)",
            (session_id, char, word, pinyin)
        )
        char_ids.append(cur.lastrowid)

    conn.commit()
    conn.close()
    return jsonify({"session_id": session_id, "session_key": session_key, "words": words, "char_ids": char_ids})


@app.route("/api/sessions", methods=["GET"])
def list_sessions():
    child_id = request.args.get("child_id", 1, type=int)
    status   = request.args.get("status")
    conn = get_db()
    cur = conn.cursor()
    if status:
        rows = cur.execute(
            "SELECT * FROM sessions WHERE child_id=? AND status=? ORDER BY created_at DESC",
            (child_id, status)
        ).fetchall()
    else:
        rows = cur.execute(
            "SELECT * FROM sessions WHERE child_id=? ORDER BY created_at DESC",
            (child_id,)
        ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/sessions/<int:sid>", methods=["GET"])
def get_session(sid):
    conn = get_db()
    cur = conn.cursor()
    sess = cur.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
    if not sess:
        conn.close()
        return jsonify({"error": "not found"}), 404
    chars = cur.execute(
        "SELECT * FROM session_chars WHERE session_id=?", (sid,)
    ).fetchall()
    conn.close()
    return jsonify({"session": dict(sess), "chars": [dict(c) for c in chars]})


@app.route("/api/sessions/<int:sid>", methods=["PUT"])
def update_session(sid):
    data = request.get_json()
    conn = get_db()
    cur = conn.cursor()
    sess = cur.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
    if not sess:
        conn.close()
        return jsonify({"error": "not found"}), 404

    if "image_url" in data:
        char_val  = data.get("char")
        image_url = data["image_url"]
        if char_val is not None:
            cur.execute(
                "UPDATE session_chars SET image_url=? WHERE session_id=? AND char=?",
                (image_url, sid, char_val)
            )

    conn.commit()
    conn.close()
    return jsonify({"ok": True})


def check_and_unlock_badges(conn, cur, child_id):
    """检查并解锁可获得的勋章，返回新增解锁数量"""
    all_badges = cur.execute("SELECT * FROM badges").fetchall()
    earned_rows = cur.execute(
        "SELECT badge_id FROM child_badges WHERE child_id=?", (child_id,)
    ).fetchall()
    earned_ids = {r["badge_id"] for r in earned_rows}

    child = cur.execute("SELECT * FROM child WHERE id=?", (child_id,)).fetchone()
    session_count = cur.execute(
        "SELECT COUNT(*) FROM sessions WHERE child_id=? AND status='submitted'", (child_id,)
    ).fetchone()[0]
    total_correct = cur.execute(
        "SELECT COUNT(*) FROM session_chars WHERE correct=1 AND session_id IN "
        "(SELECT id FROM sessions WHERE child_id=?)", (child_id,)
    ).fetchone()[0]
    cleared_wrong = cur.execute(
        "SELECT COUNT(*) FROM wrongbook WHERE child_id=? AND reviewed=1", (child_id,)
    ).fetchone()[0]
    session_days = cur.execute(
        "SELECT COUNT(DISTINCT DATE(created_at)) FROM sessions WHERE child_id=?", (child_id,)
    ).fetchone()[0]
    new_level = calc_level_from_sessions(session_count)

    added = 0
    for badge in all_badges:
        if badge["id"] in earned_ids:
            continue
        key = badge["badge_key"]
        unlock = False
        if key == "first_practice" and session_count >= 1:
            unlock = True
        elif key == "streak_3" and child["streak_days"] >= 3:
            unlock = True
        elif key == "streak_7" and child["streak_days"] >= 7:
            unlock = True
        elif key == "perfect_10":
            row = cur.execute(
                "SELECT COUNT(*) FROM sessions WHERE child_id=? AND correct_chars=total_chars AND total_chars>=10",
                (child_id,)
            ).fetchone()
            if row and row[0] >= 1:
                unlock = True
        elif key == "hundred_perfect" and total_correct >= 100:
            unlock = True
        elif key == "wrongbook_cleared_20" and cleared_wrong >= 20:
            unlock = True
        elif key == "monthly_practitioner" and session_days >= 30:
            unlock = True
        elif key == "lv10" and new_level >= 10:
            unlock = True
        if unlock:
            cur.execute(
                "INSERT OR IGNORE INTO child_badges (child_id, badge_id) VALUES (?,?)",
                (child_id, badge["id"])
            )
            earned_ids.add(badge["id"])
            added += 1
    return added


@app.route("/api/sessions/<int:sid>/submit", methods=["POST"])
def submit_session(sid):
    conn = get_db()
    cur = conn.cursor()
    sess = cur.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
    if not sess or sess["status"] != "draft":
        conn.close()
        return jsonify({"error": "invalid session"}), 400

    char_count = request.get_json().get("char_count", 0)

    # 更新状态
    cur.execute("UPDATE sessions SET status='submitted' WHERE id=?", (sid,))

    # 每次完成练习得5分（每天一练）
    cur.execute("UPDATE child SET points=points+5, last_practice=? WHERE id=1",
                (date.today().isoformat(),))
    conn.commit()

    # 更新等级
    session_count = cur.execute(
        "SELECT COUNT(*) FROM sessions WHERE child_id=1 AND status='submitted'"
    ).fetchone()[0]
    new_level = calc_level_from_sessions(session_count)
    cur.execute("UPDATE child SET level=? WHERE id=1", (new_level,))

    # 检查并解锁勋章
    badges_added = check_and_unlock_badges(conn, cur, 1)

    conn.commit()
    conn.close()

    feishu_notify(f"📝 小树提交了听写练习，共 {char_count} 个字，请及时批改。")
    if badges_added:
        feishu_notify(f"🎉 解锁了 {badges_added} 个新勋章！")
    return jsonify({"ok": True, "points_added": 5, "new_level": new_level})


# ════════════════════════════════════════════════════════════
#  批改
# ════════════════════════════════════════════════════════════

@app.route("/api/sessions/<int:sid>/grade", methods=["POST"])
def grade_session(sid):
    data = request.get_json()
    grades = data.get("grades", [])

    conn = get_db()
    cur = conn.cursor()
    sess = cur.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
    if not sess:
        conn.close()
        return jsonify({"error": "not found"}), 404

    correct_count = 0
    wrong_count   = 0

    for g in grades:
        char     = g.get("char", "")
        is_correct = 1 if g.get("correct") else 0
        if is_correct:
            correct_count += 1
        else:
            wrong_count += 1

        cur.execute(
            "UPDATE session_chars SET correct=? WHERE session_id=? AND char=?",
            (is_correct, sid, char)
        )

        # 同步 wrongbook
        existing = cur.execute(
            "SELECT * FROM wrongbook WHERE child_id=1 AND char=?", (char,)
        ).fetchone()
        now = datetime.now().isoformat()

        if is_correct:
            if existing:
                cur.execute(
                    "UPDATE wrongbook SET correct_count=correct_count+1, "
                    "last_review=? WHERE child_id=1 AND char=?",
                    (now, char)
                )
                # correct_count >= 3 → 掌握
                row = cur.execute(
                    "SELECT correct_count FROM wrongbook WHERE child_id=1 AND char=?", (char,)
                ).fetchone()
                if row and row["correct_count"] >= 3:
                    cur.execute(
                        "UPDATE wrongbook SET reviewed=1 WHERE child_id=1 AND char=?", (char,)
                    )
            # else: 对字不在 wrongbook 中，不处理
        else:
            if existing:
                cur.execute(
                    "UPDATE wrongbook SET wrong_count=wrong_count+1, reviewed=0, "
                    "last_review=? WHERE child_id=1 AND char=?",
                    (now, char)
                )
            else:
                pinyin = g.get("pinyin", "")
                word   = g.get("word", "")
                cur.execute(
                    "INSERT INTO wrongbook (child_id, char, word, pinyin, wrong_count, "
                    "first_seen, last_review) VALUES (1,?,?,?,1,?,?)",
                    (char, word, pinyin, now, now)
                )

    # 更新 session
    cur.execute(
        "UPDATE sessions SET status='graded', correct_chars=?, graded_at=? WHERE id=?",
        (correct_count, datetime.now().isoformat(), sid)
    )

    # 更新连胜天数（不管之前是否有 submit，今天 graded 就视为今日已练习）
    child_row = cur.execute("SELECT * FROM child WHERE id=1").fetchone()
    last = child_row["last_practice"]
    today = date.today()
    if last:
        last_date = datetime.strptime(last, "%Y-%m-%d").date()
        if (today - last_date).days == 0:
            pass  # 今天已练习，不变
        elif (today - last_date).days == 1:
            cur.execute("UPDATE child SET streak_days=streak_days+1, last_practice=? WHERE id=1",
                        (today.isoformat(),))
        else:
            cur.execute("UPDATE child SET streak_days=1, last_practice=? WHERE id=1",
                        (today.isoformat(),))
    else:
        cur.execute("UPDATE child SET streak_days=1, last_practice=? WHERE id=1",
                    (today.isoformat(),))

    # 更新等级（按 session 数）
    session_count = cur.execute(
        "SELECT COUNT(*) FROM sessions WHERE child_id=1 AND status='submitted'"
    ).fetchone()[0]
    new_level = calc_level_from_sessions(session_count)
    cur.execute("UPDATE child SET level=? WHERE id=1", (new_level,))

    # 积分（graded 单独加，不依赖 submit）
    cur.execute("UPDATE child SET points=points+5 WHERE id=1")

    # 检查并解锁勋章
    badges_added = check_and_unlock_badges(conn, cur, 1)

    conn.commit()
    conn.close()

    msg = f"批改完成：对了 {correct_count} 字，错了 {wrong_count} 字。"
    if wrong_count > 0:
        msg += f" {wrong_count} 个字已记入错题本。"
    else:
        msg += " 🎉 太棒了，全对！"
    feishu_notify(msg)
    if badges_added:
        feishu_notify(f"🎉 解锁了 {badges_added} 个新勋章！")

    return jsonify({
        "ok": True,
        "correct": correct_count,
        "wrong": wrong_count,
        "extra_points": extra_points
    })


# ════════════════════════════════════════════════════════════
#  错题本
# ════════════════════════════════════════════════════════════

@app.route("/api/wrongbook", methods=["GET"])
def get_wrongbook():
    child_id = request.args.get("child_id", 1, type=int)
    conn = get_db()
    cur = conn.cursor()
    rows = cur.execute(
        "SELECT * FROM wrongbook WHERE child_id=? ORDER BY last_review DESC",
        (child_id,)
    ).fetchall()
    conn.close()
    unreviewed = [r for r in rows if not r["reviewed"]]
    return jsonify({"wrongChars": [dict(r) for r in rows], "unreviewed": len(unreviewed)})


@app.route("/api/review/send-image", methods=["POST"])
def send_review_image():
    """接收 base64 图片，发送到飞书，再删掉文件"""
    data = request.get_json()
    img_data = data.get("image")   # base64 数据
    char_count = data.get("char_count", 0)

    if not img_data:
        return jsonify({"error": "no image"}), 400

    # 保存临时文件
    fname = f"review_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
    fpath = os.path.join(UPLOAD_DIR, fname)
    with open(fpath, "wb") as f:
        f.write(base64.b64decode(img_data))

    try:
        # 1. 获取 token
        app_id     = os.environ.get("FEISHU_APP_ID", "")
        app_secret = os.environ.get("FEISHU_APP_SECRET", "")
        if not app_id or not app_secret:
            return jsonify({"error": "no feishu creds"}), 500

        tok_r = subprocess.run(
            ["curl", "-s", "-X", "POST",
             "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
             "-H", "Content-Type: application/json",
             "-d", json.dumps({"app_id": app_id, "app_secret": app_secret})],
            capture_output=True, text=True)
        token = json.loads(tok_r.stdout).get("tenant_access_token", "")
        if not token:
            return jsonify({"error": "token failed"}), 500

        # 2. 上传图片
        up_r = subprocess.run(
            ["curl", "-s", "-X", "POST",
             "https://open.feishu.cn/open-apis/im/v1/images",
             "-H", f"Authorization: Bearer {token}",
             "-F", "image_type=message",
             "-F", f"image=@{fpath}"],
            capture_output=True, text=True)
        up_json = json.loads(up_r.stdout)
        image_key = up_json.get("data", {}).get("image_key", "")
        if not image_key:
            return jsonify({"error": "upload failed", "detail": up_json}), 500

        # 3. 发消息
        chat_id = os.environ.get("FEISHU_CHAT_ID", "oc_4a384f23ae8e7f2d58662aecc05c8fdc")
        text = f"📕 小树完成了 {char_count} 个错字复习"
        payload = {
            "receive_id": chat_id,
            "msg_type": "post",
            "content": json.dumps({
                "zh_cn": {"title": "小树 · 错字复习", "content": [[{"tag": "text", "text": text}]]}
            })
        }
        send_r = subprocess.run(
            ["curl", "-s", "-X", "POST",
             "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
             "-H", f"Authorization: Bearer {token}",
             "-H", "Content-Type: application/json",
             "-d", json.dumps(payload)],
            capture_output=True, text=True)
        send_json = json.loads(send_r.stdout)

        # 4. 再发图片
        if image_key:
            img_payload = {
                "receive_id": chat_id,
                "msg_type": "image",
                "content": json.dumps({"image_key": image_key})
            }
            subprocess.run(
                ["curl", "-s", "-X", "POST",
                 "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
                 "-H", f"Authorization: Bearer {token}",
                 "-H", "Content-Type: application/json",
                 "-d", json.dumps(img_payload)],
                capture_output=True, text=True)

        return jsonify({"ok": True, "msg": "sent"})

    finally:
        if os.path.exists(fpath):
            os.remove(fpath)


# ════════════════════════════════════════════════════════════
#  游戏化
# ════════════════════════════════════════════════════════════

@app.route("/api/profile", methods=["GET"])
def get_profile():
    child_id = request.args.get("child_id", 1, type=int)
    conn = get_db()
    cur = conn.cursor()
    child = cur.execute("SELECT * FROM child WHERE id=?", (child_id,)).fetchone()
    if not child:
        conn.close()
        return jsonify({"error": "no child"}), 404

    earned = cur.execute(
        "SELECT b.*, cb.earned_at FROM child_badges cb "
        "JOIN badges b ON b.id=cb.badge_id WHERE cb.child_id=?",
        (child_id,)
    ).fetchall()

    session_count = cur.execute(
        "SELECT COUNT(*) FROM sessions WHERE child_id=? AND status='submitted'",
        (child_id,)
    ).fetchone()[0]

    new_level = calc_level_from_sessions(session_count)
    # 更新数据库中的等级
    if child["level"] != new_level:
        cur.execute("UPDATE child SET level=? WHERE id=?", (new_level, child_id))
        conn.commit()
        child = cur.execute("SELECT * FROM child WHERE id=?", (child_id,)).fetchone()

    # 进度条：当前级别所需session数 vs 下一级所需session数
    lvl = new_level
    curr_sessions = (lvl - 1) if lvl <= 5 else (4 + (lvl - 5) * 2)
    if lvl <= 5:
        next_sessions = lvl
    elif lvl < 20:
        next_sessions = 4 + (lvl - 4) * 2
    else:
        next_sessions = 4 + 16 * 2 + (lvl - 20) * 3

    progress_pct = min(100, int((session_count / next_sessions) * 100)) if next_sessions > 0 else 100

    # ── 勋章解锁检查 ────────────────────────────────────────────
    badges_added = check_and_unlock_badges(conn, cur, child_id)
    conn.commit()

    # 重新读取最新 earned 列表
    earned = cur.execute(
        "SELECT b.*, cb.earned_at FROM child_badges cb "
        "JOIN badges b ON b.id=cb.badge_id WHERE cb.child_id=?", (child_id,)
    ).fetchall()

    conn.close()

    return jsonify({
        "id": child["id"],
        "name": child["name"],
        "points": child["points"],
        "level": new_level,
        "level_name": level_name(new_level),
        "streak_days": child["streak_days"],
        "next_threshold": next_sessions,
        "session_count": session_count,
        "progress_pct": progress_pct,
        "badges": [dict(b) for b in earned]
    })


@app.route("/api/badges", methods=["GET"])
def list_badges():
    conn = get_db()
    cur = conn.cursor()
    all_badges = cur.execute("SELECT * FROM badges ORDER BY id").fetchall()
    earned     = cur.execute(
        "SELECT badge_id FROM child_badges WHERE child_id=1"
    ).fetchall()
    conn.close()
    earned_ids = {r["badge_id"] for r in earned}
    result = []
    for b in all_badges:
        bd = dict(b)
        bd["earned"] = bd["id"] in earned_ids
        result.append(bd)
    return jsonify(result)


@app.route("/api/badges/check", methods=["POST"])
def check_badges():
    child_id = 1
    conn = get_db()
    cur = conn.cursor()
    child = cur.execute("SELECT * FROM child WHERE id=?", (child_id,)).fetchone()

    # 获取所有未获得的勋章
    all_badges    = cur.execute("SELECT * FROM badges").fetchall()
    earned_badges = {r["badge_id"] for r in cur.execute(
        "SELECT badge_id FROM child_badges WHERE child_id=?", (child_id,)
    ).fetchall()}

    # 计算统计
    total_sessions = cur.execute(
        "SELECT COUNT(*) FROM sessions WHERE child_id=?", (child_id,)
    ).fetchone()[0]
    total_correct  = cur.execute(
        "SELECT COUNT(*) FROM session_chars WHERE correct=1 AND session_id IN "
        "(SELECT id FROM sessions WHERE child_id=?)", (child_id,)
    ).fetchone()[0]
    cleared_wrong  = cur.execute(
        "SELECT COUNT(*) FROM wrongbook WHERE child_id=? AND reviewed=1", (child_id,)
    ).fetchone()[0]
    session_days    = cur.execute(
        "SELECT COUNT(DISTINCT DATE(created_at)) FROM sessions WHERE child_id=?",
        (child_id,)
    ).fetchone()[0]

    new_earned = []
    for badge in all_badges:
        if badge["id"] in earned_badges:
            continue
        key  = badge["badge_key"]
        unlock = False
        if key == "first_practice" and total_sessions >= 1:
            unlock = True
        elif key == "streak_3" and child["streak_days"] >= 3:
            unlock = True
        elif key == "streak_7" and child["streak_days"] >= 7:
            unlock = True
        elif key == "perfect_10":
            # 单次全对
            row = cur.execute(
                "SELECT COUNT(*) FROM sessions WHERE child_id=? AND correct_chars=total_chars AND total_chars>=10",
                (child_id,)
            ).fetchone()
            if row and row[0] >= 1:
                unlock = True
        elif key == "hundred_perfect" and total_correct >= 100:
            unlock = True
        elif key == "wrongbook_cleared_20" and cleared_wrong >= 20:
            unlock = True
        elif key == "monthly_practitioner" and session_days >= 30:
            unlock = True
        elif key == "lv10" and child["level"] >= 10:
            unlock = True

        if unlock:
            cur.execute(
                "INSERT OR IGNORE INTO child_badges (child_id, badge_id) VALUES (?,?)",
                (child_id, badge["id"])
            )
            new_earned.append(dict(badge))

    conn.commit()
    conn.close()

    if new_earned:
        names = "、".join([b["name"] for b in new_earned])
        feishu_notify(f"🎉 小树解锁了新勋章：{names}！")

    return jsonify({"new_badges": new_earned})


@app.route("/api/points/add", methods=["POST"])
def add_points():
    data = request.get_json()
    points  = data.get("points", 0)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE child SET points=points+? WHERE id=1", (points,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/rewards/redeem", methods=["POST"])
def redeem_reward():
    data = request.get_json()
    reward_key = data.get("reward")
    points     = data.get("points", 0)
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO reward_logs (child_id, reward, points) VALUES (1,?,?)",
        (reward_key, points)
    )
    conn.commit()
    conn.close()
    feishu_notify(f"🎁 小树申请兑换「{reward_key}」，消耗 {points} 积分。")
    return jsonify({"ok": True})


# ─── 启动 ───────────────────────────────────────────────────

# ─── 周计划接口 ────────────────────────────────────────────
from weekly_planner import (
    create_weekly_plan, add_plan_item, get_plan_items, simple_distribute_tasks,
    confirm_weekly_plan, get_today_tasks, get_week_summary,
    get_unit_chars, get_unit_chars_count
)

@app.route("/api/weekly-plan/current", methods=["GET"])
def api_current_plan():
    """获取当前周计划状态
    周日时返回下周计划（让孩子和家长提前看到）
    """
    child_id = 1
    db = sqlite3.connect(DB_PATH)
    cur = db.cursor()
    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")
    is_sunday = today.weekday() == 6

    if is_sunday:
        # 周日：查下周计划
        next_monday = today + timedelta(days=1)
        target_start = next_monday.strftime("%Y-%m-%d")
        cur.execute("""
            SELECT id, week_start, week_end, status, created_at
            FROM weekly_plan
            WHERE child_id = ? AND week_start = ? AND status = 'confirmed'
            ORDER BY id DESC LIMIT 1
        """, (child_id, target_start))
    else:
        cur.execute("""
            SELECT id, week_start, week_end, status, created_at
            FROM weekly_plan
            WHERE child_id = ? AND week_start <= ? AND week_end >= ? AND status = 'confirmed'
            ORDER BY id DESC LIMIT 1
        """, (child_id, today_str, today_str))

    row = cur.fetchone()
    db.close()
    if not row:
        return jsonify({"has_plan": False})
    return jsonify({
        "has_plan": True,
        "id": row[0], "week_start": row[1], "week_end": row[2],
        "status": row[3], "created_at": row[4]
    })


@app.route("/api/weekly-plan", methods=["POST"])
def api_create_plan():
    """创建新周计划"""
    data = request.json
    week_start = data.get("week_start")
    week_end = data.get("week_end")
    if not week_start or not week_end:
        return jsonify({"error": "缺少日期"}), 400
    plan_id = create_weekly_plan(1, week_start, week_end)
    return jsonify({"plan_id": plan_id})


@app.route("/api/weekly-plan/<int:plan_id>/items", methods=["POST"])
def api_add_item(plan_id):
    """添加任务到周计划任务池"""
    data = request.json
    task_type = data.get("task_type")
    unit_id = data.get("unit_id")
    unit_name = data.get("unit_name")
    content = data.get("content")
    total_chars = data.get("total_chars", 0)
    chars = data.get("chars", [])
    item_id = add_plan_item(plan_id, task_type, unit_id, unit_name, content, total_chars, chars)
    return jsonify({"item_id": item_id})


@app.route("/api/weekly-plan/<int:plan_id>/items", methods=["GET"])
def api_get_items(plan_id):
    """获取计划的所有任务项"""
    items = get_plan_items(plan_id)
    return jsonify({"items": items})


@app.route("/api/weekly-plan/<int:plan_id>/items/<int:item_id>", methods=["DELETE"])
def api_delete_item(plan_id, item_id):
    """删除计划任务项"""
    db = sqlite3.connect(DB_PATH)
    cur = db.cursor()
    cur.execute("DELETE FROM weekly_plan_item WHERE id = ? AND weekly_plan_id = ?", (item_id, plan_id))
    db.commit()
    db.close()
    return jsonify({"ok": True})

@app.route("/api/weekly-plan/<int:plan_id>/preview", methods=["GET"])
def api_plan_preview(plan_id):
    """AI 分配预览（不写入，只返回预览）"""
    db = sqlite3.connect(DB_PATH)
    cur = db.cursor()
    cur.execute("SELECT week_start, week_end FROM weekly_plan WHERE id = ?", (plan_id,))
    row = cur.fetchone()
    db.close()
    if not row:
        return jsonify({"error": "plan not found"}), 404
    preview = simple_distribute_tasks(plan_id, row[0], row[1])
    return jsonify(preview)


@app.route("/api/weekly-plan/<int:plan_id>/confirm", methods=["POST"])
def api_confirm_plan(plan_id):
    """确认周计划，生成每日任务"""
    result = confirm_weekly_plan(plan_id)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


@app.route("/api/daily-tasks/today", methods=["GET"])
def api_today_tasks():
    """获取今日任务"""
    tasks = get_today_tasks(1)
    return jsonify({"tasks": tasks, "date": datetime.now().strftime("%Y-%m-%d")})


@app.route("/api/daily-tasks/<int:task_id>/complete", methods=["POST"])
def api_complete_task(task_id):
    """标记任务完成"""
    db = sqlite3.connect(DB_PATH)
    cur = db.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute(
        "UPDATE daily_task SET status='completed', completed_at=? WHERE id=?",
        (now, task_id)
    )
    # 记录
    cur.execute("INSERT INTO daily_record (daily_task_id, child_id, completed_at) VALUES (?, 1, ?)",
                (task_id, now))
    db.commit()
    db.close()
    return jsonify({"success": True})


@app.route("/api/week-summary", methods=["GET"])
def api_week_summary():
    """本周完成情况"""
    return jsonify(get_week_summary(1))


@app.route("/api/units", methods=["GET"])
def api_units():
    """获取所有课文单元列表"""
    db = sqlite3.connect(DB_PATH)
    cur = db.cursor()
    cur.execute("SELECT DISTINCT unit_id, unit_name FROM words ORDER BY unit_id")
    rows = cur.fetchall()
    db.close()
    units = [{"unit_id": r[0], "unit_name": r[1]} for r in rows]
    return jsonify({"units": units})


@app.route("/api/units/<unit_id>/chars", methods=["GET"])
def api_unit_chars(unit_id):
    """获取某课的字词"""
    chars = get_unit_chars(unit_id)
    count = get_unit_chars_count(unit_id)
    return jsonify({"unit_id": unit_id, "chars": chars, "total": count})


@app.route("/api/wrongbook", methods=["GET"])
def api_wrongbook():
    """获取错题本"""
    child_id = 1
    db = sqlite3.connect(DB_PATH)
    cur = db.cursor()
    cur.execute(
        "SELECT char, word, pinyin, wrong_count FROM wrongbook WHERE child_id = ? ORDER BY wrong_count DESC",
        (child_id,)
    )
    rows = cur.fetchall()
    db.close()
    return jsonify({"wrongbook": [{"char": r[0], "word": r[1], "pinyin": r[2], "wrong_count": r[3]} for r in rows]})


# ═══════════════════════════════════════════════════════════════
# English 模块 API
# ═══════════════════════════════════════════════════════════════

ENGLISH_UPLOAD_DIR = os.path.join(BASE_DIR, "uploads", "english")
os.makedirs(ENGLISH_UPLOAD_DIR, exist_ok=True)

@app.route("/api/english/upload", methods=["POST"])
def api_english_upload():
    """接收 PDF 文件或图片，保存到 uploads/english/{week_date}/"""
    week_date = request.form.get("week_date", date.today().strftime("%Y-%m-%d"))
    target_dir = os.path.join(ENGLISH_UPLOAD_DIR, week_date)
    os.makedirs(target_dir, exist_ok=True)

    results = {"words": [], "articles": [], "images": []}

    # 批量处理上传文件
    files = request.files.getlist("files")
    for f in files:
        if not f.filename:
            continue
        fname = secure_filename(f.filename)
        f.save(os.path.join(target_dir, fname))

        ext = fname.lower().split(".")[-1]
        if ext == "pdf":
            results["type"] = "pdf"
        elif ext in ("jpg", "jpeg", "png", "webp"):
            results["images"].append(fname)

    return jsonify({"success": True, "week_date": week_date, "saved": len(files), "details": results})


@app.route("/api/english/words", methods=["GET"])
def api_english_words():
    """获取本周英语单词，支持 batch_id 或 week_date 过滤"""
    batch_id = request.args.get("batch_id", type=int)
    week_date = request.args.get("week_date", date.today().strftime("%Y-%m-%d"))
    word_type = request.args.get("type")  # spelling / irregular / pep

    db = get_db()
    cur = db.cursor()

    if batch_id:
        # 按批次查
        conditions = ["batch_id=?"]
        params = [batch_id]
        if word_type:
            conditions.append("word_type=?")
            params.append(word_type)
        sql = f"SELECT id, word, pronunciation, pos, meaning, lesson, word_type FROM english_words WHERE {' AND '.join(conditions)} ORDER BY id"
        cur.execute(sql, params)
    else:
        # 兼容原有 week_date 逻辑
        if word_type:
            cur.execute(
                "SELECT id, word, pronunciation, pos, meaning, lesson, word_type FROM english_words WHERE week_date=? AND word_type=? ORDER BY id",
                (week_date, word_type)
            )
        else:
            cur.execute(
                "SELECT id, word, pronunciation, pos, meaning, lesson, word_type FROM english_words WHERE week_date=? ORDER BY id",
                (week_date,)
            )

    rows = cur.fetchall()
    db.close()

    words = [dict(zip(["id","word","pronunciation","pos","meaning","lesson","word_type"], r)) for r in rows]
    result = {"week_date": week_date, "words": words}
    if batch_id:
        result["batch_id"] = batch_id
    return jsonify(result)


@app.route("/api/english/articles", methods=["GET"])
def api_english_articles():
    """获取本周阅读文章；无 week_date 参数时返回全部"""
    week_date = request.args.get("week_date", None)
    db = get_db()
    cur = db.cursor()
    if week_date:
        cur.execute(
            "SELECT id, title, content, image_urls, week_date, order_num FROM english_articles WHERE week_date=? ORDER BY order_num",
            (week_date,)
        )
    else:
        cur.execute(
            "SELECT id, title, content, image_urls, week_date, order_num FROM english_articles ORDER BY week_date DESC, order_num"
        )
    rows = cur.fetchall()
    db.close()
    articles = []
    for r in rows:
        articles.append({
            "id": r[0], "title": r[1], "content": r[2],
            "image_urls": json.loads(r[3]) if r[3] else [], "week_date": r[4], "order_num": r[5]
        })
    return jsonify({"week_date": week_date, "articles": articles})


@app.route("/api/english/schedule", methods=["GET"])
def api_english_schedule():
    """获取某天英语任务，自动fallback到上周内容"""
    target_date = request.args.get("date", date.today().strftime("%Y-%m-%d"))
    child_id = request.args.get("child_id", 1, type=int)

    # 解析target_date对应的周一开始的week_date
    target_dt = datetime.strptime(target_date, "%Y-%m-%d")
    # Monday = 0, Sunday = 6
    days_since_monday = target_dt.weekday()
    week_start = (target_dt - timedelta(days=days_since_monday)).strftime("%Y-%m-%d")

    db = get_db()
    cur = db.cursor()

    # 先查本周有没有数据
    cur.execute(
        "SELECT id, date, task_type, lesson, task_data, status FROM english_schedule WHERE child_id=? AND date=? ORDER BY task_type",
        (child_id, target_date)
    )
    rows = cur.fetchall()

    # 本周没数据，基于当前激活批次生成任务
    if not rows:
        cur.execute("SELECT id FROM study_batch WHERE subject='en' AND is_active=1 LIMIT 1")
        batch_row = cur.fetchone()
        if batch_row:
            batch_id = batch_row[0]
            cur.execute("SELECT item_type, item_id FROM study_batch_item WHERE batch_id=?", (batch_id,))
            items = cur.fetchall()
            tasks = []
            for (item_type, item_id) in items:
                if item_type in ('spelling', 'irregular', 'pep'):
                    cur.execute(f"SELECT COUNT(*) FROM english_words WHERE batch_id=? AND word_type=? AND lesson=?", (batch_id, item_type, item_id))
                    cnt = cur.fetchone()[0]
                    tasks.append({
                        'id': 0, 'date': target_date, 'task_type': item_type,
                        'lesson': item_id,
                        'task_data': json.dumps({'lesson': item_id, 'count': cnt}),
                        'status': 'pending'
                    })
            source_note = " (根据当前批次自动分配)"
        else:
            tasks = []
            source_note = " (无配置)"
    else:
        source_note = ""

    # 查今日英语打卡记录，标记已完成的任务
    today_str = target_date
    cur.execute(
        "SELECT detail FROM english_daily_log WHERE child_id=? AND date=? AND task_type='en_dictation' ORDER BY id DESC LIMIT 1",
        (child_id, today_str)
    )
    log_row = cur.fetchone()
    completed_detail = {}
    if log_row and log_row[0]:
        try:
            completed_detail = json.loads(log_row[0])
        except:
            pass

    db.close()
    # 统一格式
    normalized = []
    for t in tasks:
        # 根据 task_type 匹配 detail 中的分项
        sub_key = t['task_type']  # spelling, irregular, pep
        status = t.get('status', 'pending')
        if completed_detail.get(sub_key, 0) > 0:
            status = 'completed'
        normalized.append({
            'id': t.get('id', 0),
            'date': t.get('date', target_date),
            'task_type': t['task_type'],
            'lesson': t['lesson'],
            'task_data': t['task_data'],
            'status': status
        })
    return jsonify({"date": target_date, "tasks": normalized, "source_note": source_note})


@app.route("/api/english/weeks", methods=["GET"])
def api_english_weeks():
    """返回所有有英语配置的周（按周一开始的week_date倒序）"""
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        SELECT DISTINCT week_date FROM english_words
        UNION
        SELECT DISTINCT substr(date, 1, 10) as wd FROM english_schedule WHERE date IS NOT NULL
        ORDER BY week_date DESC
    """)
    weeks = [r[0] for r in cur.fetchall()]
    db.close()
    return jsonify({"weeks": weeks})


@app.route("/api/english/week-detail", methods=["GET"])
def api_english_week_detail():
    """返回指定周的全部内容：单词 + 每日打卡状态"""
    week_date = request.args.get("week_date")
    child_id = request.args.get("child_id", 1, type=int)
    if not week_date:
        return jsonify({"error": "week_date required"}), 400

    db = get_db()
    cur = db.cursor()

    # 单词
    cur.execute("""
        SELECT word, pos, meaning, word_type, lesson
        FROM english_words WHERE week_date=?
        ORDER BY word_type, lesson, id
    """, (week_date,))
    words = [dict(zip(["word","pos","meaning","word_type","lesson"], r)) for r in cur.fetchall()]

    # 调度（周一到周五）
    monday = week_date
    friday = (datetime.strptime(week_date, "%Y-%m-%d") + timedelta(days=4)).strftime("%Y-%m-%d")
    cur.execute("""
        SELECT date, task_type, lesson, task_data, status
        FROM english_schedule
        WHERE child_id=? AND date BETWEEN ? AND ?
        ORDER BY date, task_type
    """, (child_id, monday, friday))
    schedule = [dict(zip(["date","task_type","lesson","task_data","status"], r)) for r in cur.fetchall()]

    # 每日打卡记录
    cur.execute("""
        SELECT date, task_type, score, completed_at
        FROM english_daily_log
        WHERE child_id=? AND date BETWEEN ? AND ?
        ORDER BY date, task_type
    """, (child_id, monday, friday))
    logs = [dict(zip(["date","task_type","score","completed_at"], r)) for r in cur.fetchall()]

    db.close()
    return jsonify({
        "week_date": week_date,
        "words": words,
        "schedule": schedule,
        "logs": logs
    })


@app.route("/api/english/schedule", methods=["POST"])
def api_english_schedule_post():
    """写入/更新英语每日任务"""
    data = request.json
    child_id = data.get("child_id", 1)
    date_str = data["date"]
    task_type = data["task_type"]
    lesson = data.get("lesson", "")
    task_data = json.dumps(data.get("task_data", {}))

    db = get_db()
    cur = db.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO english_schedule (child_id, date, task_type, lesson, task_data) VALUES (?,?,?,?,?)",
        (child_id, date_str, task_type, lesson, task_data)
    )
    db.commit()
    schedule_id = cur.lastrowid
    db.close()
    return jsonify({"success": True, "id": schedule_id})


@app.route("/api/english/daily-log", methods=["GET", "POST"])
def api_english_daily_log():
    """查询或提交每日英语任务记录"""
    if request.method == "GET":
        target_date = request.args.get("date", date.today().strftime("%Y-%m-%d"))
        child_id = request.args.get("child_id", 1, type=int)
        db = get_db()
        cur = db.cursor()
        cur.execute(
            "SELECT id, date, task_type, score, answers FROM english_daily_log WHERE child_id=? AND date=?",
            (child_id, target_date)
        )
        rows = cur.fetchall()
        db.close()
        log = [dict(zip(["id","date","task_type","score","answers"], r)) for r in rows]
        return jsonify({"date": target_date, "log": log})

    data = request.json
    child_id = data.get("child_id", 1)
    date_str = data["date"]
    task_type = data["task_type"]
    score = data.get("score", 0)
    total = data.get("total", 0)
    # detail 存各阶段小分（JSON 字符串）
    detail = json.dumps(data.get("detail", {}))
    answers = json.dumps(data.get("answers", []))

    db = get_db()
    cur = db.cursor()
    cur.execute(
        "INSERT INTO english_daily_log (child_id, date, task_type, score, total, answers) VALUES (?,?,?,?,?,?)",
        (child_id, date_str, task_type, score, total, detail if data.get("detail") else answers)
    )
    db.commit()
    log_id = cur.lastrowid
    db.close()
    return jsonify({"success": True, "id": log_id})


@app.route("/api/english/word-practice", methods=["GET"])
def api_english_word_practice():
    """获取某日单词练习任务（含题目）"""
    target_date = request.args.get("date", date.today().strftime("%Y-%m-%d"))
    task_type = request.args.get("task_type")  # spelling / irregular / pep
    word_type_map = {"spelling": "spelling", "irregular": "irregular", "pep": "pep"}

    db = get_db()
    cur = db.cursor()
    cur.execute(
        "SELECT id, word, pronunciation, pos, meaning, lesson, word_type FROM english_words WHERE week_date=? AND word_type=? ORDER BY id",
        (target_date, word_type_map.get(task_type, "spelling"))
    )
    rows = cur.fetchall()
    db.close()

    words = [dict(zip(["id","word","pronunciation","pos","meaning","lesson","word_type"], r)) for r in rows]
    return jsonify({"date": target_date, "task_type": task_type, "words": words})


# ═══════════════════════════════════════════════════════════════
# 英文错题本
# ═══════════════════════════════════════════════════════════════

@app.route("/api/english/wrongbook", methods=["GET"])
def api_english_wrongbook():
    """获取英文错题列表"""
    child_id = request.args.get("child_id", 1, type=int)
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        SELECT id, word_id, word, pronunciation, meaning, word_type, lesson,
               wrong_count, last_wrong_at, reviewed_at
        FROM english_wrongbook
        WHERE child_id = ?
        ORDER BY wrong_count DESC, last_wrong_at DESC
    """, (child_id,))
    rows = cur.fetchall()
    db.close()
    items = [dict(zip(["id","word_id","word","pronunciation","meaning","word_type",
                       "lesson","wrong_count","last_wrong_at","reviewed_at"], r)) for r in rows]
    return jsonify({"items": items, "count": len(items)})


@app.route("/api/english/wrongbook", methods=["POST"])
def api_english_wrongbook_add():
    """添加或更新错题（答错时调用）"""
    data = request.json
    child_id = data.get("child_id", 1)
    word_id = data.get("word_id")
    word = data.get("word", "")
    pronunciation = data.get("pronunciation", "")
    meaning = data.get("meaning", "")
    word_type = data.get("word_type", "")
    lesson = data.get("lesson", "")

    db = get_db()
    cur = db.cursor()
    # 已有则累加 wrong_count
    cur.execute("SELECT id, wrong_count FROM english_wrongbook WHERE child_id=? AND word=?", (child_id, word))
    existing = cur.fetchone()
    if existing:
        cur.execute("""
            UPDATE english_wrongbook
            SET wrong_count = wrong_count + 1, last_wrong_at = datetime('now')
            WHERE id = ?
        """, (existing[0],))
    else:
        cur.execute("""
            INSERT INTO english_wrongbook (child_id, word_id, word, pronunciation, meaning, word_type, lesson)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (child_id, word_id, word, pronunciation, meaning, word_type, lesson))
    db.commit()
    db.close()
    return jsonify({"success": True})


@app.route("/api/english/wrongbook/<int:item_id>", methods=["DELETE"])
def api_english_wrongbook_remove(item_id):
    """从错题本移除（答对时调用）"""
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM english_wrongbook WHERE id = ?", (item_id,))
    db.commit()
    db.close()
    return jsonify({"success": True})


@app.route("/api/english/wrongbook/clear", methods=["POST"])
def api_english_wrongbook_clear():
    """清空英文错题本"""
    child_id = request.json.get("child_id", 1) if request.json else 1
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM english_wrongbook WHERE child_id = ?", (child_id,))
    db.commit()
    db.close()
    return jsonify({"success": True})


# ═══════════════════════════════════════════════════════════════
# 英文 TTS（MiniMax T2A v2）
# ═══════════════════════════════════════════════════════════════

@app.route("/api/english/tts", methods=["GET"])
def api_english_tts():
    """英文单词 TTS，调用 MiniMax T2A v2"""
    text = request.args.get("text", "").strip()
    if not text:
        return jsonify({"error": "text required"}), 400
    try:
        api_key = os.environ.get("MINIMAX_API_KEY", "")
        if not api_key:
            return jsonify({"error": "MINIMAX_API_KEY not set"}), 500
        payload = {
            "model": "speech-02-hd",
            "text": text,
            "stream": False,
            "voice_setting": {"voice_id": "male-qn-qingse"}
        }
        req = urllib.request.Request(
            "https://api.minimax.chat/v1/t2a_v2",
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            method="POST"
        )
        resp = urllib.request.urlopen(req, timeout=10)
        return resp.read(), 200, {"Content-Type": "audio/mpeg"}
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ═══════════════════════════════════════════════════════════════
# 家长端 · 学习配置批次管理
# ═══════════════════════════════════════════════════════════════

@app.route("/api/parent/batch/list", methods=["GET"])
def api_parent_batch_list():
    """返回所有批次，按 subject 分组，当前生效的排前面"""
    subject = request.args.get("subject")  # cn | en
    db = get_db()
    cur = db.cursor()
    if subject:
        cur.execute(
            "SELECT id, subject, name, is_active, created_at FROM study_batch WHERE subject=? ORDER BY is_active DESC, created_at DESC",
            (subject,)
        )
    else:
        cur.execute("SELECT id, subject, name, is_active, created_at FROM study_batch ORDER BY is_active DESC, created_at DESC")
    rows = cur.fetchall()
    batches = []
    for r in rows:
        batch = dict(zip(["id","subject","name","is_active","created_at"], r))
        cur.execute("SELECT item_type, item_id FROM study_batch_item WHERE batch_id=?", (batch["id"],))
        items = [dict(zip(["item_type","item_id"], ri)) for ri in cur.fetchall()]
        batch["items_json"] = json.dumps(items)
        batches.append(batch)
    db.close()
    return jsonify({"batches": batches})


@app.route("/api/parent/batch/options", methods=["GET"])
def api_parent_batch_options():
    """返回可选的配置项（语文单元/识字；英语词库/文章）"""
    db = get_db()
    cur = db.cursor()
    result = {"chinese": [], "english": {}}

    # 语文：从 words 表按 unit_id 分组
    cur.execute("SELECT unit_id, unit_name, COUNT(*) FROM words GROUP BY unit_id, unit_name ORDER BY unit_id")
    for (uid, uname, cnt) in cur.fetchall():
        result["chinese"].append({
            "item_type": "unit",
            "item_id": uid,
            "label": f"{uname}（{cnt}字）"
        })

    # 英语：从 english_words 读
    cur.execute("SELECT DISTINCT lesson, word_type FROM english_words ORDER BY lesson")
    lessons = cur.fetchall()
    for (lesson, wtype) in lessons:
        if wtype not in result["english"]:
            result["english"][wtype] = []
        result["english"][wtype].append({
            "item_id": lesson,
            "label": lesson,
            "count": sum(1 for l, t in lessons if l == lesson)
        })

    # 英语文章
    cur.execute("SELECT id, title FROM english_articles ORDER BY id")
    result["english"]["reading"] = [
        {"item_id": str(r[0]), "label": r[1][:30]} for r in cur.fetchall()
    ]

    db.close()
    return jsonify(result)


@app.route("/api/parent/batch/detail/<int:batch_id>", methods=["GET"])
def api_parent_batch_detail(batch_id):
    """返回某批次的详细信息（包含任务项）"""
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT id, subject, name, is_active, created_at FROM study_batch WHERE id=?", (batch_id,))
    row = cur.fetchone()
    if not row:
        db.close()
        return jsonify({"error": "not found"}), 404
    batch = dict(zip(["id","subject","name","is_active","created_at"], row))

    cur.execute("SELECT item_type, item_id FROM study_batch_item WHERE batch_id=?", (batch_id,))
    batch["items"] = [dict(zip(["item_type","item_id"], r)) for r in cur.fetchall()]

    # 填充任务详情
    if batch["subject"] == "cn":
        # 语文任务：查听写和背诵任务
        dict_ids = [it["item_id"] for it in batch["items"] if it["item_type"] == "dictation"]
        rec_ids = [it["item_id"] for it in batch["items"] if it["item_type"] == "recite"]
        cur.execute("SELECT id, name FROM units WHERE id IN (" + ",".join(["?"]*len(dict_ids) if dict_ids else [0]) + ")", dict_ids)
        batch["dictations"] = [{"id": r[0], "name": r[1]} for r in cur.fetchall()]
        cur.execute("SELECT id, name FROM recitations WHERE id IN (" + ",".join(["?"]*len(rec_ids) if rec_ids else [0]) + ")", rec_ids)
        batch["recitations"] = [{"id": r[0], "name": r[1]} for r in cur.fetchall()]
    else:
        # 英语任务：查 english_words 和 english_articles
        cur.execute("SELECT word_type, COUNT(*) FROM english_words WHERE batch_id=? GROUP BY word_type", (batch_id,))
        batch["word_summary"] = {r[0]: r[1] for r in cur.fetchall()}
        cur.execute("SELECT COUNT(*) FROM english_articles WHERE batch_id=?", (batch_id,))
        batch["article_count"] = cur.fetchone()[0]

    db.close()
    return jsonify(batch)


@app.route("/api/parent/batch/create", methods=["POST"])
def api_parent_batch_create():
    """
    创建新批次：
    1. 将同学科旧批次 is_active=0
    2. 写入 study_batch
    3. 写入 study_batch_item
    4. 更新 english_words / english_articles 的 batch_id
    """
    body = request.get_json()
    subject = body.get("subject")  # cn | en
    name = body.get("name", "")
    items = body.get("items", [])  # [{item_type, item_id}]

    if not subject or subject not in ("cn", "en"):
        return jsonify({"error": "invalid subject"}), 400

    db = get_db()
    cur = db.cursor()

    # 旧批次下线
    cur.execute("UPDATE study_batch SET is_active=0 WHERE subject=?", (subject,))

    # 新批次
    cur.execute(
        "INSERT INTO study_batch (subject, name, is_active) VALUES (?, ?, 1)",
        (subject, name)
    )
    batch_id = cur.lastrowid

    # 写任务项
    for it in items:
        cur.execute(
            "INSERT INTO study_batch_item (batch_id, item_type, item_id) VALUES (?, ?, ?)",
            (batch_id, it["item_type"], it["item_id"])
        )

    # 英语：更新 english_words 和 english_articles 的 batch_id
    if subject == "en":
        word_ids = [it["item_id"] for it in items if it["item_type"] in ("spelling", "irregular", "pep")]
        article_ids = [it["item_id"] for it in items if it["item_type"] == "article"]
        if word_ids:
            placeholders = ",".join(["?"] * len(word_ids))
            cur.execute(f"UPDATE english_words SET batch_id=? WHERE lesson IN ({placeholders})", [batch_id] + word_ids)
        if article_ids:
            placeholders = ",".join(["?"] * len(article_ids))
            cur.execute(f"UPDATE english_articles SET batch_id=? WHERE id IN ({placeholders})", [batch_id] + article_ids)

    db.commit()
    db.close()
    return jsonify({"batch_id": batch_id, "status": "ok"})


@app.route("/api/parent/batch/activate", methods=["POST"])
def api_parent_batch_activate():
    """重新激活某批次"""
    body = request.get_json()
    batch_id = body.get("batch_id")
    if not batch_id:
        return jsonify({"error": "batch_id required"}), 400
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT subject FROM study_batch WHERE id=?", (batch_id,))
    row = cur.fetchone()
    if not row:
        db.close()
        return jsonify({"error": "not found"}), 404
    subject = row[0]
    cur.execute("UPDATE study_batch SET is_active=0 WHERE subject=?", (subject,))
    cur.execute("UPDATE study_batch SET is_active=1 WHERE id=?", (batch_id,))
    db.commit()
    db.close()
    return jsonify({"status": "ok"})


@app.route("/api/parent/batch/current", methods=["GET"])
def api_parent_batch_current():
    """返回当前生效的语文和英语批次（孩子端用）"""
    subject = request.args.get("subject")
    db = get_db()
    cur = db.cursor()
    if subject:
        cur.execute(
            "SELECT id, subject, name, is_active, created_at FROM study_batch WHERE subject=? AND is_active=1",
            (subject,)
        )
        row = cur.fetchone()
        db.close()
        if not row:
            return jsonify({"batch": None})
        return jsonify({"batch": dict(zip(["id","subject","name","is_active","created_at"], row))})
    else:
        cur.execute("SELECT id, subject, name, is_active, created_at FROM study_batch WHERE is_active=1")
        rows = cur.fetchall()
        db.close()
        result = {}
        for r in rows:
            b = dict(zip(["id","subject","name","is_active","created_at"], r))
            result[b["subject"]] = b
        return jsonify(result)


# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
