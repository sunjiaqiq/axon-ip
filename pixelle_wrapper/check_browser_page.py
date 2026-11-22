"""
检查浏览器当前打开的页面
"""
import asyncio
import logging

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

async def check_browser():
    try:
        from ai_pipeline.browser_manager import browser_manager
        
        await browser_manager.ensure_initialized()
        context = await browser_manager.get_page()
        
        pages = context.pages
        logger.info(f"浏览器中有 {len(pages)} 个页面")
        
        for i, page in enumerate(pages, 1):
            try:
                url = page.url
                title = await page.title()
                logger.info(f"页面 {i}:")
                logger.info(f"  URL: {url}")
                logger.info(f"  标题: {title}")
                
                # 检查是否有video元素
                video_count = await page.query_selector_all('video')
                logger.info(f"  视频元素数量: {len(video_count)}")
                
                if video_count:
                    video = video_count[0]
                    video_src = await video.get_attribute('src')
                    logger.info(f"  视频src: {video_src[:100] if video_src else 'None'}...")
                    
            except Exception as e:
                logger.warning(f"检查页面 {i} 时出错: {e}")
        
    except Exception as e:
        logger.error(f"检查浏览器失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(check_browser())







