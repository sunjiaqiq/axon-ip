@echo off
chcp 65001 >nul
echo ========================================
echo 清理并重启后端和前端服务
echo ========================================
echo.

echo [1/5] 清理所有Python进程...
taskkill /F /IM python.exe /T 2>nul
taskkill /F /IM py.exe /T 2>nul
timeout /t 2 /nobreak >nul
echo 清理完成
echo.

echo [2/5] 检查端口占用...
netstat -ano | findstr ":38810" | findstr "LISTENING"
if %errorlevel%==0 (
    echo 发现端口38810被占用，正在清理...
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":38810" ^| findstr "LISTENING"') do taskkill /F /PID %%a 2>nul
    timeout /t 2 /nobreak >nul
)
echo.

echo [3/5] 启动后端服务...
start "Pixelle Backend" /MIN /D "%~dp0pixelle_wrapper" py -3 main.py
echo 后端服务启动中，等待15秒...
timeout /t 15 /nobreak >nul
echo.

echo [4/5] 检查后端服务状态...
netstat -ano | findstr ":38810" | findstr "LISTENING"
if %errorlevel%==0 (
    echo [OK] 后端服务已启动，端口38810正在监听
) else (
    echo [ERROR] 后端服务未启动，请检查日志
)
echo.

echo [5/5] 启动前端服务...
start "Frontend Dev Server" /D "%~dp0" cmd /k "npm run dev"
echo 前端服务启动中，等待10秒...
timeout /t 10 /nobreak >nul
echo.

echo [检查] 检查前端服务状态...
netstat -ano | findstr ":3000" | findstr "LISTENING"
if %errorlevel%==0 (
    echo [OK] 前端服务已启动，端口3000正在监听
) else (
    echo [ERROR] 前端服务未启动，请检查日志
)
echo.

echo ========================================
echo 服务启动完成
echo ========================================
echo 后端API文档: http://127.0.0.1:38810/docs
echo 前端网关: http://localhost:3000
echo.
echo 正在打开浏览器...
start http://127.0.0.1:38810/docs
start http://localhost:3000
echo.
pause




