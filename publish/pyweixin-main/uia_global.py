"""
UIA 全局初始化模块

UIAutomation 只能在主线程初始化一次，整个程序生命周期只创建一次。
所有任务必须复用这个全局 UIA 对象，禁止在任何子线程重新初始化。
"""

import pythoncom
import threading
from pywinauto import Desktop

# 全局 UIA 对象（单例）
_UIA_DESKTOP = None
_UIA_INITIALIZED = False
_UIA_INIT_THREAD = None
_lock = threading.Lock()


def initialize_uia_in_main_thread():
    """
    在主线程初始化 UIA（只能调用一次）
    
    必须在程序主入口（MainThread / GUI 主线程）调用。
    
    异常:
        如果不是主线程，抛出 RuntimeError
        如果已经初始化，直接返回
    """
    global _UIA_DESKTOP, _UIA_INITIALIZED, _UIA_INIT_THREAD
    
    with _lock:
        # 检查是否已经初始化
        if _UIA_INITIALIZED:
            print(f"[UIA] Already initialized in thread: {_UIA_INIT_THREAD}")
            return _UIA_DESKTOP
        
        # 检查是否在主线程
        current_thread = threading.current_thread()
        is_main_thread = (current_thread.name == "MainThread" or 
                         isinstance(current_thread, threading._MainThread) or
                         current_thread is threading.main_thread())
        
        if not is_main_thread:
            error_msg = f"UIAutomation must initialize in MAIN thread, current: {current_thread.name}"
            print(f"[UIA ERROR] {error_msg}")
            raise RuntimeError(error_msg)
        
        # 在主线程初始化 UIA
        try:
            pythoncom.CoInitialize()  # STA模式，必须主线程
            _UIA_DESKTOP = Desktop(backend="uia")
            _UIA_INITIALIZED = True
            _UIA_INIT_THREAD = current_thread.name
            
            print("[UIA] Initialized in MAIN thread")
            print(f"[UIA] Thread = {current_thread.name}")
            print(f"[UIA] Is main thread: {current_thread is threading.main_thread()}")
            
            # 验证初始化是否成功
            try:
                wins = _UIA_DESKTOP.windows()
                win_count = len(wins)
                print(f"[UIA] Initial check: windows = {win_count}")
                if win_count == 0:
                    print("[UIA WARNING] Desktop windows = 0 at initialization")
            except Exception as e:
                print(f"[UIA WARNING] Initial check failed: {e}")
            
            return _UIA_DESKTOP
            
        except Exception as e:
            print(f"[UIA ERROR] Initialization failed: {e}")
            _UIA_INITIALIZED = False
            _UIA_DESKTOP = None
            raise RuntimeError(f"UIA initialization failed: {e}")


def get_uia_desktop():
    """
    获取全局 UIA Desktop 对象
    
    返回:
        Desktop: 全局 UIA Desktop 对象
    
    异常:
        如果未初始化，抛出 RuntimeError
    """
    global _UIA_DESKTOP, _UIA_INITIALIZED
    
    if not _UIA_INITIALIZED or _UIA_DESKTOP is None:
        raise RuntimeError("UIA not initialized. Call initialize_uia_in_main_thread() first in main thread.")
    
    return _UIA_DESKTOP


def check_uia_alive():
    """
    检测 UIA 是否存活（只检测，不允许重建）
    
    异常:
        如果 UIA 死亡，抛出 RuntimeError
    """
    global _UIA_DESKTOP, _UIA_INITIALIZED
    
    # 检查线程信息
    current_thread = threading.current_thread()
    print(f"[UIA CHECK] Current thread: {current_thread.name}")
    print(f"[UIA CHECK] Is main thread: {current_thread is threading.main_thread()}")
    
    if not _UIA_INITIALIZED or _UIA_DESKTOP is None:
        raise RuntimeError("UIA not initialized")
    
    try:
        wins = _UIA_DESKTOP.windows()
        win_count = len(wins)
        print(f"[UIA CHECK] windows = {win_count}")
        
        if win_count == 0:
            raise RuntimeError("UIA session dead: Desktop windows = 0")
        
        if win_count > 20:
            print("[UIA CHECK] UIA OK (windows > 20)")
        elif win_count > 10:
            print(f"[UIA CHECK] UIA OK (windows = {win_count})")
        else:
            print(f"[UIA CHECK WARNING] Desktop windows = {win_count} (expected > 20)")
        
        return True
        
    except Exception as e:
        error_msg = f"UIA check failed: {e}"
        print(f"[UIA CHECK ERROR] {error_msg}")
        raise RuntimeError(error_msg)


