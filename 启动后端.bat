@echo off
chcp 65001 >nul
echo 正在启动后端服务...
cd /d "%~dp0"
py -3 -m uvicorn pixelle_wrapper.main:app --port 38810 --host 127.0.0.1
pause
