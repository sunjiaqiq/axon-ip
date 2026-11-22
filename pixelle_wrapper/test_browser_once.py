"""
测试：确保只创建一个浏览器实例，并且有账号信息
"""
import logging
import douyin_publish_mcp
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def test_browser_once():
    """测试：只创建一个浏览器实例"""
    try:
        logger.info("=" * 70)
        logger.info("测试：确保只创建一个浏览器实例，并且有账号信息")
        logger.info("=" * 70)
        
        # 检查配置
        browser_config = douyin_publish_mcp.load_browser_config()
        wrapper_dir = Path(__file__).parent
        user_data_dir = wrapper_dir / "browser_data" / "chrome_user_data"
        profile_dir = user_data_dir / browser_config.get('profile_directory', 'Profile 3')
        
        logger.info(f"\n[配置]")
        logger.info(f"User Data Dir: {user_data_dir}")
        logger.info(f"Profile Dir: {profile_dir}")
        logger.info(f"Profile 是否存在: {profile_dir.exists()}")
        
        # 第一次调用 ensure_browser()
        logger.info(f"\n[第一次调用 ensure_browser()]")
        if not douyin_publish_mcp.ensure_browser():
            logger.error("浏览器启动失败")
            return
        
        logger.info(f"✅ 浏览器已启动")
        logger.info(f"Driver: {douyin_publish_mcp.driver}")
        logger.info(f"当前 URL: {douyin_publish_mcp.driver.current_url}")
        
        # 导航到抖音创作者中心
        url = "https://creator.douyin.com/creator-micro/content/upload?enter_from=dou_web"
        logger.info(f"\n[导航到抖音创作者中心]")
        logger.info(f"URL: {url}")
        douyin_publish_mcp.driver.get(url)
        
        time.sleep(5)
        current_url = douyin_publish_mcp.driver.current_url
        page_title = douyin_publish_mcp.driver.title
        
        logger.info(f"当前 URL: {current_url}")
        logger.info(f"页面标题: {page_title}")
        
        # 检查是否有账号信息（如果已登录，URL 应该不是登录页面）
        if 'login' not in current_url.lower() and 'passport' not in current_url.lower():
            logger.info("✅ 浏览器已登录（有账号信息）")
        else:
            logger.warning("⚠️ 浏览器未登录（需要登录）")
        
        # 第二次调用 ensure_browser()（应该复用现有实例）
        logger.info(f"\n[第二次调用 ensure_browser()] - 应该复用现有实例")
        if not douyin_publish_mcp.ensure_browser():
            logger.error("浏览器启动失败")
            return
        
        logger.info(f"✅ 浏览器已启动（应该复用现有实例）")
        logger.info(f"Driver: {douyin_publish_mcp.driver}")
        logger.info(f"当前 URL: {douyin_publish_mcp.driver.current_url}")
        
        # 检查是否还是同一个浏览器实例
        if current_url == douyin_publish_mcp.driver.current_url:
            logger.info("✅ 确认：复用了同一个浏览器实例")
        else:
            logger.warning("⚠️ 警告：可能创建了新的浏览器实例")
        
        # 检查 Chrome 进程数量
        try:
            import psutil
            chrome_count = 0
            for proc in psutil.process_iter(['pid', 'name']):
                if proc.info['name'] and 'chrome.exe' in proc.info['name'].lower():
                    chrome_count += 1
            logger.info(f"\n[Chrome 进程数量]")
            logger.info(f"当前 Chrome 进程数: {chrome_count}")
            if chrome_count > 10:
                logger.warning("⚠️ 警告：Chrome 进程数量较多，可能有多个浏览器实例")
        except:
            pass
        
        logger.info("\n" + "=" * 70)
        logger.info("测试完成！")
        logger.info("=" * 70)
        logger.info("\n浏览器将保持打开状态，请检查：")
        logger.info("1. 是否只有一个浏览器窗口")
        logger.info("2. 是否有账号信息（已登录）")
        logger.info("3. 是否导航到了抖音创作者中心")
        logger.info("\n按 Ctrl+C 退出（浏览器保持打开）...")
        
        # 保持浏览器打开
        try:
            while True:
                time.sleep(1)
                try:
                    douyin_publish_mcp.driver.current_url
                except:
                    logger.info("浏览器已关闭")
                    break
        except KeyboardInterrupt:
            logger.info("\n收到中断信号，但浏览器保持打开状态")
        
    except Exception as e:
        logger.error(f"错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_browser_once()





