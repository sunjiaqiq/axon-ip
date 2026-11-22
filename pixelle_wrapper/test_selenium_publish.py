"""
测试 Selenium 方式的抖音发布
"""
import logging
from pathlib import Path
import douyin_publish_mcp

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def test_selenium_publish():
    """测试发布功能"""
    try:
        logger.info("=" * 70)
        logger.info("测试：Selenium 方式发布视频")
        logger.info("=" * 70)
        
        # 查找测试视频
        output_dir = Path(__file__).parent / "output"
        video_path = None
        if output_dir.exists():
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
        
        logger.info("\n[测试] 开始发布视频...")
        logger.info(f"[测试] 视频: {video_path}")
        logger.info(f"[测试] 标题: 测试视频 - Selenium方式")
        logger.info(f"[测试] 描述: 这是使用Selenium方式发布的测试视频")
        
        result = douyin_publish_mcp._publish_video_impl(
            video_path=video_path,
            title="测试视频 - Selenium方式",
            description="这是使用Selenium方式发布的测试视频"
        )
        
        logger.info("\n" + "=" * 70)
        logger.info("[测试] 发布结果:")
        logger.info(result)
        logger.info("=" * 70)
        
        logger.info("\n[测试] 浏览器将保持打开，您可以查看发布状态")
        logger.info("[提示] 按回车键关闭浏览器...")
        
        input()
        
        # 关闭浏览器
        if douyin_publish_mcp.driver:
            douyin_publish_mcp.driver.quit()
            logger.info("[测试] 浏览器已关闭")
        
    except Exception as e:
        logger.error(f"[测试] 错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_selenium_publish()





