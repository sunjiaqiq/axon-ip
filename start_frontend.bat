@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [启动前端] 正在启动 Vite 开发服务器...
echo [启动前端] 端口: 3000
echo.
npm run dev
pause





