"""
浏览器管理器 - 管理持久化的浏览器实例
所有操作都使用同一个浏览器，保持登录状态
"""
import logging
import asyncio
import os
from pathlib import Path
from typing import Optional
import json
import yaml

logger = logging.getLogger(__name__)

try:
    from playwright.async_api import async_playwright, Browser, BrowserContext
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    logger.warning("Playwright 未安装")
    PLAYWRIGHT_AVAILABLE = False
    Browser = None
    BrowserContext = None


class BrowserManager:
    """浏览器管理器单例"""
    _instance = None
    _playwright = None
    _browser: Optional[Browser] = None
    _context: Optional[BrowserContext] = None
    _user_data_dir: Path = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(BrowserManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self._lock = asyncio.Lock()
            # 浏览器数据目录（保存在项目目录下，与Selenium使用相同的目录）
            current_dir = Path(__file__).parent.parent
            # 使用与Selenium相同的独立user_data_dir
            self._user_data_dir = current_dir / "browser_data" / "chrome_user_data"
            self._user_data_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"[BrowserManager] 浏览器数据目录: {self._user_data_dir}")
            
            # 加载浏览器配置
            self._chrome_path = None
            self._profile_directory = None
            self._load_browser_config()
    
    def _load_browser_config(self):
        """从 config.yaml 加载浏览器配置"""
        try:
            current_dir = Path(__file__).parent.parent
            config_path = current_dir / "config.yaml"
            
            if not config_path.exists():
                # 尝试从其他位置查找
                config_path = Path.cwd() / "config.yaml"
            
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    if config and 'browser' in config:
                        browser_config = config['browser']
                        self._chrome_path = browser_config.get('chrome_path')
                        self._profile_directory = browser_config.get('profile_directory')
                        
                        if self._chrome_path:
                            logger.info(f"[BrowserManager] 从配置读取 Chrome 路径: {self._chrome_path}")
                        if self._profile_directory:
                            logger.info(f"[BrowserManager] 从配置读取配置文件: {self._profile_directory}")
            
            # 解析Chrome路径（支持相对路径）
            if self._chrome_path:
                chrome_path_obj = Path(self._chrome_path)
                # 如果是相对路径，基于项目根目录解析
                if not chrome_path_obj.is_absolute():
                    project_root = current_dir.parent
                    chrome_path_obj = project_root / self._chrome_path
                    if chrome_path_obj.exists():
                        self._chrome_path = str(chrome_path_obj)
                        logger.info(f"[BrowserManager] 解析相对路径: {self._chrome_path}")
                    else:
                        logger.warning(f"[BrowserManager] 相对路径不存在: {chrome_path_obj}，将使用系统默认路径")
                        self._chrome_path = None
            
            # 如果没有配置，使用默认值（优先相对路径）
            if not self._chrome_path:
                # 优先使用系统安装的 Chrome（更稳定），其次使用项目内的后备 chrome.exe
                system_paths = [
                    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                ]
                for p in system_paths:
                    if Path(p).exists():
                        self._chrome_path = p
                        logger.info(f"[BrowserManager] 使用系统默认Chrome: {self._chrome_path}")
                        break

                if not self._chrome_path:
                    project_root = current_dir.parent
                    default_chrome_path = project_root / "env" / "chrome" / "chrome.exe"
                    if default_chrome_path.exists():
                        self._chrome_path = str(default_chrome_path)
                        logger.info(f"[BrowserManager] 系统未安装Chrome，使用项目内Chrome: {self._chrome_path}")
                    else:
                        self._chrome_path = system_paths[0]
                        logger.warning(f"[BrowserManager] 未找到Chrome，将尝试: {self._chrome_path}")
            
            if not self._profile_directory:
                self._profile_directory = "Profile 3"
                logger.info(f"[BrowserManager] 使用默认配置文件: {self._profile_directory}")
                
        except Exception as e:
            logger.warning(f"[BrowserManager] 加载浏览器配置失败: {e}，使用默认值")
            # 尝试使用项目内的Chrome
            try:
                current_dir = Path(__file__).parent.parent
                project_root = current_dir.parent
                default_chrome_path = project_root / "env" / "chrome" / "chrome.exe"
                if default_chrome_path.exists():
                    self._chrome_path = str(default_chrome_path)
                else:
                    self._chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
            except:
                self._chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
            self._profile_directory = "Profile 3"
    
    def _get_chrome_user_data_dir(self) -> Path:
        """获取 Chrome 用户数据目录（使用与Selenium相同的独立目录）"""
        # 使用与Selenium相同的独立user_data_dir，确保使用同一个浏览器实例
        return self._user_data_dir
    
    async def initialize(self):
        """初始化浏览器（只创建一个实例）"""
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright 未安装")
        
        async with self._lock:
            # 如果浏览器已经初始化且连接正常，直接返回
            if self._browser is not None and self._browser.is_connected():
                logger.info("[BrowserManager] 浏览器已存在，复用现有实例")
                return
            
            if self._browser is not None:
                logger.warning("[BrowserManager] 检测到浏览器已断开，重新初始化...")
                try:
                    await self._context.close()
                except:
                    pass
                self._browser = None
                self._context = None
            
            if self._browser is None or not self._browser.is_connected():
                logger.info("[BrowserManager] 初始化浏览器...")
                self._playwright = await async_playwright().start()
                
                # 使用指定的 Chrome 可执行文件和配置文件
                logger.info(f"[BrowserManager] 使用指定的 Chrome: {self._chrome_path}")
                logger.info(f"[BrowserManager] 使用配置文件: {self._profile_directory}")
                
                try:
                    # 获取 Chrome 用户数据目录（使用与Selenium相同的独立目录）
                    chrome_user_data_dir = self._get_chrome_user_data_dir()
                    profile_path = chrome_user_data_dir / self._profile_directory
                    
                    logger.info(f"[BrowserManager] Chrome 用户数据目录: {chrome_user_data_dir}")
                    logger.info(f"[BrowserManager] 配置文件路径: {profile_path}")
                    
                    # 检查 Chrome 可执行文件是否存在
                    if not Path(self._chrome_path).exists():
                        logger.error(f"[BrowserManager] Chrome 可执行文件不存在: {self._chrome_path}")
                        raise FileNotFoundError(f"Chrome 可执行文件不存在: {self._chrome_path}")
                    
                    # 如果Profile不存在，尝试从系统默认位置复制（类似Selenium的方式）
                    if not profile_path.exists():
                        logger.info(f"[BrowserManager] Profile不存在，尝试从系统默认位置复制...")
                        try:
                            # 获取系统默认的Chrome用户数据目录
                            local_app_data = os.environ.get('LOCALAPPDATA')
                            if local_app_data:
                                system_user_data_dir = Path(local_app_data) / "Google" / "Chrome" / "User Data"
                                system_profile_path = system_user_data_dir / self._profile_directory
                                
                                if system_profile_path.exists():
                                    logger.info(f"[BrowserManager] 从系统位置复制Profile: {system_profile_path} -> {profile_path}")
                                    import shutil
                                    shutil.copytree(system_profile_path, profile_path, dirs_exist_ok=True)
                                    logger.info(f"[BrowserManager] Profile复制完成")
                                else:
                                    logger.warning(f"[BrowserManager] 系统Profile也不存在: {system_profile_path}，将创建新配置")
                            else:
                                logger.warning(f"[BrowserManager] 无法获取系统Chrome目录，将创建新配置")
                        except Exception as copy_error:
                            logger.warning(f"[BrowserManager] 复制Profile失败: {copy_error}，将创建新配置")
                    
                    # 首先尝试连接到已运行的 Chrome（如果启用了远程调试）
                    # 常见的调试端口：9222, 9223, 9224 等
                    connected = False
                    for port in [9222, 9223, 9224, 9225, 9226]:
                        try:
                            logger.info(f"[BrowserManager] 尝试连接到已运行的 Chrome (端口 {port})...")
                            browser = await self._playwright.chromium.connect_over_cdp(f"http://localhost:{port}")
                            contexts = browser.contexts
                            if contexts:
                                # 使用第一个可用的上下文
                                self._context = contexts[0]
                                self._browser = browser
                                logger.info(f"[BrowserManager] 成功连接到已运行的 Chrome (端口 {port})")
                                connected = True
                                break
                        except Exception as e:
                            logger.debug(f"[BrowserManager] 端口 {port} 连接失败: {e}")
                            continue
                    
                    if not connected:
                        # 如果无法连接到已运行的 Chrome，先尝试关闭已运行的 Chrome，然后启动新实例
                        logger.info("[BrowserManager] 无法连接到已运行的 Chrome，尝试关闭并重新启动...")
                        try:
                            import subprocess
                            # 尝试关闭所有 Chrome 进程
                            logger.info("[BrowserManager] 正在关闭已运行的 Chrome...")
                            subprocess.run(['taskkill', '/F', '/IM', 'chrome.exe'], 
                                         capture_output=True, timeout=5)
                            await asyncio.sleep(2)  # 等待 Chrome 完全关闭
                            logger.info("[BrowserManager] Chrome 已关闭，正在启动新实例...")
                        except Exception as e:
                            logger.warning(f"[BrowserManager] 关闭 Chrome 时出错: {e}")
                        
                        try:
                            # 使用 launch_persistent_context（必须用这个才能指定 profile）
                            # 完全拟人操作，移除所有自动化标识参数
                            self._context = await self._playwright.chromium.launch_persistent_context(
                                user_data_dir=str(chrome_user_data_dir),
                                executable_path=self._chrome_path,
                                headless=False,
                                args=[
                                    f'--profile-directory={self._profile_directory}',
                                    # 不添加任何其他参数，让浏览器完全拟人
                                ],
                                # 关键：移除所有自动化标识相关的默认参数
                                ignore_default_args=[
                                    '--enable-automation',  # 移除自动化标识
                                    '--enable-blink-features=AutomationControlled',  # 移除自动化控制标识
                                    '--no-sandbox',  # 移除 no-sandbox 参数（这是导致提示的原因！）
                                ],
                            )
                            self._browser = self._context.browser
                            logger.info(f"[BrowserManager] Chrome 启动成功（使用 Profile {self._profile_directory}，完全拟人模式）")
                        except Exception as launch_error:
                            error_msg = str(launch_error)
                            logger.error(f"[BrowserManager] Chrome 启动失败: {launch_error}")
                            raise RuntimeError(
                                f"Chrome 启动失败: {error_msg}。"
                                f"请确保 Chrome 已完全关闭，或手动使用 --remote-debugging-port=9222 启动 Chrome。"
                            )
                    
                    # 使用指定的用户数据目录和配置文件，cookies 会自动从配置文件加载
                    logger.info("[BrowserManager] 使用指定的 Chrome 配置文件，自动保持登录状态")
                    
                    # 为所有页面添加强化的反检测脚本，彻底隐藏自动化标识
                    pages = self._context.pages
                    for page in pages:
                        await page.add_init_script("""
                            // 1. 彻底隐藏 webdriver 属性
                            Object.defineProperty(navigator, 'webdriver', {
                                get: () => undefined,
                                configurable: true
                            });
                            
                            // 2. 删除 webdriver 相关属性
                            delete navigator.__proto__.webdriver;
                            delete window.navigator.webdriver;
                            
                            // 3. 添加完整的 chrome 对象
                            if (!window.chrome) {
                                window.chrome = {};
                            }
                            window.chrome.runtime = {};
                            window.chrome.loadTimes = function() {};
                            window.chrome.csi = function() {};
                            window.chrome.app = {};
                            
                            // 4. 覆盖 plugins，使其看起来像真实浏览器
                            Object.defineProperty(navigator, 'plugins', {
                                get: () => {
                                    const plugins = [];
                                    for (let i = 0; i < 5; i++) {
                                        plugins.push({
                                            name: `Plugin ${i}`,
                                            description: `Plugin ${i} Description`,
                                            filename: `plugin${i}.dll`
                                        });
                                    }
                                    return plugins;
                                },
                                configurable: true
                            });
                            
                            // 5. 覆盖 languages
                            Object.defineProperty(navigator, 'languages', {
                                get: () => ['zh-CN', 'zh', 'en-US', 'en'],
                                configurable: true
                            });
                            
                            // 6. 覆盖 permissions API
                            const originalQuery = window.navigator.permissions.query;
                            window.navigator.permissions.query = (parameters) => (
                                parameters.name === 'notifications' ?
                                    Promise.resolve({ state: Notification.permission }) :
                                    originalQuery(parameters)
                            );
                            
                            // 7. 覆盖 getBattery（如果存在）
                            if (navigator.getBattery) {
                                const originalGetBattery = navigator.getBattery;
                                navigator.getBattery = function() {
                                    return Promise.resolve({
                                        charging: true,
                                        chargingTime: 0,
                                        dischargingTime: Infinity,
                                        level: 1
                                    });
                                };
                            }
                            
                            // 8. 隐藏自动化相关的 CDP 标识
                            Object.defineProperty(navigator, 'webdriver', {
                                get: () => false
                            });
                            
                            // 9. 覆盖 userAgent（如果需要）
                            // Object.defineProperty(navigator, 'userAgent', {
                            //     get: () => 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                            //     configurable: true
                            // });
                            
                            // 10. 删除自动化相关的全局变量
                            delete window.__playwright;
                            delete window.__pw_manual;
                            delete window.__PW_inspect;
                            
                            // 11. 覆盖 document.documentElement 的 webdriver 属性
                            Object.defineProperty(document.documentElement, 'webdriver', {
                                get: () => undefined,
                                configurable: true
                            });
                        """)
                    
                    # 为所有新创建的页面也添加反检测脚本
                    async def add_stealth_to_page(page):
                        await page.add_init_script("""
                            Object.defineProperty(navigator, 'webdriver', {
                                get: () => undefined
                            });
                            delete navigator.__proto__.webdriver;
                            delete window.navigator.webdriver;
                        """)
                    
                    self._context.on("page", lambda page: asyncio.create_task(add_stealth_to_page(page)))
                    
                    logger.info("[BrowserManager] 已添加强化反检测脚本，彻底隐藏自动化标识")
                    
                    logger.info(f"[BrowserManager] 浏览器启动成功，使用配置文件: {self._profile_directory}")
                except Exception as e:
                    logger.error(f"[BrowserManager] 浏览器启动失败: {e}")
                    raise
                
                # 为所有页面添加脚本以隐藏自动化标识
                pages = self._context.pages
                for page in pages:
                    await page.add_init_script("""
                        // 隐藏webdriver属性
                        Object.defineProperty(navigator, 'webdriver', {
                            get: () => undefined
                        });
                        
                        // 添加chrome对象
                        window.chrome = {
                            runtime: {},
                            loadTimes: function() {},
                            csi: function() {},
                            app: {}
                        };
                        
                        // 覆盖plugins
                        Object.defineProperty(navigator, 'plugins', {
                            get: () => [1, 2, 3, 4, 5]
                        });
                        
                        // 覆盖languages
                        Object.defineProperty(navigator, 'languages', {
                            get: () => ['zh-CN', 'zh', 'en']
                        });
                        
                        // 覆盖permissions
                        const originalQuery = window.navigator.permissions.query;
                        window.navigator.permissions.query = (parameters) => (
                            parameters.name === 'notifications' ?
                                Promise.resolve({ state: Notification.permission }) :
                                originalQuery(parameters)
                        );
                        
                        // 删除自动化标识
                        delete navigator.__proto__.webdriver;
                    """)
                
                logger.info("[BrowserManager] 浏览器初始化完成")
                logger.info(f"[BrowserManager] 使用 Chrome 配置文件: {self._profile_directory}")
                logger.info(f"[BrowserManager] Chrome 用户数据目录: {chrome_user_data_dir}")
                logger.info("[BrowserManager] 已隐藏自动化标识，不会显示'正在受到自动测试软件的控制'")
    
    async def open_login_page(self, url: str = "https://www.douyin.com"):
        """打开登录页面"""
        await self.initialize()
        
        # 创建新页面或使用现有页面
        pages = self._context.pages
        if pages:
            page = pages[0]
        else:
            page = await self._context.new_page()
        
        logger.info(f"[BrowserManager] 打开登录页面: {url}")
        # 抖音这类站点经常长连接/持续请求，`networkidle` 可能永远等不到
        # 这里改为更稳的 `domcontentloaded`，再做少量 sleep 等 UI 渲染
        await page.goto(url, wait_until='domcontentloaded', timeout=90000)
        
        # 等待页面内容加载
        await asyncio.sleep(2)
        
        # 确保浏览器窗口显示在前台
        try:
            # 将页面带到前台
            await page.bring_to_front()
            # 等待一下确保窗口显示
            await asyncio.sleep(1)
        except Exception as e:
            logger.warning(f"[BrowserManager] 无法将窗口带到前台: {e}")
        
        # 检查页面是否成功加载
        current_url = page.url
        logger.info(f"[BrowserManager] 当前页面URL: {current_url}")
        if 'about:blank' in current_url or current_url == 'chrome://new-tab-page/':
            logger.warning(f"[BrowserManager] 页面可能未正确加载，重新导航...")
            await page.goto(url, wait_until='networkidle', timeout=60000)
        
        # 使用持久化上下文时，cookies 会自动保存，不需要定期保存
        # 但为了兼容性，仍然保留保存功能（如果需要）
        
        return page
    
    async def get_page(self) -> Optional[BrowserContext]:
        """获取浏览器上下文（用于创建新页面）"""
        await self.initialize()
        return self._context
    
    async def new_page(self):
        """创建新页面"""
        await self.initialize()
        page = await self._context.new_page()
        
        # 为新页面添加反检测脚本
        await page.add_init_script("""
            // 隐藏webdriver属性
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            
            // 添加chrome对象
            window.chrome = {
                runtime: {},
                loadTimes: function() {},
                csi: function() {},
                app: {}
            };
            
            // 覆盖plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            
            // 覆盖languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['zh-CN', 'zh', 'en']
            });
            
            // 删除自动化标识
            delete navigator.__proto__.webdriver;
        """)
        
        return page
    
    async def save_cookies(self):
        """保存当前cookies到文件"""
        if self._context:
            try:
                cookies = await self._context.cookies()
                cookies_file = self._user_data_dir / "cookies.json"
                with open(cookies_file, 'w', encoding='utf-8') as f:
                    json.dump(cookies, f, ensure_ascii=False, indent=2)
                logger.info(f"[BrowserManager] 已保存 {len(cookies)} 个cookies到 {cookies_file}")
            except Exception as e:
                logger.warning(f"[BrowserManager] 保存cookies失败: {e}")
    
    async def close(self):
        """关闭浏览器（使用持久化上下文时，cookies 会自动保存）"""
        async with self._lock:
            # 使用持久化上下文时，cookies 会自动保存到用户数据目录
            # 不需要手动保存
            
            if self._context:
                try:
                    await self._context.close()
                    logger.info("[BrowserManager] 浏览器上下文已关闭")
                except:
                    pass
                self._context = None
                self._browser = None
            
            if self._playwright:
                try:
                    await self._playwright.stop()
                    logger.info("[BrowserManager] Playwright已停止")
                except:
                    pass
                self._playwright = None
    
    def is_initialized(self) -> bool:
        """检查浏览器是否已初始化"""
        return self._browser is not None and self._browser.is_connected()
    
    async def ensure_initialized(self):
        """确保浏览器已初始化"""
        if not self.is_initialized():
            await self.initialize()


# 全局浏览器管理器实例
browser_manager = BrowserManager()

