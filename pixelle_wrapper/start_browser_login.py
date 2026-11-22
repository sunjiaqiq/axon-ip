"""
启动浏览器并打开登录页面
"""
import asyncio
import logging

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

async def main():
    logger.info("=" * 70)
    logger.info("启动浏览器登录页面")
    logger.info("=" * 70)
    logger.info("")
    
    try:
        from ai_pipeline.browser_manager import browser_manager
        
        # 打开登录页面
        logger.info("正在打开浏览器...")
        page = await browser_manager.open_login_page("https://www.douyin.com")
        
        logger.info("")
        logger.info("✓ 浏览器已打开！")
        logger.info("")
        logger.info("请在浏览器中登录您的抖音账号")
        logger.info("登录完成后，可以运行测试脚本搜索视频")
        logger.info("")
        logger.info("浏览器将保持打开状态，登录信息会自动保存")
        logger.info("按 Ctrl+C 退出（浏览器会保持打开）")
        logger.info("")
        
        # 保持脚本运行，让浏览器保持打开
        try:
            await asyncio.sleep(3600)  # 等待1小时
        except KeyboardInterrupt:
            logger.info("")
            logger.info("脚本已退出，但浏览器会保持打开状态")
            logger.info("您可以继续在浏览器中操作")
        
    except Exception as e:
        logger.error(f"启动浏览器失败: {e}")
        import traceback
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    asyncio.run(main())







