"""
15秒测试：确保打开正确的浏览器（Profile 3，有账号信息）
"""
import logging
import douyin_publish_mcp
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def test_15s():
    """15秒测试"""
    try:
        logger.info("=" * 70)
        logger.info("15秒测试：确保打开正确的浏览器")
        logger.info("=" * 70)
        
        # 检查配置
        browser_config = douyin_publish_mcp.load_browser_config()
        wrapper_dir = Path(__file__).parent
        user_data_dir = wrapper_dir / "browser_data" / "chrome_user_data"
        profile_dir = user_data_dir / browser_config.get('profile_directory', 'Profile 3')
        
        logger.info(f"\n[配置检查]")
        logger.info(f"Chrome 路径: {browser_config.get('chrome_path')}")
        logger.info(f"Profile: {browser_config.get('profile_directory')}")
        logger.info(f"User Data Dir: {user_data_dir}")
        logger.info(f"Profile Dir: {profile_dir}")
        logger.info(f"Profile 是否存在: {profile_dir.exists()}")
        
        if not profile_dir.exists():
            logger.error("❌ Profile 目录不存在！")
            return
        
        # 调用 ensure_browser()
        logger.info(f"\n[调用 ensure_browser()]")
        start_time = time.time()
        
        if not douyin_publish_mcp.ensure_browser():
            logger.error("❌ 浏览器启动失败")
            return
        
        elapsed = time.time() - start_time
        logger.info(f"✅ 浏览器启动成功（耗时: {elapsed:.2f}秒）")
        logger.info(f"Driver: {douyin_publish_mcp.driver}")
        
        # 导航到抖音创作者中心
        url = "https://creator.douyin.com/creator-micro/content/upload?enter_from=dou_web"
        logger.info(f"\n[导航]")
        logger.info(f"URL: {url}")
        douyin_publish_mcp.driver.get(url)
        
        time.sleep(3)
        current_url = douyin_publish_mcp.driver.current_url
        page_title = douyin_publish_mcp.driver.title
        
        logger.info(f"当前 URL: {current_url}")
        logger.info(f"页面标题: {page_title}")
        
        # 检查是否有账号信息
        if 'login' not in current_url.lower() and 'passport' not in current_url.lower():
            logger.info("✅ 浏览器已登录（有账号信息）")
        else:
            logger.warning("⚠️ 浏览器未登录（空白界面，需要登录）")
        
        # 检查浏览器进程
        try:
            import psutil
            chrome_count = 0
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                if proc.info['name'] and 'chrome.exe' in proc.info['name'].lower():
                    chrome_count += 1
                    cmdline = proc.info.get('cmdline', [])
                    cmdline_str = ' '.join(cmdline) if cmdline else ''
                    if 'browser_data' in cmdline_str and 'Profile 3' in cmdline_str:
                        logger.info(f"✅ 找到使用 Profile 3 的 Chrome 进程 (PID: {proc.info['pid']})")
            logger.info(f"Chrome 进程数: {chrome_count}")
        except:
            pass
        
        logger.info("\n" + "=" * 70)
        logger.info("测试完成！")
        logger.info("=" * 70)
        
        # 等待15秒后关闭
        logger.info("\n等待15秒后关闭浏览器...")
        time.sleep(15)
        
        if douyin_publish_mcp.driver:
            douyin_publish_mcp.driver.quit()
            logger.info("浏览器已关闭")
        
    except Exception as e:
        logger.error(f"错误: {e}")
        import traceback
        traceback.print_exc()
        # 确保关闭浏览器
        try:
            if douyin_publish_mcp.driver:
                douyin_publish_mcp.driver.quit()
        except:
            pass

if __name__ == "__main__":
    test_15s()





