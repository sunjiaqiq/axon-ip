@echo off
chcp 65001 >nul
echo 正在启动 Pixelle-Video Web UI...
echo.

REM 设置 FFmpeg 路径（与 pixelle_wrapper 为同级目录时生效，任意盘符均可）
set "PATH=%~dp0..\pixelle_wrapper\ffmpeg\bin;%PATH%"

REM 切换到本脚本所在目录（Video-main）
cd /d "%~dp0"

REM 启动 Streamlit
py -3 -m streamlit run web/app.py --server.port 8501 --server.address 0.0.0.0

pause




