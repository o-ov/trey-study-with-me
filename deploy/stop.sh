#!/bin/bash
# 停止所有听写 App 服务
# 用法: bash stop.sh

echo "🛑 停止听写 App 服务..."

# 杀掉所有相关进程
pkill -f "python3.*app.py"  && echo "  ✅ app.py 已停止" || true
pkill -f "python3.*tts.py" && echo "  ✅ tts.py 已停止" || true
pkill -f "python3.*grading_server" && echo "  ✅ grading_server.py 已停止" || true
pkill -f "http-server.*3000" && echo "  ✅ 学生端(3000) 已停止" || true
pkill -f "http-server.*3001" && echo "  ✅ 家长端(3001) 已停止" || true

echo ""
echo "✅ 所有服务已停止"
