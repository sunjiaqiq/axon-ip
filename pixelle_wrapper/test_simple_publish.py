"""
简单测试发布功能（直接调用，不通过 GLM 5）
"""
import asyncio
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

async def test_simple_publish():
    """直接测试发布功能"""
    try:
        import douyin_publish_mcp
        
        logger.info("=" * 70)
        logger.info("简单测试：直接调用发布功能")
        logger.info("=" * 70)
        
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
                video_path = str(final_video)
                logger.info(f"[测试] 找到视频: {video_path}")
                break
        
        if not video_path:
            logger.error("未找到测试视频")
            return
        
        # 直接调用发布函数
        logger.info("\n[测试] 开始发布视频...")
        logger.info(f"[测试] 视频: {video_path}")
        logger.info(f"[测试] 标题: 测试视频 - 自然语言定位")
        logger.info(f"[测试] 描述: 这是使用自然语言定位功能发布的测试视频")
        
        result = await douyin_publish_mcp._publish_video_impl(
            video_path=video_path,
            title="测试视频 - 自然语言定位",
            description="这是使用自然语言定位功能发布的测试视频"
        )
        
        logger.info("\n" + "=" * 70)
        logger.info("[测试] 发布结果:")
        logger.info(result)
        logger.info("=" * 70)
        
        logger.info("\n[测试] 浏览器将保持打开，您可以查看发布状态")
        logger.info("[提示] 按 Ctrl+C 关闭...")
        
        # 保持浏览器打开（保持引用防止垃圾回收）
        browser_context_ref = douyin_publish_mcp.browser_context
        main_page_ref = douyin_publish_mcp.main_page
        
        try:
            while True:
                await asyncio.sleep(1)
                # 保持引用
                _ = browser_context_ref
                _ = main_page_ref
        except KeyboardInterrupt:
            logger.info("\n[测试] 测试完成")
            # 保持引用，防止垃圾回收
            _ = browser_context_ref
            _ = main_page_ref
        
    except Exception as e:
        logger.error(f"[测试] 错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_simple_publish())

