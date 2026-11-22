"""
测试：直接搜索视频（不打开浏览器登录，先测试搜索功能）
"""
import sys
import logging
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# 添加项目路径
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

def main():
    logger.info("=" * 70)
    logger.info("测试：搜索抖音视频（浏览器会自动打开）")
    logger.info("=" * 70)
    logger.info("")
    
    try:
        from ai_pipeline.crawler import search_videos
        from ai_pipeline.video_downloader import download_video
        
        keyword = "宠物医院"
        logger.info(f"搜索关键词: {keyword}")
        logger.info("注意：浏览器会自动打开，请等待搜索完成")
        logger.info("")
        
        videos = search_videos(keyword)
        
        if not videos:
            logger.error("未找到符合条件的视频")
            return
        
        logger.info(f"找到 {len(videos)} 条符合条件的视频：")
        logger.info("")
        for i, video in enumerate(videos, 1):
            logger.info(f"视频 {i}:")
            logger.info(f"  描述: {video.get('desc', '')}")
            logger.info(f"  播放量: {video.get('playCount', 0):,}")
            logger.info(f"  点赞数: {video.get('diggCount', 0):,}")
            logger.info(f"  链接: {video.get('video_url', '')}")
            logger.info("")
        
        # 测试下载第一个真实视频
        logger.info("")
        logger.info("=" * 70)
        logger.info("测试下载功能...")
        logger.info("=" * 70)
        
        download_dir = current_dir / "materials" / keyword.replace(" ", "_")
        download_dir.mkdir(parents=True, exist_ok=True)
        
        for i, video in enumerate(videos[:1], 1):  # 只下载第一个
            video_url = video.get('video_url', '')
            if not video_url or 'mock' in video_url:
                logger.warning(f"视频 {i} URL无效，跳过")
                continue
            
            logger.info(f"正在下载视频 {i}:")
            logger.info(f"  URL: {video_url}")
            
            try:
                video_path = download_video(video_url, download_dir)
                if video_path and Path(video_path).exists():
                    file_size = Path(video_path).stat().st_size / (1024 * 1024)
                    logger.info(f"  ✓ 下载成功: {video_path.name}")
                    logger.info(f"  大小: {file_size:.2f} MB")
                    logger.info(f"  路径: {video_path}")
                else:
                    logger.error(f"  ✗ 下载失败")
            except Exception as e:
                logger.error(f"  ✗ 下载出错: {e}")
        
    except Exception as e:
        logger.error(f"测试失败: {e}")
        import traceback
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    main()







