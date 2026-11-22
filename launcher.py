#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
精简后的启动器：
- 启动 runtime_env\python 执行 bootstrap.py（保证 sys.path 正确）
- 轮询 /api/connection_status 判断服务就绪
- 就绪后自动打开 /docs 页面
"""

import os
import sys
import time
import subprocess
import webbrowser
import urllib.request
from pathlib import Path
import socket

PORT = 33710
BASE_URL = f"http://localhost:{PORT}"
HEALTH_URL = f"{BASE_URL}/api/connection_status"


def is_server_running() -> bool:
    """快速检测端口是否已有进程在监听（避免重复启动导致端口占用报错）。"""
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=0.5):
            return True
    except Exception:
        return False


def wait_for_server(timeout: float = 120.0, interval: float = 1.0) -> bool:
    """轮询 /api/connection_status，直到返回 200 视为服务就绪。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=3) as resp:
                if resp.getcode() == 200:
                    return True
        except Exception:
            time.sleep(interval)
    return False


def get_install_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def main() -> int:
    install_dir = get_install_dir()
    print(f"安装目录: {install_dir}", flush=True)

    # 如果后端已在运行：只打开浏览器，不重复启动后端
    open_url = f"{BASE_URL}/"
    if is_server_running():
        print(f"检测到后端已运行，直接打开系统界面: {open_url}", flush=True)
        webbrowser.open(open_url)
        return 0

    python_exe = os.path.join(install_dir, "runtime_env", "python", "python.exe")
    if not os.path.isfile(python_exe):
        print("未找到 runtime_env\\python\\python.exe", flush=True)
        return 1

    bootstrap = os.path.join(install_dir, "bootstrap.py")
    if not os.path.isfile(bootstrap):
        print("未找到 bootstrap.py", flush=True)
        return 1

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["AXON_PORT"] = str(PORT)
    # 与 main.pyc 内挂载 web/ 一致，避免 runpy 下 __file__ 解析错误导致旧 UI
    env["AXON_INSTALL_DIR"] = os.path.abspath(install_dir)

    print(f"Python: {python_exe}", flush=True)
    print("未检测到后端运行，正在启动后端 ...", flush=True)
    proc = subprocess.Popen(
        [python_exe, bootstrap],
        cwd=install_dir,
        env=env,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if sys.platform == "win32" else 0,
    )
    print(f"后端已启动 (PID={proc.pid})，等待服务 ...", flush=True)

    if not wait_for_server():
        print(f"等待服务超时，请手动检查 {HEALTH_URL} 和日志", flush=True)
        return 1

    print(f"服务已就绪，正在打开系统界面: {open_url}", flush=True)
    webbrowser.open(open_url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
