"""
视频编辑模块 - 使用 MoviePy 插入素材
"""
import logging
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

try:
    from moviepy.editor import VideoFileClip, CompositeVideoClip, concatenate_videoclips, AudioFileClip, CompositeAudioClip
except ImportError:
    logger.warning("MoviePy 未安装，请安装: pip install moviepy")
    VideoFileClip = None
    AudioFileClip = None
    CompositeAudioClip = None


def insert_material(host_video: str, materials: List[str], output_path: Optional[str] = None) -> Optional[Path]:
    """
    将素材插入到主视频中
    
    逻辑：
    0-3秒 主播
    3-5秒 素材
    5-8秒 主播
    8-10秒 素材
    循环插入
    
    Args:
        host_video: 主视频路径（主播视频）
        materials: 素材视频路径列表
        output_path: 输出路径，默认为 host_video 同目录
        
    Returns:
        编辑后的视频路径
    """
    logger.info(f"[VideoEditor] 开始插入素材，主视频: {host_video}, 素材数量: {len(materials)}")
    
    if VideoFileClip is None:
        logger.error("[VideoEditor] MoviePy 未安装")
        return None
    
    try:
        host_video = Path(host_video)
        if not host_video.exists():
            logger.error(f"[VideoEditor] 主视频不存在: {host_video}")
            return None
        
        # 设置输出路径
        if output_path is None:
            output_path = host_video.parent / f"{host_video.stem}_edited.mp4"
        else:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 加载主视频
        logger.info("[VideoEditor] 加载主视频...")
        host_clip = VideoFileClip(str(host_video))
        host_duration = host_clip.duration
        
        # 加载素材视频
        material_clips = []
        for material_path in materials:
            material_path = Path(material_path)
            if material_path.exists():
                try:
                    clip = VideoFileClip(str(material_path))
                    # 裁剪到2秒
                    clip = clip.subclip(0, min(2, clip.duration))
                    material_clips.append(clip)
                    logger.info(f"[VideoEditor] 加载素材: {material_path.name}")
                except Exception as e:
                    logger.warning(f"[VideoEditor] 加载素材失败 {material_path}: {e}")
                    continue
        
        if not material_clips:
            logger.warning("[VideoEditor] 没有可用的素材，直接返回主视频")
            host_clip.write_videofile(str(output_path), codec='libx264', audio_codec='aac')
            host_clip.close()
            return output_path
        
        # 构建时间轴
        # 0-3秒: 主播
        # 3-5秒: 素材1
        # 5-8秒: 主播
        # 8-10秒: 素材2
        # 循环...
        
        segments = []
        current_time = 0
        material_index = 0
        
        while current_time < host_duration:
            # 主播片段（3秒）
            if current_time + 3 <= host_duration:
                host_segment = host_clip.subclip(current_time, min(current_time + 3, host_duration))
                segments.append(host_segment)
                current_time += 3
            else:
                # 剩余部分
                host_segment = host_clip.subclip(current_time, host_duration)
                segments.append(host_segment)
                break
            
            # 素材片段（2秒）
            if material_index < len(material_clips):
                material_clip = material_clips[material_index % len(material_clips)]
                segments.append(material_clip)
                material_index += 1
                current_time += 2
            else:
                # 如果没有更多素材，继续使用主播视频
                if current_time + 2 <= host_duration:
                    host_segment = host_clip.subclip(current_time, min(current_time + 2, host_duration))
                    segments.append(host_segment)
                    current_time += 2
                else:
                    break
        
        # 合并所有片段
        logger.info(f"[VideoEditor] 合并 {len(segments)} 个片段...")
        final_clip = concatenate_videoclips(segments, method="compose")
        
        # 输出视频
        logger.info(f"[VideoEditor] 输出视频到: {output_path}")
        final_clip.write_videofile(
            str(output_path),
            codec='libx264',
            audio_codec='aac',
            fps=30,
            preset='medium',
            bitrate='8000k'
        )
        
        # 清理资源
        final_clip.close()
        host_clip.close()
        for clip in material_clips:
            clip.close()
        
        logger.info(f"[VideoEditor] 编辑完成: {output_path}")
        return output_path
        
    except Exception as e:
        logger.error(f"[VideoEditor] 编辑视频时出错: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


def add_picture_in_picture(
    host_video: str,
    showcase_videos: List[str],
    output_path: Optional[str] = None,
    start_time: float = 3.0,
    end_before: float = 5.0,
    end_time: Optional[float] = None,
    position: str = 'center',
    size_ratio: float = 2/3,
    loop: bool = True,
    effect: str = 'zoom'
) -> Optional[Path]:
    """
    添加画中画效果到口播视频
    
    时间轴设计:
    - 0 到 start_time 秒: 纯口播（无画中画）
    - start_time 到 (总时长 - end_before) 秒: 口播 + 画中画（循环播放展示视频）
    - (总时长 - end_before) 到结束: 纯口播（无画中画）
    
    Args:
        host_video: 主视频路径（口播视频）
        showcase_videos: 展示视频列表（店铺环境、产品展示等）
        output_path: 输出路径，默认为 host_video 同目录
        start_time: 画中画开始时间（秒），默认3秒
        end_before: 结束前多少秒停止画中画，默认5秒
        end_time: 指定画中画结束的绝对时间（秒）。当传入时会覆盖 end_before；默认None（使用 end_before）
        position: 画中画位置 ('top-left', 'top-right', 'bottom-left', 'bottom-right', 'center')，默认'center'
        size_ratio: 画中画大小占比（0.1-1.0），默认2/3（66.7%）
        loop: 是否循环播放展示视频，默认True
        effect: 特效类型 ('fade', 'zoom', 'slide', None) - 淡入淡出、缩放进入、滑入动画，默认'zoom'
        
    Returns:
        编辑后的视频路径
    """
    logger.info(f"[VideoEditor] 开始添加画中画，主视频: {host_video}, 展示视频数量: {len(showcase_videos)}")
    logger.info(
        f"[VideoEditor] 参数: start_time={start_time}s, end_before={end_before}s, end_time={end_time}s, position={position}, size_ratio={size_ratio}"
    )
    
    if VideoFileClip is None:
        logger.error("[VideoEditor] MoviePy 未安装")
        return None
    
    try:
        host_video = Path(host_video)
        if not host_video.exists():
            logger.error(f"[VideoEditor] 主视频不存在: {host_video}")
            return None
        
        # 设置输出路径
        if output_path is None:
            output_path = host_video.parent / f"{host_video.stem}_pip.mp4"
        else:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 加载主视频（口播视频）
        logger.info("[VideoEditor] 加载主视频...")
        host_clip = VideoFileClip(str(host_video))
        host_duration = host_clip.duration
        host_w, host_h = host_clip.size
        
        logger.info(f"[VideoEditor] 主视频时长: {host_duration:.2f}秒, 分辨率: {host_w}x{host_h}")
        
        # 计算画中画显示时间段
        pip_start = start_time
        if end_time is not None:
            # 当明确给了 end_time 时，严格按绝对时间截断（必要时再由校验决定是否可用）
            pip_end = min(float(end_time), host_duration)
        else:
            pip_end = max(host_duration - end_before, pip_start + 1)  # 至少显示1秒
        
        if pip_end <= pip_start:
            logger.warning(f"[VideoEditor] 画中画时间段无效（{pip_start}-{pip_end}），直接返回主视频")
            host_clip.write_videofile(str(output_path), codec='libx264', audio_codec='aac')
            host_clip.close()
            return output_path
        
        logger.info(f"[VideoEditor] 画中画时间段: {pip_start:.2f}秒 - {pip_end:.2f}秒")
        
        # 加载展示视频
        showcase_clips = []
        for showcase_path in showcase_videos:
            showcase_path = Path(showcase_path)
            if showcase_path.exists():
                try:
                    clip = VideoFileClip(str(showcase_path))
                    # 调整大小
                    pip_w = int(host_w * size_ratio)
                    pip_h = int(host_h * size_ratio)
                    clip = clip.resize((pip_w, pip_h))
                    # 静音画中画视频的音频
                    clip = clip.without_audio()
                    showcase_clips.append(clip)
                    logger.info(f"[VideoEditor] 加载展示视频: {showcase_path.name}, 大小: {pip_w}x{pip_h}")
                except Exception as e:
                    logger.warning(f"[VideoEditor] 加载展示视频失败 {showcase_path}: {e}")
                    continue
        
        if not showcase_clips:
            logger.warning("[VideoEditor] 没有可用的展示视频，直接返回主视频")
            host_clip.write_videofile(str(output_path), codec='libx264', audio_codec='aac')
            host_clip.close()
            return output_path
        
        # 计算画中画显示时长
        pip_duration = pip_end - pip_start
        
        # 创建循环播放的展示视频
        if loop:
            # 计算需要循环多少次才能覆盖整个时间段
            total_showcase_duration = sum(clip.duration for clip in showcase_clips)
            if total_showcase_duration > 0:
                loops_needed = int(pip_duration / total_showcase_duration) + 1
                logger.info(f"[VideoEditor] 需要循环 {loops_needed} 次来覆盖 {pip_duration:.2f} 秒")
                
                # 创建循环视频列表
                looped_clips = []
                for _ in range(loops_needed):
                    for clip in showcase_clips:
                        looped_clips.append(clip)
                
                # 合并所有循环视频
                pip_clip = concatenate_videoclips(looped_clips, method="compose")
                # 裁剪到需要的时长
                pip_clip = pip_clip.subclip(0, pip_duration)
            else:
                # 如果视频总时长为0，使用第一个视频
                pip_clip = showcase_clips[0].loop(duration=pip_duration)
        else:
            # 不循环，只播放一次
            if len(showcase_clips) == 1:
                pip_clip = showcase_clips[0].subclip(0, min(pip_duration, showcase_clips[0].duration))
            else:
                # 多个视频顺序播放
                pip_clip = concatenate_videoclips(showcase_clips, method="compose")
                pip_clip = pip_clip.subclip(0, min(pip_duration, pip_clip.duration))
        
        # 设置画中画位置
        pip_w, pip_h = pip_clip.size
        
        position_map = {
            'top-left': (10, 10),
            'top-right': (host_w - pip_w - 10, 10),
            'bottom-left': (10, host_h - pip_h - 10),
            'bottom-right': (host_w - pip_w - 10, host_h - pip_h - 10),
            'center': ((host_w - pip_w) // 2, (host_h - pip_h) // 2)
        }
        
        if position in position_map:
            pip_x, pip_y = position_map[position]
        else:
            # 默认右下角
            pip_x, pip_y = position_map['bottom-right']
        
        logger.info(f"[VideoEditor] 画中画位置: ({pip_x}, {pip_y})")
        
        # 应用特效
        if effect == 'fade':
            # 淡入淡出效果
            fade_duration = min(0.5, pip_duration / 4)  # 淡入淡出时间，最多0.5秒
            pip_clip = pip_clip.fadein(fade_duration).fadeout(fade_duration)
            logger.info(f"[VideoEditor] 应用淡入淡出特效，时长: {fade_duration:.2f}秒")
        elif effect == 'zoom':
            # 缩放进入效果（从小变大）
            import numpy as np
            original_w, original_h = pip_clip.size
            def zoom_func(t):
                if t < 0.5:  # 前0.5秒从小变大
                    scale = 0.3 + (t / 0.5) * 0.7  # 从30%到100%
                else:
                    scale = 1.0
                return (int(original_w * scale), int(original_h * scale))
            pip_clip = pip_clip.resize(zoom_func)
            logger.info(f"[VideoEditor] 应用缩放进入特效")
        elif effect == 'slide':
            # 滑入动画（从右侧滑入）
            def slide_position(t):
                slide_time = 0.5  # 滑入时间0.5秒
                if t < slide_time:
                    # 从右侧滑入
                    progress = t / slide_time
                    x = host_w - (host_w - pip_x) * (1 - progress)
                    return (x, pip_y)
                else:
                    return (pip_x, pip_y)
            pip_clip = pip_clip.set_position(slide_position)
            logger.info(f"[VideoEditor] 应用滑入动画特效（从右侧滑入）")
        
        # 设置画中画的时间段（只在指定时间段显示）
        pip_clip = pip_clip.set_start(pip_start)
        if effect != 'slide':  # slide效果已经在set_position中处理了位置
            pip_clip = pip_clip.set_position((pip_x, pip_y))
        
        # 创建合成视频（主视频 + 画中画）
        logger.info("[VideoEditor] 创建画中画合成视频...")
        final_clip = CompositeVideoClip([host_clip, pip_clip])
        
        # 输出视频
        logger.info(f"[VideoEditor] 输出视频到: {output_path}")
        final_clip.write_videofile(
            str(output_path),
            codec='libx264',
            audio_codec='aac',
            fps=30,
            preset='medium',
            bitrate='8000k'
        )
        
        # 清理资源
        final_clip.close()
        host_clip.close()
        pip_clip.close()
        for clip in showcase_clips:
            clip.close()
        
        logger.info(f"[VideoEditor] 画中画编辑完成: {output_path}")
        return output_path
        
    except Exception as e:
        logger.error(f"[VideoEditor] 添加画中画时出错: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


def add_background_music(
    video_path: str,
    music_path: str,
    output_path: Optional[str] = None,
    music_volume: float = 0.3,
    original_volume: float = 1.0,
    fade_in: float = 0.0,
    fade_out: float = 0.0,
    loop: bool = True
) -> Optional[Path]:
    """
    给视频添加背景音乐
    
    Args:
        video_path: 视频文件路径
        music_path: 背景音乐文件路径（支持 MP3, AAC, WAV, M4A 等格式）
        output_path: 输出路径，默认为 video_path 同目录
        music_volume: 背景音乐音量（0.0-1.0），默认0.3（30%）
        original_volume: 原视频音频音量（0.0-1.0），默认1.0（100%）
        fade_in: 背景音乐淡入时长（秒），默认0.0（无淡入）
        fade_out: 背景音乐淡出时长（秒），默认0.0（无淡出）
        loop: 是否循环播放背景音乐（如果音乐比视频短），默认True
        
    Returns:
        编辑后的视频路径
    """
    logger.info(f"[VideoEditor] 开始添加背景音乐，视频: {video_path}, 音乐: {music_path}")
    logger.info(f"[VideoEditor] 参数: music_volume={music_volume}, original_volume={original_volume}, loop={loop}")
    
    if VideoFileClip is None or AudioFileClip is None or CompositeAudioClip is None:
        logger.error("[VideoEditor] MoviePy 未安装或缺少音频模块")
        return None
    
    try:
        video_path = Path(video_path)
        music_path = Path(music_path)
        
        if not video_path.exists():
            logger.error(f"[VideoEditor] 视频文件不存在: {video_path}")
            return None
        
        if not music_path.exists():
            logger.error(f"[VideoEditor] 音乐文件不存在: {music_path}")
            return None
        
        # 设置输出路径
        if output_path is None:
            output_path = video_path.parent / f"{video_path.stem}_with_music.mp4"
        else:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 加载视频
        logger.info("[VideoEditor] 加载视频文件...")
        video_clip = VideoFileClip(str(video_path))
        video_duration = video_clip.duration
        
        logger.info(f"[VideoEditor] 视频时长: {video_duration:.2f}秒")
        
        # 加载背景音乐
        logger.info("[VideoEditor] 加载背景音乐文件...")
        background_music = AudioFileClip(str(music_path))
        music_duration = background_music.duration
        
        logger.info(f"[VideoEditor] 音乐时长: {music_duration:.2f}秒")
        
        # 处理背景音乐时长
        if loop and music_duration < video_duration:
            # 循环播放背景音乐
            logger.info(f"[VideoEditor] 音乐比视频短，循环播放以匹配视频时长")
            background_music = background_music.loop(duration=video_duration)
        elif music_duration > video_duration:
            # 如果音乐比视频长，裁剪到视频长度
            logger.info(f"[VideoEditor] 音乐比视频长，裁剪到视频时长")
            background_music = background_music.subclip(0, video_duration)
        else:
            # 音乐和视频长度一致
            logger.info(f"[VideoEditor] 音乐和视频长度一致")
        
        # 调整音量
        if video_clip.audio is not None:
            original_audio = video_clip.audio.volumex(original_volume)
            logger.info(f"[VideoEditor] 原音频音量: {original_volume * 100:.0f}%")
        else:
            original_audio = None
            logger.warning("[VideoEditor] 视频没有音频轨道，只添加背景音乐")
        
        background_music = background_music.volumex(music_volume)
        logger.info(f"[VideoEditor] 背景音乐音量: {music_volume * 100:.0f}%")
        
        # 应用淡入淡出效果
        if fade_in > 0:
            background_music = background_music.fadein(fade_in)
            logger.info(f"[VideoEditor] 背景音乐淡入: {fade_in:.2f}秒")
        
        if fade_out > 0:
            background_music = background_music.fadeout(fade_out)
            logger.info(f"[VideoEditor] 背景音乐淡出: {fade_out:.2f}秒")
        
        # 混合音频
        if original_audio is not None:
            composite_audio = CompositeAudioClip([original_audio, background_music])
            logger.info("[VideoEditor] 混合原音频和背景音乐")
        else:
            composite_audio = background_music
            logger.info("[VideoEditor] 只使用背景音乐")
        
        # 设置混合后的音频
        final_video = video_clip.set_audio(composite_audio)
        
        # 输出视频
        logger.info(f"[VideoEditor] 输出视频到: {output_path}")
        final_video.write_videofile(
            str(output_path),
            codec='libx264',
            audio_codec='aac',
            fps=30,
            preset='medium',
            bitrate='8000k'
        )
        
        # 清理资源
        final_video.close()
        video_clip.close()
        background_music.close()
        if original_audio is not None:
            original_audio.close()
        composite_audio.close()
        
        logger.info(f"[VideoEditor] 背景音乐添加完成: {output_path}")
        return output_path
        
    except Exception as e:
        logger.error(f"[VideoEditor] 添加背景音乐时出错: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


