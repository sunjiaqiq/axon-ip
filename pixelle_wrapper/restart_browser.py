"""
重启浏览器测试cookies保存
"""
import asyncio
import logging
import sys

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

async def main():
    try:
        from ai_pipeline.browser_manager import browser_manager
        
        logger.info("步骤1: 保存cookies...")
        await browser_manager.save_cookies()
        logger.info("✓ Cookies已保存")
        
        logger.info("步骤2: 关闭浏览器...")
        await browser_manager.close()
        logger.info("✓ 浏览器已关闭")
        
        await asyncio.sleep(3)
        
        logger.info("步骤3: 重新打开浏览器...")
        page = await browser_manager.open_login_page("https://www.douyin.com")
        logger.info("✓ 浏览器已重新打开")
        logger.info("")
        logger.info("请检查浏览器是否保持登录状态")
        logger.info("")
        
        # 保持运行
        await asyncio.sleep(3600)
        
    except Exception as e:
        logger.error(f"错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())







