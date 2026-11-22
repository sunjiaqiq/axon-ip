"""
只打开浏览器，使用与发布成功时完全相同的方式
"""
import logging
import douyin_publish_mcp
import time

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def main():
    """只打开浏览器，不做任何其他操作"""
    try:
        logger.info("=" * 70)
        logger.info("打开浏览器（使用发布成功时的配置）")
        logger.info("=" * 70)
        
        # 使用与发布成功时完全相同的方式启动浏览器
        logger.info("\n[步骤1] 启动浏览器...")
        if not douyin_publish_mcp.ensure_browser():
            logger.error("浏览器启动失败")
            return
        
        logger.info("[步骤1] 浏览器已启动")
        logger.info(f"[步骤1] 当前URL: {douyin_publish_mcp.driver.current_url}")
        
        # 导航到抖音创作者中心（与发布成功时相同的URL）
        logger.info("\n[步骤2] 导航到抖音创作者中心...")
        url = "https://creator.douyin.com/creator-micro/content/upload?enter_from=dou_web"
        logger.info(f"[步骤2] 导航到: {url}")
        douyin_publish_mcp.driver.get(url)
        
        # 等待页面加载
        logger.info("[步骤2] 等待页面加载...")
        time.sleep(5)
        
        logger.info(f"[步骤2] 当前URL: {douyin_publish_mcp.driver.current_url}")
        logger.info(f"[步骤2] 页面标题: {douyin_publish_mcp.driver.title}")
        
        logger.info("\n" + "=" * 70)
        logger.info("浏览器已打开，将保持打开状态")
        logger.info("浏览器不会自动关闭")
        logger.info("=" * 70)
        
        # 保持浏览器打开，不关闭
        try:
            while True:
                time.sleep(1)
                # 检查浏览器是否还在运行
                try:
                    douyin_publish_mcp.driver.current_url
                except:
                    logger.info("浏览器已关闭")
                    break
        except KeyboardInterrupt:
            logger.info("\n收到中断信号，但浏览器保持打开状态")
            # 不关闭浏览器，让用户手动关闭
        
    except Exception as e:
        logger.error(f"错误: {e}")
        import traceback
        traceback.print_exc()
        # 不关闭浏览器，让用户查看

if __name__ == "__main__":
    main()
