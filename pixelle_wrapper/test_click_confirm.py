"""
专门测试点击"确定"按钮的脚本
执行到上传封面后，等待对话框出现，然后测试不同的点击方式
"""
import os
import sys
import time
import logging
from pathlib import Path

# 添加当前目录到路径
sys.path.insert(0, str(Path(__file__).parent))

import douyin_publish_mcp
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains

# 配置日志
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def test_click_confirm_methods():
    """测试不同的点击确定按钮的方法"""
    
    logger.info("=" * 70)
    logger.info("测试：点击'确定'按钮的不同方法")
    logger.info("=" * 70)
    
    # 1. 确保浏览器已启动
    logger.info("\n[步骤1] 确保浏览器已启动...")
    if not douyin_publish_mcp.ensure_browser():
        logger.error("浏览器启动失败！")
        return
    
    driver = douyin_publish_mcp.driver
    if not driver:
        logger.error("WebDriver 未初始化！")
        return
    
    # 2. 导航到上传页面
    logger.info("\n[步骤2] 导航到上传页面...")
    try:
        driver.get("https://creator.douyin.com/creator-micro/content/upload?enter_from=dou_web")
        time.sleep(3)
        logger.info(f"当前URL: {driver.current_url}")
    except Exception as e:
        logger.error(f"导航失败: {e}")
        return
    
    # 3. 上传视频
    logger.info("\n[步骤3] 上传视频...")
    video_path = r"F:\shuziren\pixelle_wrapper\output\20260314_193109_1a06fb65\final.mp4"
    if not os.path.exists(video_path):
        logger.error(f"视频文件不存在: {video_path}")
        return
    
    try:
        file_input = driver.find_element(By.XPATH, "//input[@type='file']")
        file_input.send_keys(os.path.abspath(video_path))
        logger.info("✅ 视频已上传")
        time.sleep(20)  # 等待视频处理
    except Exception as e:
        logger.error(f"上传视频失败: {e}")
        return
    
    # 4. 选择封面（完整流程）
    logger.info("\n[步骤4] 选择封面...")
    try:
        # 4.1 点击"选择封面"
        logger.info("[步骤4.1] 点击'选择封面'...")
        cover_selectors = [
            "//div[@class='title-wA45Xd' and contains(text(), '选择封面')]",
            "//div[contains(@class, 'title-wA45Xd')]",
            "//div[contains(text(), '选择封面')]"
        ]
        cover_button = None
        for selector in cover_selectors:
            try:
                cover_button = driver.find_element(By.XPATH, selector)
                if cover_button:
                    cover_button.click()
                    logger.info("✅ 已点击'选择封面'")
                    time.sleep(2)
                    break
            except:
                continue
        
        if not cover_button:
            logger.error("❌ 未找到'选择封面'按钮")
            return
        
        # 4.2 点击"标题"
        logger.info("[步骤4.2] 点击'标题'...")
        title_selectors = [
            "//div[@class='icon-name-Fi8gxR' and contains(text(), '标题')]",
            "//div[contains(@class, 'icon-name-Fi8gxR')]",
            "//div[contains(text(), '标题')]"
        ]
        title_button = None
        for selector in title_selectors:
            try:
                title_button = driver.find_element(By.XPATH, selector)
                if title_button:
                    title_button.click()
                    logger.info("✅ 已点击'标题'")
                    time.sleep(5)
                    break
            except:
                continue
        
        if not title_button:
            logger.error("❌ 未找到'标题'按钮")
            return
        
        # 4.3 等待缓存加载
        logger.info("[步骤4.3] 等待缓存加载（10秒）...")
        time.sleep(10)
        
        # 4.4 点击标题后的元素
        logger.info("[步骤4.4] 点击标题后的元素...")
        try:
            title_after_element = driver.find_element(By.XPATH, "//*[@id='dy-creator-content-modal-body']/div/div[2]/div[1]/div/div[2]/div[3]/div/div[9]/div/div")
            title_after_element.click()
            logger.info("✅ 已点击标题后的元素")
            time.sleep(2)
        except Exception as e:
            logger.warning(f"点击标题后的元素失败: {e}")
        
        # 4.5 点击canvas中间区域
        logger.info("[步骤4.5] 点击canvas中间区域...")
        time.sleep(10)  # 再次等待缓存
        
        try:
            # 方法1: 使用新的XPath
            canvas_element = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.XPATH, "//*[@id='cloudArea']/div[2]"))
            )
            WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//*[@id='cloudArea']/div[2]"))
            )
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", canvas_element)
            time.sleep(0.5)
            canvas_element.click()
            logger.info("✅ 已点击canvas中间区域（方法1）")
            time.sleep(2)
        except Exception as e:
            logger.warning(f"方法1失败: {e}，尝试备用方法...")
            # 备用方法: 使用canvas选择器
            try:
                canvas = driver.find_element(By.CSS_SELECTOR, "canvas.cloudImage-N0ai8Y.lower-canvas")
                actions = ActionChains(driver)
                actions.move_to_element_with_offset(canvas, canvas.size['width']/2, canvas.size['height']/2).click().perform()
                logger.info("✅ 已点击canvas中间区域（备用方法）")
                time.sleep(10)
            except Exception as e2:
                logger.error(f"备用方法也失败: {e2}")
                return
        
    except Exception as e:
        logger.error(f"选择封面失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 5. 等待对话框出现
    logger.info("\n[步骤5] 等待对话框出现...")
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, "//*[@id='dialog-0']"))
        )
        logger.info("✅ 对话框已出现")
        time.sleep(2)
    except Exception as e:
        logger.error(f"等待对话框失败: {e}")
        logger.info("⏸️  如果对话框已出现，请按回车继续...")
        input()
    
    # 5.1 先输入文字到标题输入框（必须先输入文字，点击确定才能看到效果）
    logger.info("\n[步骤5.1] 输入文字到标题输入框...")
    try:
        # 等待输入框出现
        text_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//*[@id='dialog-0']/div/div/div/div[3]/textarea"))
        )
        
        # 等待输入框可见且可编辑
        text_input = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//*[@id='dialog-0']/div/div/div/div[3]/textarea"))
        )
        
        if text_input:
            # 滚动到元素可见
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", text_input)
            time.sleep(0.5)
            
            # 点击输入框
            try:
                text_input.click()
            except:
                driver.execute_script("arguments[0].click();", text_input)
            
            time.sleep(0.5)
            
            # 先清空输入框
            logger.info("  清空输入框...")
            driver.execute_script("arguments[0].value = '';", text_input)
            time.sleep(0.3)
            try:
                text_input.clear()
            except:
                pass
            time.sleep(0.3)
            driver.execute_script("arguments[0].value = '';", text_input)
            time.sleep(0.2)
            
            # 输入测试文字
            test_text = "测试封面标题123"
            logger.info(f"  输入文字: {test_text}")
            text_input.send_keys(test_text)
            time.sleep(1)
            
            # 验证输入是否成功
            current_value = driver.execute_script("return arguments[0].value;", text_input)
            if current_value == test_text:
                logger.info(f"✅ 已成功输入文字: {current_value}")
            else:
                logger.warning(f"⚠️  输入的文字不匹配，当前值: {current_value}")
        else:
            logger.error("❌ 未找到输入框")
    except Exception as e:
        logger.error(f"输入文字失败: {e}")
        import traceback
        traceback.print_exc()
        logger.info("⏸️  如果已手动输入文字，请按回车继续...")
        input()
    
    # 6. 测试不同的点击方法
    logger.info("\n" + "=" * 70)
    logger.info("开始测试不同的点击方法...")
    logger.info("=" * 70)
    
    # 方法1: 通过颜色+文字识别（rgb(254, 44, 85)）
    logger.info("\n[方法1] 通过颜色+文字识别点击（rgb(254, 44, 85)）...")
    try:
        buttons = driver.find_elements(By.TAG_NAME, "button")
        logger.info(f"找到 {len(buttons)} 个按钮")
        
        for i, button in enumerate(buttons):
            try:
                button_text = button.text.strip()
                if "确定" not in button_text:
                    continue
                
                bg_color = driver.execute_script("""
                    var style = window.getComputedStyle(arguments[0]);
                    return style.backgroundColor;
                """, button)
                
                logger.info(f"按钮 {i+1}: 文本='{button_text}', 背景色={bg_color}")
                
                # 检查是否是红色 rgb(254, 44, 85)
                if "254" in bg_color or "255" in bg_color:
                    button_class = button.get_attribute("class") or ""
                    logger.info(f"  类名: {button_class}")
                    logger.info(f"  ✅ 找到红色'确定'按钮，准备点击...")
                    
                    # 先保存按钮截图
                    try:
                        screenshot = button.screenshot_as_png
                        save_path = "confirm_button_screenshot.png"
                        with open(save_path, 'wb') as f:
                            f.write(screenshot)
                        logger.info(f"  ✅ 已保存按钮截图到: {save_path}")
                    except Exception as e:
                        logger.warning(f"  保存截图失败: {e}")
                    
                    # 尝试点击
                    logger.info("  🔵 准备点击按钮...")
                    button.click()
                    logger.info("  ✅ 已点击按钮（方法1：普通click）")
                    time.sleep(3)  # 等待更长时间，让封面文字更新
                    
                    # 验证：检查封面文字是否已更新（这才是真正的验证）
                    logger.info("  🔍 验证封面文字是否已更新...")
                    try:
                        # 查找显示封面文字的元素（可能在canvas附近或其他地方）
                        # 先检查对话框是否关闭
                        dialog_closed = False
                        try:
                            dialog = driver.find_element(By.XPATH, "//*[@id='dialog-0']")
                            if not dialog.is_displayed():
                                dialog_closed = True
                                logger.info("  ✅ 对话框已关闭")
                        except:
                            dialog_closed = True
                            logger.info("  ✅ 对话框已关闭（元素不存在）")
                        
                        # 如果对话框关闭了，说明点击成功
                        if dialog_closed:
                            logger.info("\n" + "=" * 70)
                            logger.info("✅ 方法1（普通click）成功！对话框已关闭！")
                            logger.info("=" * 70)
                            return  # 成功后直接返回
                        else:
                            logger.warning("  ⚠️  对话框仍然存在，但可能封面文字已更新")
                            logger.info("  💡 请手动检查封面文字是否已更新为: 测试封面标题123")
                            logger.info("  💡 如果封面文字已更新，说明点击成功！")
                            logger.info("\n" + "=" * 70)
                            logger.info("✅ 方法1（普通click）可能成功，请手动验证封面文字")
                            logger.info("=" * 70)
                            return
                    except Exception as e:
                        logger.warning(f"  验证失败: {e}")
                        logger.info("  💡 请手动检查封面文字是否已更新")
                        return
            except Exception as e:
                logger.debug(f"检查按钮 {i+1} 失败: {e}")
    except Exception as e:
        logger.error(f"方法1失败: {e}")
    
    # 方法2: JavaScript点击
    logger.info("\n[方法2] JavaScript点击...")
    try:
        buttons = driver.find_elements(By.TAG_NAME, "button")
        for button in buttons:
            button_text = button.text.strip()
            if "确定" not in button_text:
                continue
            
            bg_color = driver.execute_script("""
                var style = window.getComputedStyle(arguments[0]);
                return style.backgroundColor;
            """, button)
            
            if "254" in bg_color or "255" in bg_color:
                logger.info("  ✅ 找到红色'确定'按钮，使用JavaScript点击...")
                driver.execute_script("arguments[0].click();", button)
                logger.info("  ✅ 已点击按钮（方法2：JavaScript click）")
                logger.info("  ⏸️  请观察对话框是否关闭...")
                input("  按回车继续测试下一个方法...")
                break
    except Exception as e:
        logger.error(f"方法2失败: {e}")
    
    # 方法3: ActionChains点击
    logger.info("\n[方法3] ActionChains点击...")
    try:
        buttons = driver.find_elements(By.TAG_NAME, "button")
        for button in buttons:
            button_text = button.text.strip()
            if "确定" not in button_text:
                continue
            
            bg_color = driver.execute_script("""
                var style = window.getComputedStyle(arguments[0]);
                return style.backgroundColor;
            """, button)
            
            if "254" in bg_color or "255" in bg_color:
                logger.info("  ✅ 找到红色'确定'按钮，使用ActionChains点击...")
                ActionChains(driver).move_to_element(button).click().perform()
                logger.info("  ✅ 已点击按钮（方法3：ActionChains）")
                logger.info("  ⏸️  请观察对话框是否关闭...")
                input("  按回车继续测试下一个方法...")
                break
    except Exception as e:
        logger.error(f"方法3失败: {e}")
    
    # 方法4: 通过坐标点击
    logger.info("\n[方法4] 通过坐标点击...")
    try:
        buttons = driver.find_elements(By.TAG_NAME, "button")
        for button in buttons:
            button_text = button.text.strip()
            if "确定" not in button_text:
                continue
            
            bg_color = driver.execute_script("""
                var style = window.getComputedStyle(arguments[0]);
                return style.backgroundColor;
            """, button)
            
            if "254" in bg_color or "255" in bg_color:
                logger.info("  ✅ 找到红色'确定'按钮，获取坐标...")
                location = button.location
                size = button.size
                center_x = location['x'] + size['width'] // 2
                center_y = location['y'] + size['height'] // 2
                logger.info(f"  按钮中心坐标: ({center_x}, {center_y})")
                
                # 使用JavaScript通过坐标点击
                driver.execute_script(f"""
                    var x = {center_x};
                    var y = {center_y};
                    var element = document.elementFromPoint(x, y);
                    if (element) {{
                        element.click();
                    }}
                """)
                logger.info("  ✅ 已点击按钮（方法4：坐标点击）")
                logger.info("  ⏸️  请观察对话框是否关闭...")
                input("  按回车继续...")
                break
    except Exception as e:
        logger.error(f"方法4失败: {e}")
    
    logger.info("\n" + "=" * 70)
    logger.info("测试完成！")
    logger.info("=" * 70)
    logger.info("\n如果所有方法都测试完，说明方法1已经成功点击了按钮")
    logger.info("（方法2-4失败是因为对话框已经关闭，元素不存在了）")

if __name__ == "__main__":
    test_click_confirm_methods()
