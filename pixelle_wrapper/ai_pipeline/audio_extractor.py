"""
音频提取模块 - 从视频中提取音频
"""
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from moviepy.editor import VideoFileClip
    MOVIEPY_AVAILABLE = True
except ImportError:
    logger.warning("MoviePy 未安装，请安装: pip install moviepy")
    MOVIEPY_AVAILABLE = False
    VideoFileClip = None


def extract_audio_from_video(video_path: str, output_dir: Optional[Path] = None) -> Optional[Path]:
    """
    从视频中提取音频
    
    Args:
        video_path: 视频文件路径
        output_dir: 输出目录，默认为视频文件同目录
        
    Returns:
        提取的音频文件路径（MP3格式）
    """
    logger.info(f"[AudioExtractor] 开始提取音频: {video_path}")
    
    if not MOVIEPY_AVAILABLE or VideoFileClip is None:
        logger.error("[AudioExtractor] MoviePy 未安装")
        return None
    
    try:
        video_path = Path(video_path)
        if not video_path.exists():
            logger.error(f"[AudioExtractor] 视频文件不存在: {video_path}")
            return None
        
        # 设置输出目录
        if output_dir is None:
            output_dir = video_path.parent
        else:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
        
        # 提取音频
        logger.info("[AudioExtractor] 加载视频文件...")
        video = VideoFileClip(str(video_path))
        
        # 检查视频是否有音频轨道
        if video.audio is None:
            logger.warning("[AudioExtractor] 视频没有音频轨道，将返回视频路径供Whisper直接处理")
            video.close()
            # 返回视频路径，让Whisper直接处理视频
            return video_path
        
        # 生成音频文件路径
        audio_path = output_dir / f"{video_path.stem}.mp3"
        
        logger.info(f"[AudioExtractor] 提取音频到: {audio_path}")
        try:
            video.audio.write_audiofile(
                str(audio_path),
                codec='mp3',
                bitrate='192k',
                verbose=False,
                logger=None
            )
        except Exception as e:
            logger.warning(f"[AudioExtractor] 提取音频失败: {e}，将返回视频路径供Whisper直接处理")
            video.close()
            return video_path
        
        # 关闭视频对象
        video.close()
        
        logger.info(f"[AudioExtractor] 音频提取完成: {audio_path}")
        return audio_path
        
    except Exception as e:
        logger.error(f"[AudioExtractor] 提取音频时出错: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None

