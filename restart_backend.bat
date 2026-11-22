@echo off
chcp 65001 >nul
echo ========================================
echo 重启后端服务
echo ========================================

echo [1/3] 停止旧的后端服务...
taskkill /F /IM python.exe /T >nul 2>&1
taskkill /F /IM py.exe /T >nul 2>&1
timeout /t 2 /nobreak >nul

echo.
echo [2/3] 启动后端服务...
start "Pixelle Backend" /D "%~dp0pixelle_wrapper" cmd /k "py -3 main.py"
echo 等待后端启动...
timeout /t 10 /nobreak >nul

echo.
echo [3/3] 检查服务状态...
netstat -ano | findstr ":38810.*LISTENING"
if %errorlevel% equ 0 (
    echo [OK] 后端服务运行中 (端口38810)
) else (
    echo [ERROR] 后端服务启动失败
    pause
    exit /b 1
)

echo.
echo ========================================
echo 后端服务已重启
echo ========================================
echo 后端API: http://127.0.0.1:38810
echo 前端网关: http://localhost:3000
echo.
echo 请在前端刷新页面测试
echo.
pause



