"""
简单测试浏览器启动
"""
import asyncio
import logging
import sys

logging.basicConfig(level=logging.DEBUG, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

async def test():
    try:
        logger.info("开始测试...")
        from ai_pipeline.browser_manager import browser_manager
        
        logger.info("初始化浏览器...")
        await browser_manager.initialize()
        logger.info("浏览器初始化完成")
        
        logger.info("打开页面...")
        page = await browser_manager.open_login_page("https://www.douyin.com")
        logger.info(f"页面已打开: {page.url}")
        
        logger.info("等待10秒...")
        await asyncio.sleep(10)
        
        logger.info("测试完成！")
        
    except Exception as e:
        logger.error(f"错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(test())







