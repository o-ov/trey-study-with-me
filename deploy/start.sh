#!/bin/bash
# 一键启动所有听写 App 服务
# 用法: bash start.sh

set -e

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "🚀 启动听写 App 服务..."

# 后端 API
echo "  → app.py (8080)"
cd "$BASE_DIR/.."
python3 backend/app.py &

# TTS
echo "  → tts.py (8082)"
python3 backend/tts.py &

# 批改服务器
echo "  → grading_server.py (8081)"
python3 grading_server.py &

# 孩子端静态服务
echo "  → 学生端 (3000)"
cd "$BASE_DIR/../student"
npx http-server -p 3000 -c-1 --bind-addr 0.0.0.0 &

# 家长端静态服务
echo "  → 家长端 (3001)"
cd "$BASE_DIR/../parent"
npx http-server -p 3001 -c-1 --bind-addr 0.0.0.0 &

echo ""
echo "✅ 所有服务已启动"
echo "  孩子端: http://<IP>:3000"
echo "  家长端: http://<IP>:3001"
echo "  批改页: http://<IP>:8081"
echo "  TTS:    http://<IP>:8082/tts?text=测试"
