"""
UIA 全局运行时模块

确保 UIAutomation 在整个程序生命周期中只初始化一次：
- CoInitialize 只能执行一次
- Desktop(backend="uia") 只能创建一次
- 禁止在每个任务里重新初始化 UIA
- 禁止任务结束后释放 COM
"""

from pywinauto import Desktop
from pythoncom import CoInitialize
import threading

_lock = threading.Lock()
_desktop = None
_initialized = False

def get_desktop():
    """
    获取全局 Desktop 对象（只初始化一次）
    
    返回:
        Desktop: 全局 Desktop 对象
    
    注意:
        - CoInitialize 只执行一次
        - Desktop 只创建一次
        - 线程安全
    """
    global _desktop, _initialized
    
    with _lock:
        if not _initialized:
            CoInitialize()
            _desktop = Desktop(backend="uia")
            _initialized = True
            print("[UIA GLOBAL] Initialized once")
    
    return _desktop


