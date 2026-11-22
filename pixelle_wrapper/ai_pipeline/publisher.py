"""
发布模块 - 使用 Playwright 自动上传视频到平台
使用统一的浏览器管理器，保持登录状态
"""
import logging
import asyncio
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from playwright.async_api import Page
    from ai_pipeline.browser_manager import browser_manager
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    logger.warning("Playwright 未安装，请安装: pip install playwright && playwright install")
    PLAYWRIGHT_AVAILABLE = False
    browser_manager = None


async def _publish_to_douyin_async(
    video_path: str, 
    title: str = "", 
    description: str = "",
    cover_path: Optional[str] = None
) -> bool:
    """
    异步上传视频到抖音（内部函数）
    使用统一的浏览器管理器，保持登录状态
    
    Args:
        video_path: 视频文件路径
        title: 视频标题
        description: 视频描述/介绍
        cover_path: 封面图片路径（可选，如果不提供则从视频提取）
    
    Returns:
        是否发布成功
    """
    """
    异步上传视频到抖音（内部函数）
    使用统一的浏览器管理器，保持登录状态
    
    Args:
        video_path: 视频文件路径
        title: 视频标题
        description: 视频描述/介绍
        cover_path: 封面图片路径（可选）
    
    Returns:
        是否发布成功
    """
    logger.info(f"[Publisher] 开始发布视频到抖音: {video_path}")
    logger.info(f"[Publisher] 标题: {title}")
    logger.info(f"[Publisher] 描述: {description}")
    logger.info(f"[Publisher] 封面: {cover_path}")
    
    if not PLAYWRIGHT_AVAILABLE or browser_manager is None:
        logger.error("[Publisher] Playwright 或浏览器管理器未可用")
        return False
    
    try:
        video_path = Path(video_path)
        if not video_path.exists():
            logger.error(f"[Publisher] 视频文件不存在: {video_path}")
            return False
        
        # 如果没有提供封面，从视频提取
        if not cover_path:
            logger.info("[Publisher] 未提供封面，从视频提取封面...")
            from ai_pipeline.cover_extractor import extract_cover_from_video
            cover_path_obj = extract_cover_from_video(str(video_path), video_path.parent)
            if cover_path_obj and cover_path_obj.exists():
                cover_path = str(cover_path_obj)
                logger.info(f"[Publisher] 封面提取成功: {cover_path}")
            else:
                logger.error("[Publisher] 封面提取失败，发布可能失败")
                return False
        else:
            cover_path_obj = Path(cover_path)
            if not cover_path_obj.exists():
                logger.error(f"[Publisher] 封面文件不存在: {cover_path}")
                return False
        
        # 尝试使用 Playwright 连接，如果失败则使用 pyautogui
        use_playwright = True
        page = None
        
        try:
            # 确保浏览器已初始化
            await browser_manager.ensure_initialized()
            
            # 从浏览器管理器获取上下文并创建新页面
            context = await browser_manager.get_page()
            page = await context.new_page()
            
            # 访问抖音创作中心
            logger.info("[Publisher] 访问抖音创作中心...")
            await page.goto("https://creator.douyin.com/creator-micro/content/upload", wait_until='domcontentloaded')
        except Exception as e:
            logger.warning(f"[Publisher] Playwright 连接失败: {e}")
            logger.info("[Publisher] 切换到 pyautogui 模式，直接操作已打开的浏览器...")
            use_playwright = False
            
            # 导入 pyautogui
            try:
                import pyautogui
                import pygetwindow as gw
                import time
                
                # 激活 Chrome 窗口
                logger.info("[Publisher] 查找并激活 Chrome 窗口...")
                chrome_windows = gw.getWindowsWithTitle("Chrome")
                if not chrome_windows:
                    chrome_windows = gw.getWindowsWithTitle("抖音")
                if not chrome_windows:
                    chrome_windows = gw.getWindowsWithTitle("creator.douyin.com")
                
                if chrome_windows:
                    chrome_window = chrome_windows[0]
                    chrome_window.activate()
                    time.sleep(1)
                    logger.info("[Publisher] Chrome 窗口已激活")
                else:
                    logger.error("[Publisher] 未找到 Chrome 窗口，请确保浏览器已打开")
                    return False
            except ImportError:
                logger.error("[Publisher] 需要安装 pyautogui 和 pygetwindow: pip install pyautogui pygetwindow")
                return False
        
        # 等待页面加载（浏览器已登录，不需要等待登录）
        logger.info("[Publisher] 等待页面加载...")
        try:
            # 等待上传按钮出现
            await page.wait_for_selector('input[type="file"]', timeout=30000)  # 30秒超时
            logger.info("[Publisher] 页面加载完成，继续上传...")
        except Exception:
            logger.warning("[Publisher] 等待上传按钮超时，尝试继续...")
        
        # 查找上传按钮
        logger.info("[Publisher] 查找上传按钮...")
        upload_input = await page.query_selector('input[type="file"]')
        
        if upload_input:
            # 上传视频
            logger.info("[Publisher] 上传视频...")
            await upload_input.set_input_files(str(video_path))
            
            # 等待上传完成（视频上传需要更长时间）
            logger.info("[Publisher] 等待视频上传完成...")
            await page.wait_for_timeout(15000)  # 等待15秒让视频上传
            
            # 先选择封面（必须选择，否则无法发布）
            logger.info(f"[Publisher] 选择封面: {cover_path}")
            cover_path_obj = Path(cover_path)
            if not cover_path_obj.exists():
                logger.error(f"[Publisher] 封面文件不存在: {cover_path}")
                return False
            
            # 等待页面加载完成
            await page.wait_for_timeout(3000)
            
            # 封面选择流程（从上往下）：
            # 1. 点击"选择封面" (div.title-wA45Xd)
            # 2. 点击"标题" (div.icon-name-Fi8gxR)
            # 3. 点击canvas中间区域（会弹出文件选择对话框）
            # 4. 选择文件
            # 5. 点击"确定"按钮
            # 6. 点击"完成"按钮
            
            # 步骤1: 点击"选择封面"
            logger.info("[Publisher] 步骤1: 点击'选择封面'...")
            await page.wait_for_timeout(3000)
            
            cover_title_clicked = False
            cover_title_selectors = [
                'div.title-wA45Xd:has-text("选择封面")',
                'div:has-text("选择封面")',
                '.title-wA45Xd',
            ]
            
            for selector in cover_title_selectors:
                try:
                    await page.wait_for_selector(selector, timeout=5000)
                    cover_title = await page.query_selector(selector)
                    if cover_title and await cover_title.is_visible():
                        await cover_title.scroll_into_view_if_needed()
                        await page.wait_for_timeout(500)
                        await cover_title.click()
                        logger.info(f"[Publisher] 已点击'选择封面'（使用选择器: {selector}）")
                        cover_title_clicked = True
                        await page.wait_for_timeout(2000)
                        break
                except Exception as e:
                    logger.debug(f"[Publisher] 选择器 {selector} 失败: {e}")
                    continue
            
            if not cover_title_clicked:
                logger.error("[Publisher] 未找到'选择封面'元素")
                return False
            
            # 步骤2: 点击"标题"
            logger.info("[Publisher] 步骤2: 点击'标题'...")
            await page.wait_for_timeout(2000)
            
            title_clicked = False
            title_selectors = [
                'div.icon-name-Fi8gxR:has-text("标题")',
                'div:has-text("标题")',
                '.icon-name-Fi8gxR',
            ]
            
            for selector in title_selectors:
                try:
                    await page.wait_for_selector(selector, timeout=5000)
                    title_element = await page.query_selector(selector)
                    if title_element and await title_element.is_visible():
                        await title_element.scroll_into_view_if_needed()
                        await page.wait_for_timeout(500)
                        await title_element.click()
                        logger.info(f"[Publisher] 已点击'标题'（使用选择器: {selector}）")
                        title_clicked = True
                        await page.wait_for_timeout(2000)
                        break
                except Exception as e:
                    logger.debug(f"[Publisher] 选择器 {selector} 失败: {e}")
                    continue
            
            if not title_clicked:
                logger.error("[Publisher] 未找到'标题'元素")
                return False
            
            # 步骤3: 点击canvas中间区域（会弹出文件选择对话框）
            logger.info("[Publisher] 步骤3: 点击canvas中间区域...")
            await page.wait_for_timeout(2000)
            
            canvas_clicked = False
            canvas_selectors = [
                'canvas.cloudImage-N0ai8Y',
                'canvas.lower-canvas',
                'canvas.upper-canvas',
                'canvas#vertical_coverCanvas',
                'canvas#horizontal_coverCanvas',
                'canvas',
            ]
            
            for selector in canvas_selectors:
                try:
                    canvas = await page.query_selector(selector)
                    if canvas and await canvas.is_visible():
                        # 获取canvas的位置和尺寸
                        box = await canvas.bounding_box()
                        if box:
                            # 点击canvas中间
                            center_x = box['x'] + box['width'] / 2
                            center_y = box['y'] + box['height'] / 2
                            await page.mouse.click(center_x, center_y)
                            logger.info(f"[Publisher] 已点击canvas中间（使用选择器: {selector}）")
                            canvas_clicked = True
                            await page.wait_for_timeout(2000)
                            break
                except Exception as e:
                    logger.debug(f"[Publisher] 选择器 {selector} 失败: {e}")
                    continue
            
            if not canvas_clicked:
                logger.warning("[Publisher] 未找到canvas，尝试直接查找文件输入框...")
            
            # 步骤4: 等待文件选择对话框出现，然后设置文件
            logger.info("[Publisher] 步骤4: 等待文件选择对话框并设置文件...")
            await page.wait_for_timeout(2000)
            
            # 查找文件输入框（可能在对话框或页面中）
            file_inputs = await page.query_selector_all('input[type="file"]')
            logger.info(f"[Publisher] 找到 {len(file_inputs)} 个文件输入框")
            
            cover_file_set = False
            for i, file_input in enumerate(file_inputs):
                try:
                    accept = await file_input.get_attribute('accept') or ''
                    logger.debug(f"[Publisher] 文件输入框 {i}: accept={accept}")
                    
                    # 如果接受图片或者是第二个文件输入框（第一个通常是视频上传）
                    if 'image' in accept or (len(file_inputs) > 1 and i > 0):
                        await file_input.set_input_files(str(cover_path_obj))
                        logger.info(f"[Publisher] 已设置封面文件（使用文件输入框 {i}）")
                        cover_file_set = True
                        await page.wait_for_timeout(2000)
                        break
                except Exception as e:
                    logger.debug(f"[Publisher] 文件输入框 {i} 设置失败: {e}")
                    continue
            
            if not cover_file_set:
                logger.warning("[Publisher] 未找到合适的文件输入框，尝试所有文件输入框...")
                # 如果没找到，尝试所有文件输入框
                for i, file_input in enumerate(file_inputs):
                    try:
                        await file_input.set_input_files(str(cover_path_obj))
                        logger.info(f"[Publisher] 已设置封面文件（尝试文件输入框 {i}）")
                        cover_file_set = True
                        await page.wait_for_timeout(2000)
                        break
                    except Exception as e:
                        logger.debug(f"[Publisher] 文件输入框 {i} 设置失败: {e}")
                        continue
            
            if not cover_file_set:
                logger.error("[Publisher] 无法设置封面文件")
                return False
            
            # 步骤5: 点击"确定"按钮
            logger.info("[Publisher] 步骤5: 点击'确定'按钮...")
            await page.wait_for_timeout(2000)
            
            confirm_clicked = False
            confirm_selectors = [
                'button.button-dhlUZE.primary-cECiOJ.dialog-b5CBy1:has-text("确定")',
                'button:has-text("确定")',
                'button.button-dhlUZE.primary-cECiOJ:has-text("确定")',
                '.dialog-b5CBy1:has-text("确定")',
            ]
            
            for selector in confirm_selectors:
                try:
                    confirm_button = await page.query_selector(selector)
                    if confirm_button and await confirm_button.is_visible():
                        await confirm_button.scroll_into_view_if_needed()
                        await page.wait_for_timeout(500)
                        await confirm_button.click()
                        logger.info(f"[Publisher] 已点击'确定'按钮（使用选择器: {selector}）")
                        confirm_clicked = True
                        await page.wait_for_timeout(2000)
                        break
                except Exception as e:
                    logger.debug(f"[Publisher] 确认按钮选择器 {selector} 失败: {e}")
                    continue
            
            if not confirm_clicked:
                logger.error("[Publisher] 未找到'确定'按钮")
                return False
            
            # 步骤6: 点击"完成"按钮
            logger.info("[Publisher] 步骤6: 点击'完成'按钮...")
            await page.wait_for_timeout(2000)
            
            finish_clicked = False
            finish_selectors = [
                'span.semi-button-content:has-text("完成")',
                'button:has-text("完成")',
                'span:has-text("完成")',
                '.semi-button-content:has-text("完成")',
            ]
            
            for selector in finish_selectors:
                try:
                    finish_button = await page.query_selector(selector)
                    if finish_button and await finish_button.is_visible():
                        await finish_button.scroll_into_view_if_needed()
                        await page.wait_for_timeout(500)
                        await finish_button.click()
                        logger.info(f"[Publisher] 已点击'完成'按钮（使用选择器: {selector}）")
                        finish_clicked = True
                        await page.wait_for_timeout(2000)
                        break
                except Exception as e:
                    logger.debug(f"[Publisher] 完成按钮选择器 {selector} 失败: {e}")
                    continue
            
            if not finish_clicked:
                logger.warning("[Publisher] 未找到'完成'按钮，可能已经完成")
            
            logger.info("[Publisher] 封面选择流程完成")
            
            # 填写标题
            if title:
                logger.info(f"[Publisher] 填写标题: {title}")
                await page.wait_for_timeout(1000)
                # 尝试多种选择器
                title_selectors = [
                    'input[placeholder*="标题"]',
                    'input[placeholder*="title"]',
                    'textarea[placeholder*="标题"]',
                    'textarea[placeholder*="title"]',
                    '.input-title',
                    '#title',
                    'input[type="text"]',
                    'textarea'
                ]
                title_filled = False
                for selector in title_selectors:
                    try:
                        title_input = await page.query_selector(selector)
                        if title_input:
                            # 先清空再填写
                            await title_input.click()
                            await title_input.fill('')
                            await title_input.fill(title)
                            logger.info(f"[Publisher] 标题填写成功（使用选择器: {selector}）")
                            title_filled = True
                            await page.wait_for_timeout(500)
                            break
                    except Exception as e:
                        logger.debug(f"[Publisher] 选择器 {selector} 失败: {e}")
                        continue
                
                if not title_filled:
                    logger.warning("[Publisher] 未找到标题输入框，继续...")
            
            # 填写描述（必须填写）
            if description:
                logger.info(f"[Publisher] 填写描述: {description}")
                # 等待页面完全加载（封面选择后）
                await page.wait_for_timeout(3000)
                
                desc_filled = False
                
                # 方法1: 尝试所有textarea，排除标题输入框
                try:
                    all_textareas = await page.query_selector_all('textarea')
                    logger.info(f"[Publisher] 找到 {len(all_textareas)} 个textarea元素")
                    
                    for i, textarea in enumerate(all_textareas):
                        try:
                            # 获取placeholder和class属性
                            placeholder = await textarea.get_attribute('placeholder') or ''
                            class_name = await textarea.get_attribute('class') or ''
                            id_attr = await textarea.get_attribute('id') or ''
                            
                            logger.info(f"[Publisher] textarea {i}: placeholder='{placeholder}', class='{class_name}', id='{id_attr}'")
                            
                            # 排除标题输入框（标题通常包含"标题"、"title"等关键词）
                            if ('标题' in placeholder or 'title' in placeholder.lower() or 
                                'title' in class_name.lower() or 'title' in id_attr.lower()):
                                logger.debug(f"[Publisher] textarea {i} 是标题输入框，跳过")
                                continue
                            
                            # 滚动到元素
                            await textarea.scroll_into_view_if_needed()
                            await page.wait_for_timeout(500)
                            
                            # 点击聚焦
                            await textarea.click()
                            await page.wait_for_timeout(500)
                            
                            # 清空现有内容
                            await textarea.fill('')
                            await page.wait_for_timeout(300)
                            
                            # 填写描述
                            await textarea.fill(description)
                            await page.wait_for_timeout(1000)
                            
                            # 验证是否填写成功
                            value = await textarea.input_value()
                            logger.info(f"[Publisher] textarea {i} 填写后的值: {value[:100]}...")
                            
                            if description in value or value == description or len(value) > 0:
                                logger.info(f"[Publisher] 描述填写成功（使用textarea {i}）")
                                desc_filled = True
                                break
                            else:
                                logger.debug(f"[Publisher] textarea {i} 填写验证失败，值: {value[:50]}...")
                        except Exception as e:
                            logger.debug(f"[Publisher] textarea {i} 处理失败: {e}")
                            continue
                except Exception as e:
                    logger.warning(f"[Publisher] 查找textarea失败: {e}")
                
                # 方法2: 如果方法1失败，尝试使用contenteditable元素
                if not desc_filled:
                    logger.info("[Publisher] 尝试使用contenteditable元素填写描述...")
                    try:
                        editable_elements = await page.query_selector_all('[contenteditable="true"]')
                        logger.info(f"[Publisher] 找到 {len(editable_elements)} 个contenteditable元素")
                        
                        for i, element in enumerate(editable_elements):
                            try:
                                placeholder = await element.get_attribute('placeholder') or ''
                                class_name = await element.get_attribute('class') or ''
                                
                                logger.info(f"[Publisher] contenteditable {i}: placeholder='{placeholder}', class='{class_name}'")
                                
                                # 排除标题
                                if '标题' in placeholder or 'title' in placeholder.lower():
                                    continue
                                
                                await element.click()
                                await page.wait_for_timeout(500)
                                
                                # 清空并填写
                                await element.fill('')
                                await page.wait_for_timeout(300)
                                await element.fill(description)
                                await page.wait_for_timeout(1000)
                                
                                # 验证
                                text_content = await element.inner_text()
                                if description in text_content or len(text_content) > 0:
                                    logger.info(f"[Publisher] 描述填写成功（使用contenteditable {i}）")
                                    desc_filled = True
                                    break
                            except Exception as e:
                                logger.debug(f"[Publisher] contenteditable {i} 处理失败: {e}")
                                continue
                    except Exception as e:
                        logger.warning(f"[Publisher] 查找contenteditable失败: {e}")
                
                # 方法3: 如果都失败，尝试使用键盘输入
                if not desc_filled:
                    logger.info("[Publisher] 尝试使用键盘输入描述...")
                    try:
                        # 查找所有可能的输入元素
                        all_inputs = await page.query_selector_all('textarea, input[type="text"], [contenteditable="true"]')
                        for element in all_inputs:
                            try:
                                placeholder = await element.get_attribute('placeholder') or ''
                                if '标题' not in placeholder and 'title' not in placeholder.lower():
                                    await element.click()
                                    await page.wait_for_timeout(500)
                                    
                                    # 使用键盘输入
                                    await element.type(description, delay=50)
                                    await page.wait_for_timeout(1000)
                                    
                                    logger.info("[Publisher] 描述填写成功（使用键盘输入）")
                                    desc_filled = True
                                    break
                            except:
                                continue
                    except Exception as e:
                        logger.warning(f"[Publisher] 键盘输入失败: {e}")
                
                if not desc_filled:
                    logger.error("[Publisher] 描述填写失败！")
                    # 不返回False，继续尝试发布（有些平台可能允许空描述）
            else:
                logger.warning("[Publisher] 未提供描述，使用空描述")
            
            # 等待一下让所有内容填写完成
            await page.wait_for_timeout(2000)
            
            # 点击发布按钮
            logger.info("[Publisher] 查找发布按钮...")
            publish_selectors = [
                'button:has-text("发布")',
                'button:has-text("发布视频")',
                'button:has-text("Publish")',
                '.publish-button',
                '#publish',
                'button[type="submit"]'
            ]
            publish_clicked = False
            for selector in publish_selectors:
                try:
                    publish_button = await page.query_selector(selector)
                    if publish_button:
                        # 检查按钮是否可点击
                        is_disabled = await publish_button.evaluate('el => el.disabled')
                        if not is_disabled:
                            await publish_button.click()
                            logger.info(f"[Publisher] 发布按钮已点击（使用选择器: {selector}）")
                            publish_clicked = True
                            break
                except Exception as e:
                    logger.debug(f"[Publisher] 选择器 {selector} 失败: {e}")
                    continue
            
            if not publish_clicked:
                logger.warning("[Publisher] 未找到可点击的发布按钮，可能需要手动发布")
                # 不关闭页面，让用户手动操作
                logger.info("[Publisher] 页面保持打开，请手动完成发布")
                return False
            
            # 等待发布完成并验证发布成功
            logger.info("[Publisher] 等待发布完成...")
            
            # 等待URL变化或出现成功提示
            max_wait_time = 60  # 最多等待60秒
            wait_interval = 2  # 每2秒检查一次
            waited_time = 0
            publish_success = False
            
            initial_url = page.url
            logger.info(f"[Publisher] 初始URL: {initial_url}")
            
            while waited_time < max_wait_time:
                await page.wait_for_timeout(wait_interval * 1000)
                waited_time += wait_interval
                
                current_url = page.url
                
                # 检查URL是否变化（发布成功通常会跳转）
                if current_url != initial_url:
                    logger.info(f"[Publisher] URL已变化: {current_url}")
                    publish_success = True
                    break
                
                # 检查是否有成功提示
                try:
                    success_selectors = [
                        'text=发布成功',
                        'text=发布完成',
                        'text=上传成功',
                        '[class*="success"]',
                        '[class*="success-message"]',
                    ]
                    for selector in success_selectors:
                        try:
                            success_element = await page.query_selector(selector)
                            if success_element:
                                text = await success_element.inner_text()
                                if '成功' in text or '完成' in text:
                                    logger.info(f"[Publisher] 检测到成功提示: {text}")
                                    publish_success = True
                                    break
                        except:
                            continue
                    
                    if publish_success:
                        break
                except Exception as e:
                    logger.debug(f"[Publisher] 检查成功提示时出错: {e}")
                
                # 检查是否有错误提示
                try:
                    error_selectors = [
                        'text=发布失败',
                        'text=上传失败',
                        '[class*="error"]',
                        '[class*="error-message"]',
                    ]
                    for selector in error_selectors:
                        try:
                            error_element = await page.query_selector(selector)
                            if error_element:
                                text = await error_element.inner_text()
                                if '失败' in text or '错误' in text:
                                    logger.error(f"[Publisher] 检测到错误提示: {text}")
                                    # 不关闭页面，让用户查看错误
                                    logger.info("[Publisher] 页面保持打开，请查看错误信息")
                                    return False
                        except:
                            continue
                except Exception as e:
                    logger.debug(f"[Publisher] 检查错误提示时出错: {e}")
                
                logger.info(f"[Publisher] 等待发布完成... ({waited_time}/{max_wait_time}秒)")
            
            if not publish_success:
                logger.warning("[Publisher] 等待超时，无法确认发布是否成功")
                # 不关闭页面，让用户手动确认
                logger.info("[Publisher] 页面保持打开，请手动确认发布状态")
                return False
            
            # 等待一下确保发布完成
            await page.wait_for_timeout(3000)
            
            # 再次确认发布成功（检查URL或页面内容）
            final_url = page.url
            logger.info(f"[Publisher] 最终URL: {final_url}")
            
            # 如果URL包含成功相关的路径，确认发布成功
            if 'post' in final_url.lower() or 'success' in final_url.lower() or 'content' in final_url.lower():
                logger.info("[Publisher] 根据URL判断，发布成功！")
                publish_success = True
            
            if publish_success:
                # 不关闭页面，让用户查看发布结果
                logger.info("[Publisher] 视频发布成功！页面保持打开，您可以查看发布结果。")
                # 注意：不关闭页面，保持浏览器打开
                return True
            else:
                logger.warning("[Publisher] 无法确认发布是否成功，页面保持打开")
                return False
        else:
            logger.error("[Publisher] 未找到上传按钮")
            await page.close()
            return False
            
    except Exception as e:
        logger.error(f"[Publisher] 发布视频时出错: {e}")
        import traceback
        logger.error(traceback.format_exc())
        try:
            await page.close()
        except:
            pass
        return False


def publish_to_douyin(
    video_path: str, 
    title: str = "", 
    description: str = "",
    cover_path: Optional[str] = None
) -> bool:
    """
    同步包装器：上传视频到抖音
    
    Args:
        video_path: 视频文件路径
        title: 视频标题
        description: 视频描述/介绍
        cover_path: 封面图片路径（可选）
        
    Returns:
        是否发布成功
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(_publish_to_douyin_async(video_path, title, description, cover_path))


def publish_to_kuaishou(video_path: str, title: str = "") -> bool:
    """发布到快手（类似实现）"""
    logger.info(f"[Publisher] 快手发布功能待实现: {video_path}")
    return False


def publish_to_xiaohongshu(video_path: str, title: str = "") -> bool:
    """发布到小红书（类似实现）"""
    logger.info(f"[Publisher] 小红书发布功能待实现: {video_path}")
    return False
