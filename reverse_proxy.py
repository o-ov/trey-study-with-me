"""HTTP server on 8080: serves static + session submission API."""
import http.server
import socketserver
import os
import re
import uuid
import base64
import json
import subprocess
from datetime import datetime

HTML_DIR = "/root/.hermes/profiles/leader/cache/documents"
LISTEN_PORT = 8080
UPLOAD_DIR = "/tmp/dictation_uploads"
SESSIONS_DIR = "/root/dictation_sessions"
WRONGBOOK_FILE = "/root/dictation_sessions/wrongbook.json"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(SESSIONS_DIR, exist_ok=True)


class ReuseAddrTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


def save_session(session):
    path = os.path.join(SESSIONS_DIR, f"session_{session['id']}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(session, f, ensure_ascii=False, indent=2)


def load_wrongbook():
    if not os.path.exists(WRONGBOOK_FILE):
        return {}
    with open(WRONGBOOK_FILE, encoding="utf-8") as f:
        data = json.load(f)
        # 支持新 dict 格式（{char: stats}）和旧数组格式（[{char, ...}]）
        if isinstance(data, dict):
            return data
        return {}


def notify_feishu(session):
    grade = session.get("grade", "")
    unit = session.get("unit", "")
    words = session.get("words", [])
    date = session.get("date", "")
    grading_url = "http://47.243.65.57:8081"
    words_text = "、".join(words) if words else "未知"
    msg = (
        f"📝 孩子听写已提交\n\n"
        f"• 年级：{grade}\n"
        f"• 单元：{unit}\n"
        f"• 词汇：{words_text}\n"
        f"• 日期：{date}\n\n"
        f"👉 请点击前往批改：\n{grading_url}"
    )
    try:
        subprocess.run(
            ["lark-cli", "im", "+messages-send",
             "--chat-id", "oc_7c2b51a013b7408f6cb978c3f44cf48c",
             "--text", msg],
            capture_output=True, text=True, timeout=15
        )
        print(f"[通知] 飞书消息已发送: session={session['id']}")
    except Exception as e:
        print(f"[通知] 飞书消息发送失败: {e}")


class Handler(http.server.BaseHTTPRequestHandler):
    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/wrongbook":
            book = load_wrongbook()
            # 新 dict 格式：{char: {char, word, reviewed, ...}}
            if isinstance(book, dict):
                unreviewed = [v for v in book.values() if not v.get("reviewed", False)]
            else:
                unreviewed = [e for e in book if not e.get("reviewed", False)]
            self.send_json({"wrongChars": unreviewed, "count": len(unreviewed)})
            return

        if self.path.startswith("/uploads/"):
            filename = os.path.basename(self.path)
            filepath = os.path.join(UPLOAD_DIR, filename)
            if os.path.exists(filepath):
                with open(filepath, "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", len(body))
                self.end_headers()
                self.wfile.write(body)
                return
            else:
                self.send_response(404)
                self.end_headers()
                return

        path = self.path
        if path == "/" or path == "/index.html":
            path = "/doc_7e85f47f4148_index.html"
        safe_path = os.path.normpath(os.path.join(HTML_DIR, path.lstrip("/")))
        if not safe_path.startswith(HTML_DIR):
            self.send_response(403)
            self.end_headers()
            return
        if os.path.exists(safe_path) and os.path.isfile(safe_path):
            with open(safe_path, "rb") as f:
                body = f.read()
            ext = os.path.splitext(path)[-1].lstrip(".")
            mime = {"html": "text/html", "css": "text/css", "js": "application/javascript",
                    "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                    "ico": "image/x-icon", "svg": "image/svg+xml"}.get(ext, "application/octet-stream")
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", len(body))
            if ext == "html":
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.send_header("Pragma", "no-cache")
                self.send_header("Expires", "0")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/api/save-image":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body)
                image_data = data.get("imageDataUrl", "")
                b64 = re.sub(r'^data:image/\w+;base64,', '', image_data)
                filename = f"{uuid.uuid4().hex}.png"
                filepath = os.path.join(UPLOAD_DIR, filename)
                with open(filepath, "wb") as f:
                    f.write(base64.b64decode(b64 + "=="))
                self.send_json({"success": True, "path": f"/uploads/{filename}"})
            except Exception as e:
                self.send_json({"success": False, "error": str(e)}, 500)
            return

        if self.path == "/api/submit-session":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body.decode("utf-8"))
            except Exception:
                self.send_json({"success": False, "error": "Invalid JSON"}, 400)
                return

            session_id = uuid.uuid4().hex
            words = data.get("words", [])
            chars = data.get("chars", [])
            images = data.get("images", [])
            word_start_indices = []
            idx = 0
            for w in words:
                word_start_indices.append(idx)
                idx += len(w)

            session = {
                "id": session_id,
                "createdAt": datetime.now().isoformat(),
                "date": datetime.now().strftime("%Y-%m-%d"),
                "grade": data.get("grade", ""),
                "unit": data.get("unit", ""),
                "mode": data.get("mode", ""),
                "words": words,
                "chars": chars,
                "images": images,
                "wordStartIndices": word_start_indices,
                "status": "pending",
                "results": [None] * len(chars),
                "gradedAt": None
            }
            save_session(session)
            notify_feishu(session)
            self.send_json({"success": True, "sessionId": session_id})
            return

        if self.path == "/api/recognize":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            # Rewrite /uploads/ paths to local filesystem
            new_body = body
            if b"/uploads/" in body:
                try:
                    parsed = json.loads(body.decode("utf-8"))
                    if parsed.get("image_path", "").startswith("/uploads/"):
                        fname = os.path.basename(parsed["image_path"])
                        parsed["image_path"] = os.path.join(UPLOAD_DIR, fname)
                        new_body = json.dumps(parsed, ensure_ascii=False).encode("utf-8")
                except Exception:
                    pass
            # Forward to proxy.py on port 3000
            try:
                import urllib.request as ureq
                headers = {"Content-Type": "application/json", "Content-Length": str(len(new_body))}
                fwd_req = ureq.Request(f"http://localhost:3000{self.path}", data=new_body, headers=headers, method="POST")
                with ureq.urlopen(fwd_req, timeout=30) as resp:
                    resp_body = resp.read()
                    self.send_response(resp.status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", len(resp_body))
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(resp_body)
            except Exception as e:
                self.send_json({"success": False, "error": str(e)}, 502)
            return

        self.send_json({"error": "Not found"}, 404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, fmt, *args):
        print(f'[RP] {fmt % args}')


if __name__ == "__main__":
    with ReuseAddrTCPServer(("0.0.0.0", LISTEN_PORT), Handler) as httpd:
        print(f"Serving on :{LISTEN_PORT}, uploads -> {UPLOAD_DIR}, sessions -> {SESSIONS_DIR}")
        httpd.serve_forever()
