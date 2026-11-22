@echo off
chcp 65001 >nul
echo ========================================
echo 智能启动 Chrome（支持自动化）
echo ========================================
echo.
echo 正在检查 Chrome 是否已运行...
echo.

:: 检查 Chrome 是否已运行
tasklist /FI "IMAGENAME eq chrome.exe" 2>NUL | find /I /N "chrome.exe">NUL
if "%ERRORLEVEL%"=="0" (
    echo [警告] 检测到 Chrome 已在运行！
    echo.
    echo 请选择操作：
    echo 1. 关闭所有 Chrome 窗口，然后重新启动（推荐）
    echo 2. 保持当前 Chrome 打开，但自动化可能无法连接
    echo.
    set /p choice="请输入选择 (1 或 2): "
    
    if "!choice!"=="1" (
        echo.
        echo 正在关闭所有 Chrome 窗口...
        taskkill /F /IM chrome.exe >nul 2>&1
        timeout /t 2 >nul
        echo Chrome 已关闭
    ) else (
        echo.
        echo [提示] 如果自动化无法连接，请关闭 Chrome 后重新运行此脚本
        echo.
        pause
        exit /b
    )
)

echo.
echo 正在启动 Chrome（启用远程调试）...
echo.
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --profile-directory="Profile 3" --remote-debugging-port=9222
echo.
echo [成功] Chrome 已启动，支持自动化连接！
echo.
echo 请保持此窗口打开，不要关闭 Chrome。
echo 现在可以运行自动化脚本了。
echo.
pause





