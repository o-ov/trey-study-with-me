#!/usr/bin/env python3
"""
服务健康监控脚本
每分钟检查一次，挂了自动重启 + 飞书通知
"""

import requests
import subprocess
import time
import os
import sys
import json

SERVICES = [
    ("API",       "http://localhost:8080/api/health",    "dictation-api"),
    ("TTS",       "http://localhost:8082/health",        "dictation-tts"),
    ("Grading",   "http://localhost:8081/",              "dictation-grading"),
    ("Student",   "http://localhost:3000/",              "dictation-student"),
    ("Parent",    "http://localhost:3001/",              "dictation-parent"),
]

LOG_FILE   = "/tmp/zlzp-monitor.log"
TOKEN_FILE = "/tmp/zlzp-feishu-token.txt"

FEISHU_APP_ID    = "cli_a9746a2be2791cd5"
FEISHU_APP_SECRET = "O5oAOtmjaOcaUzBa4u2v3fckFbhQyO3B"


def log(msg):
    ts = subprocess.getoutput("date '+%Y-%m-%d %H:%M:%S'")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def check_service(name, url):
    try:
        r = requests.get(url, timeout=5)
        return r.status_code == 200
    except:
        return False


def restart_all():
    """杀掉并重启所有服务"""
    log("=== Restarting all services ===")

    patterns = [
        "python3.*backend/app.py",
        "python3.*backend/tts.py",
        "python3.*grading_server.py",
        "http-server.*3000",
        "http-server.*3001",
    ]
    for p in patterns:
        subprocess.run(f"pkill -f '{p}' 2>/dev/null", shell=True)

    time.sleep(2)

    BASE = "/home/ubuntu/zlzp-dictation"

    subprocess.Popen(
        f"cd {BASE} && /usr/bin/python3 backend/app.py > /tmp/zlzp-api.log 2>&1",
        shell=True
    )
    time.sleep(1)
    subprocess.Popen(
        f"cd {BASE} && /usr/bin/python3 backend/tts.py > /tmp/zlzp-tts.log 2>&1",
        shell=True
    )
    time.sleep(1)
    subprocess.Popen(
        f"cd {BASE} && /usr/bin/python3 grading_server.py > /tmp/zlzp-grading.log 2>&1",
        shell=True
    )
    time.sleep(1)
    subprocess.Popen(
        f"cd {BASE}/student && npx http-server -p 3000 -c-1 --bind-addr 0.0.0.0 > /tmp/zlzp-student.log 2>&1",
        shell=True
    )
    subprocess.Popen(
        f"cd {BASE}/parent && npx http-server -p 3001 -c-1 --bind-addr 0.0.0.0 > /tmp/zlzp-parent.log 2>&1",
        shell=True
    )

    log("All services restarted")


def get_feishu_token():
    """获取飞书 tenant access token"""
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    data = {"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}
    try:
        r = requests.post(url, json=data, timeout=10)
        return r.json().get("tenant_access_token", "")
    except:
        return ""


def send_feishu(title, content):
    """发飞书消息给 Stan"""
    token = get_feishu_token()
    if not token:
        log("Feishu token failed")
        return

    # Stan 的 open_id
    open_ids = ["ou_fa32b9b15abf59036f51d5eec0afb70d"]

    url = "https://open.feishu.cn/open-apis/im/v1/messages"
    for oid in open_ids:
        payload = {
            "receive_id": oid,
            "msg_type": "text",
            "content": json.dumps({"text": f"{title}\n\n{content}"})
        }
        try:
            requests.post(
                url,
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
                timeout=10
            )
        except Exception as e:
            log(f"Feishu send failed: {e}")


def run_check():
    failed = []
    for name, url, svc in SERVICES:
        ok = check_service(name, url)
        if not ok:
            failed.append(name)
            log(f"[DOWN] {name} ({url})")

    if failed:
        log(f"Services DOWN: {', '.join(failed)}. Restarting...")
        restart_all()

        # 读最新日志发给 Stan
        log_lines = subprocess.getoutput(
            f"tail -20 /tmp/zlzp-api.log 2>/dev/null || echo 'no log'"
        )
        send_feishu(
            f"🔴 服务异常: {', '.join(failed)}",
            f"时间: {subprocess.getoutput('date')}\n\n最近日志:\n{log_lines[-500:]}"
        )
    else:
        log("All services OK")


if __name__ == "__main__":
    run_check()
