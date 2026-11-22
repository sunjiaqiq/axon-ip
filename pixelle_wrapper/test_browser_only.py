"""
只测试浏览器启动功能
"""
import asyncio
import logging
import os
from pathlib import Path

logging.basicConfig(level=logging.DEBUG, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

async def test_browser_only():
    """只测试浏览器启动"""
    try:
        import douyin_publish_mcp
        
        logger.info("=" * 70)
        logger.info("测试：只启动浏览器")
        logger.info("=" * 70)
        
        # 检查配置
        config = douyin_publish_mcp.load_browser_config()
        logger.info(f"[测试] Chrome 路径: {config.get('chrome_path')}")
        logger.info(f"[测试] Profile: {config.get('profile_directory')}")
        
        # 检查 Chrome 是否存在
        chrome_path = config.get('chrome_path')
        if chrome_path and os.path.exists(chrome_path):
            logger.info(f"[测试] ✅ Chrome 文件存在")
        else:
            logger.error(f"[测试] ❌ Chrome 文件不存在: {chrome_path}")
            return
        
        # 尝试启动浏览器
        logger.info("\n[测试] 开始启动浏览器...")
        try:
            await douyin_publish_mcp.ensure_browser()
            logger.info("[测试] ✅ 浏览器启动成功")
            
            if douyin_publish_mcp.main_page:
                logger.info(f"[测试] ✅ main_page 已初始化")
                logger.info(f"[测试] 当前 URL: {douyin_publish_mcp.main_page.url}")
                
                # 尝试导航到一个简单页面
                logger.info("\n[测试] 尝试导航到百度...")
                await douyin_publish_mcp.main_page.goto("https://www.baidu.com", timeout=30000)
                logger.info(f"[测试] ✅ 导航成功，当前 URL: {douyin_publish_mcp.main_page.url}")
            else:
                logger.error("[测试] ❌ main_page 为 None")
        except Exception as e:
            logger.error(f"[测试] ❌ 浏览器启动失败: {e}")
            import traceback
            traceback.print_exc()
            return
        
        logger.info("\n[测试] 浏览器已打开，将保持打开状态...")
        logger.info("[测试] 按 Ctrl+C 关闭浏览器")
        logger.info("[测试] 当前页面 URL: " + douyin_publish_mcp.main_page.url)
        
        # 保持浏览器打开，直到用户按 Ctrl+C
        # 重要：保持对 browser_context 和 main_page 的引用
        browser_context_ref = douyin_publish_mcp.browser_context
        main_page_ref = douyin_publish_mcp.main_page
        
        try:
            while True:
                await asyncio.sleep(1)
                # 检查浏览器是否还活着
                try:
                    if browser_context_ref and browser_context_ref.pages:
                        # 浏览器还活着
                        pass
                    else:
                        logger.warning("[测试] 浏览器已关闭")
                        break
                except:
                    logger.warning("[测试] 浏览器上下文已失效")
                    break
        except KeyboardInterrupt:
            logger.info("\n[测试] 收到 Ctrl+C，测试完成")
            # 不关闭浏览器，让用户查看
            logger.info("[测试] 浏览器保持打开状态，您可以查看")
            # 保持引用，防止垃圾回收
            _ = browser_context_ref
            _ = main_page_ref
        
    except Exception as e:
        logger.error(f"[测试] 错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_browser_only())

