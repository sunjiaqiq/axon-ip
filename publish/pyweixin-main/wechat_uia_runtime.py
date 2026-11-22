"""
微信 UIA 运行时模块

为微信自动化模块创建独立的 COM 会话，确保 UIAutomation 在整个程序生命周期中保持有效：
- CoInitialize 只执行一次（独立 COM 会话）
- Desktop(backend="uia") 只创建一次
- 禁止在每个任务里重新初始化 UIA
- 禁止释放 COM（CoUninitialize）
- 禁止销毁 Desktop 对象
"""

import pythoncom
from pywinauto import Desktop


class WeChatUIARuntime:
    """
    微信 UIA 运行时类
    
    提供独立的 COM 会话，确保微信自动化模块的 UIA 在整个程序生命周期中保持有效。
    """
    _desktop = None
    _initialized = False
    
    @classmethod
    def get_desktop(cls):
        """
        获取微信 UIA Desktop 对象（只初始化一次）
        
        返回:
            Desktop: 微信 UIA Desktop 对象
        
        注意:
            - CoInitialize 只执行一次（独立 COM 会话）
            - Desktop 只创建一次
            - 禁止释放 COM（CoUninitialize）
            - 禁止销毁 Desktop 对象
        """
        if not cls._initialized:
            pythoncom.CoInitialize()
            cls._desktop = Desktop(backend="uia")
            cls._initialized = True
            print("[WX UIA] Initialized")
        
        return cls._desktop
    
    @classmethod
    def check_alive(cls):
        """
        检查 UIA 是否 alive
        
        返回:
            bool: True 如果 UIA alive，False 如果 UIA dead
        
        异常:
            如果 UIA dead，抛出 RuntimeError
        """
        d = cls.get_desktop()
        try:
            wins = d.windows()
            win_count = len(wins)
            print(f"[WX UIA CHECK] windows={win_count}")
            
            if win_count == 0:
                raise RuntimeError("UIA Dead")
            
            return True
        except Exception as e:
            print(f"[WX UIA CHECK ERROR] {e}")
            raise RuntimeError("UIA Dead")


