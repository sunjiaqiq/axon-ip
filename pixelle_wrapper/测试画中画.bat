@echo off
chcp 65001 >nul
echo ============================================================
echo 画中画功能测试
echo ============================================================
echo.

cd /d "%~dp0"

REM 尝试不同的Python命令
where python >nul 2>&1
if %errorlevel% == 0 (
    python test_pip_simple.py
    goto :end
)

where python3 >nul 2>&1
if %errorlevel% == 0 (
    python3 test_pip_simple.py
    goto :end
)

where py >nul 2>&1
if %errorlevel% == 0 (
    py test_pip_simple.py
    goto :end
)

echo [ERROR] 未找到Python命令！
echo 请确保Python已安装并添加到PATH环境变量中
echo.
echo 或者手动运行: python test_pip_simple.py

:end
pause




