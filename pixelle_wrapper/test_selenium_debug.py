"""
调试版本的测试脚本，添加更多日志
"""
import logging
import time
from pathlib import Path
import douyin_publish_mcp

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def test_debug():
    """调试测试"""
    try:
        logger.info("=" * 70)
        logger.info("调试测试：Selenium 方式")
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
                    logger.info(f"[调试] 找到视频: {video_path}")
                    break
        
        if not video_path:
            logger.error("未找到测试视频")
            return
        
        logger.info("\n[调试] 步骤1: 启动浏览器...")
        if not douyin_publish_mcp.ensure_browser():
            logger.error("浏览器启动失败")
            return
        
        logger.info(f"[调试] 浏览器已启动，当前URL: {douyin_publish_mcp.driver.current_url}")
        
        logger.info("\n[调试] 步骤2: 导航到创作者中心...")
        upload_url = "https://creator.douyin.com/creator-micro/content/upload?enter_from=dou_web"
        logger.info(f"[调试] 导航到: {upload_url}")
        
        douyin_publish_mcp.driver.get(upload_url)
        logger.info("[调试] 等待页面加载...")
        time.sleep(5)
        
        logger.info(f"[调试] 当前URL: {douyin_publish_mcp.driver.current_url}")
        logger.info(f"[调试] 页面标题: {douyin_publish_mcp.driver.title}")
        
        logger.info("\n[调试] 等待3秒后自动继续执行发布流程...")
        time.sleep(3)
        
        logger.info("\n[调试] 步骤3: 开始发布流程...")
        result = douyin_publish_mcp._publish_video_impl(
            video_path=video_path,
            title="测试视频标题",
            description="这是测试视频的描述内容"
        )
        
        logger.info("\n" + "=" * 70)
        logger.info("[调试] 发布结果:")
        logger.info(result)
        logger.info("=" * 70)
        
        logger.info("\n[调试] 浏览器将保持打开30秒，您可以查看发布状态...")
        time.sleep(30)
        
        # 关闭浏览器
        if douyin_publish_mcp.driver:
            douyin_publish_mcp.driver.quit()
            logger.info("[调试] 浏览器已关闭")
        
    except Exception as e:
        logger.error(f"[调试] 错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_debug()

