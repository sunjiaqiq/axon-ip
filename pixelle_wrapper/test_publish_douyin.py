"""
测试抖音发布功能
"""
import asyncio
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

async def test_publish():
    """测试发布功能"""
    from ai_pipeline.publisher import _publish_to_douyin_async
    
    # 查找一个测试视频（从output目录）
    output_dir = Path(__file__).parent / "output"
    if not output_dir.exists():
        logger.error("output目录不存在")
        return
    
    # 查找最新的任务目录中的final.mp4
    video_path = None
    task_dirs = sorted([d for d in output_dir.iterdir() if d.is_dir()], key=lambda x: x.stat().st_mtime, reverse=True)
    for task_dir in task_dirs:
        final_video = task_dir / "final.mp4"
        if final_video.exists():
            video_path = final_video
            logger.info(f"找到视频: {video_path}")
            break
    
    if not video_path:
        logger.error("未找到测试视频，请先生成一个视频")
        return
    
    # 测试发布（使用简单的文字）
    title = "测试视频"
    description = "测试"
    
    logger.info("=" * 70)
    logger.info("测试抖音发布功能")
    logger.info("=" * 70)
    logger.info(f"视频路径: {video_path}")
    logger.info(f"标题: {title}")
    logger.info(f"描述: {description}")
    logger.info("=" * 70)
    logger.info("")
    
    success = await _publish_to_douyin_async(
        str(video_path),
        title=title,
        description=description,
        cover_path=None
    )
    
    if success:
        logger.info("✓ 发布成功！")
    else:
        logger.error("✗ 发布失败")

if __name__ == "__main__":
    asyncio.run(test_publish())


