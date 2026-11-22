"""
原创处理模块 - 避免视频hash重复，实现原创检测规避
"""
import logging
import random
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from moviepy.editor import VideoFileClip, CompositeVideoClip
    import numpy as np
except ImportError:
    logger.warning("MoviePy 未安装，请安装: pip install moviepy")
    VideoFileClip = None
    np = None


def apply_filter(video_path: str, output_path: Optional[str] = None) -> Optional[Path]:
    """
    应用原创处理，避免视频hash重复
    
    随机执行以下操作：
    - speed: 1.02x 速度调整
    - crop: 3% 裁剪
    - mirror: 30% 概率镜像
    
    Args:
        video_path: 输入视频路径
        output_path: 输出路径，默认为 video_path 同目录
        
    Returns:
        处理后的视频路径
    """
    logger.info(f"[OriginalFilter] 开始原创处理: {video_path}")
    
    if VideoFileClip is None:
        logger.error("[OriginalFilter] MoviePy 未安装")
        return None
    
    try:
        video_path = Path(video_path)
        if not video_path.exists():
            logger.error(f"[OriginalFilter] 视频文件不存在: {video_path}")
            return None
        
        # 设置输出路径
        if output_path is None:
            output_path = video_path.parent / f"{video_path.stem}_original.mp4"
        else:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 加载视频
        logger.info("[OriginalFilter] 加载视频...")
        clip = VideoFileClip(str(video_path))
        
        # 随机应用处理
        processed_clip = clip
        
        # 1. 速度调整 (1.02x)
        speed_factor = 1.02
        logger.info(f"[OriginalFilter] 应用速度调整: {speed_factor}x")
        processed_clip = processed_clip.fx(lambda c: c.set_duration(c.duration / speed_factor))
        processed_clip = processed_clip.fx(lambda c: c.set_fps(c.fps * speed_factor))
        
        # 2. 裁剪 (3%)
        crop_percent = 0.03
        logger.info(f"[OriginalFilter] 应用裁剪: {crop_percent*100}%")
        w, h = processed_clip.size
        crop_w = int(w * crop_percent)
        crop_h = int(h * crop_percent)
        processed_clip = processed_clip.crop(
            x1=crop_w, y1=crop_h,
            x2=w - crop_w, y2=h - crop_h
        )
        
        # 3. 镜像 (30% 概率)
        if random.random() < 0.3:
            logger.info("[OriginalFilter] 应用镜像")
            processed_clip = processed_clip.fx(lambda c: c.fl_image(lambda f: np.fliplr(f)))
        
        # 4. 轻微亮度调整（避免hash重复）
        brightness_factor = random.uniform(0.98, 1.02)
        logger.info(f"[OriginalFilter] 应用亮度调整: {brightness_factor}")
        if np is not None:
            processed_clip = processed_clip.fx(
                lambda c: c.fl_image(lambda f: np.clip(f * brightness_factor, 0, 255).astype(np.uint8))
            )
        
        # 输出视频
        logger.info(f"[OriginalFilter] 输出视频到: {output_path}")
        processed_clip.write_videofile(
            str(output_path),
            codec='libx264',
            audio_codec='aac',
            fps=30,
            preset='medium',
            bitrate='8000k'
        )
        
        # 清理资源
        processed_clip.close()
        clip.close()
        
        logger.info(f"[OriginalFilter] 原创处理完成: {output_path}")
        return output_path
        
    except Exception as e:
        logger.error(f"[OriginalFilter] 原创处理时出错: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None







