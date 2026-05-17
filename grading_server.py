#!/usr/bin/env python3
"""
家长批改页面服务器 (Port 8081)
显示所有待批改/已批改的听写记录，按字符逐个标记对错。
批改时自动更新错题本（对/错次数、全对/全错状态）。
"""
import http.server
import socketserver
import os
import json
import subprocess
import urllib.request
from datetime import datetime

PORT = 8081
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSIONS_DIR = os.path.join(BASE_DIR, "sessions")
WRONGBOOK_FILE = os.path.join(SESSIONS_DIR, "wrongbook.json")

os.makedirs(SESSIONS_DIR, exist_ok=True)


def load_wrongbook():
    if not os.path.exists(WRONGBOOK_FILE):
        return {}
    with open(WRONGBOOK_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_wrongbook(book):
    with open(WRONGBOOK_FILE, "w", encoding="utf-8") as f:
        json.dump(book, f, ensure_ascii=False, indent=2)


def sync_grade_to_app(session_id, session):
    """批改完成后，同步到 app.py SQLite（供学生端错题本使用）

    grading_server 的 session JSON 用 session_key 字符串，
    而 app.py 用整数 id。先通过 POST /api/sessions 在 app.py
    创建记录拿到整数 id，再调用 grade 接口写入批改结果。
    """
    results = session.get("results", [])
    chars = session.get("chars", [])
    words = session.get("words", [])
    mode = session.get("mode", "practice")

    # 构造 grades 数组
    grades = []
    for i, char in enumerate(chars):
        result = results[i] if i < len(results) else True
        grades.append({"char": char, "correct": result})

    app_session_id = None

    # 1. 尝试在 app.py 创建 session（如已有则跳过）
    try:
        create_payload = {
            "mode": mode,
            "child_id": 1,
            "words": [{"char": w, "word": w} for w in words] if words else [],
            "unit_ids": []
        }
        req = urllib.request.Request(
            "http://localhost:8080/api/sessions",
            data=json.dumps(create_payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            created = json.loads(resp.read())
            app_session_id = created.get("session_id")
        print(f"[同步] 在 app.py 创建 session 成功，id={app_session_id}")
    except Exception as e:
        # session 可能已存在，尝试从 app.py 查询
        print(f"[同步] 创建 session 失败（可能已存在）: {e}")
        try:
            req = urllib.request.Request(
                f"http://localhost:8080/api/sessions/{session_id}",
                method="GET"
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                existing = json.loads(resp.read())
                app_session_id = existing.get("session_id")
            print(f"[同步] 从 app.py 查询到 session id={app_session_id}")
        except Exception:
            print(f"[同步] 无法获取 app.py session id，跳过本次同步")
            return

    if not app_session_id:
        return

    # 2. 写入批改结果
    try:
        req = urllib.request.Request(
            f"http://localhost:8080/api/sessions/{app_session_id}/grade",
            data=json.dumps({"grades": grades}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
        print(f"[同步] 已将 session={session_id}(app_id={app_session_id}) 批改结果写入 SQLite")
    except Exception as e:
        print(f"[同步] 写入 SQLite 失败: {e}")


def update_char_stats(session):
    """
    批改时调用：更新每个字的统计。
    session: 已含 results[] 的 session 对象
    返回: (wrong_chars, correct_chars) 列表
    """
    book = load_wrongbook()
    chars = session.get("chars", [])
    results = session.get("results", [])
    words = session.get("words", [])
    word_start_indices = session.get("wordStartIndices", [])
    session_id = session.get("id", "")
    now = datetime.now().isoformat()

    wrong_chars = []
    correct_chars = []

    for i, (char, result) in enumerate(zip(chars, results)):
        # 找到该字对应的词
        word = ""
        for wi, start in enumerate(word_start_indices):
            end = word_start_indices[wi + 1] if wi + 1 < len(word_start_indices) else len(chars)
            if start <= i < end:
                word = words[wi] if words else ""
                break

        if char not in book:
            book[char] = {
                "char": char,
                "word": word,
                "addedAt": now,
                "lastSeen": now,
                "lastSessionId": session_id,
                "wrongCount": 0,
                "correctCount": 0,
                "lastResult": None,
                "reviewed": False
            }

        entry = book[char]
        entry["lastSeen"] = now
        entry["lastSessionId"] = session_id
        entry["word"] = word or entry.get("word", "")

        if result is False:
            entry["wrongCount"] = entry.get("wrongCount", 0) + 1
            entry["lastResult"] = False
            entry["reviewed"] = False  # 新错字 → 待复习
            wrong_chars.append(char)
        else:
            entry["correctCount"] = entry.get("correctCount", 0) + 1
            entry["lastResult"] = True

        book[char] = entry

    save_wrongbook(book)
    return wrong_chars, correct_chars


def notify_feishu_graded(session, wrong_chars):
    """家长批改完成后，通知 Stan 本次批改结果"""
    grade = session.get("grade", "")
    unit = session.get("unit", "")
    words = session.get("words", [])
    words_text = "、".join(words) if words else "未知"
    if wrong_chars:
        wrong_text = "、".join(wrong_chars)
        msg = (
            f"📋 听写批改完成\n\n"
            f"• 年级：{grade}  单元：{unit}\n"
            f"• 词汇：{words_text}\n"
            f"• 本次错字：{wrong_text}\n\n"
            f"已记入错题本，请督促复习"
        )
    else:
        msg = (
            f"🎉 听写批改完成\n\n"
            f"• 年级：{grade}  单元：{unit}\n"
            f"• 词汇：{words_text}\n"
            f"• 本次听写全部正确，太棒了！"
        )
    try:
        subprocess.run(
            ["lark-cli", "im", "+messages-send",
             "--chat-id", "oc_7c2b51a013b7408f6cb978c3f44cf48c",
             "--text", msg],
            capture_output=True, text=True, timeout=15
        )
        print(f"[通知] 批改完成消息已发送: session={session['id']}, wrong={wrong_chars}")
    except Exception as e:
        print(f"[通知] 发送失败: {e}")


class ReuseAddrTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


class Handler(http.server.BaseHTTPRequestHandler):
    def send_cors(self, status=200, ctype="text/html; charset=utf-8"):
        self.send_response(status)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Type", ctype)
        self.end_headers()

    def do_OPTIONS(self):
        self.send_cors(204)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_GET(self):
        if self.path == "/" or self.path == "/index":
            self.serve_index()
        elif self.path == "/api/sessions":
            self.api_sessions()
        elif self.path.startswith("/api/session/"):
            parts = self.path.split("/")
            if len(parts) >= 4 and parts[3]:
                session_id = parts[3]
                self.api_session(session_id)
            else:
                self.send_error(404)
        elif self.path.startswith("/uploads/"):
            self.serve_upload()
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path.startswith("/api/session/"):
            parts = self.path.split("/")
            if len(parts) >= 5 and parts[4] == "grade":
                session_id = parts[3]
                self.api_grade(session_id)
                return
            elif len(parts) >= 4:
                session_id = parts[3]
                self.api_session(session_id)
                return

    def serve_index(self):
        sessions = get_sessions()
        pending = [s for s in sessions if s.get("status") == "pending"]
        graded = [s for s in sessions if s.get("status") == "graded"]
        pending_html = self._session_cards(pending, "pending")
        graded_html = self._session_cards(graded, "graded")
        html = self._render_page(pending, graded, pending_html, graded_html)
        self.send_cors()
        self.wfile.write(html.encode("utf-8"))

    def api_sessions(self):
        sessions = get_sessions()
        data = json.dumps({"sessions": sessions}, ensure_ascii=False)
        self.send_cors(200, "application/json")
        self.wfile.write(data.encode("utf-8"))

    def api_session(self, session_id):
        path = os.path.join(SESSIONS_DIR, f"session_{session_id}.json")
        if not os.path.exists(path):
            self.send_error(404)
            return
        with open(path, encoding="utf-8") as f:
            data = json.dumps(json.load(f), ensure_ascii=False)
        self.send_cors(200, "application/json")
        self.wfile.write(data.encode("utf-8"))

    def api_grade(self, session_id):
        path = os.path.join(SESSIONS_DIR, f"session_{session_id}.json")
        if not os.path.exists(path):
            self.send_error(404)
            return
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len)
        try:
            data = json.loads(body.decode("utf-8"))
        except Exception:
            self.send_error(400)
            return

        with open(path, encoding="utf-8") as f:
            session = json.load(f)

        session["results"] = data.get("results", [])
        session["gradedAt"] = data.get("gradedAt", datetime.now().isoformat())
        session["status"] = "graded"
        save_session(session)

        # 更新每个字的统计（对/错次数）
        wrong_chars, _ = update_char_stats(session)

        # 同步到 app.py SQLite（供学生端错题本使用）
        sync_grade_to_app(session_id, session)

        # 通知 Stan
        notify_feishu_graded(session, wrong_chars)

        resp = json.dumps({"success": True})
        self.send_cors(200, "application/json")
        self.wfile.write(resp.encode("utf-8"))

    def serve_upload(self):
        fname = os.path.basename(self.path)
        import urllib.request
        try:
            url = f"http://localhost:8080/uploads/{fname}"
            with urllib.request.urlopen(url, timeout=5) as resp:
                body = resp.read()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", len(body))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        except Exception:
            self.send_error(404)

    def _session_cards(self, sessions, kind):
        if not sessions:
            label = "待批改" if kind == "pending" else "已批改"
            return f'<div class="empty">{"🎉" if kind == "pending" else "📋"} 暂无{label}记录</div>'

        html = ""
        for s in sessions:
            words = s.get("words", [])
            chars = s.get("chars", [])
            results = s.get("results", [])
            word_start_indices = s.get("wordStartIndices", [])

            word_results = []
            if word_start_indices and chars and results:
                for i, start in enumerate(word_start_indices):
                    end = word_start_indices[i + 1] if i + 1 < len(word_start_indices) else len(chars)
                    word_chars = results[start:end]
                    if all(r is True for r in word_chars):
                        word_results.append("correct")
                    elif any(r is False for r in word_chars):
                        word_results.append("wrong")
                    else:
                        word_results.append("pending")
            else:
                word_results = ["pending"] * len(words)

            preview_tags = ""
            for i, w in enumerate(words):
                status = word_results[i] if i < len(word_results) else "pending"
                cls = "pending" if status == "pending" else ("correct" if status == "correct" else "wrong")
                preview_tags += f'<span class="word-tag {cls}">{w} {"✓" if status=="correct" else ("✗" if status=="wrong" else "?")}</span>'

            meta = f"{s.get('grade','')} · {s.get('unit','')}单元 · {len(words)}词"
            date = s.get("date", "")

            html += f"""
        <div class="card card-{kind}" onclick="showDetail('{s['id']}')">
            <div class="card-header">
                <span class="card-date">{date}</span>
                <span class="card-meta">{meta}</span>
            </div>
            <div class="word-preview">{preview_tags}</div>
        </div>"""
        return html

    def _render_page(self, pending, graded, pending_html, graded_html):
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>听写批改 - 家长页面</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, 'Noto Sans SC', sans-serif; background: #F5F5F5; color: #333; }}
.header {{ background: #4CAF50; color: white; padding: 1rem 1.5rem; display: flex; align-items: center; justify-content: space-between; }}
.header h1 {{ font-size: 1.2rem; }}
.main {{ max-width: 600px; margin: 0 auto; padding: 1rem; }}
.tab-bar {{ display: flex; background: white; border-radius: 12px; overflow: hidden; margin-bottom: 1rem; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
.tab {{ flex: 1; padding: 0.75rem; text-align: center; font-weight: 600; cursor: pointer; border: none; background: white; font-size: 0.95rem; }}
.tab.active {{ background: #4CAF50; color: white; }}
.badge {{ background: #FF5722; color: white; border-radius: 10px; padding: 0 6px; font-size: 0.75rem; margin-left: 4px; }}
.card {{ background: white; border-radius: 16px; padding: 1rem 1.25rem; margin-bottom: 0.75rem; box-shadow: 0 2px 8px rgba(0,0,0,0.08); cursor: pointer; transition: transform 0.15s; }}
.card:active {{ transform: scale(0.98); }}
.card-pending {{ border-left: 4px solid #FF9800; }}
.card-graded {{ border-left: 4px solid #4CAF50; }}
.card-header {{ display: flex; justify-content: space-between; margin-bottom: 0.5rem; }}
.card-date {{ font-size: 0.85rem; color: #666; }}
.card-meta {{ font-size: 0.8rem; color: #999; }}
.word-preview {{ font-size: 0.85rem; color: #555; margin-top: 0.5rem; line-height: 1.6; }}
.word-tag {{ display: inline-block; padding: 2px 8px; border-radius: 4px; margin: 2px; font-size: 0.75rem; background: #F5F5F5; }}
.word-tag.wrong {{ background: #FFEBEE; color: #D32F2F; }}
.word-tag.correct {{ background: #E8F5E9; color: #388E3C; }}
.word-tag.pending {{ background: #FFF3E0; color: #E65100; }}
.empty {{ text-align: center; padding: 3rem; color: #999; font-size: 0.95rem; }}
.detail {{ display: none; }}
.detail.active {{ display: block; }}
.detail-header {{ display: flex; align-items: center; gap: 1rem; margin-bottom: 1rem; }}
.back-btn {{ background: white; border: none; border-radius: 8px; padding: 0.5rem 1rem; cursor: pointer; font-size: 0.9rem; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
.word-group {{ background: white; border-radius: 12px; padding: 1rem; margin-bottom: 0.75rem; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
.word-group-header {{ font-size: 1rem; font-weight: 700; color: #333; margin-bottom: 0.75rem; display: flex; align-items: center; gap: 0.5rem; }}
.word-group-status {{ font-size: 0.75rem; padding: 2px 8px; border-radius: 4px; }}
.status-correct {{ background: #E8F5E9; color: #388E3C; }}
.status-wrong {{ background: #FFEBEE; color: #D32F2F; }}
.status-pending {{ background: #FFF3E0; color: #E65100; }}
.chars-grid {{ display: flex; flex-wrap: wrap; gap: 0.75rem; }}
.char-item {{ display: flex; flex-direction: column; align-items: center; gap: 0.4rem; }}
.char-item img {{ width: 100px; height: 100px; border: 2px solid #333; border-radius: 8px; object-fit: contain; background: white; }}
.char-label {{ font-size: 0.9rem; font-weight: 600; color: #333; }}
.grade-btns {{ display: flex; gap: 0.5rem; }}
.gbtn {{ padding: 0.4rem 0.8rem; border-radius: 8px; border: none; font-size: 0.85rem; font-weight: 700; cursor: pointer; }}
.gbtn.correct {{ background: #E8F5E9; color: #388E3C; }}
.gbtn.wrong {{ background: #FFEBEE; color: #D32F2F; }}
.gbtn.sel-correct {{ background: #4CAF50; color: white; }}
.gbtn.sel-wrong {{ background: #F44336; color: white; }}
.submit-btn {{ width: 100%; padding: 1rem; border-radius: 16px; border: none; background: #4CAF50; color: white; font-size: 1rem; font-weight: 700; cursor: pointer; margin-top: 1rem; }}
.submit-btn:disabled {{ background: #ccc; cursor: not-allowed; }}
</style>
</head>
<body>
<div class="header">
  <h1>📝 听写批改</h1>
  <a href="/" style="color:white;text-decoration:none;font-size:0.9rem;">刷新</a>
</div>

<div class="main">
  <!-- 列表视图 -->
  <div id="list-view">
    <div class="tab-bar">
      <button class="tab active" id="tab-pending" onclick="showTab('pending')">待批改<span class="badge" id="pending-count">{len(pending)}</span></button>
      <button class="tab" id="tab-graded" onclick="showTab('graded')">已批改</button>
    </div>
    <div id="pending-list">{pending_html}</div>
    <div id="graded-list" style="display:none;">{graded_html}</div>
  </div>

  <!-- 详情视图 -->
  <div id="detail-view" class="detail">
    <div class="detail-header">
      <button class="back-btn" onclick="showList()">← 返回</button>
      <div>
        <div style="font-weight:700;" id="detail-title"></div>
        <div style="font-size:0.8rem;color:#666;" id="detail-meta"></div>
      </div>
    </div>
    <div id="word-groups"></div>
    <button class="submit-btn" id="submit-btn" onclick="submitGrades()" disabled>请为所有字标记对错</button>
  </div>
</div>

<script>
let currentSession = null;
let currentResults = [];

function showTab(tab) {{
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById('tab-' + tab).classList.add('active');
  document.getElementById('pending-list').style.display = tab === 'pending' ? 'block' : 'none';
  document.getElementById('graded-list').style.display = tab === 'graded' ? 'block' : 'none';
}}

function showList() {{
  document.getElementById('list-view').style.display = 'block';
  document.getElementById('detail-view').classList.remove('active');
}}

async function showDetail(sessionId) {{
  try {{
    const resp = await fetch('/api/session/' + sessionId);
    const s = await resp.json();
    currentSession = s;
    currentResults = s.results ? [...s.results] : new Array(s.chars.length).fill(null);

    document.getElementById('list-view').style.display = 'none';
    document.getElementById('detail-view').classList.add('active');
    document.getElementById('detail-title').textContent = (s.grade || '') + ' · ' + (s.unit || '') + '单元';
    document.getElementById('detail-meta').textContent = s.date + ' · ' + (s.words || []).length + '个词';

    renderWordGroups(s);
    updateSubmitBtn();
  }} catch(e) {{
    alert('加载失败: ' + e);
  }}
}}

function renderWordGroups(s) {{
  const container = document.getElementById('word-groups');
  container.innerHTML = '';
  const words = s.words || [];
  const chars = s.chars || [];
  const images = s.images || [];
  const wordStartIndices = s.wordStartIndices || [];
  const results = currentResults;

  words.forEach((word, wi) => {{
    const start = wordStartIndices[wi] || 0;
    const end = wordStartIndices[wi + 1] || chars.length;
    const wordChars = chars.slice(start, end);
    const wordImgs = images.slice(start, end);
    const wordResults = results.slice(start, end);

    const allCorrect = wordResults.every(r => r === true);
    const anyWrong = wordResults.some(r => r === false);
    const pending = wordResults.some(r => r === null);
    let wordStatus = 'pending';
    if (!pending && allCorrect) wordStatus = 'correct';
    if (anyWrong) wordStatus = 'wrong';

    const statusLabel = wordStatus === 'correct' ? '全对' : (wordStatus === 'wrong' ? '有错' : '待判');
    const statusCls = 'status-' + wordStatus;

    let charsHtml = '';
    for (let ci = 0; ci < wordChars.length; ci++) {{
      const charIdx = start + ci;
      const charResult = wordResults[ci];
      const imgSrc = wordImgs[ci] || '';
      charsHtml += `
        <div class="char-item">
          ${{imgSrc ? '<img src="' + imgSrc + '" alt="书写">' : '<div style="width:100px;height:100px;border:2px solid #ccc;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:2rem;color:#ccc;">?</div>'}}
          <span class="char-label">${{wordChars[ci]}}</span>
          <div class="grade-btns">
            <button class="gbtn correct ${{charResult === true ? 'sel-correct' : ''}}" onclick="setChar(${{charIdx}}, true)">✓</button>
            <button class="gbtn wrong ${{charResult === false ? 'sel-wrong' : ''}}" onclick="setChar(${{charIdx}}, false)">✗</button>
          </div>
        </div>`;
    }}

    container.innerHTML += `
      <div class="word-group">
        <div class="word-group-header">
          ${{word}}
          <span class="word-group-status ${{statusCls}}">${{statusLabel}}</span>
        </div>
        <div class="chars-grid">${{charsHtml}}</div>
      </div>`;
  }});
}}

function setChar(charIdx, correct) {{
  currentResults[charIdx] = correct;
  renderWordGroups(currentSession);
  updateSubmitBtn();
}}

function updateSubmitBtn() {{
  const btn = document.getElementById('submit-btn');
  const allFilled = currentResults.every(r => r !== null);
  btn.disabled = !allFilled;
  btn.textContent = allFilled ? '提交批改' : '请为所有字标记对错';
}}

async function submitGrades() {{
  const btn = document.getElementById('submit-btn');
  btn.disabled = true;
  btn.textContent = '提交中...';
  try {{
    const resp = await fetch('/api/session/' + currentSession.id + '/grade', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{
        results: currentResults,
        gradedAt: new Date().toISOString()
      }})
    }});
    const data = await resp.json();
    if (data.success) {{
      btn.textContent = '已提交 ✓';
      setTimeout(() => {{ location.reload(); }}, 800);
    }} else {{
      btn.textContent = '提交失败，请重试';
      btn.disabled = false;
    }}
  }} catch(e) {{
    btn.textContent = '提交失败，请重试';
    btn.disabled = false;
  }}
}}
</script>
</body>
</html>"""


# ─── shared helpers ─────────────────────────────────────────────────────────

def get_sessions():
    sessions = []
    if not os.path.exists(SESSIONS_DIR):
        return sessions
    for fname in sorted(os.listdir(SESSIONS_DIR), reverse=True):
        if fname.endswith(".json") and not fname.startswith("wrongbook"):
            with open(os.path.join(SESSIONS_DIR, fname), encoding="utf-8") as f:
                sessions.append(json.load(f))
    return sessions


def save_session(session):
    path = os.path.join(SESSIONS_DIR, f"session_{session['id']}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(session, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    print(f"[Grading Server] Starting on http://0.0.0.0:{PORT}")
    with ReuseAddrTCPServer(("", PORT), Handler) as httpd:
        httpd.serve_forever()
