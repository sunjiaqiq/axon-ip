# PowerShell 版本的清理脚本（更精确）
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "清理 Pixelle-Video Wrapper 进程" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 查找并关闭 PixelleWrapper.exe
Write-Host "[1/2] 正在查找 PixelleWrapper.exe 进程..." -ForegroundColor Yellow
$wrapperProcesses = Get-Process -Name "PixelleWrapper" -ErrorAction SilentlyContinue
if ($wrapperProcesses) {
    Write-Host "找到 $($wrapperProcesses.Count) 个 PixelleWrapper.exe 进程，正在关闭..." -ForegroundColor Yellow
    $wrapperProcesses | Stop-Process -Force
    Write-Host "✅ PixelleWrapper.exe 已关闭" -ForegroundColor Green
} else {
    Write-Host "✅ 未找到运行中的 PixelleWrapper.exe" -ForegroundColor Green
}

# 查找并关闭运行 main.py 的 Python 进程（更精确）
Write-Host ""
Write-Host "[2/2] 正在查找 Python Wrapper 进程..." -ForegroundColor Yellow
$pythonProcesses = Get-Process -Name "python*" -ErrorAction SilentlyContinue
$found = $false
foreach ($proc in $pythonProcesses) {
    try {
        $cmdLine = (Get-CimInstance Win32_Process -Filter "ProcessId = $($proc.Id)").CommandLine
        if ($cmdLine -and $cmdLine -match "pixelle_wrapper[\\/]main\.py") {
            Write-Host "找到 Python Wrapper 进程 (PID: $($proc.Id))，正在关闭..." -ForegroundColor Yellow
            Stop-Process -Id $proc.Id -Force
            Write-Host "✅ Python Wrapper 进程已关闭" -ForegroundColor Green
            $found = $true
        }
    } catch {
        # 忽略无法访问的进程
    }
}
if (-not $found) {
    Write-Host "✅ 未找到运行中的 Python Wrapper 进程" -ForegroundColor Green
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "清理完成！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "提示：如果端口 38887 仍被占用，请等待几秒后重试" -ForegroundColor Yellow
Start-Sleep -Seconds 2









