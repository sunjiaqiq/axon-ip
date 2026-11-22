@echo off
chcp 65001 >nul
echo ========================================
echo 启动 Chrome（支持自动化连接）
echo ========================================
echo.
echo 正在启动 Chrome，请保持此窗口打开...
echo.
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --profile-directory="Profile 3" --remote-debugging-port=9222
echo.
echo Chrome 已启动，现在可以运行自动化脚本了。
echo 请保持此窗口打开，不要关闭 Chrome。
echo.
pause





