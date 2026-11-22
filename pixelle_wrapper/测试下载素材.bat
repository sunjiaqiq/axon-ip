@echo off
chcp 65001 >nul
echo ========================================
echo 测试：搜索并下载"宠物医院"相关视频素材
echo ========================================
echo.

cd /d %~dp0

echo 正在运行测试脚本...
echo.

py test_download.py

if errorlevel 1 (
    echo.
    echo 如果提示找不到python，请使用以下命令：
    echo python3 test_download.py
    echo 或者
    echo py -3 test_download.py
)

echo.
echo ========================================
pause







