#!/bin/bash
# 生产环境启动脚本
# 用法: bash start-prod.sh

set -e
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$BASE_DIR/venv-prod/bin/python3"

echo "🚀 [PROD] 启动听写App服务..."

echo "  → app.py (8080)"
cd "$BASE_DIR"
$VENV backend/app.py > /tmp/zlzp-api.log 2>&1 &

echo "  → tts.py (8082)"
$VENV backend/tts.py > /tmp/zlzp-tts.log 2>&1 &

echo "  → grading_server.py (8081)"
$VENV grading_server.py > /tmp/zlzp-grading.log 2>&1 &

echo "  → 学生端 (3000)"
cd student && npx http-server -p 3000 -c-1 --bind-addr 0.0.0.0 > /tmp/zlzp-student.log 2>&1 &

echo "  → 家长端 (3001)"
cd ../parent && npx http-server -p 3001 -c-1 --bind-addr 0.0.0.0 > /tmp/zlzp-parent.log 2>&1 &

echo "✅ [PROD] 所有服务已启动"
