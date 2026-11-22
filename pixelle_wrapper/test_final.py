"""
最终测试：确保系统设置里的登录功能使用正确的浏览器（有账号信息）
"""
import logging
import douyin_publish_mcp
import time

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def test_final():
    """最终测试"""
    try:
        logger.info("=" * 70)
        logger.info("最终测试：系统设置登录功能")
        logger.info("=" * 70)
        
        # 这就是系统设置里点击"登录"按钮时调用的函数
        logger.info("\n[调用 ensure_browser()]")
        logger.info("这是系统设置里点击'登录'按钮时调用的函数")
        
        if not douyin_publish_mcp.ensure_browser():
            logger.error("❌ 浏览器启动失败")
            return
        
        logger.info("✅ 浏览器已启动")
        logger.info(f"Driver: {douyin_publish_mcp.driver}")
        
        # 导航到抖音创作者中心（与系统设置登录功能相同的 URL）
        url = "https://creator.douyin.com/creator-micro/content/upload?enter_from=dou_web"
        logger.info(f"\n[导航到抖音创作者中心]")
        logger.info(f"URL: {url}")
        douyin_publish_mcp.driver.get(url)
        
        time.sleep(5)
        current_url = douyin_publish_mcp.driver.current_url
        page_title = douyin_publish_mcp.driver.title
        
        logger.info(f"当前 URL: {current_url}")
        logger.info(f"页面标题: {page_title}")
        
        # 检查是否有账号信息
        if 'login' not in current_url.lower() and 'passport' not in current_url.lower():
            logger.info("✅ 浏览器已登录（有账号信息）")
        else:
            logger.warning("⚠️ 浏览器未登录（需要登录）")
        
        logger.info("\n" + "=" * 70)
        logger.info("测试完成！")
        logger.info("=" * 70)
        logger.info("\n请检查浏览器：")
        logger.info("1. ✅ 是否只有一个浏览器窗口")
        logger.info("2. ✅ 是否有账号信息（已登录）")
        logger.info("3. ✅ 是否导航到了抖音创作者中心")
        logger.info("\n浏览器将保持打开状态...")
        
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
    test_final()





