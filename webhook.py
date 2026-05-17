#!/usr/bin/env python3
"""
GitHub Webhook Receiver
Receives push events from GitHub and triggers git pull + service restart.
"""

import http.server
import socketserver
import subprocess
import json
import os
import signal
import sys
from pathlib import Path

# Configuration
WEBHOOK_PORT = 9090
GIT_DIR = "/home/ubuntu/zlzp-dictation"
SECRET_TOKEN = os.environ.get("WEBHOOK_SECRET", "")

LOG_FILE = "/tmp/zlzp-webhook.log"


def log(msg):
    timestamp = subprocess.getoutput("date '+%Y-%m-%d %H:%M:%S'")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] {msg}\n")
    print(f"[{timestamp}] {msg}")


def restart_services():
    log("Restarting services...")

    # Kill old processes
    kills = [
        "python3.*backend/app.py",
        "python3.*backend/tts.py",
        "python3.*grading_server.py",
        "http-server.*3000",
        "http-server.*3001",
    ]
    for pattern in kills:
        subprocess.run(f"pkill -f '{pattern}' 2>/dev/null", shell=True)

    import time
    time.sleep(2)

    # Start services
    os.chdir(GIT_DIR)

    subprocess.Popen(
        "/usr/bin/python3 backend/app.py",
        shell=True, stdout=open("/tmp/zlzp-api.log", "a"), stderr=subprocess.STDOUT
    )
    time.sleep(1)
    subprocess.Popen(
        "/usr/bin/python3 backend/tts.py",
        shell=True, stdout=open("/tmp/zlzp-tts.log", "a"), stderr=subprocess.STDOUT
    )
    time.sleep(1)
    subprocess.Popen(
        "/usr/bin/python3 grading_server.py",
        shell=True, stdout=open("/tmp/zlzp-grading.log", "a"), stderr=subprocess.STDOUT
    )
    time.sleep(1)
    subprocess.Popen(
        "cd student && npx http-server -p 3000 -c-1 --bind-addr 0.0.0.0",
        shell=True, stdout=open("/tmp/zlzp-student.log", "a"), stderr=subprocess.STDOUT
    )
    subprocess.Popen(
        "cd parent && npx http-server -p 3001 -c-1 --bind-addr 0.0.0.0",
        shell=True, stdout=open("/tmp/zlzp-parent.log", "a"), stderr=subprocess.STDOUT
    )

    log("Services restarted successfully")


class WebhookHandler(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path == "/webhook":
            # Verify content type
            if self.headers.get("Content-Type") != "application/json":
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Expected application/json")
                return

            content_length = int(self.headers.get("Content-Length", 0))
            payload = self.rfile.read(content_length)

            try:
                data = json.loads(payload)
                event = self.headers.get("X-GitHub-Event", "push")

                log(f"Received GitHub event: {event}")

                if event == "push":
                    branch = data.get("ref", "")
                    if "main" in branch:
                        log(f"Push to main branch detected")
                        restart_services()
                        self.send_response(200)
                        self.wfile.write(json.dumps({"status": "ok"}).encode())
                    else:
                        log(f"Ignoring push to {branch}")
                        self.send_response(200)
                        self.wfile.write(json.dumps({"status": "ignored"}).encode())
                else:
                    log(f"Ignoring event: {event}")
                    self.send_response(200)
                    self.wfile.write(json.dumps({"status": "ignored"}).encode())

            except json.JSONDecodeError:
                log("Invalid JSON payload")
                self.send_response(400)
                self.wfile.write(b"Invalid JSON")

            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress default logging


if __name__ == "__main__":
    log("Webhook receiver starting...")

    # Graceful shutdown
    def signal_handler(sig, frame):
        log("Shutting down...")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    with socketserver.TCPServer(("", WEBHOOK_PORT), WebhookHandler) as httpd:
        log(f"Listening on port {WEBHOOK_PORT}")
        httpd.serve_forever()
