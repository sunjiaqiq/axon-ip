"""
直接测试自然语言元素定位功能
"""
import asyncio
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

async def test_natural_language():
    """测试自然语言定位功能"""
    try:
        import douyin_publish_mcp
        
        logger.info("=" * 70)
        logger.info("测试自然语言元素定位功能")
        logger.info("=" * 70)
        
        # 1. 测试浏览器启动
        logger.info("\n[测试] 步骤1: 启动浏览器...")
        await douyin_publish_mcp.ensure_browser()
        logger.info("[测试] ✅ 浏览器启动成功")
        
        if not douyin_publish_mcp.main_page:
            logger.error("[测试] ❌ main_page 为 None")
            return
        
        # 2. 导航到抖音上传页面
        logger.info("\n[测试] 步骤2: 导航到抖音上传页面...")
        await douyin_publish_mcp.main_page.goto(
            "https://creator.douyin.com/creator-micro/content/upload",
            wait_until='domcontentloaded',
            timeout=60000
        )
        await asyncio.sleep(3)
        logger.info(f"[测试] ✅ 已导航到: {douyin_publish_mcp.main_page.url}")
        
        # 3. 测试自然语言定位工具
        logger.info("\n[测试] 步骤3: 测试自然语言定位工具...")
        
        # 测试 browser_click
        logger.info("\n[测试] 3.1: 测试 browser_click('选择封面按钮')...")
        result = await douyin_publish_mcp.browser_click("选择封面按钮")
        logger.info(f"[测试] 结果: {result}")
        
        await asyncio.sleep(2)
        
        # 测试 browser_click - 标题
        logger.info("\n[测试] 3.2: 测试 browser_click('标题')...")
        result = await douyin_publish_mcp.browser_click("标题")
        logger.info(f"[测试] 结果: {result}")
        
        await asyncio.sleep(2)
        
        logger.info("\n[测试] ========== 测试完成 ==========")
        logger.info("[测试] 浏览器将保持打开，您可以查看页面状态")
        logger.info("[提示] 按 Ctrl+C 关闭浏览器...")
        
        # 保持浏览器打开
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("\n[测试] 正在关闭浏览器...")
            # 不关闭浏览器，让用户查看
            logger.info("[测试] 浏览器保持打开状态")
        
    except Exception as e:
        logger.error(f"[测试] 错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_natural_language())





