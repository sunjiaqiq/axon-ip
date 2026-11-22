"""
抖音发布 MCP Server
基于 fastmcp 实现，提供抖音视频发布功能
使用 Selenium 方式（基于之前成功的实现）
"""
from typing import Any, Optional
import os
import logging
import subprocess
import time
import random
from pathlib import Path
from urllib.parse import urlparse
from fastmcp import FastMCP
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchElementException
try:
    from webdriver_manager.chrome import ChromeDriverManager
    WEBDRIVER_MANAGER_AVAILABLE = True
except ImportError:
    WEBDRIVER_MANAGER_AVAILABLE = False
import yaml
import threading

# 配置日志
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def human_sleep(min_seconds: float, max_seconds: float, *, reason: str = "") -> float:
    """
    用随机等待的人类化策略替代固定 sleep，降低机械化特征。
    返回实际睡眠秒数，便于日志排查。
    """
    delay = float(random.uniform(min_seconds, max_seconds))
    if reason:
        logger.info(f"[Selenium] 人类化随机等待: {delay:.2f}s ({reason})")
    time.sleep(delay)
    return delay


def _pause_tiny(*, reason: str = "") -> float:
    """极短的人类化停顿（UI 事件/滚动/动画过渡）。"""
    return human_sleep(0.35, 1.1, reason=reason)


def _pause_short(*, reason: str = "") -> float:
    """短等待（局部渲染/状态同步）。"""
    return human_sleep(1.8, 4.5, reason=reason)


def _pause_medium(*, reason: str = "") -> float:
    """中等等待（弹窗/模块加载）。"""
    return human_sleep(5.0, 13.0, reason=reason)


def _pause_after_title_click(*, reason: str = "") -> float:
    """点击「标题」后，给足时间让封面编辑模块初始化（网络慢/渲染慢时更关键）。"""
    return human_sleep(10.5, 18.5, reason=reason or "点击标题后等待封面编辑模块初始化")


def _dismiss_shepherd_if_present(driver) -> None:
    """尽量关闭新手引导遮挡层（关不了就忽略）。"""
    try:
        buttons = driver.find_elements(By.TAG_NAME, "button")
        for b in buttons:
            try:
                t = (b.text or "").strip()
                if t in ["我知道了", "知道了", "关闭", "跳过"]:
                    driver.execute_script("arguments[0].click();", b)
                    _pause_tiny(reason="关闭引导/遮挡层后缓冲")
                    return
            except Exception:
                continue
    except Exception:
        pass


def _iter_dialog_ids(max_idx: int = 8) -> list:
    """抖音弹窗 id 可能是 dialog-0 / dialog-1 / dialog-2 …，依次尝试。"""
    return [f"dialog-{i}" for i in range(max_idx + 1)]


def _find_visible_cover_dialog_id(driver, timeout: float = 22.0) -> Optional[str]:
    """
    找到当前可见、且内含封面标题 textarea 的弹窗（dialog-*）。
    轮询 dialog-0..dialog-8，直到超时。
    """
    end = time.time() + max(3.0, timeout)
    while time.time() < end:
        for did in _iter_dialog_ids():
            try:
                el = driver.find_element(By.ID, did)
                if not el.is_displayed():
                    continue
                for ta in driver.find_elements(By.XPATH, f"//*[@id='{did}']//textarea"):
                    try:
                        if ta.is_displayed():
                            logger.info(f"[Selenium] 检测到封面弹窗: #{did}（含可见 textarea）")
                            return did
                    except Exception:
                        continue
            except Exception:
                continue
        time.sleep(0.35)
    return None


def _wait_confirm_dialog_and_click_ok(driver, cover_dialog_id: str) -> bool:
    """在同一 cover_dialog_id 内点「确定」。若弹窗未及时消失，仅告警并继续后续“完成”流程。"""
    _dismiss_shepherd_if_present(driver)
    confirm_button = WebDriverWait(driver, 35).until(
        EC.element_to_be_clickable(
            (By.XPATH, f"//*[@id='{cover_dialog_id}']//button[contains(normalize-space(.), '确定')]")
        )
    )
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", confirm_button)
    _pause_tiny(reason="滚动到确定按钮后缓冲")
    confirm_button.click()
    logger.info("[Selenium] ✅ 已点击'确定'按钮")
    # 实际页面中“确定”后可能不立即消失或复用同层，不能因此中断后续“完成/暂不设置”链路
    try:
        WebDriverWait(driver, 8).until(
            EC.invisibility_of_element_located((By.ID, cover_dialog_id))
        )
        logger.info(f"[Selenium] ✅ 弹窗 #{cover_dialog_id} 已关闭")
        return True
    except TimeoutException:
        logger.warning(f"[Selenium] ⚠️ 弹窗 #{cover_dialog_id} 未在8秒内关闭，继续尝试点击“完成”")
        return False

# 初始化 FastMCP 服务器
mcp = FastMCP("douyin_publisher")

# 全局变量 - 整个系统共享的浏览器实例
# 所有打开浏览器的操作都使用这个实例，确保登录状态一致
driver = None  # Selenium WebDriver（全局单例）
_driver_lock = threading.Lock()  # 线程锁，确保多线程环境下只创建一个浏览器实例
_driver_navigation_lock = threading.Lock()  # Selenium driver 不是线程安全的，导航必须串行
_last_user_data_dir = None  # 记录上次使用的 user_data_dir，确保一致性
_last_browser_error = ""  # 返回给前端的最后一次真实启动/接管错误


def _create_chromedriver_service(
    chromedriver_path: str,
    diagnostic_log: Optional[str] = None,
) -> Service:
    """创建不弹控制台的 ChromeDriver；启动故障时可写入本地诊断日志。"""
    if diagnostic_log:
        kwargs = {
            "log_output": diagnostic_log,
            "service_args": ["--verbose", "--append-log"],
        }
    else:
        kwargs = {
            "log_output": subprocess.DEVNULL,
            "service_args": ["--log-level=OFF"],
        }
    if os.name == "nt":
        kwargs["popen_kw"] = {
            "creation_flags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        }
    return Service(chromedriver_path, **kwargs)


def _append_browser_diagnostic(log_path: Path, message: str) -> None:
    """尽最大努力保存客户机启动诊断，失败不影响自愈。"""
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8", errors="replace") as fp:
            fp.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
    except Exception:
        pass


def _resolve_browser_user_data_dir(wrapper_dir: Path) -> str:
    """浏览器数据放到当前用户 LocalAppData，避免安装目录权限和覆盖升级干扰。"""
    override = os.environ.get("AXON_BROWSER_USER_DATA_DIR")
    if override:
        return str(Path(override).expanduser().resolve())

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        base_dir = Path(local_app_data) / "IP_auto" / "browser_data"
    else:
        base_dir = wrapper_dir / "browser_data"
    base_dir = base_dir.expanduser().resolve()
    base_dir.mkdir(parents=True, exist_ok=True)

    # 若曾自动切换到恢复目录，后续重启继续使用成功的目录，不再碰旧坏配置。
    marker = base_dir / "active_chrome_user_data.txt"
    try:
        marked = Path(marker.read_text(encoding="utf-8").strip()).expanduser().resolve()
        if marked.parent == base_dir and marked.is_dir():
            return str(marked)
    except Exception:
        pass
    return str((base_dir / "chrome_user_data").resolve())


def _create_recovery_user_data_dir(failed_dir: str) -> str:
    """保留原登录数据，创建完全独立的新配置目录并记住它。"""
    failed = Path(failed_dir).expanduser().resolve()
    stamp = time.strftime("%Y%m%d_%H%M%S")
    recovery = failed.parent / f"chrome_user_data_recovery_{stamp}_{os.getpid()}"
    recovery.mkdir(parents=True, exist_ok=False)

    # 仅正式默认目录写标记；测试/运维显式覆盖目录时不污染其父目录配置。
    if not os.environ.get("AXON_BROWSER_USER_DATA_DIR"):
        try:
            (failed.parent / "active_chrome_user_data.txt").write_text(
                str(recovery), encoding="utf-8"
            )
        except Exception as exc:
            logger.warning(f"[Selenium] 记录恢复配置目录失败: {exc}")
    return str(recovery.resolve())


def _url_matches_domains(current_url: str, expected_domains) -> bool:
    """判断当前页面是否已经进入目标平台（允许登录重定向到同平台子域名）。"""
    try:
        host = (urlparse(current_url or "").hostname or "").lower().strip(".")
    except Exception:
        return False
    for domain in expected_domains or ():
        domain = str(domain or "").lower().strip().strip(".")
        if domain and (host == domain or host.endswith("." + domain)):
            return True
    return False


def _read_devtools_active_port(user_data_dir: str) -> Optional[int]:
    """读取 Chrome --remote-debugging-port=0 写入的真实随机端口。"""
    try:
        port_file = Path(user_data_dir) / "DevToolsActivePort"
        if not port_file.is_file():
            return None
        first_line = port_file.read_text(encoding="utf-8", errors="ignore").splitlines()[0].strip()
        port = int(first_line)
        return port if 0 < port < 65536 else None
    except Exception as exc:
        logger.debug(f"[Selenium] 读取 DevToolsActivePort 失败: {exc}")
        return None


def _is_local_tcp_port_open(port: int, timeout: float = 0.35) -> bool:
    """快速判断本机调试端口是否可连接，避免 ChromeDriver 对陈旧端口长时间等待。"""
    try:
        import socket

        with socket.create_connection(("127.0.0.1", int(port)), timeout=timeout):
            return True
    except (OSError, TypeError, ValueError):
        return False


def _cmdline_uses_user_data_dir(cmdline, expected_dir: str) -> bool:
    """按目录实体而非字符串比较，兼容 Windows 的 Administrator/ADMINI~1 路径差异。"""
    expected = str(Path(expected_dir).expanduser().resolve())
    for arg in cmdline or ():
        text = str(arg or "").strip()
        if not text.lower().startswith("--user-data-dir="):
            continue
        actual = text.split("=", 1)[1].strip().strip('"')
        try:
            if os.path.samefile(actual, expected):
                return True
        except Exception:
            pass
        try:
            if os.path.normcase(os.path.abspath(actual)) == os.path.normcase(os.path.abspath(expected)):
                return True
        except Exception:
            pass
    return False


def _stop_dedicated_chrome(processes, user_data_dir: str) -> None:
    """只结束使用本软件专用 user-data-dir 的 Chrome，不影响客户日常 Chrome。"""
    try:
        import psutil

        roots = list(processes or ())
        # 调用方可能因为短路径/长路径或瞬时进程枚举失败而没有收集到进程；
        # 这里再按 user-data-dir 精确扫描一次，仍然只处理本软件专用 Chrome。
        known_root_pids = {proc.pid for proc in roots}
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                name = str(proc.info.get("name") or "").lower()
                if "chrome.exe" not in name:
                    continue
                if proc.pid not in known_root_pids and _cmdline_uses_user_data_dir(
                    proc.info.get("cmdline") or (), user_data_dir
                ):
                    known_root_pids.add(proc.pid)
                    roots.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        targets = []
        seen = set()
        for proc in roots:
            try:
                for child in proc.children(recursive=True):
                    if child.pid not in seen:
                        seen.add(child.pid)
                        targets.append(child)
                if proc.pid not in seen:
                    seen.add(proc.pid)
                    targets.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        for proc in reversed(targets):
            try:
                proc.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        _, alive = psutil.wait_procs(targets, timeout=5)
        for proc in alive:
            try:
                proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        if alive:
            psutil.wait_procs(alive, timeout=3)
    except Exception as exc:
        logger.warning(f"[Selenium] 关闭专用 Chrome 时出现异常: {exc}")

    # 进程异常退出时可能残留这些锁；仅清理本软件专用目录下的运行时锁文件。
    for name in ("DevToolsActivePort", "SingletonLock", "SingletonCookie", "SingletonSocket"):
        try:
            (Path(user_data_dir) / name).unlink(missing_ok=True)
        except Exception:
            pass


def _build_chrome_options(
    chrome_path: str,
    user_data_dir: str,
    profile_directory: str,
    start_url: Optional[str] = None,
):
    """每次启动都重新构造 Options，避免失败会话污染下一次重试。"""
    options = webdriver.ChromeOptions()
    if chrome_path:
        options.binary_location = chrome_path
    for arg in (
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-extensions",
        "--disable-logging",
        "--log-level=3",
        "--no-first-run",
        "--no-default-browser-check",
        "--start-maximized",
        "--disable-notifications",
        "--window-size=1920,1080",
    ):
        options.add_argument(arg)
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument(f"--user-data-dir={user_data_dir}")
    options.add_argument(f"--profile-directory={profile_directory}")
    if start_url and str(start_url).lower().startswith(("https://", "http://")):
        options.add_argument(str(start_url))
    return options


def _launch_chrome_direct_and_attach(
    chrome_path: str,
    chromedriver_path: str,
    user_data_dir: str,
    profile_directory: str,
    start_url: Optional[str],
    diagnostic_log: Path,
):
    """最后兜底：绕开 ChromeDriver 的浏览器拉起阶段，先启动 Chrome 再通过 CDP 接管。"""
    _stop_dedicated_chrome([], user_data_dir)
    command = [
        chrome_path,
        "--remote-debugging-port=0",
        f"--user-data-dir={user_data_dir}",
        f"--profile-directory={profile_directory}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-notifications",
        "--start-maximized",
    ]
    if start_url and str(start_url).lower().startswith(("https://", "http://")):
        command.append(str(start_url))
    else:
        command.append("about:blank")

    _append_browser_diagnostic(
        diagnostic_log,
        f"启动最终兜底 Chrome: user_data_dir={user_data_dir!r}, profile={profile_directory!r}",
    )
    process = subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=(
            getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if os.name == "nt" else 0
        ),
    )

    port = None
    deadline = time.time() + 25
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Chrome 直接启动后提前退出，退出码 {process.returncode}")
        port = _read_devtools_active_port(user_data_dir)
        if port and _is_local_tcp_port_open(port, timeout=0.5):
            break
        time.sleep(0.25)
    else:
        raise RuntimeError("Chrome 直接启动后未生成可连接的调试端口")

    cdp_options = webdriver.ChromeOptions()
    cdp_options.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")
    cdp_service = _create_chromedriver_service(
        chromedriver_path, diagnostic_log=str(diagnostic_log)
    )
    attached = webdriver.Chrome(service=cdp_service, options=cdp_options)
    attached.current_url
    return attached

def _try_click_span_button_by_text(
    text: str,
    timeout_sec: int = 8,
    root_xpath: str = "//*[(@role='dialog') or contains(@class, 'semi-modal') or contains(@class, 'modal')]",
) -> bool:
    """
    在页面中查找包含指定文本的 span（semi-button-content）并点击其父 button。
    不依赖 dialog-x 的动态编号，适配 dialog-1/dialog-3 等变化。
    """
    global driver
    if not driver:
        return False

    end_at = time.time() + max(1, int(timeout_sec))
    span_xpath_candidates = [
        # 优先：弹窗内的 semi-button-content 精确匹配
        f"{root_xpath}//span[contains(@class,'semi-button-content') and normalize-space(text())='{text}']",
        # 兼容：弹窗内任意 span 文本匹配
        f"{root_xpath}//span[normalize-space(text())='{text}']",
        # 最后兜底：全局查找
        f"//span[contains(@class,'semi-button-content') and normalize-space(text())='{text}']",
        f"//span[normalize-space(text())='{text}']",
    ]

    last_err = None
    while time.time() < end_at:
        for xp in span_xpath_candidates:
            try:
                span = driver.find_element(By.XPATH, xp)
                if not span or not span.is_displayed():
                    continue
                btn = span.find_element(By.XPATH, "./ancestor::button[1]")
                if not btn:
                    continue
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                except Exception:
                    pass
                _pause_tiny(reason=f"滚动到按钮后缓冲（{text}）")
                try:
                    btn.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", btn)
                return True
            except Exception as e:
                last_err = e
                continue
        _pause_tiny(reason=f"重试点击按钮（{text}）前缓冲")

    if last_err:
        logger.debug(f"[Selenium] 点击 '{text}' 未成功（最终异常）：{last_err}")
    return False

# 从配置文件读取浏览器设置
def load_browser_config():
    """从 config.yaml 读取浏览器配置"""
    try:
        config_path = Path(__file__).parent / "config.yaml"
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                if config and 'browser' in config:
                    return {
                        'chrome_path': config['browser'].get('chrome_path'),
                        'profile_directory': config['browser'].get('profile_directory', 'Profile 3')
                    }
    except Exception as e:
        logger.warning(f"读取配置文件失败: {e}")
    
    # 默认配置：优先使用客户机已安装的 Google Chrome（须与包内 ChromeDriver 主版本一致，当前交付版为 157）
    wrapper_dir = Path(__file__).parent
    project_root = wrapper_dir.parent

    system_chrome_paths = [
        "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
        "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
    ]

    chrome_path = None
    for system_path in system_chrome_paths:
        if Path(system_path).exists():
            chrome_path = system_path
            logger.info(f"[Selenium] 使用系统 Chrome: {chrome_path}")
            break

    if not chrome_path:
        project_chrome_path = project_root / "env" / "chrome" / "chrome.exe"
        if project_chrome_path.is_file():
            chrome_path = str(project_chrome_path.resolve())
            logger.info(f"[Selenium] 系统未安装 Chrome，使用项目内 Chrome: {chrome_path}")
        else:
            chrome_path = system_chrome_paths[0]
            logger.warning(f"[Selenium] 未找到 Chrome，将尝试: {chrome_path}")
    
    return {
        'chrome_path': chrome_path,
        'profile_directory': "Profile 3"
    }

def get_chromedriver_path():
    """获取 ChromeDriver 路径，优先使用项目内的"""
    wrapper_dir = Path(__file__).parent
    project_root = wrapper_dir.parent
    
    # 优先使用项目内的 ChromeDriver
    project_chromedriver = project_root / "env" / "chromedriver" / "chromedriver.exe"
    if project_chromedriver.exists():
        logger.info(f"[Selenium] 使用项目内的 ChromeDriver: {project_chromedriver}")
        return str(project_chromedriver)
    
    # 如果项目内不存在，尝试使用 webdriver_manager（作为后备）
    if WEBDRIVER_MANAGER_AVAILABLE:
        try:
            driver_path = ChromeDriverManager().install()
            logger.info(f"[Selenium] 使用 webdriver_manager 下载的 ChromeDriver: {driver_path}")
            return driver_path
        except Exception as e:
            logger.warning(f"[Selenium] webdriver_manager 安装失败: {e}")
    
    # 最后尝试系统 PATH 中的 chromedriver
    import shutil
    system_chromedriver = shutil.which("chromedriver")
    if system_chromedriver:
        logger.info(f"[Selenium] 使用系统 PATH 中的 ChromeDriver: {system_chromedriver}")
        return system_chromedriver
    
    # 如果都找不到，返回 None，让调用者处理
    logger.error("[Selenium] 未找到 ChromeDriver，请确保 env/chromedriver/chromedriver.exe 存在")
    return None

def find_element_with_multiple_selectors(selectors_dict: dict, timeout: int = 10):
    """
    使用多种选择器尝试查找元素（Selenium方式）
    完全按照之前成功的脚本实现（douyin_publish_selenium.py）
    
    Args:
        selectors_dict: 包含不同类型选择器的字典，如 {"xpath": [...], "css": [...]}
        timeout: 超时时间（秒）
    
    Returns:
        找到的元素或None
    """
    global driver
    
    if not driver:
        return None
    
    # 首先尝试XPath选择器
    for xpath in selectors_dict.get("xpath", []):
        try:
            element = WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.XPATH, xpath))
            )
            if element and element.is_displayed():
                logger.info(f"[Selenium] 找到元素（XPath）: {xpath[:50]}...")
                return element
        except:
            pass
    
    # 然后尝试CSS选择器
    for css in selectors_dict.get("css", []):
        try:
            element = WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, css))
            )
            if element and element.is_displayed():
                logger.info(f"[Selenium] 找到元素（CSS）: {css[:50]}...")
                return element
        except:
            pass
    
    return None

def ensure_browser(start_url: Optional[str] = None):
    """
    确保浏览器已启动（Selenium方式）
    
    重要：这是整个系统唯一的浏览器实例入口
    - 所有打开浏览器的操作都调用此函数
    - 使用全局 driver 变量，确保只创建一个浏览器实例
    - 使用线程锁，确保多线程环境下线程安全
    - 浏览器数据保存在项目内的独立目录：browser_data/chrome_user_data/Profile 3
    - 登录信息会永久保存，下次打开自动登录
    """
    global driver, _last_browser_error
    _last_browser_error = ""
    
    # 使用线程锁，确保多线程环境下只创建一个浏览器实例
    with _driver_lock:
        if driver:
            try:
                # 检查浏览器是否仍然有效
                driver.current_url
                logger.info("[Selenium] ✅ 浏览器已启动（复用现有实例）")
                return True
            except:
                # 浏览器已关闭，重置
                logger.warning("[Selenium] ⚠️ 浏览器实例已失效，将重新创建")
                driver = None
        
        # 再次检查（双重检查，确保线程安全）
        if driver:
            try:
                driver.current_url
                logger.info("[Selenium] ✅ 浏览器已启动（其他线程已创建）")
                return True
            except:
                driver = None
        
        try:
            browser_config = load_browser_config()
            chrome_path = browser_config.get('chrome_path')
            profile_directory = browser_config.get('profile_directory', 'Profile 3')
            
            # 解析Chrome路径（支持相对路径）
            wrapper_dir = Path(__file__).parent
            project_root = wrapper_dir.parent
            
            # 如果chrome_path是相对路径或None，优先使用系统默认Chrome
            if chrome_path:
                chrome_path_obj = Path(chrome_path)
                if not chrome_path_obj.is_absolute():
                    chrome_path_obj = project_root / chrome_path
                    if chrome_path_obj.exists():
                        chrome_path = str(chrome_path_obj)
                        logger.info(f"[Selenium] 使用相对路径解析的Chrome: {chrome_path}")
                    else:
                        chrome_path = None  # 相对路径不存在，重置为None，使用系统默认
            
            # 如果 chrome_path 为 None 或不存在，优先系统 Chrome，再回退项目内 env/chrome（开发/离线调试）
            if not chrome_path or not Path(chrome_path).exists():
                system_paths = [
                    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
                    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
                ]
                found_system_chrome = False
                for system_path in system_paths:
                    if Path(system_path).exists():
                        chrome_path = system_path
                        logger.info(f"[Selenium] 使用系统 Chrome: {chrome_path}")
                        found_system_chrome = True
                        break
                if not found_system_chrome:
                    project_chrome_path = project_root / "env" / "chrome" / "chrome.exe"
                    if project_chrome_path.is_file():
                        chrome_path = str(project_chrome_path.resolve())
                        logger.info(f"[Selenium] 系统未安装 Chrome，使用项目内 Chrome: {chrome_path}")
                    else:
                        _last_browser_error = "未找到 Google Chrome，请先安装 Chrome 150"
                        logger.error(f"[Selenium] ❌ {_last_browser_error}")
                        return False
            
            # 使用当前用户 LocalAppData 下的专用目录：不受 Program Files/E 盘安装目录
            # ACL、覆盖安装或旧版本文件影响，并且升级后仍能保留登录状态。
            user_data_dir = _resolve_browser_user_data_dir(wrapper_dir)
            os.makedirs(user_data_dir, exist_ok=True)
            
            # 确保使用相同的 user_data_dir（如果之前已经创建过浏览器）
            global _last_user_data_dir
            if _last_user_data_dir and _last_user_data_dir != user_data_dir:
                logger.warning(f"[Selenium] 检测到 user_data_dir 不一致！之前: {_last_user_data_dir}, 现在: {user_data_dir}")
                logger.warning(f"[Selenium] 将使用之前的 user_data_dir: {_last_user_data_dir}")
                user_data_dir = _last_user_data_dir
            else:
                _last_user_data_dir = user_data_dir
            
            # 不再复制客户日常 Chrome 的 Profile。运行中的系统 Profile 直接复制可能包含
            # 不完整的数据库/锁文件，正是 Chrome 150 启动即退出的常见来源。
            temp_profile_dir = os.path.join(user_data_dir, profile_directory)
            if os.path.exists(temp_profile_dir):
                logger.info(f"[Selenium] 使用已存在的独立 Profile")
            else:
                logger.info(f"[Selenium] 将由 Chrome 创建全新的独立 Profile: {profile_directory}")
            
            logger.info(f"[Selenium] 启动浏览器，使用 Profile: {profile_directory}")
            logger.info(f"[Selenium] 独立用户数据目录: {user_data_dir}")
            
            # 检查是否已有使用相同 user_data_dir 的专用 Chrome 进程。
            # Windows 可能把同一路径显示成 Administrator 或 ADMINI~1，不能用字符串包含判断。
            # 如果有，说明浏览器已经打开，不需要创建新的
            chrome_already_running = False
            dedicated_chrome_processes = []
            try:
                import psutil
                for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                    try:
                        if proc.info['name'] and 'chrome.exe' in proc.info['name'].lower():
                            cmdline = proc.info.get('cmdline', [])
                            if _cmdline_uses_user_data_dir(cmdline, user_data_dir):
                                logger.info(f"[Selenium] ✅ 检测到已运行的 Chrome 进程 (PID: {proc.info['pid']})，使用相同的配置")
                                logger.info(f"[Selenium] ✅ 浏览器已打开，将尝试重新接管")
                                chrome_already_running = True
                                dedicated_chrome_processes.append(proc)
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        continue
            except ImportError:
                logger.warning("[Selenium] psutil 未安装，无法检测已运行的 Chrome 进程")

            # Chrome 使用随机调试端口时会留下此文件。即使进程枚举因权限/路径形式没有命中，
            # 也应先尝试接管；如果文件陈旧，接管失败后会安全清锁并重新启动。
            active_port = _read_devtools_active_port(user_data_dir)
            if active_port and not chrome_already_running:
                logger.info(
                    f"[Selenium] 检测到 DevToolsActivePort ({active_port})，优先尝试接管专用 Chrome"
                )
                chrome_already_running = True
            
            if not chrome_already_running:
                # 只关闭可能冲突的 ChromeDriver 进程，不关闭 Chrome 本身
                logger.info("[Selenium] 未检测到使用相同配置的 Chrome，将创建新实例")
                try:
                    import subprocess
                    # 只关闭 ChromeDriver，不关闭 Chrome
                    subprocess.run(
                        ["taskkill", "/f", "/im", "chromedriver.exe"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=5
                    )
                    _pause_short(reason="关闭 chromedriver 后缓冲")
                except Exception as e:
                    logger.warning(f"[Selenium] 关闭 ChromeDriver 时出错: {e}")
            else:
                # 如果浏览器已经运行，尝试通过 CDP 连接到它
                logger.info("[Selenium] ✅ 检测到浏览器已运行，尝试通过 CDP 连接...")
                
                # ChromeDriver 默认使用 --remote-debugging-port=0（随机端口），真实值写在
                # user-data-dir/DevToolsActivePort。必须先读该文件，固定 9222 仅作为兼容兜底。
                cdp_connected = False
                chromedriver_path = get_chromedriver_path()
                if not chromedriver_path:
                    logger.error("[Selenium] 无法获取 ChromeDriver 路径，跳过 CDP 连接")
                else:
                    candidate_ports = []
                    if active_port:
                        candidate_ports.append(active_port)
                        logger.info(f"[Selenium] 从 DevToolsActivePort 读取到真实调试端口: {active_port}")
                    for fixed_port in (9222, 9223, 9224, 9225):
                        if fixed_port not in candidate_ports:
                            candidate_ports.append(fixed_port)

                    for port in candidate_ports:
                        if not _is_local_tcp_port_open(port):
                            logger.debug(f"[Selenium] 端口 {port} 未监听，跳过 ChromeDriver 接管")
                            continue
                        try:
                            from selenium.webdriver.chrome.options import Options as ChromeOptions
                            
                            # 创建连接到已运行 Chrome 的选项
                            cdp_options = ChromeOptions()
                            cdp_options.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")
                            
                            # 尝试连接
                            try:
                                cdp_service = _create_chromedriver_service(chromedriver_path)
                                
                                logger.info(f"[Selenium] 尝试连接到端口 {port}...")
                                cdp_driver = webdriver.Chrome(service=cdp_service, options=cdp_options)
                                # 测试连接是否成功
                                cdp_driver.current_url
                                logger.info(f"[Selenium] ✅ 成功通过 CDP 连接到已运行的浏览器 (端口 {port})")
                                driver = cdp_driver
                                cdp_connected = True
                                break
                            except Exception as e:
                                logger.debug(f"[Selenium] 端口 {port} 连接失败: {e}")
                                continue
                        except Exception as e:
                            logger.debug(f"[Selenium] 尝试 CDP 连接时出错: {e}")
                            continue
                
                if not cdp_connected:
                    # 后端重启/覆盖安装后，旧 chromedriver 可能已经丢失而 Chrome 仍占用 Profile。
                    # 只关闭本软件专用 user-data-dir 的 Chrome，然后在下方自动创建新实例。
                    logger.warning("[Selenium] 无法接管遗留的专用 Chrome，将仅重启本软件浏览器")
                    _stop_dedicated_chrome(dedicated_chrome_processes, user_data_dir)
                    try:
                        subprocess.run(
                            ["taskkill", "/f", "/im", "chromedriver.exe"],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            timeout=5,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
                            if os.name == "nt" else 0,
                        )
                    except Exception:
                        pass
                    time.sleep(1.0)
                else:
                    # CDP 连接成功，直接返回
                    logger.info("[Selenium] ✅ 已通过 CDP 连接到已运行的浏览器")
                    return True
            
            # 创建WebDriver（优先使用项目内的 ChromeDriver）
            chromedriver_path = get_chromedriver_path()
            if not chromedriver_path:
                _last_browser_error = "未找到 ChromeDriver，安装包可能不完整"
                logger.error(f"[Selenium] ❌ {_last_browser_error}")
                logger.error("[Selenium] 请确保 env/chromedriver/chromedriver.exe 存在")
                return False

            diagnostic_log = Path(user_data_dir).parent / "chromedriver_startup.log"
            try:
                diagnostic_log.write_text(
                    f"IP auto Chrome startup diagnostic\n"
                    f"time={time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"chrome={chrome_path}\nchromedriver={chromedriver_path}\n"
                    f"user_data_dir={user_data_dir}\nprofile={profile_directory}\n",
                    encoding="utf-8",
                )
            except Exception:
                pass

            # 第一次失败后清理本软件专用进程和锁，再用相同配置重试一次。
            startup_errors = []
            logger.info(f"[Selenium] 使用 ChromeDriver: {chromedriver_path}")
            for startup_attempt in range(1, 3):
                service = None
                try:
                    options = _build_chrome_options(
                        chrome_path, user_data_dir, profile_directory, start_url
                    )
                    service = _create_chromedriver_service(
                        chromedriver_path, diagnostic_log=str(diagnostic_log)
                    )
                    logger.info(
                        f"[Selenium] 正在创建 Chrome WebDriver 实例（第 {startup_attempt}/2 次）..."
                    )
                    driver = webdriver.Chrome(service=service, options=options)
                    driver.set_page_load_timeout(60)
                    logger.info("[Selenium] 浏览器启动成功（全局单例，所有操作共享此实例）")
                    return True
                except Exception as exc:
                    driver = None
                    startup_errors.append(str(exc) or type(exc).__name__)
                    logger.warning(
                        f"[Selenium] 第 {startup_attempt}/2 次启动失败，将自动清理重试: {exc}"
                    )
                    _append_browser_diagnostic(
                        diagnostic_log,
                        f"WebDriver 启动第 {startup_attempt}/2 次失败: {exc}",
                    )
                    try:
                        if service:
                            service.stop()
                    except Exception:
                        pass
                    _stop_dedicated_chrome([], user_data_dir)
                    time.sleep(1.0)

            # 原配置连续失败时不删除客户登录数据，而是切换到全新目录。
            # 先直接启动 Chrome 再让 ChromeDriver 接管，绕开 session 创建阶段的启动退出问题。
            recovery_dir = _create_recovery_user_data_dir(user_data_dir)
            _last_user_data_dir = recovery_dir
            logger.warning(
                f"[Selenium] 原浏览器配置连续启动失败，已保留并切换全新配置: {recovery_dir}"
            )
            try:
                driver = _launch_chrome_direct_and_attach(
                    chrome_path,
                    chromedriver_path,
                    recovery_dir,
                    profile_directory,
                    start_url,
                    diagnostic_log,
                )
                driver.set_page_load_timeout(60)
                logger.info("[Selenium] ✅ 已通过全新配置直接启动并接管 Chrome")
                return True
            except Exception as exc:
                driver = None
                startup_errors.append(str(exc) or type(exc).__name__)
                logger.warning(f"[Selenium] 全新配置直接启动/接管失败: {exc}")
                _append_browser_diagnostic(
                    diagnostic_log, f"全新配置直接启动/接管失败: {exc}"
                )
                _stop_dedicated_chrome([], recovery_dir)

            # 最后再让 ChromeDriver 使用全新目录启动一次，覆盖直接启动被安全软件拦截的情况。
            try:
                options = _build_chrome_options(
                    chrome_path, recovery_dir, profile_directory, start_url
                )
                service = _create_chromedriver_service(
                    chromedriver_path, diagnostic_log=str(diagnostic_log)
                )
                logger.info("[Selenium] 使用全新配置执行最终 ChromeDriver 启动...")
                driver = webdriver.Chrome(service=service, options=options)
                driver.set_page_load_timeout(60)
                logger.info("[Selenium] ✅ 全新配置最终启动成功")
                return True
            except Exception as exc:
                driver = None
                startup_errors.append(str(exc) or type(exc).__name__)
                _append_browser_diagnostic(
                    diagnostic_log, f"全新配置最终 ChromeDriver 启动失败: {exc}"
                )
                _stop_dedicated_chrome([], recovery_dir)
                _last_browser_error = (
                    "Chrome 已自动清理并切换全新配置，但仍连续启动失败。"
                    f"请把诊断日志发给技术人员：{diagnostic_log}"
                )
                logger.error(f"[Selenium] {_last_browser_error}")
                return False
            
        except Exception as e:
            _last_browser_error = "浏览器自动恢复过程出现异常，请重新点击一次登录"
            logger.error(f"[Selenium] 启动浏览器失败: {e}")
            driver = None  # 确保失败时重置 driver
            return False


def open_login_url(url: str, expected_domains) -> dict:
    """
    打开并确认平台登录页。

    与旧逻辑不同，本函数不会在 Chrome 仅打开空白页时返回成功；会依次尝试当前页、
    直接导航和新标签页导航，最终以实际域名作为成功判据。
    """
    global driver, _last_browser_error

    if not str(url or "").lower().startswith(("https://", "http://")):
        return {"success": False, "error": f"无效登录地址: {url}"}

    with _driver_navigation_lock:
        if not ensure_browser(start_url=url):
            return {
                "success": False,
                "error": _last_browser_error or "Chrome 或 ChromeDriver 启动失败",
            }
        if not driver:
            return {"success": False, "error": "浏览器已启动，但 Selenium driver 未建立"}

        last_error = ""
        for attempt in range(3):
            try:
                current_url = driver.current_url or ""
                if _url_matches_domains(current_url, expected_domains):
                    try:
                        driver.maximize_window()
                    except Exception:
                        pass
                    return {
                        "success": True,
                        "current_url": current_url,
                        "title": driver.title or "",
                        "attempt": attempt,
                    }

                if attempt == 0:
                    logger.info(f"[BrowserLogin] 直接导航到: {url}")
                    driver.get(url)
                elif attempt == 1:
                    logger.warning("[BrowserLogin] 首次导航未进入目标域名，改用新标签页重试")
                    driver.switch_to.new_window("tab")
                    driver.get(url)
                else:
                    logger.warning("[BrowserLogin] 新标签页导航仍未成功，使用页面脚本最后重试")
                    driver.execute_script("window.location.assign(arguments[0]);", url)

                WebDriverWait(driver, 45).until(
                    lambda d: _url_matches_domains(d.current_url, expected_domains)
                )
                current_url = driver.current_url or ""
                try:
                    driver.maximize_window()
                except Exception:
                    pass
                return {
                    "success": True,
                    "current_url": current_url,
                    "title": driver.title or "",
                    "attempt": attempt + 1,
                }
            except Exception as exc:
                last_error = str(exc)
                try:
                    current_url = driver.current_url or ""
                except Exception:
                    current_url = ""
                logger.warning(
                    f"[BrowserLogin] 第 {attempt + 1} 次导航失败，当前 URL={current_url!r}: {exc}"
                )

        try:
            current_url = driver.current_url or ""
        except Exception:
            current_url = ""
        return {
            "success": False,
            "error": last_error or "浏览器未进入目标平台",
            "current_url": current_url,
        }

def _publish_video_impl(
    video_path: str,
    title: str,
    description: str,
    cover_path: Optional[str] = None,
    cover_text: Optional[str] = None
) -> str:
    """
    发布视频到抖音（Selenium方式，使用你提供的元素选择器）
    
    Args:
        video_path: 视频文件路径
        title: 视频标题
        description: 视频描述
        cover_path: 封面图片路径（可选，如果不提供则从视频提取）
    
    Returns:
        str: 发布结果
    """
    global driver
    
    try:
        # 1. 启动浏览器
        logger.info("[Selenium] ========== 步骤1: 启动浏览器 ==========")
        if not ensure_browser():
            logger.error("[Selenium] 浏览器启动失败")
            return "浏览器启动失败"
        logger.info("[Selenium] 浏览器启动成功")
        
        # 2. 导航到上传页面
        logger.info("[Selenium] ========== 步骤2: 导航到上传页面 ==========")
        logger.info(f"[Selenium] 当前URL: {driver.current_url}")
        upload_url = "https://creator.douyin.com/creator-micro/content/upload?enter_from=dou_web"
        logger.info(f"[Selenium] 导航到: {upload_url}")
        
        try:
            driver.get(upload_url)
            logger.info("[Selenium] 页面请求已发送，等待加载...")
        except Exception as e:
            logger.error(f"[Selenium] 导航失败: {e}")
            return f"导航失败: {e}"
        
        # 等待页面加载完成
        try:
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            logger.info("[Selenium] 页面已加载")
            logger.info(f"[Selenium] 当前URL: {driver.current_url}")
            logger.info(f"[Selenium] 页面标题: {driver.title}")
        except Exception as e:
            logger.warning(f"[Selenium] 等待页面加载超时: {e}")
            logger.info(f"[Selenium] 当前URL: {driver.current_url}")
        
        # 检查是否需要登录
        current_url = driver.current_url
        if 'login' in current_url.lower() or 'passport' in current_url.lower():
            logger.warning("[Selenium] 检测到需要登录，请先在浏览器中登录")
            return "需要登录抖音账号，请先在浏览器中登录后再试"
        
        # 再次等待，确保页面完全加载
        logger.info("[Selenium] 等待页面完全加载...")
        _pause_short(reason="页面稳定等待")
        
        # 3. 上传视频
        logger.info("[Selenium] ========== 步骤3: 上传视频 ==========")
        try:
            logger.info(f"[Selenium] 查找文件输入框...")
            # 等待更长时间，并尝试多种方式查找
            file_input = None
            try:
                # 方式1: 直接查找
                file_input = WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='file']"))
                )
            except:
                # 方式2: 查找所有input，然后筛选
                logger.info("[Selenium] 方式1失败，尝试方式2...")
                all_inputs = driver.find_elements(By.TAG_NAME, "input")
                for inp in all_inputs:
                    if inp.get_attribute("type") == "file":
                        file_input = inp
                        break
            
            if not file_input:
                # 方式3: 使用XPath
                logger.info("[Selenium] 方式2失败，尝试方式3...")
                file_input = driver.find_element(By.XPATH, "//input[@type='file']")
            
            if file_input:
                logger.info(f"[Selenium] 找到文件输入框，上传视频: {video_path}")
                file_input.send_keys(os.path.abspath(video_path))
                logger.info("[Selenium] 视频已上传")
                _pause_short(reason="上传动作后等待页面接收文件")
            else:
                raise Exception("未找到文件输入框")
        except Exception as e:
            logger.error(f"[Selenium] 上传视频失败: {e}")
            logger.error(f"[Selenium] 当前页面源码片段: {driver.page_source[:500]}")
            import traceback
            logger.error(traceback.format_exc())
            return f"上传视频失败: {e}"
        
        # 等待视频处理
        logger.info("[Selenium] 等待视频处理...")
        human_sleep(15, 25, reason="等待视频处理")
        
        # 4. 选择封面（按你提供的流程）
        logger.info("[Selenium] ========== 步骤4: 选择封面 ==========")
        
        # 4.1 点击"选择封面" - 使用你提供的选择器
        logger.info("[Selenium] 步骤4.1: 点击'选择封面'按钮...")
        cover_selectors = {
            "xpath": [
                "//div[@class='title-wA45Xd' and contains(text(), '选择封面')]",
                "//div[contains(@class, 'title-wA45Xd')]",
                "//div[contains(text(), '选择封面')]"
            ],
            "css": [
                "div.title-wA45Xd"
            ]
        }
        cover_button = find_element_with_multiple_selectors(cover_selectors, timeout=10)
        if cover_button:
            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", cover_button)
                _pause_tiny(reason="滚动到选择封面按钮后缓冲")
                cover_button.click()
                logger.info("[Selenium] ✅ 已点击'选择封面'")
                _pause_short(reason="点击选择封面后等待弹窗/模块响应")
            except Exception as e:
                logger.warning(f"[Selenium] 点击'选择封面'失败，尝试JavaScript点击: {e}")
                try:
                    driver.execute_script("arguments[0].click();", cover_button)
                    logger.info("[Selenium] ✅ 已使用JavaScript点击'选择封面'")
                    _pause_short(reason="JS点击选择封面后等待弹窗/模块响应")
                except Exception as e2:
                    logger.error(f"[Selenium] ❌ 点击'选择封面'完全失败: {e2}")
                    raise Exception("无法点击'选择封面'按钮，封面流程无法继续")
        else:
            logger.error("[Selenium] ❌ 未找到'选择封面'按钮，封面流程无法继续")
            raise Exception("未找到'选择封面'按钮")
        
        # 4.2 点击"标题" - 使用你提供的选择器
        logger.info("[Selenium] 步骤4.2: 点击'标题'按钮...")
        title_button_selectors = {
            "xpath": [
                "//div[@class='icon-name-Fi8gxR' and contains(text(), '标题')]",
                "//div[contains(@class, 'icon-name-Fi8gxR')]",
                "//div[contains(text(), '标题')]"
            ],
            "css": [
                "div.icon-name-Fi8gxR"
            ]
        }
        title_button = find_element_with_multiple_selectors(title_button_selectors, timeout=10)
        if title_button:
            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", title_button)
                _pause_tiny(reason="滚动到标题按钮后缓冲")
                title_button.click()
                logger.info("[Selenium] ✅ 已点击'标题'")
                logger.info("[Selenium] 等待弹窗完全加载（>=10秒）...")
                _pause_after_title_click(reason="点击标题后等待弹窗/编辑器加载")
            except Exception as e:
                logger.warning(f"[Selenium] 点击'标题'失败，尝试JavaScript点击: {e}")
                try:
                    driver.execute_script("arguments[0].click();", title_button)
                    logger.info("[Selenium] ✅ 已使用JavaScript点击'标题'")
                    _pause_after_title_click(reason="JS点击标题后等待弹窗/编辑器加载")
                except Exception as e2:
                    logger.error(f"[Selenium] ❌ 点击'标题'完全失败: {e2}")
                    raise Exception("无法点击'标题'按钮，封面流程无法继续")
        else:
            logger.error("[Selenium] ❌ 未找到'标题'按钮，封面流程无法继续")
            raise Exception("未找到'标题'按钮")
        
        # 4.2.1 点击标题后的元素（等待缓存后）
        logger.info("[Selenium] 等待缓存加载（10秒）...")
        human_sleep(5, 13, reason="等待缓存加载")
        
        logger.info("[Selenium] 点击标题后的元素...")
        title_after_selectors = {
            "xpath": [
                # 本机常见结构（div[3] 分支）
                "//*[@id='dy-creator-content-modal-body']/div/div[2]/div[1]/div/div[2]/div[3]/div/div[9]/div/div",
                # 客户环境：点「标题」后需先点封面预览格（div[2] 分支，含 outer-img-wrap / effect 图）
                "//*[@id='dy-creator-content-modal-body']/div/div[2]/div[1]/div/div[2]/div[2]/div/div[9]/div/div",
                "//*[@id='dy-creator-content-modal-body']/div/div[2]/div[1]/div/div[2]/div[2]/div/div[9]/div/div/img",
                "//div[contains(@class,'outer-img-wrap')]//img",
                "//div[contains(@class,'outer-img-wrap')]",
                "//img[contains(@src,'byteeffecttos.com')]",
            ]
        }
        title_after_element = find_element_with_multiple_selectors(title_after_selectors, timeout=15)
        if title_after_element:
            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", title_after_element)
                _pause_tiny(reason="滚动到标题后预览区后缓冲")
                title_after_element.click()
                logger.info("[Selenium] 已点击标题后的元素")
            except Exception as e:
                logger.warning(f"[Selenium] 点击标题后的元素失败，尝试JavaScript点击: {e}")
                driver.execute_script("arguments[0].click();", title_after_element)
                logger.info("[Selenium] 已使用JavaScript点击标题后的元素")
            _pause_short(reason="点击标题后的元素后等待编辑区稳定")
        else:
            logger.warning("[Selenium] 未找到标题后的元素，继续执行...")
        
        # 4.3 点击canvas中间区域 - 使用新的XPath
        logger.info("[Selenium] 等待缓存加载（10秒）...")
        human_sleep(5, 13, reason="等待缓存加载（canvas前）")
        
        logger.info("[Selenium] 点击canvas中间区域...")
        try:
            # 使用新的XPath定位元素
            canvas_element = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.XPATH, "//*[@id='cloudArea']/div[2]"))
            )
            
            if canvas_element:
                # 等待元素可见
                WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//*[@id='cloudArea']/div[2]"))
                )
                
                # 滚动到元素可见
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", canvas_element)
                _pause_tiny(reason="滚动到canvas区域后缓冲")
                
                # 点击元素
                try:
                    canvas_element.click()
                    logger.info("[Selenium] 已点击canvas中间区域")
                except:
                    # 如果普通点击失败，尝试JavaScript点击
                    driver.execute_script("arguments[0].click();", canvas_element)
                    logger.info("[Selenium] 已使用JavaScript点击canvas中间区域")

                _pause_short(reason="点击canvas后等待焦点/编辑器响应")
        except Exception as e:
            logger.warning(f"[Selenium] 点击canvas中间区域失败: {e}")
            # 备用方案：尝试使用原来的canvas选择器
            try:
                logger.info("[Selenium] 尝试备用方案...")
                canvas = driver.find_element(By.CSS_SELECTOR, "canvas.cloudImage-N0ai8Y.lower-canvas")
                if canvas:
                    actions = ActionChains(driver)
                    actions.move_to_element_with_offset(canvas, canvas.size['width']/2, canvas.size['height']/2).click().perform()
                    logger.info("[Selenium] 已使用备用方案点击canvas")
                    _pause_short(reason="备用点击canvas后等待响应")
            except Exception as backup_error:
                logger.warning(f"[Selenium] 备用方案也失败: {backup_error}")
        
        # 4.3.1 输入标题框内容（在封面选择流程中）
        logger.info("[Selenium] 步骤4.3.1: 输入标题框内容...")
        logger.info("[Selenium] 等待封面弹窗 dialog-0..dialog-8 中出现标题 textarea...")
        text_input = None
        cover_dialog_id = None
        try:
            cover_dialog_id = _find_visible_cover_dialog_id(driver, timeout=24.0)
            if not cover_dialog_id:
                raise TimeoutException("未找到含 textarea 的封面弹窗（dialog-*）")
            # 同一弹窗内任意 textarea（结构随版本可能变化，不锁死 div[3]）
            text_input = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.XPATH, f"//*[@id='{cover_dialog_id}']//textarea"))
            )
            logger.info(f"[Selenium] ✅ 找到标题框输入框（#{cover_dialog_id}）")
            
            text_input = WebDriverWait(driver, 12).until(
                EC.element_to_be_clickable((By.XPATH, f"//*[@id='{cover_dialog_id}']//textarea"))
            )
            logger.info("[Selenium] ✅ 标题框输入框已可编辑")
            
            if text_input:
                # 滚动到元素可见
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", text_input)
                _pause_tiny(reason="滚动到标题输入框后缓冲")
                
                # 尝试点击，如果失败则使用JavaScript
                try:
                    text_input.click()
                    logger.info("[Selenium] 已点击标题框输入框")
                except:
                    driver.execute_script("arguments[0].click();", text_input)
                    logger.info("[Selenium] 已使用JavaScript点击标题框输入框")

                _pause_tiny(reason="聚焦输入框后缓冲")
                
                # 先清空：使用JavaScript直接设置value为空（最彻底的方式）
                driver.execute_script("arguments[0].value = '';", text_input)
                _pause_tiny(reason="清空输入框后缓冲（js置空）")
                
                # 再次使用clear方法清空
                try:
                    text_input.clear()
                except:
                    pass
                
                time.sleep(0.3)
                
                # 再次使用JavaScript清空，确保完全清空
                driver.execute_script("arguments[0].value = '';", text_input)
                time.sleep(0.2)
                
                # 验证是否已清空
                current_value = driver.execute_script("return arguments[0].value;", text_input)
                if current_value:
                    logger.warning(f"[Selenium] 输入框仍有内容，再次清空: {current_value}")
                    driver.execute_script("arguments[0].value = '';", text_input)
                    _pause_tiny(reason="二次清空输入框后缓冲")
                
                # 使用send_keys输入文字（封面文字，如果提供了的话）
                cover_text_to_input = cover_text if cover_text else "测试文字"
                logger.info(f"[Selenium] 准备输入文字: {cover_text_to_input}")
                text_input.send_keys(cover_text_to_input)
                logger.info(f"[Selenium] 已使用send_keys输入标题框内容：{cover_text_to_input}")
                _pause_short(reason="输入封面文字后等待页面处理")
                
                # 验证输入是否成功
                current_value = driver.execute_script("return arguments[0].value;", text_input)
                if current_value:
                    logger.info(f"[Selenium] ✅ 已成功输入文字: {current_value}")
                else:
                    logger.warning(f"[Selenium] ⚠️  输入的文字可能未成功，当前值: {current_value}")
                    # 如果send_keys失败，尝试使用JavaScript直接设置value
                    driver.execute_script("arguments[0].value = arguments[1];", text_input, cover_text_to_input)
                    _pause_tiny(reason="JS写入输入框后缓冲")
                    current_value = driver.execute_script("return arguments[0].value;", text_input)
                    if current_value:
                        logger.info(f"[Selenium] ✅ 已使用JavaScript成功输入文字: {current_value}")
                    else:
                        logger.error(f"[Selenium] ❌ 输入文字失败，当前值: {current_value}")
                        raise Exception("无法输入标题框内容")
        except TimeoutException:
            logger.error("[Selenium] ❌ 等待标题框输入框超时，封面流程无法继续")
            raise Exception("未找到标题框输入框")
        except Exception as e:
            logger.error(f"[Selenium] ❌ 输入标题框内容失败: {e}")
            raise Exception(f"输入标题框内容失败: {e}")
        
        # 4.3.2 点击"确定"按钮（与 4.3.1 使用同一 dialog-*，避免只认 dialog-0）
        logger.info("[Selenium] 步骤4.3.2: 点击'确定'按钮...")
        if not cover_dialog_id:
            logger.warning("[Selenium] 无 cover_dialog_id，尝试探测带「确定」的弹窗...")
            for did in _iter_dialog_ids():
                try:
                    el = driver.find_element(By.ID, did)
                    if el.is_displayed() and driver.find_elements(
                        By.XPATH, f"//*[@id='{did}']//button[contains(normalize-space(.), '确定')]"
                    ):
                        cover_dialog_id = did
                        logger.info(f"[Selenium] 使用带「确定」的弹窗: #{cover_dialog_id}")
                        break
                except Exception:
                    continue
        if cover_dialog_id:
            try:
                _wait_confirm_dialog_and_click_ok(driver, cover_dialog_id)
            except TimeoutException as e:
                logger.warning(f"[Selenium] 点击「确定」后等待状态超时，继续走“完成”流程: {e}")
        else:
            logger.warning("[Selenium] 未定位到可点击「确定」的弹窗，跳过步骤4.3.2")
        
        # 4.3.3 点击"完成"按钮（封面选择流程的完成）- 必须先点击完成，然后才可能弹出"暂不设置"
        logger.info("[Selenium] ========== 步骤4.3.3: 点击'完成'按钮 ==========")
        logger.info("[Selenium] 等待页面稳定后点击'完成'按钮...")
        _pause_short(reason="点击完成前等待页面更新/稳定")
        
        finish_clicked = False
        # 优先：不依赖 dialog-0/1/2/3 编号，在弹窗/modal 内按文案点「完成」（你之前那套思路）
        if _try_click_span_button_by_text("完成", timeout_sec=22):
            finish_clicked = True
            logger.info("[Selenium] ✅ 已通过动态 span 定位点击「完成」")
            _pause_short(reason="点击完成后等待弹窗/状态变化")
        
        # 尝试多种方式查找并点击"完成"按钮（使用颜色+文字识别，参考确定按钮的成功逻辑）
        
        # 方式1: 直接查找所有包含"完成"文字的按钮（最简单直接）
        logger.info("[Selenium] 方式1: 直接查找包含'完成'文字的按钮...")
        try:
            buttons = driver.find_elements(By.TAG_NAME, "button")
            logger.info(f"[Selenium] 找到 {len(buttons)} 个按钮")
            
            for i, button in enumerate(buttons):
                try:
                    button_text = button.text.strip()
                    logger.info(f"[Selenium] 按钮 {i+1}: 文本='{button_text}'")
                    
                    if "完成" not in button_text:
                        continue
                    
                    logger.info(f"[Selenium] ✅ 找到包含'完成'的按钮 {i+1}: '{button_text}'，准备点击...")
                    
                    # 方法1: 普通click
                    try:
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                        _pause_tiny(reason="滚动到完成按钮后缓冲")
                        button.click()
                        logger.info("[Selenium] ✅ 已点击'完成'按钮（方法1：普通click）")
                        finish_clicked = True
                        _pause_short(reason="点击完成后等待弹窗/状态变化")
                        break
                    except Exception as e1:
                        logger.debug(f"[Selenium] 方法1失败: {e1}")
                    
                    # 方法2: JavaScript点击
                    if not finish_clicked:
                        try:
                            driver.execute_script("arguments[0].click();", button)
                            logger.info("[Selenium] ✅ 已点击'完成'按钮（方法2：JavaScript click）")
                            finish_clicked = True
                            _pause_short(reason="JS点击完成后等待弹窗/状态变化")
                            break
                        except Exception as e2:
                            logger.debug(f"[Selenium] 方法2失败: {e2}")
                    
                    # 方法3: ActionChains点击
                    if not finish_clicked:
                        try:
                            ActionChains(driver).move_to_element(button).click().perform()
                            logger.info("[Selenium] ✅ 已点击'完成'按钮（方法3：ActionChains）")
                            finish_clicked = True
                            _pause_short(reason="ActionChains点击完成后等待弹窗/状态变化")
                            break
                        except Exception as e3:
                            logger.debug(f"[Selenium] 方法3失败: {e3}")
                    
                    # 方法4: 坐标点击
                    if not finish_clicked:
                        try:
                            location = button.location
                            size = button.size
                            center_x = location['x'] + size['width'] // 2
                            center_y = location['y'] + size['height'] // 2
                            logger.info(f"[Selenium] 按钮中心坐标: ({center_x}, {center_y})")
                            
                            driver.execute_script(f"""
                                var x = {center_x};
                                var y = {center_y};
                                var element = document.elementFromPoint(x, y);
                                if (element) {{
                                    element.click();
                                }}
                            """)
                            logger.info("[Selenium] ✅ 已点击'完成'按钮（方法4：坐标点击）")
                            finish_clicked = True
                            _pause_short(reason="坐标点击完成后等待弹窗/状态变化")
                            break
                        except Exception as e4:
                            logger.debug(f"[Selenium] 方法4失败: {e4}")
                            
                except Exception as e:
                    logger.debug(f"[Selenium] 检查按钮 {i+1} 失败: {e}")
                    continue
        except Exception as e:
            logger.warning(f"[Selenium] 方式1查找'完成'按钮失败: {e}")
        
        # 方式1.5: 使用颜色+文字识别（参考确定按钮的成功逻辑，作为备用）
        if not finish_clicked:
            logger.info("[Selenium] 方式1.5: 使用颜色+文字识别查找'完成'按钮（备用方案）...")
            try:
                buttons = driver.find_elements(By.TAG_NAME, "button")
                logger.info(f"[Selenium] 找到 {len(buttons)} 个按钮")
                
                for i, button in enumerate(buttons):
                    try:
                        button_text = button.text.strip()
                        if "完成" not in button_text:
                            continue
                        
                        # 获取按钮内span元素的颜色（应该是#252632CC或类似深灰色）
                        try:
                            # 查找span.semi-button-content
                            span = button.find_element(By.CSS_SELECTOR, "span.semi-button-content")
                            if span:
                                text_color = driver.execute_script("""
                                    var style = window.getComputedStyle(arguments[0]);
                                    return style.color;
                                """, span)
                                logger.info(f"[Selenium] 按钮 {i+1}: 文本='{button_text}', span颜色={text_color}")
                                
                                # 检查颜色是否是深灰色（#252632CC或rgba(37, 38, 50, 0.8)）
                                if "252632" in text_color or "37" in text_color or "38" in text_color or "50" in text_color:
                                    logger.info("[Selenium] ✅ 找到'完成'按钮（颜色+文字匹配），准备点击...")
                                    
                                    # 方法1: 普通click
                                    try:
                                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                                        _pause_tiny(reason="滚动到完成按钮后缓冲（颜色匹配）")
                                        button.click()
                                        logger.info("[Selenium] ✅ 已点击'完成'按钮（颜色匹配，方法1：普通click）")
                                        finish_clicked = True
                                        _pause_short(reason="点击完成后等待弹窗/状态变化（颜色匹配）")
                                        break
                                    except Exception as e1:
                                        logger.debug(f"[Selenium] 方法1失败: {e1}")
                                    
                                    # 方法2: JavaScript点击
                                    if not finish_clicked:
                                        try:
                                            driver.execute_script("arguments[0].click();", button)
                                            logger.info("[Selenium] ✅ 已点击'完成'按钮（颜色匹配，方法2：JavaScript click）")
                                            finish_clicked = True
                                            _pause_short(reason="JS点击完成后等待弹窗/状态变化（颜色匹配）")
                                            break
                                        except Exception as e2:
                                            logger.debug(f"[Selenium] 方法2失败: {e2}")
                        except:
                            # 如果没有span，跳过这个按钮
                            continue
                    except Exception as e:
                        logger.debug(f"[Selenium] 检查按钮 {i+1} 失败: {e}")
                        continue
            except Exception as e:
                logger.warning(f"[Selenium] 方式1.5查找'完成'按钮失败: {e}")
        
        # 方式2: 使用XPath定位span.semi-button-content（用户截图显示的元素）
        if not finish_clicked:
            logger.info("[Selenium] 方式2: 使用XPath定位span.semi-button-content...")
            try:
                finish_selectors = {
                    "xpath": [
                        "//span[@class='semi-button-content' and contains(text(), '完成')]",
                        "//span[contains(@class, 'semi-button-content') and contains(text(), '完成')]",
                        "//button[.//span[@class='semi-button-content' and contains(text(), '完成')]]",
                        "//button[contains(text(), '完成')]"
                    ],
                    # 禁用宽泛 CSS，避免误命中“高清发布/发布”
                    "css": []
                }
                finish_element = find_element_with_multiple_selectors(finish_selectors, timeout=5)
                if finish_element:
                    # 如果是span，找到父按钮
                    if finish_element.tag_name == 'span':
                        finish_button = finish_element.find_element(By.XPATH, "./..")
                    else:
                        finish_button = finish_element

                    # 二次保险：必须是“完成”相关按钮，禁止误点发布类按钮
                    finish_text = (finish_button.text or "").strip()
                    if ("完成" not in finish_text) or ("发布" in finish_text):
                        logger.warning(f"[Selenium] 跳过疑似错误按钮（非完成）: '{finish_text}'")
                        finish_button = None
                    
                    if finish_button is not None:
                        logger.info("[Selenium] 找到'完成'按钮（XPath方式），准备点击...")
                        try:
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", finish_button)
                            _pause_tiny(reason="滚动到完成按钮后缓冲（XPath）")
                            finish_button.click()
                            logger.info("[Selenium] ✅ 已点击'完成'按钮（方式2：XPath，普通点击）")
                            finish_clicked = True
                            _pause_short(reason="点击完成后等待弹窗/状态变化（XPath）")
                        except:
                            driver.execute_script("arguments[0].click();", finish_button)
                            logger.info("[Selenium] ✅ 已点击'完成'按钮（方式2：XPath，JavaScript点击）")
                            finish_clicked = True
                            _pause_short(reason="JS点击完成后等待弹窗/状态变化（XPath）")
            except Exception as e:
                logger.warning(f"[Selenium] 方式2也失败: {e}")
        
        # 标记：是否已处理“暂不设置”
        skip_setting_clicked = False

        if finish_clicked:
            logger.info("[Selenium] ✅ '完成'按钮已成功点击！")
            _pause_short(reason="完成点击后等待页面响应")
            
            # 4.3.4 点击"完成"后，检查是否有"暂不设置"弹窗（dialog-3）
            logger.info("[Selenium] ========== 步骤4.3.4: 检查'暂不设置'弹窗（点击完成后） ==========")
            try:
                # 不依赖 dialog-x：按按钮文本查找并点击
                if _try_click_span_button_by_text("暂不设置", timeout_sec=10):
                    skip_setting_clicked = True
                    logger.info("[Selenium] ✅ 已点击'暂不设置'按钮（动态定位）")
                    _pause_short(reason="点击暂不设置后等待页面响应")

                    # 4.3.5 点击"暂不设置"后，固定再尝试一次“完成”（存在就点，不存在就继续）
                    logger.info("[Selenium] ========== 步骤4.3.5: 固定尝试再次点击'完成' ==========")
                    logger.info("[Selenium] 按顺序流程执行：完成 -> 暂不设置 -> 再次完成（若存在）")
                    _pause_short(reason="暂不设置后等待页面更新")
                    finish_clicked_again = False

                    # 再次查找并点击"完成"按钮（复用之前的逻辑）
                    if not finish_clicked_again:

                        # 方式1: 直接查找所有包含"完成"文字的按钮
                        logger.info("[Selenium] 方式1: 直接查找包含'完成'文字的按钮...")
                        try:
                            buttons = driver.find_elements(By.TAG_NAME, "button")
                            logger.info(f"[Selenium] 找到 {len(buttons)} 个按钮")

                            for i, button in enumerate(buttons):
                                try:
                                    button_text = button.text.strip()
                                    logger.info(f"[Selenium] 按钮 {i+1}: 文本='{button_text}'")

                                    if "完成" not in button_text:
                                        continue

                                    logger.info(f"[Selenium] ✅ 找到包含'完成'的按钮 {i+1}: '{button_text}'，准备点击...")

                                    # 方法1: 普通click
                                    try:
                                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                                        _pause_tiny(reason="滚动到完成按钮后缓冲（再次完成）")
                                        button.click()
                                        logger.info("[Selenium] ✅ 已再次点击'完成'按钮（方法1：普通click）")
                                        finish_clicked_again = True
                                        _pause_short(reason="再次点击完成后等待页面响应")
                                        break
                                    except Exception as e1:
                                        logger.debug(f"[Selenium] 方法1失败: {e1}")

                                    # 方法2: JavaScript点击
                                    if not finish_clicked_again:
                                        try:
                                            driver.execute_script("arguments[0].click();", button)
                                            logger.info("[Selenium] ✅ 已再次点击'完成'按钮（方法2：JavaScript click）")
                                            finish_clicked_again = True
                                            _pause_short(reason="JS再次点击完成后等待页面响应")
                                            break
                                        except Exception as e2:
                                            logger.debug(f"[Selenium] 方法2失败: {e2}")

                                    # 方法3: ActionChains点击
                                    if not finish_clicked_again:
                                        try:
                                            ActionChains(driver).move_to_element(button).click().perform()
                                            logger.info("[Selenium] ✅ 已再次点击'完成'按钮（方法3：ActionChains）")
                                            finish_clicked_again = True
                                            _pause_short(reason="ActionChains再次点击完成后等待页面响应")
                                            break
                                        except Exception as e3:
                                            logger.debug(f"[Selenium] 方法3失败: {e3}")

                                    # 方法4: 坐标点击
                                    if not finish_clicked_again:
                                        try:
                                            location = button.location
                                            size = button.size
                                            center_x = location['x'] + size['width'] // 2
                                            center_y = location['y'] + size['height'] // 2
                                            logger.info(f"[Selenium] 按钮中心坐标: ({center_x}, {center_y})")

                                            driver.execute_script(f"""
                                                var x = {center_x};
                                                var y = {center_y};
                                                var element = document.elementFromPoint(x, y);
                                                if (element) {{
                                                    element.click();
                                                }}
                                            """)
                                            logger.info("[Selenium] ✅ 已再次点击'完成'按钮（方法4：坐标点击）")
                                            finish_clicked_again = True
                                            _pause_short(reason="坐标再次点击完成后等待页面响应")
                                            break
                                        except Exception as e4:
                                            logger.debug(f"[Selenium] 方法4失败: {e4}")

                                except Exception as e:
                                    logger.debug(f"[Selenium] 检查按钮 {i+1} 失败: {e}")
                                    continue
                        except Exception as e:
                            logger.warning(f"[Selenium] 方式1查找'完成'按钮失败: {e}")

                        # 方式2: 使用XPath定位span.semi-button-content
                        if not finish_clicked_again:
                            logger.info("[Selenium] 方式2: 使用XPath定位span.semi-button-content...")
                            try:
                                finish_selectors = {
                                    "xpath": [
                                        "//span[@class='semi-button-content' and contains(text(), '完成')]",
                                        "//span[contains(@class, 'semi-button-content') and contains(text(), '完成')]",
                                        "//button[.//span[@class='semi-button-content' and contains(text(), '完成')]]",
                                        "//button[contains(text(), '完成')]"
                                    ],
                                    # 禁用宽泛 CSS，避免误命中“高清发布/发布”
                                    "css": []
                                }
                                finish_element = find_element_with_multiple_selectors(finish_selectors, timeout=5)
                                if finish_element:
                                    # 如果是span，找到父按钮
                                    if finish_element.tag_name == 'span':
                                        finish_button = finish_element.find_element(By.XPATH, "./..")
                                    else:
                                        finish_button = finish_element

                                    # 二次保险：必须是“完成”相关按钮，禁止误点发布类按钮
                                    finish_text = (finish_button.text or "").strip()
                                    if ("完成" not in finish_text) or ("发布" in finish_text):
                                        logger.warning(f"[Selenium] 跳过疑似错误按钮（非完成）: '{finish_text}'")
                                        finish_button = None

                                    if finish_button is not None:
                                        logger.info("[Selenium] 找到'完成'按钮（XPath方式），准备再次点击...")
                                        try:
                                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", finish_button)
                                            _pause_tiny(reason="滚动到完成按钮后缓冲（XPath再次完成）")
                                            finish_button.click()
                                            logger.info("[Selenium] ✅ 已再次点击'完成'按钮（方式2：XPath，普通点击）")
                                            finish_clicked_again = True
                                            _pause_short(reason="再次点击完成后等待页面响应（XPath）")
                                        except Exception:
                                            driver.execute_script("arguments[0].click();", finish_button)
                                            logger.info("[Selenium] ✅ 已再次点击'完成'按钮（方式2：XPath，JavaScript点击）")
                                            finish_clicked_again = True
                                            _pause_short(reason="JS再次点击完成后等待页面响应（XPath）")
                            except Exception as e:
                                logger.warning(f"[Selenium] 方式2也失败: {e}")

                    if finish_clicked_again:
                        logger.info("[Selenium] ✅ '完成'按钮已再次成功点击！")
                        _pause_short(reason="再次完成后等待页面响应")
                    else:
                        logger.info("[Selenium] 第二次未找到'完成'按钮，按顺序流程继续进入主界面填写")
                else:
                    logger.info("[Selenium] 未检测到'暂不设置'弹窗或无需处理，跳过该步骤")
            except Exception as e:
                logger.warning(f"[Selenium] 检查'暂不设置'弹窗时出错: {e}，继续执行后续流程...")
        else:
            logger.warning("[Selenium] ⚠️ 未找到'完成'按钮，但继续执行后续流程（可能页面已自动跳转）...")
        
        # 4.4 上传封面文件
        # 封面弹窗流（4.1~4.3）完成后，不再重复走 4.4 上传，避免回跳封面流程
        should_upload_cover = not finish_clicked
        if cover_path and os.path.exists(cover_path) and should_upload_cover:
            logger.info(f"[Selenium] 上传封面文件: {cover_path}")
            try:
                # 查找文件输入框（可能是新出现的）
                file_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
                for file_input in file_inputs:
                    try:
                        file_input.send_keys(os.path.abspath(cover_path))
                        logger.info("[Selenium] 封面文件已上传")
                        _pause_short(reason="封面文件上传后等待页面处理")
                        break
                    except:
                        continue
            except Exception as e:
                logger.warning(f"[Selenium] 上传封面失败: {e}")
        elif cover_path and os.path.exists(cover_path):
            logger.info("[Selenium] 已完成封面弹窗流程，跳过重复封面上传步骤")
        else:
            logger.warning("[Selenium] 未提供封面路径，跳过封面上传")
        
        
        
        # 5. 填写标题
        logger.info("[Selenium] 步骤5: 填写标题...")
        
        # 检查浏览器窗口是否仍然打开
        try:
            current_url = driver.current_url
            logger.info(f"[Selenium] 当前URL: {current_url}")
        except Exception as e:
            logger.error(f"[Selenium] 浏览器窗口已关闭: {e}")
            raise Exception("浏览器窗口已关闭，无法继续填写标题")
        
        # 等待页面稳定（完成按钮点击后可能需要时间）
        logger.info("[Selenium] 等待页面稳定（3秒）...")
        _pause_short(reason="填写标题前等待页面稳定")
        
        title_selectors = {
            "xpath": [
                "//input[contains(@placeholder, '标题')]",
                "//textarea[contains(@placeholder, '标题')]",
                "//input[@placeholder]",
                "//textarea[@placeholder]"
            ],
            "css": [
                "input[placeholder*='标题']",
                "textarea[placeholder*='标题']"
            ]
        }
        title_input = find_element_with_multiple_selectors(title_selectors, timeout=15)
        if title_input:
            # 再次检查窗口状态
            try:
                driver.current_url
            except:
                logger.error("[Selenium] 浏览器窗口在查找标题输入框时被关闭")
                raise Exception("浏览器窗口已关闭")
            
            # 滚动到元素可见，避免被canvas遮挡
            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", title_input)
                _pause_short(reason="滚动到标题输入框后等待稳定")
            except:
                pass
            
            # 尝试点击，如果被遮挡则使用JavaScript
            try:
                title_input.click()
            except:
                # 如果普通点击失败（被遮挡），使用JavaScript点击
                driver.execute_script("arguments[0].click();", title_input)
                logger.info("[Selenium] 使用JavaScript点击标题输入框（避免被遮挡）")
            
            _pause_tiny(reason="聚焦标题输入框后缓冲")
            title_input.clear()
            title_input.send_keys(title)
            logger.info("[Selenium] 标题已填写")
            _pause_short(reason="填写标题后等待页面处理")
        else:
            logger.warning("[Selenium] 未找到标题输入框，继续执行...")
        
        # 6. 填写描述
        logger.info("[Selenium] ========== 步骤6: 填写描述 ==========")
        desc_selectors = {
            "xpath": [
                "//div[@role='textbox' or @contenteditable='true']",
                "//textarea[contains(@placeholder, '作品介绍') or contains(@placeholder, '描述')]",
                "//div[contains(@class, 'DraftEditor-root')]"
            ],
            "css": [
                "div[contenteditable='true']",
                "textarea[placeholder*='作品介绍']"
            ]
        }
        desc_input = find_element_with_multiple_selectors(desc_selectors, timeout=10)
        if desc_input:
            # 滚动到元素可见，避免被canvas遮挡
            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", desc_input)
                _pause_short(reason="滚动到描述输入框后等待稳定")
            except:
                pass
            
            # 尝试点击，如果被遮挡则使用JavaScript
            try:
                desc_input.click()
            except:
                # 如果普通点击失败（被遮挡），使用JavaScript点击
                driver.execute_script("arguments[0].click();", desc_input)
                logger.info("[Selenium] 使用JavaScript点击描述输入框（避免被遮挡）")
            
            _pause_tiny(reason="聚焦描述输入框后缓冲")
            if desc_input.tag_name == 'div':
                # 对于contenteditable的div，使用JavaScript设置文本
                driver.execute_script("arguments[0].innerText = arguments[1];", desc_input, description)
            else:
                desc_input.clear()
                desc_input.send_keys(description)
            logger.info("[Selenium] 描述已填写")
            _pause_short(reason="填写描述后等待页面处理")
        else:
            logger.warning("[Selenium] 未找到描述输入框，继续执行...")
        
        # 7. 点击发布按钮（找不到就等，避免误点）
        logger.info("[Selenium] ========== 步骤7: 点击发布按钮 ==========")

        def _handle_skip_and_finish_again() -> bool:
            """
            在发布阶段再次处理可能出现的“暂不设置”弹窗，并补点一次“完成”按钮。
            返回值：True 表示成功处理过一次对话框并补点完成；False 表示未检测到或处理失败。
            """
            try:
                # 点击“暂不设置”
                logger.info("[Selenium] 再次检查是否出现'暂不设置'弹窗（动态定位）...")
                if not _try_click_span_button_by_text("暂不设置", timeout_sec=6):
                    logger.info("[Selenium] 当前未检测到'暂不设置'弹窗")
                    return False
                logger.info("[Selenium] ✅ 已点击'暂不设置'按钮（发布阶段，动态定位）")
                _pause_short(reason="发布阶段点击暂不设置后等待页面响应")

                # 你刚补的逻辑：先检查标题/描述输入框是否已可见；可见则直接进入填写，不强制补点“完成”
                def _main_inputs_visible() -> bool:
                    try:
                        # 标题输入框（与步骤5复用相同判断口径）
                        title_candidates = driver.find_elements(By.XPATH, "//input[contains(@placeholder, '标题')]") + \
                            driver.find_elements(By.XPATH, "//textarea[contains(@placeholder, '标题')]")
                        title_ok = any(el.is_displayed() for el in title_candidates)

                        # 描述输入框（与步骤6复用相同判断口径）
                        desc_candidates = driver.find_elements(By.XPATH, "//div[@role='textbox' or @contenteditable='true']") + \
                            driver.find_elements(By.XPATH, "//textarea[contains(@placeholder, '作品介绍') or contains(@placeholder, '描述')]") + \
                            driver.find_elements(By.XPATH, "//div[contains(@class, 'DraftEditor-root')]")
                        desc_ok = any(el.is_displayed() for el in desc_candidates)

                        return bool(title_ok and desc_ok)
                    except Exception:
                        return False

                if _main_inputs_visible():
                    logger.info("[Selenium] ✅ 已可见标题/描述输入框，跳过补点'完成'，直接进入填写流程")
                    return True

                # 看不到输入框：再补点一次“完成”按钮，避免对话框残留影响
                logger.info("[Selenium] 暂未看到标题/描述输入框，尝试再次点击'完成'按钮以稳定页面...")
                try:
                    buttons = driver.find_elements(By.TAG_NAME, "button")
                    for i, btn in enumerate(buttons):
                        try:
                            txt = btn.text.strip()
                            if "完成" not in txt:
                                continue
                            logger.info(f"[Selenium] 发布阶段再次找到'完成'按钮 {i+1}: '{txt}'，尝试点击...")
                            try:
                                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                                _pause_tiny(reason="发布阶段滚动到完成按钮后缓冲")
                                btn.click()
                            except Exception:
                                driver.execute_script("arguments[0].click();", btn)
                            logger.info("[Selenium] ✅ 发布阶段已补点'完成'按钮")
                            _pause_short(reason="发布阶段补点完成后等待页面响应")
                            return True
                        except Exception:
                            continue
                except Exception as e:
                    logger.warning(f"[Selenium] 发布阶段再次点击'完成'按钮时出错: {e}")
            except Exception as e:
                logger.warning(f"[Selenium] 处理'暂不设置'弹窗时出错: {e}")
            return False

        try:
            # 关键：只允许“精确文本=发布”，明确排除“高清发布/发布视频/一键发布”等同名干扰按钮
            publish_button_xpath = (
                "//button[normalize-space(.)='发布' "
                "and not(contains(normalize-space(.), '高清发布')) "
                "and not(contains(normalize-space(.), '发布视频')) "
                "and not(contains(normalize-space(.), '一键发布'))]"
            )

            # 部分页面需要先滚动到底部，最终发布按钮才会加载/进入可点击区域
            try:
                logger.info("[Selenium] 发布前执行到底部滚动，确保发布按钮在视区内...")
                last_scroll_y = -1
                for i in range(12):
                    driver.execute_script("window.scrollTo(0, document.documentElement.scrollHeight);")
                    human_sleep(0.28, 0.85, reason="发布前滚动缓冲")
                    # 额外发送 PAGE_DOWN，兼容容器滚动而不是 window 滚动
                    try:
                        from selenium.webdriver.common.keys import Keys
                        body = driver.find_element(By.TAG_NAME, "body")
                        body.send_keys(Keys.PAGE_DOWN)
                    except Exception:
                        pass
                    # 尝试滚动主容器（有些页面并非 window 滚动）
                    try:
                        driver.execute_script(
                            "var els=document.querySelectorAll('main,section,div');"
                            "for (var i=0;i<els.length;i++){"
                            " var e=els[i];"
                            " if(e && e.scrollHeight>e.clientHeight+80){e.scrollTop=e.scrollHeight;}"
                            "}"
                        )
                    except Exception:
                        pass
                    cur_scroll_y = driver.execute_script("return window.pageYOffset || document.documentElement.scrollTop || 0;")
                    doc_h = driver.execute_script("return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);")
                    inner_h = driver.execute_script("return window.innerHeight || document.documentElement.clientHeight || 0;")
                    logger.info(f"[Selenium] 发布前滚动第{i+1}/12次")
                    if cur_scroll_y == last_scroll_y and (cur_scroll_y + inner_h) >= (doc_h - 8):
                        logger.info("[Selenium] 已到页面底部附近，停止额外滚动")
                        break
                    last_scroll_y = cur_scroll_y
            except Exception as e:
                logger.warning(f"[Selenium] 发布前滚动失败（继续尝试点击）: {e}")

            # 等待发布按钮出现（放在滚动之后，避免先抓到顶部错误按钮）
            WebDriverWait(driver, 120).until(
                EC.presence_of_element_located((By.XPATH, publish_button_xpath))
            )
            _pause_tiny(reason="检测到发布按钮后缓冲")

            # 优先选择“页面最底部”的那个精确“发布”按钮（通常是最终提交按钮）
            def _get_bottom_publish_button():
                buttons = driver.find_elements(By.XPATH, publish_button_xpath)
                visible = []
                for b in buttons:
                    try:
                        if b.is_displayed():
                            visible.append(b)
                    except Exception:
                        continue
                if not visible:
                    return None
                # 优先选择靠近文档底部的“发布”按钮；没有则退回可见区域最靠下的按钮
                doc_h = driver.execute_script("return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);")
                near_bottom = []
                for b in visible:
                    try:
                        y = b.location.get("y", 0)
                        if y >= doc_h * 0.6:
                            near_bottom.append(b)
                    except Exception:
                        continue
                bucket = near_bottom if near_bottom else visible
                chosen = max(bucket, key=lambda x: x.location.get("y", 0))
                try:
                    # 输出候选日志，便于确认没有误选“高清发布”区域
                    for idx, b in enumerate(visible):
                        txt = (b.text or "").strip()
                        y = b.location.get("y", -1)
                        logger.info(f"[Selenium] 发布候选按钮[{idx+1}] text='{txt}' y={y}")
                    logger.info(f"[Selenium] 已选择最终发布候选 text='{(chosen.text or '').strip()}' y={chosen.location.get('y', -1)}")
                except Exception:
                    pass
                return chosen

            # 多策略点击发布：普通点击 -> JS点击 -> ActionChains（每次都重新定位，避免 stale）
            clicked = False
            last_click_err = None
            for attempt in range(1, 6):
                try:
                    publish_button = _get_bottom_publish_button()
                    if publish_button is None:
                        publish_button = WebDriverWait(driver, 20).until(
                            EC.element_to_be_clickable((By.XPATH, publish_button_xpath))
                        )
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", publish_button)
                    human_sleep(0.25, 0.95, reason="滚动到发布按钮后缓冲")
                    publish_button.click()
                    clicked = True
                    logger.info(f"[Selenium] ✅ 已点击'发布'按钮（普通点击，第{attempt}次）")
                    break
                except Exception as e1:
                    last_click_err = e1
                    try:
                        publish_button = _get_bottom_publish_button() or driver.find_element(By.XPATH, publish_button_xpath)
                        driver.execute_script("arguments[0].scrollIntoView({block: 'end'});", publish_button)
                        driver.execute_script("arguments[0].click();", publish_button)
                        clicked = True
                        logger.info(f"[Selenium] ✅ 已点击'发布'按钮（JS点击，第{attempt}次）")
                        break
                    except Exception as e2:
                        last_click_err = e2
                        try:
                            publish_button = _get_bottom_publish_button() or driver.find_element(By.XPATH, publish_button_xpath)
                            ActionChains(driver).move_to_element(publish_button).click().perform()
                            clicked = True
                            logger.info(f"[Selenium] ✅ 已点击'发布'按钮（ActionChains，第{attempt}次）")
                            break
                        except Exception as e3:
                            last_click_err = e3
                            human_sleep(0.8, 2.2, reason="发布按钮点击重试间隔")

            if not clicked:
                raise Exception(f"发布按钮点击失败（多策略重试后仍失败）: {last_click_err}")

            human_sleep(5, 13, reason="发布后等待页面处理")
            current_url = driver.current_url
            logger.info(f"[Selenium] 点击'发布'后当前URL: {current_url}")

            # 成功判据放宽：URL离开上传页，或页面出现“发布成功/审核中/处理中”等提示
            page_text = ""
            try:
                page_text = (driver.find_element(By.TAG_NAME, "body").text or "")[:3000]
            except Exception:
                pass
            if (
                ('upload' not in current_url.lower())
                or ('success' in current_url.lower())
                or ('发布成功' in page_text)
                or ('审核中' in page_text)
                or ('处理中' in page_text)
                or ('已提交' in page_text)
            ):
                logger.info("[Selenium] 发布成功！准备关闭浏览器...")
                try:
                    driver.quit()
                except Exception:
                    pass
                finally:
                    driver = None
                return f"视频发布成功！\n标题: {title}\n描述: {description}\n当前URL: {current_url}"

            return "已点击'发布'按钮，但未检测到明确成功信号（请人工确认）"
        except Exception as e:
            return f"未完成'发布'动作（已重试点击并等待，当前停止以避免误点）：{e}"
        
    except Exception as e:
        logger.error(f"[Selenium] 发布失败: {e}")
        import traceback
        traceback.print_exc()
        return f"发布失败: {e}"

def _check_browser_status_impl() -> str:
    """检查浏览器状态"""
    global driver
    
    try:
        if driver is None:
            return "浏览器未启动"
        
        try:
            current_url = driver.current_url
            return f"浏览器运行正常\n当前URL: {current_url}"
        except:
            return "浏览器已关闭"
    
    except Exception as e:
        return f"检查浏览器状态时出错: {str(e)}"

# MCP 工具包装
@mcp.tool()
def publish_video(
    video_path: str,
    title: str,
    description: str,
    cover_path: Optional[str] = None
) -> str:
    """发布视频到抖音（MCP 工具包装）"""
    return _publish_video_impl(video_path, title, description, cover_path)

@mcp.tool()
def check_browser_status() -> str:
    """检查浏览器状态（MCP 工具包装）"""
    return _check_browser_status_impl()

if __name__ == "__main__":
    # 初始化并运行服务器
    logger.info("=" * 70)
    logger.info("启动抖音发布 MCP Server（Selenium方式）...")
    logger.info("=" * 70)
    logger.info("请在 MCP Client（如 Claude Desktop）中配置此服务器")
    logger.info("=" * 70)
    mcp.run(transport='stdio')
