"""
测试 AI 驱动的抖音发布功能
使用 GLM 5 作为 Agent，通过 MCP 调用 Playwright 工具
"""
import asyncio
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

async def test_ai_publish():
    """测试AI驱动的发布功能"""
    from ai_pipeline.ai_agent import publish_with_ai_agent
    
    # 查找测试视频
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
            logger.info(f"找到视频: {video_path}")
            break
    
    if not video_path:
        logger.error("未找到测试视频")
        return
    
    # 测试发布
    title = "测试视频"
    description = "测试"
    
    logger.info("=" * 70)
    logger.info("测试 AI 驱动的抖音发布功能")
    logger.info("=" * 70)
    logger.info(f"视频路径: {video_path}")
    logger.info(f"标题: {title}")
    logger.info(f"描述: {description}")
    logger.info("=" * 70)
    logger.info("")
    logger.info("AI Agent 将使用 GLM 5 自主决策，调用 Playwright 工具完成发布")
    logger.info("")
    
    success = await publish_with_ai_agent(
        str(video_path),
        title=title,
        description=description,
        cover_path=None
    )
    
    if success:
        logger.info("✓ AI驱动的发布成功！")
    else:
        logger.error("✗ AI驱动的发布失败")

if __name__ == "__main__":
    asyncio.run(test_ai_publish())





