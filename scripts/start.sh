#!/usr/bin/env bash
# 一键启动脚本（Linux/macOS）
set -e
cd "$(dirname "$0")/.."

echo "[1/3] 启动 FISCO-BCOS 联盟链..."
( cd deploy && docker-compose up -d )

echo "[2/3] 启动后端..."
( cd backend && source .venv/bin/activate 2>/dev/null || true && python run.py ) &
BACKEND_PID=$!

echo "[3/3] 启动前端..."
( cd frontend && npm run dev ) &
FRONTEND_PID=$!

echo "前端: http://localhost:5173"
echo "后端: http://localhost:8000/docs"
wait $BACKEND_PID $FRONTEND_PID
