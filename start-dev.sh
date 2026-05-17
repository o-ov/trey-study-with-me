#!/bin/bash
# 开发环境启动脚本
# 用法: bash start-dev.sh

set -e
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$BASE_DIR/venv-dev/bin/python3"

echo "🚀 [DEV] 启动听写App开发环境..."

echo "  → app.py (8180)"
cd "$BASE_DIR"
PORT=8180 $VENV backend/app.py > /tmp/zlzp-dev-api.log 2>&1 &

echo "  → tts.py (8182)"
TTS_PORT=8182 $VENV backend/tts.py > /tmp/zlzp-dev-tts.log 2>&1 &

echo "  → grading_server.py (8181)"
GRADING_PORT=8181 $VENV grading_server.py > /tmp/zlzp-dev-grading.log 2>&1 &

echo "  → 学生端 (3100)"
cd student && npx http-server -p 3100 -c-1 --bind-addr 0.0.0.0 > /tmp/zlzp-dev-student.log 2>&1 &

echo "  → 家长端 (3101)"
cd ../parent && npx http-server -p 3101 -c-1 --bind-addr 0.0.0.0 > /tmp/zlzp-dev-parent.log 2>&1 &

echo "✅ [DEV] 所有开发服务已启动"
echo "   API:      http://localhost:8180"
echo "   TTS:      http://localhost:8182"
echo "   Grading:  http://localhost:8181"
echo "   Student:  http://localhost:3100"
echo "   Parent:   http://localhost:3101"
