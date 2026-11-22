"""
测试登录功能使用的浏览器
确保与成功发布的脚本使用完全相同的浏览器
"""
import logging
import douyin_publish_mcp
import time

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def test_login_browser():
    """测试登录功能使用的浏览器"""
    try:
        logger.info("=" * 70)
        logger.info("测试登录功能使用的浏览器")
        logger.info("=" * 70)
        
        # 读取配置
        browser_config = douyin_publish_mcp.load_browser_config()
        logger.info(f"\n[配置信息]")
        logger.info(f"Chrome 路径: {browser_config.get('chrome_path')}")
        logger.info(f"Profile 目录: {browser_config.get('profile_directory')}")
        
        # 计算 user_data_dir
        from pathlib import Path
        wrapper_dir = Path(__file__).parent
        user_data_dir = wrapper_dir / "browser_data" / "chrome_user_data"
        logger.info(f"\n[用户数据目录]")
        logger.info(f"独立 user_data_dir: {user_data_dir}")
        logger.info(f"是否存在: {user_data_dir.exists()}")
        
        profile_dir = user_data_dir / browser_config.get('profile_directory', 'Profile 3')
        logger.info(f"Profile 路径: {profile_dir}")
        logger.info(f"是否存在: {profile_dir.exists()}")
        
        # 测试 ensure_browser
        logger.info("\n[测试 ensure_browser]")
        logger.info("调用 douyin_publish_mcp.ensure_browser()...")
        if not douyin_publish_mcp.ensure_browser():
            logger.error("浏览器启动失败")
            return
        
        logger.info("浏览器启动成功")
        logger.info(f"Driver 对象: {douyin_publish_mcp.driver}")
        logger.info(f"当前 URL: {douyin_publish_mcp.driver.current_url}")
        
        # 导航到抖音创作者中心
        url = "https://creator.douyin.com/creator-micro/content/upload?enter_from=dou_web"
        logger.info(f"\n[导航测试]")
        logger.info(f"导航到: {url}")
        douyin_publish_mcp.driver.get(url)
        
        time.sleep(5)
        logger.info(f"当前 URL: {douyin_publish_mcp.driver.current_url}")
        logger.info(f"页面标题: {douyin_publish_mcp.driver.title}")
        
        logger.info("\n" + "=" * 70)
        logger.info("测试完成！浏览器已打开，请检查是否是之前成功发布的浏览器")
        logger.info("=" * 70)
        
        # 保持浏览器打开
        logger.info("\n浏览器将保持打开状态，按 Ctrl+C 退出...")
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
    test_login_browser()





