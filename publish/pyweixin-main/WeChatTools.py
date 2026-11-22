'''
 
WeChatTools
===========
该模块中封装了Tools与Navigator两个静态类,主要用来辅助WeChatAuto实现其他自动化功能。


Tools
------
    - `is_weixin_running`: 判断微信是否在运行
    - `where_weixin`: 查找微信路径
    - `get_current_wxid`: 获取当前登录账号wxid
    - `where_wxid_folder`: 当前登录微信的wxid文件夹
    - `where_msg_folder`: 获取微信msg文件夹路径
    - `where_chatfiles_folder`: 获取微信聊天文件存放路径(文件夹)
    - `set_weixin_as_environ_path`: 将微信路径添加到用户变量
    - `cancle_pin`: 取消窗口置顶,为了保证准确性(基于微信主界面的操作,必须让微信主界面置于顶层,不然在当前界面内乱点就尴尬了),
        open_weixin需要将微信主窗口置于桌面顶层,但这可能导致打开微信内独立(比如朋友圈)窗口时,该窗口无法自动浮于微信窗口顶层,
        只是在微信主界面底部,为解决该问题,已在涉及各种类似操作的方法中调用过该方法,如果二次开发时遇到这个特性,可以使用该方法取消微信主窗口置顶
    - `move_window_to_center`: 将未全屏的窗口移动到屏幕中央
    - `...`
    - `is_scrollable`: 判断列表类型UI是否可以滚动

Navigator
----------
    - `open_weixin`: 打开微信主界面
    - `find_friend_in_SessionList`: 在会话列表中查找好友
    - `open_moments`: 打开通讯录界面
    - `open_moments`: 打开通讯录管理界面
    - `open_moments`: 打开收藏
    - `open_moments`: 打开朋友圈
    - `open_channels`: 打开视频号
    - `open_search`: 打开搜一搜
    - `open_miniprograme_pane`: 打开小程序面板
    - `open_settings`: 打开设置
    - `open_chatfiles`: 打开微信聊天文件
    - `open_dialog_window`: 打开与好友的聊天窗口
    - `open_friend_profile`:打开好友个人简介界面
    - `open_chatinfo`:  打开好友或群聊右侧的聊天信息界面
    - `open_friend_profile`: 打开好友的个人简介界面
    - `open_friend_moments`: 打开好友的朋友圈窗口
    - `open_chat_history`: 打开与好友聊天记录窗口
    - `search_miniprogram`: 搜索并打开指定小程序
    - `search_official_account`: 搜索并打开指定公众号
    - `search_channels`: 打开视频号并搜索指定内容


Examples
========
使用该模块的方法时,你可以:

    >>> from pyweixin.WeChatTools import Navigator
    >>> Navigator.open_dialog_window(name='一家人')

或者:

    >>> from pyweixin import Navigator
    >>> Navigator.open_dialog_window(friend='一家人')


Also:
=====

    pyweixin内所有方法的位置参数的支持全局设置,be like:

    ```
    from pyweixin import Navigator,GlobalConfig
    GlobalConfig.load_delay=1.5
    GlobalConfig.is_maximize=True
    GlobalConfig.close_weixin=False
    Navigator.search_channels(search_content='微信4.0')
    Navigator.search_miniprogram(name='问卷星')
    Navigator.search_official_account(name='微信')
    ```
                                                                    
'''

# ██████  ██    ██ ██     ██ ███████  ██████ ██   ██  █████  ████████ 
# ██   ██  ██  ██  ██     ██ ██      ██      ██   ██ ██   ██    ██    
# ██████    ████   ██  █  ██ █████   ██      ███████ ███████    ██    
# ██         ██    ██ ███ ██ ██      ██      ██   ██ ██   ██    ██    
# ██         ██     ███ ███  ███████  ██████ ██   ██ ██   ██    ██    
                                                                    
                                                                    
                                                                    
############################依赖环境###########################
import os
import re
import time
import winreg
import psutil
import win32api
import pyautogui
import win32gui
import win32con
import win32process
import win32com.client
from typing import Literal
from .Config import GlobalConfig
from .Errors import NetWorkNotConnectError#所有可能出现的异常
from .Errors import NoSuchFriendError
from .Errors import NotFriendError
from .Errors import NoResultsError,NotInstalledError
from pywinauto import mouse,Desktop
from pywinauto.controls.uia_controls import ListViewWrapper,ListItemWrapper,EditWrapper #TypeHint要用到
from pywinauto import WindowSpecification
from pyweixin.Uielements import (Login_window,Main_window,SideBar,Independent_window,ListItems,
Buttons,Texts,Menus,TabItems,Lists,Edits,Windows,Panes)
from pyweixin.WinSettings import SystemSettings

# 导入 sys（用于检测打包环境）
import sys

# 调试日志文件路径
_debug_log_path = None
_debug_log_initialized = False

# 在模块导入时立即初始化日志路径（确保文件一定会被创建）
def _init_debug_log_immediately():
    """在模块导入时立即初始化日志文件"""
    global _debug_log_path, _debug_log_initialized
    if _debug_log_initialized:
        return
    
    try:
        # 获取程序目录
        app_dir = None
        if hasattr(sys, 'frozen') and sys.frozen:
            # 打包环境
            app_dir = os.path.dirname(os.path.abspath(sys.executable))
        else:
            # 开发环境
            app_dir = os.getcwd()
        
        # 如果还是获取不到，使用当前目录
        if not app_dir:
            app_dir = os.getcwd()
        
        log_path = os.path.join(app_dir, 'wx_moments_debug.log')
        _debug_log_path = log_path
        
        # 立即创建文件并写入启动信息
        try:
            with open(log_path, 'a', encoding='utf-8') as f:
                f.write(f"\n{'='*60}\n")
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - 微信朋友圈调试日志模块已加载\n")
                f.write(f"日志文件路径: {log_path}\n")
                f.write(f"程序目录: {app_dir}\n")
                f.write(f"Python版本: {sys.version}\n")
                f.write(f"是否为打包环境: {hasattr(sys, 'frozen') and sys.frozen}\n")
                if hasattr(sys, 'frozen') and sys.frozen:
                    f.write(f"EXE路径: {sys.executable}\n")
                f.write(f"{'='*60}\n")
                f.flush()
            print(f"[微信调试] 日志文件已创建: {log_path}")
            print(f"[微信调试] 请在此位置查找日志文件！")
        except Exception as e:
            print(f"[微信调试错误] 创建日志文件失败: {e}")
            print(f"[微信调试错误] 尝试路径: {log_path}")
        
        _debug_log_initialized = True
    except Exception as e:
        print(f"[微信调试错误] 初始化日志系统失败: {e}")

# 立即执行初始化
_init_debug_log_immediately()

def _get_debug_log_path():
    """获取调试日志文件路径，确保文件一定会被创建"""
    global _debug_log_path, _debug_log_initialized
    
    if _debug_log_path is not None:
        return _debug_log_path
    
    # 尝试多种方法获取程序目录
    app_dir = None
    
    # 方法1: 尝试从主程序获取路径（如果主程序已导入）
    try:
        import path_utils
        app_dir = path_utils.get_app_dir()
        print(f"[微信调试] 通过 path_utils 获取目录: {app_dir}")
    except Exception as e1:
        try:
            # 方法2: 尝试从 pyqt_main_axon 获取
            import pyqt_main_axon
            app_dir = pyqt_main_axon.get_app_dir()
            print(f"[微信调试] 通过 pyqt_main_axon 获取目录: {app_dir}")
        except Exception as e2:
            # 方法3: 使用标准方法
            if hasattr(sys, 'frozen') and sys.frozen:
                # 打包环境 - exe所在目录
                app_dir = os.path.dirname(os.path.abspath(sys.executable))
                print(f"[微信调试] 通过 sys.executable 获取目录: {app_dir}")
            else:
                # 开发环境 - 当前工作目录
                app_dir = os.getcwd()
                print(f"[微信调试] 使用当前工作目录: {app_dir}")
    
    # 确保目录存在
    if app_dir and not os.path.exists(app_dir):
        try:
            os.makedirs(app_dir, exist_ok=True)
        except:
            pass
    
    # 如果还是获取不到，使用多个备选路径
    if not app_dir:
        app_dir = os.getcwd()
    
    log_path = os.path.join(app_dir, 'wx_moments_debug.log')
    _debug_log_path = log_path
    
    # 首次初始化时立即创建文件并写入启动标记
    if not _debug_log_initialized:
        try:
            # 确保文件被创建（即使为空）
            with open(log_path, 'a', encoding='utf-8') as f:
                f.write(f"\n{'='*60}\n")
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - 微信朋友圈调试日志启动\n")
                f.write(f"日志文件路径: {log_path}\n")
                f.write(f"程序目录: {app_dir}\n")
                f.write(f"{'='*60}\n")
                f.flush()
            print(f"[微信调试] 日志文件已创建: {log_path}")
            print(f"[微信调试] 请在此位置查找日志文件！")
        except Exception as e:
            print(f"[微信调试错误] 无法创建日志文件: {e}")
            print(f"[微信调试错误] 尝试路径: {log_path}")
            # 尝试备选路径
            try:
                fallback_path = os.path.join(os.getcwd(), 'wx_moments_debug.log')
                with open(fallback_path, 'a', encoding='utf-8') as f:
                    f.write(f"\n{'='*60}\n")
                    f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - 微信朋友圈调试日志启动（备选路径）\n")
                    f.write(f"日志文件路径: {fallback_path}\n")
                    f.write(f"{'='*60}\n")
                    f.flush()
                _debug_log_path = fallback_path
                print(f"[微信调试] 使用备选路径: {fallback_path}")
            except:
                pass
        
        _debug_log_initialized = True
    
    return _debug_log_path

def _debug_print(msg):
    """调试打印函数，同时输出到控制台和日志文件"""
    print(msg)  # 输出到控制台
    try:
        log_path = _get_debug_log_path()
        # 确保文件存在
        if not os.path.exists(log_path):
            # 如果文件不存在，重新初始化
            global _debug_log_path, _debug_log_initialized
            _debug_log_path = None
            _debug_log_initialized = False
            log_path = _get_debug_log_path()
        
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {msg}\n")
            f.flush()  # 立即刷新，确保内容写入
    except Exception as e:
        # 如果写入日志失败，打印错误信息
        print(f"[微信调试错误] 写入日志失败: {e}")
        print(f"[微信调试错误] 尝试的日志路径: {_debug_log_path}") 
##########################################################################################

#各种UI实例化
Login_window=Login_window()#登录界面的UI
Main_window=Main_window()#主界面UI
SideBar=SideBar()#侧边栏UI
Independent_window=Independent_window()#独立主界面UI
Buttons=Buttons()#所有Button类型UI
Texts=Texts()#所有Text类型UI
TabItems=TabItems()#所有TabIem类型UI
Lists=Lists()#所有列表类型UI
Menus=Menus()#所有Menu类型UI
Edits=Edits()#所有Edits类型UI
Windows=Windows()#所有Window类型UI
Panes=Panes()#所有Pane类型UI
ListItems=ListItems()#所有ListItem类型UI
desktop=Desktop(backend='uia')#Window桌面
pyautogui.FAILSAFE=False#防止鼠标在屏幕边缘处造成的误触


class WxWindowManage():
    '''win32gui与pywinauto结合的关于微信窗口的'''
    def __init__(self):
        self.hwnd=0
        self.possible_windows=[]
        self.window_type=1#1为主界面,0为登录界面
        self.classname_pattern=re.compile(r'Qt\d+QWindowIcon')#Qt51514QWindowIcon,QT窗口通用的classname

    def filter(self,hwnd,param):
        #EnumDesktopWindows的回调函数
        classname=win32gui.GetClassName(hwnd)
        if self.classname_pattern.match(classname):
            self.possible_windows.append(hwnd) 
    
    def find_wx_window(self):
        '''当微信在运行时,即使关闭掉窗口。win32gui也可以找到窗口句柄
        不过win32gui获取到的classname是通用的qt窗口类名
        pywinauto可以获取到真正的窗口类名mmui::,其中mm与微信移动版的package包名一致
        猜测是微信为了全平台的一致性
        
        修改：在打包环境中，desktop.window().class_name() 可能会卡住
        所以先使用 win32gui 获取窗口标题匹配，然后再验证 class_name（带超时保护）
        ''' 
        import win32gui
        win32gui.EnumDesktopWindows(0,self.filter,None)
        
        # 先使用窗口标题匹配（更安全，不会卡住）
        wechat_windows = []
        for hwnd in self.possible_windows:
            try:
                window_title = win32gui.GetWindowText(hwnd)
                if window_title == "微信" or "微信" in window_title:
                    wechat_windows.append(hwnd)
            except:
                continue
        
        # 如果标题匹配找到窗口，直接使用（避免 pywinauto 卡住）
        if wechat_windows:
            self.hwnd = wechat_windows[0]
            # 尝试验证 class_name（但不阻塞）
            try:
                import threading
                import queue
                result_queue = queue.Queue()
                def _get_class_name():
                    try:
                        class_name = desktop.window(handle=self.hwnd).class_name()
                        result_queue.put(class_name)
                    except:
                        result_queue.put(None)
                thread = threading.Thread(target=_get_class_name, daemon=True)
                thread.start()
                thread.join(timeout=1.0)  # 最多等待1秒
                if not result_queue.empty():
                    class_name = result_queue.get()
                    if class_name == 'mmui::LoginWindow':
                        self.window_type = 0
            except:
                pass  # 如果验证失败，仍然使用找到的窗口
            return self.hwnd
        
        # 如果标题匹配失败，尝试使用原来的方法（但添加超时保护）
        verified_windows = []
        for hwnd in self.possible_windows[:5]:  # 只检查前5个窗口，避免卡太久
            try:
                import threading
                import queue
                result_queue = queue.Queue()
                def _verify_window():
                    try:
                        class_name = desktop.window(handle=hwnd).class_name()
                        if 'mmui::MainWindow' in class_name or 'mmui::LoginWindow' in class_name:
                            result_queue.put((hwnd, class_name))
                    except:
                        pass
                thread = threading.Thread(target=_verify_window, daemon=True)
                thread.start()
                thread.join(timeout=2.0)  # 每个窗口最多2秒
                if not result_queue.empty():
                    verified_hwnd, class_name = result_queue.get()
                    verified_windows.append((verified_hwnd, class_name))
            except:
                continue
        
        if verified_windows:
            self.hwnd = verified_windows[0][0]
            if verified_windows[0][1] == 'mmui::LoginWindow':
                self.window_type = 0
            return self.hwnd
        
        return None

wx=WxWindowManage()


class Tools():
    '''
    一些关于PC微信的工具
    ''' 
    @staticmethod
    def is_weixin_running()->bool:
        '''
        该方法通过检测当前windows系统的进程中
        是否有Weixin.exe该项进程来判断微信是否在运行
        '''
        wmi=win32com.client.GetObject('winmgmts:')
        processes=wmi.InstancesOf('Win32_Process')
        for process in processes:
            if process.Name.lower()=='Weixin.exe'.lower():
                return True
        return False
    
    @staticmethod
    def where_weixin(copy_to_clipboard:bool=False)->str:
        '''该方法用来查找微信的路径,无论微信是否运行都可以查找到(如果没安装那就找不到)
        Args:
            copy_to_clipboard:是否将微信路径复制到剪贴板
        '''
        #执行顺序 正在运行->查询注册表
        if Tools.is_weixin_running():
            weixin_path=''
            wmi=win32com.client.GetObject('winmgmts:')
            processes=wmi.InstancesOf('Win32_Process')
            for process in processes:
                if process.Name.lower()=='Weixin.exe'.lower():
                    weixin_path=process.ExecutablePath
            if weixin_path:
                #规范化路径并检查文件是否存在
                weixin_path=os.path.abspath(weixin_path)
            if copy_to_clipboard:
                SystemSettings.copy_text_to_windowsclipboard(weixin_path)
                print("已将微信程序路径复制到剪贴板")
            return weixin_path
        else:
           
            try:
                reg_path=r"Software\Tencent\Weixin"
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path) as key:
                    Installdir=winreg.QueryValueEx(key,"InstallPath")[0]
                weixin_path=os.path.join(Installdir,'Weixin.exe')
                if copy_to_clipboard:
                    SystemSettings.copy_text_to_windowsclipboard(weixin_path)
                    print("已将微信程序路径复制到剪贴板")
                return weixin_path
            except FileNotFoundError:
                raise NotInstalledError
    
    @staticmethod
    def where_wxid_folder(open_folder:bool=False)->str:
        '''
        该方法用来获取当前登录微信的wxid文件夹
        使用时微信必须登录,否则无法获取到完整路径
        Args:
            open_folder:是否打开存放聊天文件的文件夹,默认不打开
        Returns:
            wxid_folder:wxid文件夹路径
        '''
        possible_process=[]
        weixin_process=None
        for process in psutil.process_iter(['pid', 'name','cmdline']):
            if process.info['name']=='Weixin.exe':
                possible_process.append(process)
        weixin_process=next((proc for proc in possible_process if not any('--type' in arg for arg in proc.info['cmdline'] or [])),None)
        if not weixin_process:
            return ''
        #只要微信登录了,就一定会用到本地聊天文件保存位置:xwechat_files下的wxid文件夹db_storage内的MMKV文件,这是微信用来快速读写本地的sqlite数据库
        #只需要获取到这个文件路径后,获取前两级目录即可得到wxid文件夹,这个文件夹里包含了聊天纪录数据,联系人等库,聊天文件等一系列内容
        wxid_folder=''
        for mem_map in weixin_process.memory_maps():
            if 'MMKV'  in mem_map.path:
                wxid_folder=os.path.dirname(mem_map.path).replace('db_storage','').replace('MMKV','')
                break
        if wxid_folder:
            wxid_folder=os.path.normpath(wxid_folder)
        if open_folder:
            os.startfile(wxid_folder)
        return wxid_folder

    @staticmethod
    def where_msg_folder(open_folder:bool=False)->str:
        '''
        该方法用来获取微信msg文件夹路径
        使用时微信必须登录,否则无法获取到完整路径
        Args:
            open_folder:是否打开存放聊天文件的文件夹,默认不打开
        Returns:
            msg_folder:msg文件夹路径
        '''
        msg_folder=''
        wxid_folder=Tools.where_wxid_folder(open_folder=False)
        if wxid_folder:
            msg_folder=os.path.join(wxid_folder,'msg')
        if open_folder:
            os.startfile(msg_folder)
        return msg_folder

    @staticmethod
    def where_chatfile_folder(open_folder:bool=False)->str:
        '''
        该方法用来获取微信聊天文件存放路径(文件夹)
        使用时微信必须登录,否则无法获取到路径
        Args:
            open_folder:是否打开存放聊天文件的文件夹,默认不打开
        Returns:
            chatfile_folder:聊天文件存放路径
        '''
        chatfile_folder=''
        wxid_folder=Tools.where_wxid_folder(open_folder=False)
        if wxid_folder:
            chatfile_folder=os.path.join(wxid_folder,'msg','file')
        if open_folder:
            os.startfile(chatfile_folder)
        return chatfile_folder
    
    @staticmethod
    def where_video_folder(open_folder:bool=False)->str:
        '''
        该方法用来获取微信Video文件夹路径
        使用时微信必须登录,否则无法获取到完整路径
        Args:
            open_folder:是否打开存放聊天文件的文件夹,默认不打开
        Returns:
            video_folder:video文件夹路径
        '''
        video_folder=''
        msg_folder=Tools.where_msg_folder(open_folder=False)
        if msg_folder:
            video_folder=os.path.join(msg_folder,'video')
        if open_folder:os.startfile(video_folder)
        return video_folder

    @staticmethod
    def get_current_wxid()->str:
        '''该方法用来获取当前登录账号的wxid,只有登录后才可以获取到'''
        wxid_folder=Tools.where_wxid_folder(open_folder=False)
        wxid_pattern=re.compile(r'wxid_\w+\d+')
        wxid=wxid_pattern.search(wxid_folder)
        if wxid:return wxid.group(0)
        return ''

    @staticmethod
    def cancel_pin(main_window:WindowSpecification):
        '''
        某些打开独立窗口的函数中需要调用一次该函数
        因为open_weixin方法默认将主窗口至于顶层
        '''
        win32gui.SetWindowPos(main_window.handle,win32con.HWND_NOTOPMOST,
        0, 0, 0, 0,win32con.SWP_NOMOVE|win32con.SWP_NOSIZE)

    @staticmethod
    def move_window_to_center(Window:dict=Main_window.MainWindow,Window_handle:int=0):
        '''该方法用来将已打开的界面移动到屏幕中央并返回该窗口的windowspecification实例
        Args:
            Window:pywinauto定位元素kwargs参数字典
            Window_handle:窗口句柄
        '''
        if Window_handle==0:
            handle=desktop.window(**Window).handle
        else:
            handle=Window_handle
        win32gui.ShowWindow(handle,1)
        screen_width,screen_height=win32api.GetSystemMetrics(win32con.SM_CXSCREEN),win32api.GetSystemMetrics(win32con.SM_CYSCREEN)
        window=desktop.window(handle=handle)
        window_width,window_height=window.rectangle().width(),window.rectangle().height()
        new_left=(screen_width-window_width)//2
        new_top=(screen_height-window_height)//2
        if screen_width!=window_width:
            win32gui.MoveWindow(handle, new_left, new_top, window_width, window_height, True)
            win32gui.SetWindowPos(handle,win32con.HWND_TOPMOST, 
            0, 0, 0, 0,win32con.SWP_NOMOVE|win32con.SWP_NOSIZE)
        return window

    @staticmethod
    def is_scrollable(list_control:ListViewWrapper,back:Literal['top','end']='top')->bool:
        '''
        该方法通过列表滚动首元素的变化情况来判断其是否可以竖直方向滚动
        Args:
            list_control:UIA_ListControl控件
            back:回到列表的顶部还是底部,默认顶部
        Returns:
            scrollable:是否可以竖直方向滚动
        '''
        #List内一个元素也没有必然无法滚动
        if len(list_control.children())==0:
            return False
        list_control.set_focus()
        list_control.type_keys("{HOME}")
        first_children=list_control.children()[0]
        list_control.type_keys("{PGDN}")
        scrollable=list_control.children()[0]!=first_children
        if back=='top':
            list_control.type_keys("{HOME}") 
        if back=='end':
            list_control.type_keys("{END}")
        return scrollable
    
    @staticmethod
    def is_my_bubble(main_window:WindowSpecification,listitem:ListItemWrapper,edit_area:EditWrapper)->bool:
        '''右键左侧消息区域检测最新的一条消息(bubble)是否是由本人发送'''
        rect=listitem.rectangle()
        mouse.right_click(coords=(rect.left+100,rect.mid_point().y))
        copy_menu_item=main_window.child_window(title="复制",auto_id="XMenuItem",control_type="MenuItem")        
        if copy_menu_item.exists(timeout=0.1):
            edit_rect=edit_area.rectangle()
            mouse.click(coords=(edit_rect.left+5,edit_rect.mid_point().y))
            return False
        return True
    
    @staticmethod
    def is_group_chat(main_window:WindowSpecification):
        '''通过是否有多人通话这个按钮来判断是否是当前聊天界面是否是群聊'''
        return main_window.child_window(**Buttons.GroupCallButton).exists(timeout=0.1)

    @staticmethod
    def activate_chatList(chatList:ListViewWrapper):
        '''主界面或聊天窗口右侧的消息列表激活至于底部'''
        activate_position=(chatList.rectangle().right-12,chatList.rectangle().mid_point().y)
        mouse.click(coords=activate_position)
        chatList.type_keys('{END}')
    
    @staticmethod
    def activate_chatHistoryList(chat_history_list):
        '''点击激活聊天记录列表,这样后续可以按键选中'''
        first_item=chat_history_list.children(control_type='ListItem')[0]
        rectangle=first_item.rectangle()
        mouse.click(coords=(rectangle.right-15,rectangle.mid_point().y))
    
    @staticmethod
    def get_next_item(listview:ListViewWrapper,listitem:ListItemWrapper):
        '''获取当前listview中给定的listitem的下一个,如果该listitem是最后一个则返回None'''
        items=listview.children()
        for i in range(len(items)):
            if items[i]==listitem and i<len(items)-1:
                return items[i+1]
        return None

    @staticmethod
    def get_search_result(friend:str,search_result:ListViewWrapper)->(ListItemWrapper|None):
        '''查看顶部搜索列表里有没有名为friend的listitem,只能用来查找联系人,群聊,服务号,公众号'''
        texts=[listitem.window_text() for listitem in search_result.children(control_type="ListItem")]
        listitems=search_result.children(control_type='ListItem')
        #正常好友群聊服务号公众号的class_name是mmui::SearchContentCellView
        if '最近使用' in texts or '联系人' in texts or '群聊' in texts or '服务号' in texts or '公众号' in texts:
            listitems=[listitem for listitem in listitems if listitem.class_name()=="mmui::SearchContentCellView"]
            listitems=[listitem for listitem in listitems if listitem.window_text()==friend]
            if listitems:
                return listitems[0]
        if '功能' in texts or '最近使用' in texts:#功能比如文件传输助手,微信支付的class_name是mmui::XTableCell
            listitems=search_result.children(control_type='ListItem',class_name="mmui::XTableCell")
            listitems=[listitem for listitem in listitems if listitem.window_text()==friend]
            if listitems:
                return listitems[0]
        return None
    
    @staticmethod
    def capture_alias(listitem:ListItemWrapper):
        '''用来截取聊天记录中的聊天对象昵称,左上角灰白色文本'''
        rectangle=listitem.rectangle()
        width=rectangle.right-rectangle.left
        x=rectangle.left+80
        y=rectangle.top+5
        image=pyautogui.screenshot(region=(x,y,width-270,38))
        return image

    @staticmethod
    def collapse_contact_manage(contacts_manage:WindowSpecification):
        '''用来收起通讯录管理界面中每个分区:包括"朋友权限","标签","最近群聊"
        一般而言通讯录管理界面由这几个部分组成:
            朋友权限
            标签
            最近群聊
        若任意一个被打开,那么下方的另一个就可能会被挤到最下边,直接遍历查找费时费力
        这里给出一个解决方法--逐级向上收起,这几个listitem中我们只需要关心其存在的时候
        假如这个项目被展开,那么他的下一个是listitem与该分区名称所对应的listitem的classname必定不同,
        (要注意的是这个listitem是否被点击无法通过selected或keyboard_focused等属性判断)
        那么我们就点击一下即可收起同理,对每一个listitem进行同样的步骤即可逐级收起
        注意顺序千万不可以打乱，必须按照上边固定的顺序。
        '''
        def get_next_item(listitem):
            '''获取当前listitem的下一个listitem,如果不是最后一个的话'''
            items=contacts_manage_list.children()
            for i in range(len(items)):
                if items[i]==listitem and i<len(items)-1:
                    return items[i+1]
            return None
        contacts_manage_list=contacts_manage.child_window(**Lists.ContactsManageList)
        friend_privacy_item=contacts_manage.child_window(**ListItems.FriendPrivacyListItem)
        tag_item=contacts_manage.child_window(**ListItems.TagListItem)
        recent_group_item=contacts_manage.child_window(**ListItems.RecentGroupListItem)
        contacts_manage_list.type_keys('{HOME}')
        if friend_privacy_item.exists(timeout=0.1):
            if contacts_manage_list.children()[3].class_name()!="mmui::ContactsManagerControlFolderCell":
                friend_privacy_item.click_input()
        if tag_item.exists(timeout=0.1):
            next_item=get_next_item(tag_item)
            if next_item is not None and next_item.class_name()!="mmui::ContactsManagerControlFolderCell":
                tag_item.click_input()
        if recent_group_item.exists(timeout=0.1):
            next_item=get_next_item(recent_group_item)
            if next_item is not None and next_item.class_name()!="mmui::ContactsManagerControlFolderCell":
                recent_group_item.click_input()

    @staticmethod
    def collapse_contacts(main_window,contact_list):
        '''用来收起通讯录中每个分区:包括"新的朋友","群聊","企业微信联系人","联系人"等
        一般而言微信通讯录由这几个部分组成:
            新的朋友
            群聊
            公众号
            服务号
            企业微信联系人
            我的企业
            联系人
        若任意一个被打开,那么下方的另一个就可能会被挤到最下边,直接遍历查找费时费力
        这里给出一个解决方法--逐级向上收起,这几个listitem中我们只需要关心其存在的时候
        假如这个项目被展开,那么他的下一个是listitem与该分区名称所对应的listitem的classname必定不同,
        (要注意的是这个listitem是否被点击无法通过selected或keyboard_focused等属性判断)
        那么我们就点击一下即可收起同理,对每一个listitem进行同样的步骤即可逐级收起
        注意顺序千万不可以打乱，必须按照上边固定的顺序。
        '''
        #Contacts内每个方法都依赖于此，自上而下通过下一个的位置关系逐级收起
        def get_next_item(listitem):
            '''获取当前listitem的下一个listitem,如果不是最后一个的话'''
            items=contact_list.children()
            for i in range(len(items)):
                if items[i]==listitem and i<len(items)-1:
                    return items[i+1]
            return None
        newfriend_item=main_window.child_window(control_type='ListItem',title=r'新的朋友',class_name="mmui::ContactsCellGroupView")
        group_item=main_window.child_window(control_type='ListItem',title_re=r'群聊\d+',class_name="mmui::ContactsCellGroupView")
        official_item=main_window.child_window(control_type='ListItem',title_re=r'公众号\d+',class_name="mmui::ContactsCellGroupView")
        service_item=main_window.child_window(control_type='ListItem',title_re=r'服务号\d+',class_name="mmui::ContactsCellGroupView")
        wecom_item=main_window.child_window(control_type='ListItem',title_re=r'企业微信联系人\d+',class_name="mmui::ContactsCellGroupView")
        mycom_item=main_window.child_window(control_type='ListItem',title_re=r'我的企业\d+',class_name="mmui::ContactsCellGroupView")
        contact_item=main_window.child_window(control_type='ListItem',title_re=r'联系人\d+',class_name="mmui::ContactsCellGroupView")
        contact_list.type_keys('{HOME}')
        if newfriend_item.exists(timeout=0.1):
            if contact_list.children()[2].class_name()!="mmui::ContactsCellGroupView":
                newfriend_item.click_input()
        if group_item.exists(timeout=0.1):
            next_item=get_next_item(group_item)
            if next_item is not None and next_item.class_name()!="mmui::ContactsCellGroupView":
                group_item.click_input()
        if official_item.exists(timeout=0.1):
            next_item=get_next_item(official_item)
            if next_item is not None and next_item.class_name()!="mmui::ContactsCellGroupView":
               official_item.click_input()
        if service_item.exists(timeout=0.1):
            next_item=get_next_item(service_item)
            if next_item is not None and next_item.class_name()!="mmui::ContactsCellGroupView":
                service_item.click_input()
        if wecom_item.exists(timeout=0.1):
            next_item=get_next_item(wecom_item)
            if next_item is not None and next_item.class_name()!="mmui::ContactsCellGroupView":
                wecom_item.click_input()
        if mycom_item.exists(timeout=0.1):
            next_item=get_next_item(mycom_item)
            if next_item is not None and next_item.class_name()!="mmui::ContactsCellGroupView":
                mycom_item.click_input()
        if contact_item.exists(timeout=0.1):
            next_item=get_next_item(contact_item)
            if next_item is not None and next_item.class_name()!="mmui::ContactsCellGroupView":
                contact_item.click_input()

    def match_duration(duration:str)->float:
        '''
        该函数用来将字符串类型的时间段转换为秒
        Args:
            duration:持续时间,格式为:'30s','1min','1h'
        '''
        if "s" in duration:
            try:
                duration=duration.replace('s','')
                duration=float(duration)
                return duration
            except Exception:
                return None
        elif 'min' in duration:
            try:
                duration=duration.replace('min','')
                duration=float(duration)*60
                return duration
            except Exception:
                return None
        elif 'h' in duration:
            try:
                duration=duration.replace('h','')
                duration=float(duration)*60*60
                return duration
            except Exception:
                return None
        else:
            return None

class Navigator():

    '''打开微信内一切能打开的界面'''
    _task_index = 0  # 任务计数器，用于日志追踪
    
    @staticmethod
    def bind_wechat_window():
        """
        UIA 初始化守卫机制：绑定微信窗口（只检测，不允许重建）
        
        UIAutomation 只能在主线程初始化一次，所有任务必须复用全局 UIA 对象。
        禁止任何子线程重新初始化 UIA。
        
        每个任务开始时：
        1. 检测 UIA 是否存活（只检测，不允许重建）
        2. 使用全局 UIA Desktop 对象
        3. 绑定微信窗口
        
        返回:
            tuple: (微信窗口对象, Desktop对象)
        
        异常:
            如果 UIA 未初始化、UIA 死亡或未找到微信窗口，抛出 RuntimeError
        """
        # ========== 【任务线程入口：只检测 UIA 是否存活，不允许重建】 ==========
        # UIAutomation 只能在主线程初始化一次，所有任务必须复用全局 UIA 对象
        # 禁止任何子线程重新初始化 UIA
        
        # ========== 【1】在 UIA 初始化前加入 DPI 感知和允许设置前台窗口 ==========
        import ctypes
        try:
            ctypes.windll.user32.SetProcessDPIAware()
            _debug_print("[UIA] SetProcessDPIAware OK")
        except Exception as e:
            _debug_print(f"[UIA] SetProcessDPIAware FAIL: {e}")
        
        try:
            ctypes.windll.user32.AllowSetForegroundWindow(-1)
            _debug_print("[UIA] AllowSetForegroundWindow OK")
        except Exception as e:
            _debug_print(f"[UIA] AllowSetForegroundWindow FAIL: {e}")
        
        # ========== 【2】检测当前是否在交互桌面 ==========
        import win32gui
        import win32process
        
        try:
            hwnd = win32gui.GetForegroundWindow()
            _debug_print(f"[UIA] Foreground hwnd: {hwnd}")
            
            if hwnd == 0:
                _debug_print("[UIA ERROR] Not in interactive desktop (hwnd == 0)")
                raise RuntimeError("Not in interactive desktop")
            
            # 获取窗口进程信息
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                _debug_print(f"[UIA] Foreground window PID: {pid}")
            except:
                pass
        except Exception as e:
            _debug_print(f"[UIA ERROR] Desktop check failed: {e}")
            raise RuntimeError(f"Desktop check failed: {e}")
        
        # ========== 【3】禁止任何子线程初始化 UIAutomation ==========
        import threading
        current_thread = threading.current_thread()
        is_main_thread = (current_thread.name == "MainThread" or 
                         isinstance(current_thread, threading._MainThread) or
                         current_thread is threading.main_thread())
        
        _debug_print(f"[UIA] Current thread: {current_thread.name}")
        _debug_print(f"[UIA] Is main thread: {is_main_thread}")
        
        if not is_main_thread:
            _debug_print(f"[UIA] Task running in worker thread: {current_thread.name}")
            # 允许在子线程使用 UIA，但禁止重新初始化
        
        # ========== 【4】使用全局 UIA 对象 ==========
        # ========== 【3】绑定微信也只查一次 ==========
        wx = desktop.window(title_re="微信")
        
        wx_exists = wx.exists(timeout=2)
        wx_visible = False
        wx_enabled = False
        wx_handle = None
        
        if wx_exists:
            try:
                wx_visible = wx.is_visible()
            except:
                wx_visible = False
            
            try:
                wx_enabled = wx.is_enabled()
            except:
                wx_enabled = False
            
            try:
                wx_handle = wx.handle
            except:
                wx_handle = None
        
        _debug_print(f"[WX FOUND] exists={wx_exists}")
        _debug_print(f"[WX FOUND] visible={wx_visible}")
        _debug_print(f"[WX FOUND] enabled={wx_enabled}")
        _debug_print(f"[WX FOUND] handle={wx_handle}")
        
        if not wx_exists:
            _debug_print("[WX NOT FOUND] 本次任务未找到微信窗口")
            raise RuntimeError("未找到微信UI")
        
        # 返回微信窗口对象和全局 Desktop 对象（所有任务复用同一个全局 UIA 对象）
        return wx, desktop
    
    @staticmethod
    def _find_search_box(main_window, Main_window):
        """
        查找搜索框，支持多种方法回退
        
        参数:
            main_window: 微信主窗口对象
            Main_window: Main_window UI元素配置对象
        
        返回:
            搜索框对象
        
        异常:
            如果所有方法都失败，抛出异常
        """
        # 方法1：优先使用 descendants 方法
        try:
            search_list = main_window.descendants(**Main_window.Search)
            if search_list and len(search_list) > 0:
                search = search_list[0]
                # 验证搜索框是否可用
                if hasattr(search, 'click_input'):
                    return search
        except (IndexError, AttributeError, Exception) as e:
            pass  # 如果失败，尝试下一种方法
        
        # 方法2：使用 child_window 方法（回退方案）
        try:
            search = main_window.child_window(**Main_window.Search)
            if search.exists(timeout=2):
                return search
        except Exception as e:
            pass  # 如果失败，尝试下一种方法
        
        # 方法3：使用更通用的 child_window 查找（仅使用 control_type 和 class_name）
        try:
            search_criteria = Main_window.Search
            # 只使用 control_type 和 class_name，忽略 title（可能不匹配）
            if 'control_type' in search_criteria or 'class_name' in search_criteria:
                simplified_criteria = {}
                if 'control_type' in search_criteria:
                    simplified_criteria['control_type'] = search_criteria['control_type']
                if 'class_name' in search_criteria:
                    simplified_criteria['class_name'] = search_criteria['class_name']
                if simplified_criteria:
                    search = main_window.child_window(**simplified_criteria)
                    if search.exists(timeout=2):
                        return search
        except Exception as e:
            pass
        
        # 所有方法都失败，抛出异常
        raise Exception("无法找到微信主界面的搜索框，可能窗口未完全加载或讲述人模式未启用")
    
    @staticmethod 
    def open_weixin(is_maximize:bool=None,window_size:tuple=None)->WindowSpecification:
        '''打开微信,不登录情况效果不是很好,建议登录'''
        def log_in(wx_window):
            '''登录逻辑'''
            login_window=move_window_to_center(wx_window,is_maximize=is_maximize)
            login_button=login_window.child_window(**Login_window.LoginButton)
            login_button.click_input()
            #等待进入主界面
            window_type=wx.window_type
            while window_type!=1:
                handle=wx.find_wx_window()
                window_type=wx.window_type
                time.sleep(0.01)
            handle=wx.find_wx_window()
            main_window=desktop.window(handle=handle)
            main_window.restore()
            main_window=move_window_to_center(main_window,is_maximize=is_maximize)
            return main_window
        
        def move_window_to_center(window:WindowSpecification,is_maximize:bool):
            #将微信主界面移动到窗口正中间,并调整全屏
            window.restore()
            win32gui.SetWindowPos(window.handle,win32con.HWND_TOPMOST, 
            0, 0,window_size[0],window_size[1],win32con.SWP_NOMOVE)
            window_width,window_height=window_size[0],window_size[1]
            screen_width,screen_height=win32api.GetSystemMetrics(win32con.SM_CXSCREEN),win32api.GetSystemMetrics(win32con.SM_CYSCREEN)
            new_left=(screen_width-window_width)//2
            new_top=(screen_height-window_height)//2
            if screen_width!=window_width:
                #移动窗口到屏幕中央
                win32gui.MoveWindow(window.handle,new_left,new_top,window_width,window_height,True)
            ###############################
            if is_maximize:
                win32gui.SendMessage(window.handle, win32con.WM_SYSCOMMAND, win32con.SC_MAXIMIZE,0)
            if not is_maximize:
                win32gui.SendMessage(window.handle, win32con.WM_SYSCOMMAND, win32con.SC_RESTORE,0)
            return window
        if is_maximize is None:
            is_maximize=GlobalConfig.is_maximize
        if window_size is None:
            window_size=GlobalConfig.window_size

        wx=WxWindowManage()
        is_running=Tools.is_weixin_running()
        if not is_running:#微信不在运行,主界面看不到窗口，需要先启动
            weixin_path=Tools.where_weixin(copy_to_clipboard=False)
            os.startfile(weixin_path)
        handle=wx.find_wx_window()
        max_attempts = 30  # 最多尝试30次，每次0.1秒，总共3秒
        attempt = 0
        while not handle and attempt < max_attempts:
            handle=wx.find_wx_window()
            time.sleep(0.1)
            attempt += 1
        if not handle:
            raise Exception(f"无法找到微信窗口（尝试了{max_attempts}次）")
        
        # 使用超时保护获取窗口对象（在打包环境中可能卡住）
        import threading
        import queue
        window_result_queue = queue.Queue()
        window_exception_queue = queue.Queue()
        def _get_window():
            try:
                wx_window = desktop.window(handle=handle)
                window_result_queue.put(wx_window)
            except Exception as e:
                window_exception_queue.put(e)
        window_thread = threading.Thread(target=_get_window, daemon=True)
        window_thread.start()
        window_thread.join(timeout=5.0)  # 最多等待5秒
        
        if window_thread.is_alive():
            raise Exception("获取微信窗口对象超时（5秒），可能卡在 pywinauto 的 window() 调用")
        if not window_exception_queue.empty():
            raise window_exception_queue.get()
        if window_result_queue.empty():
            raise Exception("获取微信窗口对象失败：未返回结果")
        
        wx_window = window_result_queue.get()
        #只有在窗口激活的时候
        if wx.window_type==0:
            main_window=log_in(wx_window)
        if wx.window_type==1:#微信在运行，主界面存在(可能被关闭或者可见)
            main_window=move_window_to_center(wx_window,is_maximize=is_maximize)
            Tools.cancel_pin(main_window)
        offline_button=main_window.child_window(**Buttons.OffLineButton)
        if offline_button.exists(timeout=0.1):
            main_window.close()
            raise NetWorkNotConnectError('当前网络不可用,无法进行UI自动化!')
        return main_window

    @staticmethod
    def find_friend_in_SessionList(friend:str,is_maximize:bool=None,search_pages:int=None)->tuple[bool,WindowSpecification]:
        '''
        该方法用于在会话列表中寻找好友(非公众号)。
        Args:
            friend:好友或群聊备注名称,需提供完整名称
            is_maximize:微信界面是否全屏,默认全屏。
            search_pages:在会话列表中查询查找好友时滚动列表的次数,默认为5
        Returns:
            (is_find,main_window):is_find:是否在会话列表中找到了好友,main_window:微信主界面
        '''
        def select_in_messageList(friend):
            '''
            用来返回会话列表中automation_id为friend的ListItem项是否为最后一项
            最后一项就不点了,直接返回is_find=False顶部搜索
            '''
            is_last=False
            friend_button=None
            listItems=session_list.children(control_type='ListItem')
            for i in range(len(listItems)):
                #listitem的automation_id是固定的session_item_好友名称
                name=listItems[i].automation_id().replace('session_item_','')
                if name==friend:
                    friend_button=listItems[i]
                    break
            if i==len(listItems)-1:
                is_last=True
            return friend_button,is_last

        if is_maximize is None:
            is_maximize=GlobalConfig.is_maximize
        is_find=False
        main_window=Navigator.open_weixin(is_maximize=is_maximize)
        #先看看当前微信右侧界面是不是聊天界面可能存在不是聊天界面的情况比如是纯白色的微信的icon
        chats_button=main_window.child_window(**SideBar.Chats)
        session_list=main_window.child_window(**Main_window.ConversationList)
        if not session_list.exists():
            chats_button.click_input()
        if not session_list.is_visible():
            chats_button.click_input()
        current_chat=main_window.child_window(**Texts.CurrentChatText)
        if current_chat.exists(timeout=0.1) and current_chat.window_text()==friend:
        #如果当前主界面聊天界面顶部的名称为好友名称，is_find为True,直接返回此时主界面
            is_find=True
            return is_find,main_window
        else:
            # 不再访问会话列表，直接返回False，让调用者使用搜索框（避免崩溃）
            return False,main_window
    
    # @staticmethod
    # def open_wx_tray()->WindowSpecification|None:
    #     '''
    #     该方法用于打开微信托盘
    #     '''
    #     def hardware_mouse_move(x,y):
    #         """使用硬件级鼠标移动"""
    #         #直接设置光标位置
    #         ctypes.windll.user32.SetCursorPos(x, y)
    #         for _ in range(3):
    #             ctypes.windll.user32.mouse_event(0x0001, 1, 0, 0, 0)
    #             time.sleep(0.05)
    #     wechat_tray=None
    #     shell_tray=desktop.window(class_name="Shell_TrayWnd",title="任务栏")
    #     wx_button=shell_tray.child_window(title_re="",auto_id="NotifyItemIcon",control_type="Button")
    #     if not wx_button.exists(timeout=1):
    #         raise NoTrayFindError
    #     center_x,center_y=wx_button.children()[0].rectangle().mid_point()
    #     hardware_mouse_move(center_x,center_y)
    #     wechat_tray=desktop.window(class_name='mmui::UnreadMessageHoverWindow')
    #     return wechat_tray

    @staticmethod
    def open_collections(is_maximize:bool=None)->WindowSpecification:
        '''
        该方法用于打开收藏界面
        Args:
            is_maximize:微信界面是否全屏,默认不全屏。
        '''
        if is_maximize is None:
            is_maximize=GlobalConfig.is_maximize
        main_window=Navigator.open_weixin(is_maximize=is_maximize)
        collections_button=main_window.child_window(**SideBar.Collections)
        collections_button.click_input()
        return main_window
    
    @staticmethod
    def open_chatinfo(friend:str,is_maximize:bool=None,search_pages:int=None)->tuple[WindowSpecification]:
        '''
        该函数用来打开好友或群聊的聊天信息界面,即在聊天界面中点击···后右侧弹出的界面
        Args:
            friend:好友或群聊名称
            is_maximize:微信界面是否全屏,默认不全屏
        Returns:
            (chatinfo_pane,main_window):聊天信息界面,主界面
        '''
        if is_maximize is None:
            is_maximize=GlobalConfig.is_maximize
        if search_pages is None:
            search_pages=GlobalConfig.search_pages
        main_window=Navigator.open_dialog_window(friend=friend,is_maximize=is_maximize,search_pages=search_pages)
        chatinfo_button=main_window.child_window(**Buttons.ChatInfoButton)
        friend_chatinfo_pane=main_window.child_window(auto_id="single_chat_info_view",control_type='Group',class_name='mmui::XView')
        group_chatinfo_pane=main_window.child_window(class_name="mmui::ChatRoomMemberInfoView",control_type='Group')
        if not chatinfo_button.exists(timeout=0.1):
            main_window.close()
            raise NotFriendError(f'非正常好友或群聊！无法打开该好友或群聊的聊天信息界面')
        else: 
            if not friend_chatinfo_pane.exists(timeout=0.1) and not group_chatinfo_pane.exists(timeout=0.1): 
                chatinfo_button.click_input()
            if friend_chatinfo_pane.exists(timeout=0.1) and not group_chatinfo_pane.exists(timeout=0.1):
                return friend_chatinfo_pane,main_window
            if group_chatinfo_pane.exists(timeout=0.1) and not friend_chatinfo_pane.exists(timeout=0.1):
                return group_chatinfo_pane,main_window

    @staticmethod 
    def open_friend_profile(friend:str,is_maximize:bool=None,search_pages:int=None)->tuple[WindowSpecification,WindowSpecification]:
        '''
        该函数用来打开好友的个人简介界面
        Args:
            friend:好友名称。
            is_maximize:微信界面是否全屏,默认不全屏。
        '''
        
        if is_maximize is None:
            is_maximize=GlobalConfig.is_maximize
        if search_pages is None:
            search_pages=GlobalConfig.search_pages
        chatinfo_pane,main_window=Navigator.open_chatinfo(friend=friend,is_maximize=is_maximize,search_pages=search_pages)
        friend_button=chatinfo_pane.child_window(title=friend,control_type='Button')
        if friend_button.exists(timeout=0.2):
            time.sleep(1)
            profile_button=friend_button.children(title='',control_type='Button')[0]
            profile_button.click_input()
            time.sleep(1.5)  # 增加等待时间，确保资料页完全打开
            profile_pane=desktop.window(**Windows.PopUpProfileWindow)
            # 等待资料页完全加载
            time.sleep(0.5)
            return profile_pane,main_window
        else:
            chatinfo_button=main_window.child_window(**Buttons.ChatInfoButton)
            chatinfo_button.click_input()
            main_window.close()
            raise NotFriendError(f'此为群聊,非好友,无法打开个人简介界面!')
        
    @staticmethod
    def open_friend_moments(friend:str,search_pages:int=None,is_maximize:bool=None,close_weixin:bool=None)->WindowSpecification:
        '''
        该函数用来打开好友朋友圈
        Args:
            friend:好友名称。
            is_maximize:微信界面是否全屏,默认不全屏。
        '''
        # ========== 【任务开始日志】 ==========
        Navigator._task_index += 1
        task_index = Navigator._task_index
        _debug_print(f"######## TASK START ########")
        _debug_print(f"Task Index: {task_index}")
        _debug_print(f"############################")
        
        if is_maximize is None:
            is_maximize=GlobalConfig.is_maximize
        if close_weixin is None:
            close_weixin=GlobalConfig.close_weixin
        if search_pages is None:
            search_pages=GlobalConfig.search_pages
        
        # ========== 【1】任务线程入口：只检测 UIA 是否存活，不允许重建 ==========
        # 使用 bind_wechat_window() 函数，复用全局 UIA 对象
        # 如果绑定失败会抛出异常并终止任务
        wx, desktop_new = Navigator.bind_wechat_window()
        
        # 如果绑定成功，确保窗口在前台
        try:
            wx.set_focus()
            wx.set_foreground()
            _debug_print("WX focused")
        except Exception as e:
            _debug_print(f"WX focus failed: {e}")
        
        # 使用全局 UIA Desktop 对象（在主线程初始化，所有任务复用）
        
        profile_pane,main_window=Navigator.open_friend_profile(friend=friend,is_maximize=is_maximize,search_pages=search_pages)
        # 等待资料页完全加载
        time.sleep(1.5)  # 增加等待时间，确保资料页完全加载
        
        # ========== 【2】进入联系人主页后，对"朋友圈"按钮做完整状态检测 ==========
        _debug_print("==== Moments Debug ====")
        # 重新获取 profile_pane（不缓存，使用新的 desktop）
        try:
            profile_pane_new = desktop_new.window(**Windows.PopUpProfileWindow)
            if not profile_pane_new.exists(timeout=2):
                # 如果新获取失败，使用原来的
                profile_pane_new = profile_pane
        except:
            # 如果获取失败，使用原来的
            profile_pane_new = profile_pane
        
        # ========== 【唯一筛选模式】找到所有匹配"朋友圈"的元素，然后筛选 ==========
        _debug_print("[Moments] 开始查找所有匹配'朋友圈'的元素...")
        
        # 查找所有包含"朋友圈"文本的元素（不限制类型）
        all_elements = []
        try:
            # 查找所有 descendants（包括子元素和后代元素）
            descendants = profile_pane_new.descendants()
            for elem in descendants:
                try:
                    elem_text = elem.window_text()
                    if '朋友圈' in elem_text:
                        all_elements.append(elem)
                except:
                    try:
                        # 尝试通过 element_info.name 获取
                        if hasattr(elem, 'element_info') and hasattr(elem.element_info, 'name'):
                            if '朋友圈' in elem.element_info.name:
                                all_elements.append(elem)
                    except:
                        pass
        except Exception as e:
            _debug_print(f"[Moments] 查找 descendants 失败: {e}")
        
        _debug_print(f"[Moments] found elements = {len(all_elements)}")
        
        # ========== 【筛选逻辑】只允许点击 Button 类型，禁止 Static/Text ==========
        # 删除所有 exists() 判断（Wrapper 没有 exists 方法）
        # 只通过 control_type 筛选 Button
        buttons = []
        text_elements = []  # 保存文字元素，用于坐标备用点击
        
        for i, e in enumerate(all_elements):
            try:
                # 获取 control_type
                control_type = None
                try:
                    control_type = e.element_info.control_type
                except:
                    try:
                        # 尝试通过其他方式获取
                        if hasattr(e, 'element_info'):
                            control_type = e.element_info.control_type
                    except:
                        pass
                
                # 只接受 Button 类型
                if control_type == "Button":
                    # 检查 rectangle 是否有效
                    try:
                        rect = e.rectangle()
                        if rect.width() > 0 and rect.height() > 0:
                            buttons.append(e)
                            _debug_print(f"[Moments] element {i}: Button (pos=({rect.left},{rect.top}), size=({rect.width()},{rect.height()}))")
                    except Exception as ex:
                        _debug_print(f"[Moments] element {i}: Button but invalid rectangle: {ex}")
                else:
                    # 保存非Button元素（可能是Text/Static），用于坐标备用点击
                    try:
                        rect = e.rectangle()
                        if rect.width() > 0 and rect.height() > 0:
                            text_elements.append(e)
                            _debug_print(f"[Moments] element {i}: {control_type} (pos=({rect.left},{rect.top}), size=({rect.width()},{rect.height()})) - 保存用于坐标备用")
                    except:
                        pass
            except Exception as ex:
                _debug_print(f"[Moments] element {i}: check failed: {ex}")
                continue
        
        _debug_print(f"[Moments] button count = {len(buttons)}")
        _debug_print(f"[Moments] text elements (for fallback) = {len(text_elements)}")
        
        # ========== 【优先点击 Button】如果 Button 存在，优先点击 Button ==========
        click_success = False
        clicked_method = None
        
        if len(buttons) > 0:
            # 选择第一个 Button（通常只有一个）
            target_button = buttons[0]
            try:
                r = target_button.rectangle()
                _debug_print(f"[Moments] 选择 Button (pos=({r.left},{r.top}), size=({r.width()},{r.height()}))")
            except:
                pass
            
            # 方式1: click_input()
            try:
                target_button.click_input()
                time.sleep(0.5)
                # 检查是否成功打开朋友圈窗口
                moments_window_check = None
                try:
                    moments_window_check = Tools.move_window_to_center(Window=Windows.MomentsWindow)
                    if moments_window_check and moments_window_check.class_name() == 'mmui::SNSWindow':
                        click_success = True
                        clicked_method = "Button (click_input)"
                        _debug_print("[Moments] clicked = Button (click_input)")
                    else:
                        _debug_print("[Moments] Button click_input failed (window not opened)")
                except:
                    _debug_print("[Moments] Button click_input failed (exception)")
            except Exception as e:
                _debug_print(f"[Moments] Button click_input failed: {e}")
            
            # 方式2: invoke()
            if not click_success:
                try:
                    target_button.invoke()
                    time.sleep(0.5)
                    moments_window_check = None
                    try:
                        moments_window_check = Tools.move_window_to_center(Window=Windows.MomentsWindow)
                        if moments_window_check and moments_window_check.class_name() == 'mmui::SNSWindow':
                            click_success = True
                            clicked_method = "Button (invoke)"
                            _debug_print("[Moments] clicked = Button (invoke)")
                        else:
                            _debug_print("[Moments] Button invoke failed (window not opened)")
                    except:
                        _debug_print("[Moments] Button invoke failed (exception)")
                except Exception as e:
                    _debug_print(f"[Moments] Button invoke failed: {e}")
            
            # 方式3: click()
            if not click_success:
                try:
                    target_button.click()
                    time.sleep(0.5)
                    moments_window_check = None
                    try:
                        moments_window_check = Tools.move_window_to_center(Window=Windows.MomentsWindow)
                        if moments_window_check and moments_window_check.class_name() == 'mmui::SNSWindow':
                            click_success = True
                            clicked_method = "Button (click)"
                            _debug_print("[Moments] clicked = Button (click)")
                        else:
                            _debug_print("[Moments] Button click failed (window not opened)")
                    except:
                        _debug_print("[Moments] Button click failed (exception)")
                except Exception as e:
                    _debug_print(f"[Moments] Button click failed: {e}")
        
        # ========== 【坐标备用点击】如果 Button 不存在或点击失败，使用坐标点击 ==========
        if not click_success:
            _debug_print("[Moments] Button 不存在或点击失败，尝试坐标备用点击...")
            
            # 优先使用文字元素的右侧偏移坐标
            if len(text_elements) > 0:
                try:
                    # 选择第一个文字元素（通常是"朋友圈"文字）
                    text_elem = text_elements[0]
                    rect = text_elem.rectangle()
                    
                    # 计算右侧偏移坐标（右偏移约1.5~2cm，约40像素）
                    click_x = rect.right + 40
                    click_y = rect.top + (rect.bottom - rect.top) // 2
                    
                    _debug_print(f"[Moments] Fallback click right-offset of Moments label: ({click_x}, {click_y})")
                    _debug_print(f"[Moments] Text element rect: left={rect.left}, right={rect.right}, top={rect.top}, bottom={rect.bottom}")
                    
                    # 使用绝对坐标点击（mouse已在文件顶部导入）
                    mouse.click(coords=(click_x, click_y))
                    time.sleep(0.8)  # 等待朋友圈窗口打开
                    
                    # 检查是否打开了朋友圈窗口
                    moments_window_check = Tools.move_window_to_center(Window=Windows.MomentsWindow)
                    if moments_window_check and moments_window_check.class_name() == 'mmui::SNSWindow':
                        click_success = True
                        clicked_method = "Offset"
                        _debug_print("[Moments] clicked = Offset")
                    else:
                        _debug_print("[Moments] Offset click failed (window not opened)")
                except Exception as e:
                    _debug_print(f"[Moments] Offset click failed: {e}")
            
            # 如果文字元素坐标点击也失败，尝试使用所有元素的中心点
            if not click_success and len(all_elements) > 0:
                try:
                    first_elem = all_elements[0]
                    rect = first_elem.rectangle()
                    center_x = rect.left + (rect.right - rect.left) // 2
                    center_y = rect.top + (rect.bottom - rect.top) // 2
                    _debug_print(f"[Moments] Fallback click center: ({center_x}, {center_y})")
                    mouse.click(coords=(center_x, center_y))
                    time.sleep(0.8)
                    moments_window_check = Tools.move_window_to_center(Window=Windows.MomentsWindow)
                    if moments_window_check and moments_window_check.class_name() == 'mmui::SNSWindow':
                        click_success = True
                        clicked_method = "Center"
                        _debug_print("[Moments] clicked = Center")
                except Exception as e:
                    _debug_print(f"[Moments] Center click failed: {e}")
        
        if not click_success:
            # 添加详细的调试信息
            _debug_print(f"[Moments] ERROR: 所有点击方式都失败")
            _debug_print(f"[Moments] 找到的元素总数: {len(all_elements)}")
            _debug_print(f"[Moments] Button 数量: {len(buttons)}")
            _debug_print(f"[Moments] Text 元素数量: {len(text_elements)}")
            
            # 列出所有找到的元素信息
            debug_info = []
            debug_info.append(f"找到 {len(all_elements)} 个匹配'朋友圈'的元素")
            debug_info.append(f"其中 {len(buttons)} 个 Button，{len(text_elements)} 个 Text/Static")
            
            for i, e in enumerate(buttons):
                try:
                    r = e.rectangle()
                    debug_info.append(f"Button {i}: pos=({r.left},{r.top}), size=({r.width()},{r.height()})")
                except:
                    debug_info.append(f"Button {i}: 无法获取 rectangle")
            
            for i, e in enumerate(text_elements):
                try:
                    r = e.rectangle()
                    debug_info.append(f"Text/Static {i}: pos=({r.left},{r.top}), size=({r.width()},{r.height()})")
                except:
                    debug_info.append(f"Text/Static {i}: 无法获取 rectangle")
            
            debug_msg = f"无法点击'{friend}'的资料页中的朋友圈按钮。\n" + "\n".join(debug_info)
            _debug_print(debug_msg)
            raise Exception(debug_msg)
        time.sleep(1)  # 等待朋友圈窗口打开
        # 尝试查找朋友圈窗口，最多等待5秒
        # desktop已在文件顶部定义，直接使用
        moments_window=None
        for i in range(10):  # 最多尝试10次，每次0.5秒
            try:
                moments_window=Tools.move_window_to_center(Window=Windows.MomentsWindow)
                # 验证窗口类名是否正确
                if moments_window.class_name()=='mmui::SNSWindow':
                    break
                else:
                    moments_window=None
            except:
                pass
            time.sleep(0.5)
        if moments_window is None or moments_window.class_name()!='mmui::SNSWindow':
            raise Exception(f"无法打开'{friend}'的朋友圈窗口，可能窗口未正确打开")
        if close_weixin:
            main_window.close()
        return moments_window
       

    @staticmethod
    def open_moments(is_maximize:bool=None,close_weixin:bool=None)->WindowSpecification:
        '''
        该方法用于打开微信朋友圈
        Args:
            is_maximize:微信界面是否全屏,默认不全屏。
            close_weixin:任务结束后是否关闭微信,默认关闭。
        '''
        if is_maximize is None:
            is_maximize=GlobalConfig.is_maximize
        if close_weixin is None:
            close_weixin=GlobalConfig.close_weixin
        main_window=Navigator.open_weixin(is_maximize=is_maximize)
        toolbar=main_window.child_window(**Main_window.Toolbar)
        moments_button=toolbar.child_window(**SideBar.Moments)
        moments_button.click_input()
        moments_window=Tools.move_window_to_center(Independent_window.MomentsWindow)
        if close_weixin:
            main_window.close()
        return moments_window
    
    @staticmethod
    def open_channels(is_maximize:bool=None,window_maximize:bool=None,close_weixin:bool=None)->WindowSpecification:
        '''
        该方法用于打开微信视频号
        Args:
            is_maximize:微信界面是否全屏,默认不全屏。
            window_maximize:打开的视频号窗口是否全屏。
            close_weixin:任务结束后是否关闭微信,默认关闭。
        '''
        if is_maximize is None:
            is_maximize=GlobalConfig.is_maximize
        if window_maximize is None:
            window_maximize=GlobalConfig.window_maximize
        if close_weixin is None:
            close_weixin=GlobalConfig.close_weixin
        main_window=Navigator.open_weixin(is_maximize=is_maximize)
        channels_button=main_window.child_window(**SideBar.Channels)
        channels_button.click_input()
        channels_window=Tools.move_window_to_center(Independent_window.ChannelsWindow)
        if window_maximize:
            channels_window.maximize()
        if close_weixin:
            main_window.close()
        return channels_window
    
    @staticmethod
    def open_search(is_maximize:bool=None,window_maximize:bool=None,close_weixin:bool=None)->WindowSpecification:
        '''
        该方法用于打开微信搜一搜
        Args:
            is_maximize:微信界面是否全屏,默认不全屏。
            window_maximize:打开的搜一搜窗口是否全屏,默认不全屏。
            close_weixin:任务结束后是否关闭微信,默认关闭
        '''
        if is_maximize is None:
            is_maximize=GlobalConfig.is_maximize
        if window_maximize is None:
            window_maximize=GlobalConfig.window_maximize
        if close_weixin is None:
            close_weixin=GlobalConfig.close_weixin
        main_window=Navigator.open_weixin(is_maximize=is_maximize)
        search_button=main_window.child_window(**SideBar.Search)
        search_button.click_input()
        search_window=Tools.move_window_to_center(Independent_window.SearchWindow)
        if window_maximize:
            search_window.maximize()
        if close_weixin:
            main_window.close()
        return search_window

    @staticmethod
    def open_miniprogram_pane(is_maximize:bool=None,window_maximize:bool=None,close_weixin:bool=None)->WindowSpecification:
        '''
        该方法用来打开小程序面板
        Args:
            is_maximize:微信界面是否全屏,默认不全屏。
            window_maximize:打开的小程序面板窗口是否全屏,默认不全屏。
            close_weixin:任务结束后是否关闭微信,默认关闭
        '''
        if is_maximize is None:
            is_maximize=GlobalConfig.is_maximize
        if window_maximize is None:
            window_maximize=GlobalConfig.window_maximize
        if close_weixin is None:
            close_weixin=GlobalConfig.close_weixin
        main_window=Navigator.open_weixin(is_maximize=is_maximize)
        program_button=main_window.child_window(**SideBar.MiniProgram)
        program_button.click_input()
        program_window=Tools.move_window_to_center(Independent_window.MiniProgramWindow)
        if window_maximize:
            program_window.maximize()
        if close_weixin:
            main_window.close()
        return program_window

    @staticmethod
    def open_settings(is_maximize:bool=None,close_weixin:bool=None)->WindowSpecification:
        '''
        该方法用来打开微信设置界面。
        Args:
            is_maximize:微信界面是否全屏,默认不全屏。
            close_weixin:任务结束后是否关闭微信,默认关闭
        '''   
        if is_maximize is None:
            is_maximize=GlobalConfig.is_maximize
        if close_weixin is None:
            close_weixin=GlobalConfig.close_weixin
        main_window=Navigator.open_weixin(is_maximize=is_maximize)
        more=main_window.child_window(**SideBar.More)
        more.click_input()
        settings_button=main_window.child_window(**Buttons.SettingsButton)
        settings_button.click_input()
        settings_window=Tools.move_window_to_center(Independent_window.SettingWindow)        
        if close_weixin:
            main_window.close() 
        return settings_window
    
    @staticmethod
    def open_contacts(is_maximize:bool=None)->WindowSpecification:
        '''
        该方法用于打开微信通信录界面
        Args:
            is_maximize:微信界面是否全屏,默认不全屏。
        '''
        if is_maximize is None:
            is_maximize=GlobalConfig.is_maximize
        main_window=Navigator.open_weixin(is_maximize=is_maximize)
        contacts=main_window.child_window(**SideBar.Contacts)
        contacts.click_input()
        #类型是自定义的控件,必须先定位到该控件才可以继续定位通讯录列表
        #直接main_window.child_window()定位不到
        custom=main_window.descendants(control_type='Custom')
        contact_list=custom[-1].children()[1].descendants(control_type='List')[0]
        contact_list.type_keys("{HOME}")
        return contact_list,main_window

    @staticmethod
    def open_contacts_manage(is_maximize:bool=None,close_weixin:bool=None)->WindowSpecification:
        '''
        该方法用于打开微信通信录管理界面
        Args:
            is_maximize:微信界面是否全屏,默认不全屏。
        '''
        if is_maximize is None:
            is_maximize=GlobalConfig.is_maximize
        if close_weixin is None:
            close_weixin=GlobalConfig.close_weixin
        contact_list,main_window=Navigator.open_contacts(is_maximize=is_maximize)
        contact_list.children()[0].click_input()
        contact_manager=Tools.move_window_to_center(Independent_window.ContactManagerWindow)
        if close_weixin:
            main_window.close()
        return contact_manager
    
    @staticmethod
    def open_chatfiles(is_maximize:bool=None,close_weixin:bool=None)->WindowSpecification:
        '''
        该方法用来打开微信聊天文件。
        Args:
            is_maximize:微信界面是否全屏,默认不全屏。
            close_weixin:任务结束后是否关闭微信,默认关闭
        '''   
        if is_maximize is None:
            is_maximize=GlobalConfig.is_maximize
        if close_weixin is None:
            close_weixin=GlobalConfig.close_weixin
        main_window=Navigator.open_weixin(is_maximize=is_maximize)
        more=main_window.child_window(**SideBar.More)
        more.click_input()
        chatfiles_button=main_window.child_window(**Buttons.ChatFilesButton)
        chatfiles_button.click_input()
        chatfiles_window=Tools.move_window_to_center(Independent_window.ChatFilesWindow)
        if close_weixin:
            main_window.close() 
        return chatfiles_window

    @staticmethod
    def _validate_window_object(window_obj, is_maximize=None):
        """验证窗口对象，确保不是按钮对象"""
        try:
            # 检查是否是字典格式的按钮对象（pywinauto 有时会返回字典）
            if isinstance(window_obj, dict):
                if window_obj.get('control_type') == 'Button' or 'Button' in str(window_obj):
                    # 是按钮对象（字典格式），重新获取窗口
                    return Navigator.open_weixin(is_maximize=is_maximize)
            
            # 检查是否是按钮对象
            if hasattr(window_obj, 'control_type'):
                try:
                    ctrl_type = window_obj.control_type()
                    if ctrl_type == 'Button':
                        # 是按钮对象，重新获取窗口
                        return Navigator.open_weixin(is_maximize=is_maximize)
                except:
                    # control_type() 调用失败，继续检查其他属性
                    pass
            
            # 检查是否有窗口相关的方法
            if not hasattr(window_obj, 'child_window') or not hasattr(window_obj, 'descendants'):
                # 不是窗口对象，重新获取
                return Navigator.open_weixin(is_maximize=is_maximize)
            
            # 尝试调用 child_window 方法，如果失败说明不是窗口对象
            try:
                # 尝试获取一个子窗口，如果失败说明不是窗口对象
                test_child = window_obj.child_window(title='', found_index=0)
                if test_child is None:
                    return Navigator.open_weixin(is_maximize=is_maximize)
            except:
                # 调用失败，重新获取窗口
                return Navigator.open_weixin(is_maximize=is_maximize)
            
            return window_obj
        except Exception as e:
            # 验证失败，重新获取窗口
            try:
                return Navigator.open_weixin(is_maximize=is_maximize)
            except:
                # 如果重新获取失败，尝试返回原对象（但记录错误）
                import traceback
                print(f"[警告] _validate_window_object 验证失败: {e}")
                print(f"[警告] 堆栈: {traceback.format_exc()}")
                return window_obj  # 如果重新获取失败，返回原对象
    
    @staticmethod
    def open_dialog_window(friend:str,is_maximize:bool=None,search_pages:int=None)->WindowSpecification:
        '''
        该方法用于打开某个好友(非公众号)的聊天窗口
        Args:
            friend:好友或群聊备注名称,需提供完整名称
            is_maximize:微信界面是否全屏,默认不全屏。
            search_pages:在会话列表中查询查找好友时滚动列表的次数,默认为5,一次可查询5-12人,当search_pages为0时,直接从顶部搜索栏搜索好友信息打开聊天界面
        Returns:
            main_window:切换为好友聊天窗口后的main_window:微信主界面
        '''
       
        if is_maximize is None:
            is_maximize=GlobalConfig.is_maximize
        if search_pages is None:
            search_pages=GlobalConfig.search_pages

        #如果search_pages不为0,即需要在会话列表中滚动查找时，使用find_friend_in_SessionList方法找到好友,并点击打开对话框
        if search_pages:
            is_find,main_window=Navigator.find_friend_in_SessionList(friend=friend,is_maximize=is_maximize,search_pages=search_pages)
            if is_find:#is_find不为False,即说明find_friend_in_SessionList找到了聊天窗口,直接返回结果
                edit_area=main_window.child_window(**Edits.CurrentChatEdit)
                if edit_area.exists(timeout=0.1):
                    edit_area.click_input()
                # 验证返回的是窗口对象
                main_window = Navigator._validate_window_object(main_window, is_maximize)
                return main_window
            #is_find为False没有在会话列表中找到好友,直接在顶部搜索栏中搜索好友
            #先点击侧边栏的聊天按钮切回到聊天主界面
            #顶部搜索按钮搜索好友
            search = Navigator._find_search_box(main_window, Main_window)
            search.click_input()
            search.set_text(friend)
            time.sleep(1)
            search_results=main_window.child_window(**Main_window.SearchResult).wait(wait_for='ready',timeout=2)
            search_result=Tools.get_search_result(friend=friend,search_result=search_results)
            chat_button=main_window.child_window(**SideBar.Chats)
            if search_result:
                search_result.click_input()
                edit_area=main_window.child_window(**Edits.CurrentChatEdit)
                if edit_area.exists(timeout=0.1):
                    edit_area.click_input()
                # 验证返回的是窗口对象
                main_window = Navigator._validate_window_object(main_window, is_maximize)
                return main_window #同时返回搜索到的该好友的聊天窗口与主界面！若只需要其中一个需要使用元祖索引获取。
            else:#搜索结果栏中没有关于传入参数friend好友昵称或备注的搜索结果，关闭主界面,引发NosuchFriend异常
                chat_button.click_input()
                main_window.close()
                raise NoSuchFriendError
        else: #searchpages为0，不在会话列表查找，直接使用搜索栏
            #这部分代码先判断微信主界面是否可见,如果可见不需要重新打开,这在多个close_wechat为False需要进行来连续操作的方式使用时要用到
            main_window=Navigator.open_weixin(is_maximize=is_maximize)
            chat_button=main_window.child_window(**SideBar.Chats)
            #先看看当前聊天界面是不是好友的聊天界面
            current_chat=main_window.child_window(**Edits.CurrentChatEdit)
            if current_chat.exists(timeout=0.2) and current_chat.window_text()==friend:
                edit_area=main_window.child_window(**Edits.CurrentChatEdit)
                if edit_area.exists(timeout=0.1):
                    edit_area.click_input()
            #如果当前主界面聊天界面顶部的名称为好友名称，直接返回结果
                # 验证返回的是窗口对象
                main_window = Navigator._validate_window_object(main_window, is_maximize)
                return main_window
            else:#否则直接从顶部搜索栏出搜索结果
                #search_pages=0时，完全跳过会话列表检查，直接使用搜索栏
                #点击聊天按钮确保在主界面（不检查会话列表）
                chat_button.click_input()
                search = Navigator._find_search_box(main_window, Main_window)
                search.click_input()
                search.set_text(friend)
                time.sleep(1)
                search_results=main_window.child_window(title='',control_type='List')
                search_result=Tools.get_search_result(friend=friend,search_result=search_results)
                if search_result:
                    search_result.click_input()
                    edit_area=main_window.child_window(**Edits.CurrentChatEdit)
                    if edit_area.exists(timeout=0.1):
                        edit_area.click_input()
                    # 最终验证：确保返回的是窗口对象，不是按钮对象
                    main_window = Navigator._validate_window_object(main_window, is_maximize)
                    # 再次验证：尝试调用 child_window 方法，如果失败说明不是窗口对象
                    try:
                        test_child = main_window.child_window(title='', found_index=0)
                        if test_child is None:
                            # 验证失败，重新获取窗口
                            main_window = Navigator.open_weixin(is_maximize=is_maximize)
                    except Exception as e:
                        # 调用失败，重新获取窗口
                        main_window = Navigator.open_weixin(is_maximize=is_maximize)
                    return main_window
                else:#搜索结果栏中没有关于传入参数friend好友昵称或备注的搜索结果，关闭主界面,引发NosuchFriend异常
                    try:
                        chat_button.click_input()
                        if hasattr(main_window, 'close'):
                            main_window.close()
                    except:
                        pass
                    raise NoSuchFriendError
    @staticmethod
    def open_seperate_dialog_window(friend:str,is_maximize:bool=None,window_minimize:bool=False,close_weixin:bool=None)->WindowSpecification:
        '''
        该方法用于单独打开某个好友(非公众号)的聊天窗口(主要用于监听消息)
        Args:
            friend:好友或群聊备注名称,需提供完整名称
            is_maximize:微信界面是否全屏,默认不全屏
            window_minimize:独立聊天窗口是否最小化(监听消息方便),默认不最小
            search_pages:在会话列表中查询查找好友时滚动列表的次数,默认为5,一次可查询5-12人,当search_pages为0时,直接从顶部搜索栏搜索好友信息打开聊天界面
            close_weixin:打开独立窗口后关闭微信
        Returns:
            dialog_window:与好友的聊天窗口
        '''

        def get_search_result(friend:str,search_result:ListViewWrapper)->(ListItemWrapper|None):
            '''查看顶部搜索列表里有没有名为friend的listitem,只能用来查找联系人,群聊,服务号,公众号'''
            is_contact=True
            texts=[listitem.window_text() for listitem in search_result.children(control_type="ListItem")]
            listitems=search_result.children(control_type='ListItem')
            if '联系人' in texts or '群聊' in texts or '最近使用':
                listitems=[listitem for listitem in listitems if listitem.class_name()=="mmui::SearchContentCellView"]
                listitems=[listitem for listitem in listitems if listitem.window_text()==friend]
                if listitems:
                    return listitems[0],is_contact
            if  '服务号' in texts or '公众号' in texts:
                is_contact=False
                listitems=[listitem for listitem in listitems if listitem.class_name()=="mmui::SearchContentCellView"]
                listitems=[listitem for listitem in listitems if listitem.window_text()==friend]
                if listitems:
                    return listitems[0],is_contact
            if '功能' in texts:
                listitems=search_result.children(control_type='ListItem',class_name="mmui::XTableCell")
                listitems=[listitem for listitem in listitems if listitem.window_text()==friend]
                if listitems:
                    return listitems[0],is_contact
            return None,is_contact
    
        if is_maximize is None:
            is_maximize=GlobalConfig.is_maximize
        
        if close_weixin is None:
            close_weixin=GlobalConfig.close_weixin

        main_window=Navigator.open_weixin(is_maximize=is_maximize)
        chat_button=main_window.child_window(**SideBar.Chats)
        chat_button.click_input()
        session_list=main_window.child_window(**Main_window.ConversationList)
        search = Navigator._find_search_box(main_window, Main_window)
        search.click_input()
        search.set_text(friend)
        time.sleep(1)
        search_results=main_window.child_window(title='',control_type='List')
        search_result,is_contact=get_search_result(friend=friend,search_result=search_results)
        if search_result:
            search_result.click_input()
            time.sleep(1)
            # 不再访问会话列表，直接打开对话框（避免崩溃）
            # if is_contact:
            #     listItems=session_list.children(control_type='ListItem')
            #     friend_listitem=[listitem for listitem in listItems if listitem.is_selected()][0]
            #     friend_listitem.double_click_input()
            dialog_window=Tools.move_window_to_center(Window={'class_name':'mmui::ChatSingleWindow','title':f'{friend}'})
            if window_minimize:
                win32gui.SendMessage(dialog_window.handle, win32con.WM_SYSCOMMAND, win32con.SC_MINIMIZE, 0)
            if close_weixin:
                main_window.close()
            return dialog_window
        else:#搜索结果栏中没有关于传入参数friend好友昵称或备注的搜索结果，关闭主界面,引发NosuchFriend异常
            chat_button.click_input()
            main_window.close()
            raise NoSuchFriendError

    @staticmethod
    def open_chat_history(friend:str,TabItem:str=None,is_maximize:bool=None,close_weixin:bool=None)->WindowSpecification:
        '''
        该方法用于打开好友聊天记录界面
        Args:
            friend:好友备注名称,需提供完整名称
            TabItem:聊天记录界面打开的具体分区{'文件','图片与视频','链接','音乐与音频','小程序','视频号','日期'}中的任意一个
            is_maximize:微信界面是否全屏,默认不全屏
            close_weixin:任务结束后是否关闭微信,默认关闭
        '''
        if is_maximize is None:
            is_maximize=GlobalConfig.is_maximize
        if close_weixin is None:
            close_weixin=GlobalConfig.close_weixin
        main_window=Navigator.open_dialog_window(friend=friend,is_maximize=is_maximize)
        chat_history_button=main_window.child_window(**Buttons.ChatHistoryButton)
        if not chat_history_button.exists(timeout=0.1):
            main_window.close()
            raise NotFriendError(f'非正常好友或群聊！无法打开该好友或群聊的聊天记录界面')
        chat_history_button.click_input()
        chat_history_window=Tools.move_window_to_center(Independent_window.ChatHistoryWindow)
        tab_button=chat_history_window.child_window(control_type='Button',class_name="mmui::XMouseEventView")
        if tab_button.exists(timeout=0.1):
            tab_button.click_input()
        if TabItem:
            tabItems={'文件':TabItems.FileTabItem,'图片与视频':TabItems.PhotoAndVideoTabItem,'链接':TabItems.LinkTabItem,
            '音乐与音频':TabItems.MusicTabItem,'小程序':TabItems.MiniProgramTabItem,'视频号':TabItems.ChannelTabItem,'日期':TabItems.DateTabItem}
            item=tabItems.get(TabItem)
            if item:
                chat_history_window.child_window(**item).click_input()
        if close_weixin:
            main_window.close()
        return chat_history_window

    @staticmethod
    def open_add_friend_panel(is_maximize:bool=None)->WindowSpecification:
        '''
        该方法用于打开添加好友窗口
        Args:
            is_maximize:微信界面是否全屏,默认不全屏。
        '''
        if is_maximize is None:
            is_maximize=GlobalConfig.is_maximize
        main_window=Navigator.open_weixin()
        chat_button=main_window.child_window(**SideBar.Chats)
        quick_actions_button=main_window.child_window(**Buttons.QuickActionsButton)
        quick_actions_list=main_window.child_window(**Lists.QuickActionsList)
        chat_button.click_input()
        quick_actions_button.click_input()
        quick_actions_list.type_keys('{UP}'*2)
        quick_actions_list.type_keys('{ENTER}')
        addfriendWindow=Tools.move_window_to_center(Window=Independent_window.AddFriendWindow)
        return addfriendWindow,main_window

    @staticmethod
    def search_official_account(name:str,load_delay:float=None,is_maximize:bool=None,close_weixin:bool=None)->WindowSpecification:
        '''
        该方法用于搜索打开指定的微信公众号窗口
        Args:
            name:微信公众号名称
            load_delay:加载搜索公众号结果的时间,单位:s
            is_maximize:微信界面是否全屏,默认不全屏。
        '''
        if is_maximize is None:
            is_maximize=GlobalConfig.is_maximize
        if load_delay is None:
            load_delay=GlobalConfig.load_delay
        if close_weixin is None:
            close_weixin=GlobalConfig.close_weixin
        search_window=Navigator.open_search(is_maximize=is_maximize,close_weixin=close_weixin)
        official_acount_button=search_window.child_window(**Buttons.OfficialAcountButton)
        if not official_acount_button.exists(timeout=load_delay,retry_interval=0.1):
            search_window.close()
            print('网络不良,请尝试增加load_delay时长,或更换网络!')
        official_acount_button.click_input()
        search=search_window.child_window(control_type='Edit',found_index=0)
        search.click_input()
        SystemSettings.copy_text_to_windowsclipboard(name)
        pyautogui.hotkey('ctrl','v')
        pyautogui.press('enter')
        search_result=search_window.child_window(control_type="Button",found_index=0,framework_id="Chrome",title_re=name)
        if search_result.exists(timeout=load_delay,retry_interval=0.1):
            search_result.click_input()
            official_acount_window=desktop.window(**Independent_window.OfficialAccountWindow)
            search_window.close()
            return official_acount_window
        else:
            search_window.close()
            raise NoResultsError('查无此公众号!')

    @staticmethod
    def search_channels(search_content:str,load_delay:float=None,
        is_maximize:bool=None,window_maximize:bool=None,close_weixin:bool=None)->WindowSpecification:
        '''
        该方法用于打开视频号并搜索指定内容
        Args:
            search_content:在视频号内待搜索内容
            load_delay:加载查询结果的时间,单位:s
            is_maximize:微信界面是否全屏,默认不全屏。
            window_maximize:打开的视频号窗口是否全屏
        '''
        if load_delay is None:
            load_delay=GlobalConfig.load_delay
        if is_maximize is None:
            is_maximize=GlobalConfig.is_maximize
        if window_maximize is None:
            window_maximize=GlobalConfig.window_maximize
        if close_weixin is None:
            close_weixin=GlobalConfig.close_weixin
        SystemSettings.copy_text_to_windowsclipboard(search_content)
        channel_widow=Navigator.open_channels(is_maximize=is_maximize,close_weixin=close_weixin,window_maximize=window_maximize)
        search_bar=channel_widow.child_window(control_type='Edit',title='搜索',framework_id='Chrome')
        if search_bar.exists(timeout=load_delay,retry_interval=0.1):
            search_bar.click_input()
            pyautogui.hotkey('ctrl','v')
            pyautogui.press('enter')
            search_result=channel_widow.child_window(control_type='Document',title=f'{search_content}_搜索')
            if search_result.exists(timeout=load_delay,retry_interval=0.1):
                return channel_widow 
        else:
            channel_widow.close()
            print('网络不良,请尝试增加load_delay时长,或更换网络!')
            return None
           
   
    @staticmethod
    def search_miniprogram(name:str,load_delay:float=None,is_maximize:bool=None,
        close_weixin:bool=None,close_program_pane:bool=True)->WindowSpecification:
        '''
        该方法用于搜索并打开指定小程序
        Args:
            name:微信小程序名字,必须是全称!
            load_delay:搜索小程序名称后等待时长,默认为2秒
            is_maximize:微信界面是否全屏,默认不全屏。
            close_weixin:任务结束后是否关闭微信,默认关闭。
        '''
        if load_delay is None:
            load_delay=GlobalConfig.load_delay
        if is_maximize is None:
            is_maximize=GlobalConfig.is_maximize
        if close_weixin is None:
            close_weixin=GlobalConfig.close_weixin
        up=5
        program_window=Navigator.open_miniprogram_pane(is_maximize=is_maximize,close_weixin=close_weixin)
        miniprogram_tab=program_window.child_window(title='小程序',control_type='TabItem',found_index=0)
        miniprogram_tab.click_input()
        more=program_window.child_window(title='更多',control_type='Text',found_index=0)
        if not more.exists(timeout=load_delay,retry_interval=0.1):
            program_window.close()
            print('网络不良,请尝试增加load_delay时长,或更换网络!')
        rec=more.rectangle()
        mouse.click(coords=(rec.right+20,rec.top-50))
        search=program_window.child_window(control_type='Edit',title='搜索小程序')
        while not search.exists(timeout=0.1,retry_interval=0.1):
            mouse.click(coords=(rec.right+20,rec.top-50-up))
            search=program_window.child_window(control_type='Edit',title='搜索小程序')
            up+=5
        search.click_input()
        SystemSettings.copy_text_to_windowsclipboard(name)
        pyautogui.hotkey('ctrl','v',_pause=False)
        pyautogui.press("enter")
        search_result=program_window.child_window(control_type="Document",class_name="Chrome_RenderWidgetHostHWND")
        text=search_result.child_window(title=name,control_type='Text',found_index=0)
        if text.exists(timeout=load_delay,retry_interval=0.1):
            text.click_input()
            if close_program_pane:
                program_window.close()
            program=desktop.window(control_type='Pane',title=name)
            return program
        else:
            print('网络不良,请尝试增加load_delay时长,或更换网络!')
            program_window.close()
            return None
