"""
检查 Chrome 进程是否使用了 Profile 3
"""
import psutil
from pathlib import Path

wrapper_dir = Path(__file__).parent
user_data_dir = wrapper_dir / "browser_data" / "chrome_user_data"
user_data_str = str(user_data_dir).replace('\\', '/').lower()

print(f"查找使用以下配置的 Chrome 进程：")
print(f"User Data Dir: {user_data_dir}")
print(f"Profile: Profile 3")
print()

found = False
for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
    try:
        if proc.info.get('name') and 'chrome.exe' in proc.info.get('name', '').lower():
            cmdline = proc.info.get('cmdline', [])
            cmdline_str = ' '.join(cmdline) if cmdline else ''
            cmdline_lower = cmdline_str.replace('\\', '/').lower()
            
            if user_data_str in cmdline_lower and 'profile 3' in cmdline_lower:
                print(f"[OK] 找到使用 Profile 3 的 Chrome 进程:")
                print(f"   PID: {proc.info['pid']}")
                print(f"   命令行包含: {user_data_str}")
                print(f"   命令行包含: Profile 3")
                found = True
                break
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        continue

if not found:
    print("[ERROR] 未找到使用 Profile 3 的 Chrome 进程")
    print("可能原因：")
    print("1. 浏览器使用了其他配置")
    print("2. 浏览器还未完全启动")
    print("3. 浏览器进程已关闭")

