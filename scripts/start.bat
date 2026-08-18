@echo off
REM FISCO 联盟链学习平台 - 一键启动脚本（Windows）
setlocal
cd /d "%~dp0"

echo [1/3] 启动 FISCO-BCOS 联盟链...
pushd deploy
docker-compose up -d
popd

echo [2/3] 启动后端 FastAPI...
start "chain-backend" cmd /k "cd backend && call .venv\Scripts\activate && python run.py"

echo [3/3] 启动前端 Vite...
start "chain-frontend" cmd /k "cd frontend && npm run dev"

echo.
echo 前端: http://localhost:5173
echo 后端: http://localhost:8000/docs
endlocal
