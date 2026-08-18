@echo off
REM ========= Windows 一键发布脚本（后端 + 前端构建 + 复制到部署目录）=========
REM 以管理员身份执行，若部署目录不同请修改下两行
set DEPLOY_FRONT=C:\inetpub\wwwroot\chain
set BACKEND_ROOT=%~dp0..\backend
set FRONTEND_ROOT=%~dp0..\frontend

echo [1/4] 备份 SQLite ...
if exist "%BACKEND_ROOT%\app\storage\db\chain.sqlite3" (
  if not exist "%BACKEND_ROOT%\app\storage\db\backup" mkdir "%BACKEND_ROOT%\app\storage\db\backup"
  copy /Y "%BACKEND_ROOT%\app\storage\db\chain.sqlite3" ^
       "%BACKEND_ROOT%\app\storage\db\backup\chain-%date:~0,4%%date:~5,2%%date:~8,2%-%time:~0,2%%time:~3,2%.sqlite3"
)

echo [2/4] 后端依赖同步 ...
cd /d "%BACKEND_ROOT%"
call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt

echo [3/4] 前端构建 ...
cd /d "%FRONTEND_ROOT%"
call npm ci
if errorlevel 1 (echo npm ci failed & exit /b 1)
call npm run build
if errorlevel 1 (echo frontend build failed & exit /b 1)

echo [4/4] 部署前端静态 ...
if not exist "%DEPLOY_FRONT%" mkdir "%DEPLOY_FRONT%"
rmdir /S /Q "%DEPLOY_FRONT%" 2>nul
mkdir "%DEPLOY_FRONT%"
xcopy /E /H /Y "%FRONTEND_ROOT%\dist\*" "%DEPLOY_FRONT%\"

echo OK done.
echo - Restart backend service (NSSM): nssm restart ChainBackend
echo - Recycle IIS app pool or net stop w3svc ^&^& net start w3svc
