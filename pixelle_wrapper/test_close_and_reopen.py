"""
关闭浏览器并重新打开，测试cookies是否保存
"""
import asyncio
import logging

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

async def main():
    logger.info("=" * 70)
    logger.info("测试：关闭浏览器并重新打开")
    logger.info("=" * 70)
    logger.info("")
    
    try:
        from ai_pipeline.browser_manager import browser_manager
        
        # 1. 保存cookies并关闭浏览器
        logger.info("正在保存cookies并关闭浏览器...")
        await browser_manager.save_cookies()
        await browser_manager.close()
        logger.info("✓ 浏览器已关闭，cookies已保存")
        logger.info("")
        
        # 等待2秒
        await asyncio.sleep(2)
        
        # 2. 重新打开浏览器
        logger.info("正在重新打开浏览器...")
        page = await browser_manager.open_login_page("https://www.douyin.com")
        logger.info("")
        logger.info("✓ 浏览器已重新打开！")
        logger.info("")
        logger.info("请检查是否仍然保持登录状态")
        logger.info("如果已登录，说明cookies保存成功！")
        logger.info("")
        logger.info("浏览器将保持打开状态")
        logger.info("按 Ctrl+C 退出")
        logger.info("")
        
        # 保持脚本运行
        try:
            await asyncio.sleep(3600)  # 等待1小时
        except KeyboardInterrupt:
            logger.info("")
            logger.info("脚本已退出")
        
    except Exception as e:
        logger.error(f"操作失败: {e}")
        import traceback
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    asyncio.run(main())







