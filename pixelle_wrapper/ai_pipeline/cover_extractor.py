"""
封面提取模块 - 从视频中提取封面图片
"""
import logging
import subprocess
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def extract_cover_from_video(video_path: str, output_dir: Optional[Path] = None, time_offset: float = 1.0) -> Optional[Path]:
    """
    从视频中提取封面图片（使用FFmpeg）
    
    Args:
        video_path: 视频文件路径
        output_dir: 输出目录，默认为视频文件同目录
        time_offset: 提取时间点（秒），默认1秒
        
    Returns:
        提取的封面图片路径（JPG格式）
    """
    logger.info(f"[CoverExtractor] 开始提取封面: {video_path}")
    
    # 查找FFmpeg（优先使用项目内的FFmpeg）
    ffmpeg_path = None
    
    # 方法1: 检查项目内的FFmpeg
    wrapper_dir = Path(__file__).parent.parent
    project_ffmpeg = wrapper_dir / "ffmpeg" / "bin" / "ffmpeg.exe"
    if project_ffmpeg.exists():
        ffmpeg_path = str(project_ffmpeg)
        logger.info(f"[CoverExtractor] 使用项目内的FFmpeg: {ffmpeg_path}")
    else:
        # 方法2: 检查系统PATH
        ffmpeg_path = shutil.which("ffmpeg")
        if ffmpeg_path:
            logger.info(f"[CoverExtractor] 使用系统PATH中的FFmpeg: {ffmpeg_path}")
    
    if not ffmpeg_path:
        logger.error("[CoverExtractor] FFmpeg 未找到，请安装 FFmpeg")
        return None
    
    try:
        video_path = Path(video_path)
        if not video_path.exists():
            logger.error(f"[CoverExtractor] 视频文件不存在: {video_path}")
            return None
        
        # 设置输出目录
        if output_dir is None:
            output_dir = video_path.parent
        else:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成封面文件路径
        cover_path = output_dir / f"{video_path.stem}_cover.jpg"
        
        logger.info(f"[CoverExtractor] 提取封面到: {cover_path}")
        logger.info(f"[CoverExtractor] 使用FFmpeg: {ffmpeg_path}")
        logger.info(f"[CoverExtractor] 提取时间点: {time_offset}秒")
        
        # 使用FFmpeg提取封面
        cmd = [
            ffmpeg_path,
            "-i", str(video_path),
            "-ss", str(time_offset),  # 跳转到指定时间
            "-vframes", "1",  # 只提取一帧
            "-q:v", "2",  # 高质量
            "-y",  # 覆盖输出文件
            str(cover_path)
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0 and cover_path.exists():
            logger.info(f"[CoverExtractor] 封面提取成功: {cover_path}")
            return cover_path
        else:
            logger.error(f"[CoverExtractor] FFmpeg提取失败: {result.stderr}")
            return None
            
    except subprocess.TimeoutExpired:
        logger.error("[CoverExtractor] FFmpeg提取超时")
        return None
    except Exception as e:
        logger.error(f"[CoverExtractor] 提取封面时出错: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None

