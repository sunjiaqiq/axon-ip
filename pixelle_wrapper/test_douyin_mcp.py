"""
测试抖音发布 MCP Server
"""
import asyncio
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

async def test_mcp_tools():
    """测试 MCP 工具"""
    from douyin_publish_mcp import ensure_browser, check_browser_status
    
    try:
        # 1. 测试浏览器启动
        logger.info("=" * 70)
        logger.info("测试抖音发布 MCP Server")
        logger.info("=" * 70)
        
        logger.info("[测试] 启动浏览器...")
        await ensure_browser()
        
        # 2. 检查浏览器状态
        logger.info("[测试] 检查浏览器状态...")
        status = await check_browser_status()
        logger.info(f"[测试] 浏览器状态: {status}")
        
        # 3. 查找测试视频
        logger.info("[测试] 查找测试视频...")
        output_dir = Path(__file__).parent / "output"
        if not output_dir.exists():
            logger.error("output目录不存在")
            return
        
        video_path = None
        task_dirs = sorted([d for d in output_dir.iterdir() if d.is_dir()], 
                          key=lambda x: x.stat().st_mtime, reverse=True)
        for task_dir in task_dirs:
            final_video = task_dir / "final.mp4"
            if final_video.exists():
                video_path = final_video
                logger.info(f"[测试] 找到视频: {video_path}")
                break
        
        if not video_path:
            logger.error("未找到测试视频")
            return
        
        # 4. 测试发布功能（不实际发布，只测试流程）
        logger.info("\n[测试] MCP Server 已准备就绪")
        logger.info("[测试] 可以使用以下方式调用:")
        logger.info("  1. 在 MCP Client 中配置此服务器")
        logger.info("  2. 调用 publish_video 工具发布视频")
        logger.info(f"[测试] 示例视频路径: {video_path}")
        
        logger.info("\n[测试] 浏览器将保持打开，请检查是否还有自动化标识...")
        await asyncio.sleep(10)
        
    except Exception as e:
        logger.error(f"[测试] 错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_mcp_tools())





