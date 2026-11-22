"""
测试：搜索"宠物医院"关键词并下载真实抖音视频素材
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

# 导入模块
from ai_pipeline.crawler import search_videos
from ai_pipeline.video_downloader import download_video

def main():
    keyword = "宠物医院"
    logger.info("=" * 70)
    logger.info(f"测试：搜索并下载 '{keyword}' 相关真实视频素材")
    logger.info("=" * 70)
    logger.info("")
    
    # 步骤1: 搜索视频
    logger.info("步骤1: 搜索爆款视频...")
    logger.info("-" * 70)
    
    videos = search_videos(keyword)
    
    if not videos:
        logger.error("未找到符合条件的视频")
        return
    
    logger.info(f"✓ 找到 {len(videos)} 条符合条件的视频：")
    logger.info("")
    for i, video in enumerate(videos, 1):
        logger.info(f"视频 {i}:")
        logger.info(f"  描述: {video.get('desc', '')}")
        logger.info(f"  播放量: {video.get('playCount', 0):,}")
        logger.info(f"  点赞数: {video.get('diggCount', 0):,}")
        logger.info(f"  作者: @{video.get('author', 'unknown')}")
        logger.info(f"  链接: {video.get('video_url', '')}")
        logger.info("")
    
    # 步骤2: 下载视频（下载前3个）
    logger.info("")
    logger.info("=" * 70)
    logger.info("步骤2: 下载视频素材...")
    logger.info("=" * 70)
    
    # 创建下载目录
    download_dir = current_dir / "materials" / keyword.replace(" ", "_")
    download_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"下载目录: {download_dir}")
    logger.info("")
    
    downloaded_files = []
    for i, video in enumerate(videos[:3], 1):  # 只下载前3个
        video_url = video.get('video_url', '')
        if not video_url or 'mock' in video_url:
            logger.warning(f"视频 {i} URL无效，跳过")
            continue
        
        logger.info(f"正在下载视频 {i}/{min(3, len(videos))}:")
        logger.info(f"  URL: {video_url}")
        logger.info(f"  描述: {video.get('desc', '')[:60]}...")
        
        try:
            video_path = download_video(video_url, download_dir)
            if video_path and Path(video_path).exists():
                downloaded_files.append(video_path)
                file_size = Path(video_path).stat().st_size / (1024 * 1024)  # MB
                logger.info(f"  ✓ 下载成功: {video_path.name}")
                logger.info(f"  大小: {file_size:.2f} MB")
                logger.info(f"  路径: {video_path}")
            else:
                logger.error(f"  ✗ 下载失败：文件不存在")
        except Exception as e:
            logger.error(f"  ✗ 下载出错: {e}")
        
        logger.info("")
    
    # 总结
    logger.info("")
    logger.info("=" * 70)
    logger.info("下载完成！")
    logger.info("=" * 70)
    logger.info(f"成功下载 {len(downloaded_files)} 个视频文件：")
    for file_path in downloaded_files:
        file_size = Path(file_path).stat().st_size / (1024 * 1024)
        logger.info(f"  ✓ {file_path.name} ({file_size:.2f} MB)")
    logger.info("")
    logger.info(f"文件保存在: {download_dir}")
    logger.info("")
    logger.info("你可以打开该目录查看下载的视频文件")

if __name__ == "__main__":
    main()

