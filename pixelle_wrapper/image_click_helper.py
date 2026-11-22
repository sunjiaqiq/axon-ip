"""
图像识别点击辅助函数
用于识别和点击红色"确定"按钮
"""
import logging
import time
from typing import Optional, Tuple
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

logger = logging.getLogger(__name__)


def click_confirm_by_color_and_text(driver: webdriver.Chrome, timeout: int = 15) -> bool:
    """
    通过颜色和文字识别点击"确定"按钮
    结合Selenium元素定位和颜色验证
    
    Args:
        driver: Selenium WebDriver实例
        timeout: 超时时间（秒）
    
    Returns:
        bool: 是否成功点击
    """
    logger.info("[ImageClick] 使用颜色+文字识别点击'确定'按钮...")
    
    try:
        # 等待对话框出现
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, "//*[@id='dialog-0']"))
        )
        
        # 查找所有按钮
        buttons = driver.find_elements(By.TAG_NAME, "button")
        logger.info(f"[ImageClick] 找到 {len(buttons)} 个按钮")
        
        for button in buttons:
            try:
                # 检查按钮文本
                button_text = button.text.strip()
                if "确定" not in button_text:
                    continue
                
                # 检查按钮颜色（通过计算样式）
                bg_color = driver.execute_script("""
                    var style = window.getComputedStyle(arguments[0]);
                    return style.backgroundColor;
                """, button)
                
                logger.info(f"[ImageClick] 按钮文本: '{button_text}', 背景色: {bg_color}")
                
                # 检查是否是红色（rgb(254, 44, 85) 或类似）
                if "254" in bg_color or "255" in bg_color or "rgb(254" in bg_color or "rgb(255" in bg_color:
                    # 检查class是否包含primary
                    button_class = button.get_attribute("class") or ""
                    if "primary" in button_class.lower():
                        logger.info(f"[ImageClick] ✅ 找到红色'确定'按钮，准备点击...")
                        button.click()
                        logger.info("[ImageClick] ✅ 已点击'确定'按钮")
                        return True
                        
            except Exception as e:
                logger.debug(f"[ImageClick] 检查按钮失败: {e}")
                continue
        
        logger.warning("[ImageClick] 未找到红色'确定'按钮")
        return False
        
    except Exception as e:
        logger.error(f"[ImageClick] 颜色+文字识别失败: {e}")
        return False


def save_confirm_button_screenshot(driver: webdriver.Chrome, save_path: str = "confirm_button.png") -> bool:
    """
    保存"确定"按钮的截图，用于后续的图像匹配
    
    Args:
        driver: Selenium WebDriver实例
        save_path: 保存路径
    
    Returns:
        bool: 是否成功保存
    """
    try:
        # 先找到按钮元素
        confirm_selectors = {
            "xpath": [
                "//*[@id='dialog-0']/div/div/div/div[4]/button[2]",
                "//button[contains(text(), '确定')]"
            ]
        }
        
        from douyin_publish_mcp import find_element_with_multiple_selectors
        button = find_element_with_multiple_selectors(confirm_selectors, timeout=10)
        
        if button:
            # 截取按钮区域
            screenshot = button.screenshot_as_png
            with open(save_path, 'wb') as f:
                f.write(screenshot)
            logger.info(f"[ImageClick] ✅ 已保存按钮截图到: {save_path}")
            return True
        else:
            logger.warning("[ImageClick] 未找到按钮，无法保存截图")
            return False
    except Exception as e:
        logger.error(f"[ImageClick] 保存按钮截图失败: {e}")
        return False


def click_confirm_by_color_and_text(driver: webdriver.Chrome, timeout: int = 15) -> bool:
    """
    通过颜色和文字识别点击"确定"按钮
    结合Selenium元素定位和颜色验证
    
    Args:
        driver: Selenium WebDriver实例
        timeout: 超时时间（秒）
    
    Returns:
        bool: 是否成功点击
    """
    logger.info("[ImageClick] 使用颜色+文字识别点击'确定'按钮...")
    
    try:
        # 等待对话框出现
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, "//*[@id='dialog-0']"))
        )
        
        # 查找所有按钮
        buttons = driver.find_elements(By.TAG_NAME, "button")
        logger.info(f"[ImageClick] 找到 {len(buttons)} 个按钮")
        
        for button in buttons:
            try:
                # 检查按钮文本
                button_text = button.text.strip()
                if "确定" not in button_text:
                    continue
                
                # 检查按钮颜色（通过计算样式）
                bg_color = driver.execute_script("""
                    var style = window.getComputedStyle(arguments[0]);
                    return style.backgroundColor;
                """, button)
                
                logger.info(f"[ImageClick] 按钮文本: '{button_text}', 背景色: {bg_color}")
                
                # 检查是否是红色（rgb(254, 44, 85) 或类似）
                if "254" in bg_color or "255" in bg_color or "rgb(254" in bg_color or "rgb(255" in bg_color:
                    # 检查class是否包含primary
                    button_class = button.get_attribute("class") or ""
                    if "primary" in button_class.lower():
                        logger.info(f"[ImageClick] ✅ 找到红色'确定'按钮，准备点击...")
                        button.click()
                        logger.info("[ImageClick] ✅ 已点击'确定'按钮")
                        return True
                        
            except Exception as e:
                logger.debug(f"[ImageClick] 检查按钮失败: {e}")
                continue
        
        logger.warning("[ImageClick] 未找到红色'确定'按钮")
        return False
        
    except Exception as e:
        logger.error(f"[ImageClick] 颜色+文字识别失败: {e}")
        return False

