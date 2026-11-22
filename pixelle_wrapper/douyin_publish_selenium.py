"""
抖音发布 - 使用 Selenium 实现（基于之前的成功方式）
"""
import logging
import time
import random
import os
from typing import Dict, Any, Optional
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
import yaml

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

# 全局变量
driver = None

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
    
    # 默认配置
    return {
        'chrome_path': "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
        'profile_directory': "Profile 3"
    }

def start_browser(user_data_dir: str = None, profile_directory: str = None) -> bool:
    """
    启动浏览器
    
    Args:
        user_data_dir: Chrome 用户数据目录
        profile_directory: Profile 目录名称
    
    Returns:
        bool: 是否成功启动
    """
    global driver
    
    if driver:
        logger.info("[Selenium] 浏览器已启动")
        return True
    
    try:
        browser_config = load_browser_config()
        
        # 如果没有提供，使用配置文件的
        if not user_data_dir:
            # Chrome 用户数据目录
            user_data_dir = os.path.expanduser(
                os.path.join("~", "AppData", "Local", "Google", "Chrome", "User Data")
            )
            user_data_dir = os.path.expandvars(
                user_data_dir.replace("~", os.environ.get("USERPROFILE", ""))
            )
        
        if not profile_directory:
            profile_directory = browser_config.get('profile_directory', 'Profile 3')
        
        logger.info(f"[Selenium] 启动浏览器，使用 Profile: {profile_directory}")
        logger.info(f"[Selenium] 用户数据目录: {user_data_dir}")
        
        # 设置Chrome选项
        options = webdriver.ChromeOptions()
        options.binary_location = browser_config.get('chrome_path', "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe")
        
        # 基础选项
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-extensions")
        
        # 关闭自动化提示
        options.add_experimental_option('excludeSwitches', ['enable-automation'])
        options.add_experimental_option('useAutomationExtension', False)
        
        # 使用用户数据目录
        if user_data_dir:
            options.add_argument(f"--user-data-dir={user_data_dir}")
            options.add_argument(f"--profile-directory={profile_directory}")
        
        # 其他选项
        options.add_argument("--start-maximized")
        options.add_argument("--disable-notifications")
        options.add_argument("--window-size=1920,1080")
        
        # 创建WebDriver
        try:
            service = Service(ChromeDriverManager().install())
        except:
            # 如果WebDriverManager失败，尝试使用系统PATH中的chromedriver
            service = Service()
        
        logger.info("[Selenium] 正在创建Chrome WebDriver实例...")
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(60)
        logger.info("[Selenium] 浏览器启动成功")
        
        return True
        
    except Exception as e:
        logger.error(f"[Selenium] 启动浏览器失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def find_element_with_multiple_selectors(selectors_dict: Dict[str, list], timeout: int = 10) -> Optional[Any]:
    """
    使用多种选择器尝试查找元素
    
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

def publish_video_selenium(
    video_path: str,
    title: str,
    description: str,
    cover_path: Optional[str] = None
) -> str:
    """
    使用 Selenium 发布视频到抖音
    
    Args:
        video_path: 视频文件路径
        title: 视频标题
        description: 视频描述
        cover_path: 封面图片路径（可选）
    
    Returns:
        发布结果描述
    """
    global driver
    
    try:
        # 1. 启动浏览器
        logger.info("[Selenium] 步骤1: 启动浏览器...")
        if not start_browser():
            return "浏览器启动失败"
        
        # 2. 导航到上传页面
        logger.info("[Selenium] 步骤2: 导航到上传页面...")
        driver.get("https://creator.douyin.com/creator-micro/content/upload")
        human_sleep(5, 13, reason="等待页面加载")
        
        # 3. 上传视频
        logger.info("[Selenium] 步骤3: 上传视频...")
        try:
            file_input = driver.find_element(By.CSS_SELECTOR, "input[type='file']")
            file_input.send_keys(os.path.abspath(video_path))
            logger.info("[Selenium] 视频已上传")
        except Exception as e:
            logger.error(f"[Selenium] 上传视频失败: {e}")
            return f"上传视频失败: {e}"
        
        # 等待视频处理
        logger.info("[Selenium] 等待视频处理...")
        human_sleep(15, 25, reason="等待视频处理")
        
        # 4. 选择封面（按你提供的流程）
        logger.info("[Selenium] 步骤4: 选择封面...")
        
        # 4.1 点击"选择封面"
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
            cover_button.click()
            logger.info("[Selenium] 已点击'选择封面'")
            time.sleep(2)
        else:
            logger.warning("[Selenium] 未找到'选择封面'按钮，继续执行...")
        
        # 4.2 点击"标题"
        title_selectors = {
            "xpath": [
                "//div[@class='icon-name-Fi8gxR' and contains(text(), '标题')]",
                "//div[contains(@class, 'icon-name-Fi8gxR')]",
                "//div[contains(text(), '标题')]"
            ],
            "css": [
                "div.icon-name-Fi8gxR"
            ]
        }
        title_button = find_element_with_multiple_selectors(title_selectors, timeout=10)
        if title_button:
            title_button.click()
            logger.info("[Selenium] 已点击'标题'")
            time.sleep(1)
        else:
            logger.warning("[Selenium] 未找到'标题'按钮，继续执行...")
        
        # 4.3 点击canvas中间区域
        try:
            canvas = driver.find_element(By.CSS_SELECTOR, "canvas.cloudImage-N0ai8Y.lower-canvas")
            if canvas:
                # 获取canvas的位置和大小
                location = canvas.location
                size = canvas.size
                center_x = location['x'] + size['width'] / 2
                center_y = location['y'] + size['height'] / 2
                
                # 使用ActionChains点击中间
                from selenium.webdriver.common.action_chains import ActionChains
                actions = ActionChains(driver)
                actions.move_to_element_with_offset(canvas, size['width']/2, size['height']/2).click().perform()
                logger.info("[Selenium] 已点击canvas中间区域")
                time.sleep(1)
        except Exception as e:
            logger.warning(f"[Selenium] 点击canvas失败: {e}")
        
        # 4.4 上传封面文件
        if cover_path and os.path.exists(cover_path):
            logger.info(f"[Selenium] 上传封面文件: {cover_path}")
            try:
                # 查找文件输入框（可能是新出现的）
                file_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
                for file_input in file_inputs:
                    try:
                        file_input.send_keys(os.path.abspath(cover_path))
                        logger.info("[Selenium] 封面文件已上传")
                        time.sleep(2)
                        break
                    except:
                        continue
            except Exception as e:
                logger.warning(f"[Selenium] 上传封面失败: {e}")
        else:
            logger.warning("[Selenium] 未提供封面路径，跳过封面上传")
        
        # 4.5 输入文字（如果有输入框）
        # 这里可能需要根据实际情况调整
        
        # 4.6 点击"确定"按钮 - 使用完整的XPath路径（4层div）
        logger.info("[Selenium] 点击'确定'按钮...")
        logger.info("[Selenium] 等待对话框完全加载（额外等待3秒）...")
        time.sleep(3)  # 额外等待，确保对话框完全加载
        
        # 先等待 dialog-0 出现
        logger.info("[Selenium] 等待对话框容器 dialog-0 出现...")
        try:
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            dialog_container = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//*[@id='dialog-0']"))
            )
            logger.info("[Selenium] 对话框容器 dialog-0 已找到")
        except Exception as e:
            logger.error(f"[Selenium] 未找到对话框容器 dialog-0: {e}")
            dialog_container = None
        
        # 使用完整的XPath路径定位确定按钮（4层div）
        confirm_selectors = {
            "xpath": [
                # 完整路径：//*[@id="dialog-0"]/div/div/div/div[4]/button[2]
                "//*[@id='dialog-0']/div/div/div/div[4]/button[2]",
                # 备用：在 dialog-0 内部查找确定按钮
                "//*[@id='dialog-0']//button[contains(text(), '确定')]",
                "//*[@id='dialog-0']//button[contains(@class, 'primary') and contains(text(), '确定')]",
                # 如果 dialog-0 不存在，尝试全局查找
                "//button[contains(@class, 'button-dhIUZE') and contains(@class, 'primary') and contains(text(), '确定')]",
                "//button[contains(@class, 'button-dhlUZE') and contains(@class, 'primary') and contains(text(), '确定')]",
                "//button[contains(text(), '确定')]"
            ],
            "css": [
                "#dialog-0 > div > div > div > div:nth-child(4) > button:nth-child(2)",
                "#dialog-0 button.primary",
                "button.button-dhIUZE.primary",
                "button.button-dhlUZE.primary"
            ]
        }
        confirm_button = find_element_with_multiple_selectors(confirm_selectors, timeout=15)
        if confirm_button:
            logger.info("[Selenium] 找到'确定'按钮，准备点击...")
            try:
                # 滚动到按钮可见
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", confirm_button)
                time.sleep(0.5)
                confirm_button.click()
                logger.info("[Selenium] 已点击'确定'按钮")
            except Exception as e:
                logger.warning(f"[Selenium] 普通点击失败，尝试JavaScript点击: {e}")
                driver.execute_script("arguments[0].click();", confirm_button)
                logger.info("[Selenium] 已使用JavaScript点击'确定'按钮")
            time.sleep(2)
        else:
            logger.error("[Selenium] 未找到'确定'按钮！")
            # 调试：查找所有按钮
            try:
                all_buttons = driver.find_elements(By.TAG_NAME, "button")
                logger.info(f"[Selenium] 页面上共有 {len(all_buttons)} 个按钮")
                for i, btn in enumerate(all_buttons[:15]):  # 显示前15个
                    try:
                        btn_text = btn.text
                        btn_class = btn.get_attribute("class")
                        btn_id = btn.get_attribute("id")
                        logger.info(f"[Selenium] 按钮 {i+1}: 文本='{btn_text}', class='{btn_class}', id='{btn_id}'")
                    except:
                        pass
            except Exception as e:
                logger.warning(f"[Selenium] 查找按钮失败: {e}")
            logger.warning("[Selenium] 未找到'确定'按钮，继续执行...")
        
        # 4.7 点击"完成"按钮
        finish_selectors = {
            "xpath": [
                "//span[@class='semi-button-content' and contains(text(), '完成')]",
                "//span[contains(@class, 'semi-button-content') and contains(text(), '完成')]",
                "//span[contains(text(), '完成')]"
            ],
            "css": [
                "span.semi-button-content"
            ]
        }
        finish_button = find_element_with_multiple_selectors(finish_selectors, timeout=10)
        if finish_button:
            finish_button.click()
            logger.info("[Selenium] 已点击'完成'按钮")
            time.sleep(2)
        else:
            logger.warning("[Selenium] 未找到'完成'按钮，继续执行...")
        
        # 5. 填写标题
        logger.info("[Selenium] 步骤5: 填写标题...")
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
        title_input = find_element_with_multiple_selectors(title_selectors, timeout=10)
        if title_input:
            title_input.click()
            time.sleep(0.5)
            title_input.clear()
            title_input.send_keys(title)
            logger.info("[Selenium] 标题已填写")
            time.sleep(1)
        else:
            logger.warning("[Selenium] 未找到标题输入框，继续执行...")
        
        # 6. 填写描述
        logger.info("[Selenium] 步骤6: 填写描述...")
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
            desc_input.click()
            time.sleep(0.5)
            if desc_input.tag_name == 'div':
                # 对于contenteditable的div，使用JavaScript设置文本
                driver.execute_script("arguments[0].innerText = arguments[1];", desc_input, description)
            else:
                desc_input.clear()
                desc_input.send_keys(description)
            logger.info("[Selenium] 描述已填写")
            time.sleep(1)
        else:
            logger.warning("[Selenium] 未找到描述输入框，继续执行...")
        
        # 7. 点击发布按钮
        logger.info("[Selenium] 步骤7: 点击发布按钮...")
        publish_selectors = {
            "xpath": [
                "//button[contains(text(), '发布')]",
                "//button[@type='submit']",
                "//button[contains(text(), '发布视频')]"
            ],
            "css": [
                "button:contains('发布')"
            ]
        }
        publish_button = find_element_with_multiple_selectors(publish_selectors, timeout=10)
        if publish_button:
            publish_button.click()
            logger.info("[Selenium] 已点击'发布'按钮")
            human_sleep(5, 13, reason="发布后等待页面处理")
            
            # 检查发布是否成功
            current_url = driver.current_url
            if 'upload' not in current_url.lower() or 'success' in current_url.lower():
                logger.info("[Selenium] 发布成功！")
                return f"视频发布成功！\n标题: {title}\n描述: {description}\n当前URL: {current_url}"
            else:
                return "发布按钮已点击，请手动确认是否发布成功"
        else:
            return "未找到'发布'按钮"
        
    except Exception as e:
        logger.error(f"[Selenium] 发布失败: {e}")
        import traceback
        traceback.print_exc()
        return f"发布失败: {e}"

def close_browser():
    """关闭浏览器"""
    global driver
    if driver:
        try:
            driver.quit()
        except:
            pass
        finally:
            driver = None

if __name__ == "__main__":
    # 测试
    import asyncio
    
    # 查找测试视频
    output_dir = Path(__file__).parent / "output"
    video_path = None
    if output_dir.exists():
        task_dirs = sorted([d for d in output_dir.iterdir() if d.is_dir()], 
                          key=lambda x: x.stat().st_mtime, reverse=True)
        for task_dir in task_dirs:
            final_video = task_dir / "final.mp4"
            if final_video.exists():
                video_path = str(final_video)
                break
    
    if video_path:
        result = publish_video_selenium(
            video_path=video_path,
            title="测试视频 - Selenium方式",
            description="这是使用Selenium方式发布的测试视频"
        )
        print(result)
        
        # 保持浏览器打开
        input("按回车键关闭浏览器...")
        close_browser()
    else:
        print("未找到测试视频")

