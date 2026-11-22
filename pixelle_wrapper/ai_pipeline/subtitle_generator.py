"""
字幕生成模块 - 使用 Whisper 生成字幕
"""
import logging
import sys
import os
import shutil
from pathlib import Path
from typing import Optional

# 添加 Whisper 路径
# current_dir 是项目根目录（shuziren/）
current_dir = Path(__file__).parent.parent.parent
project_root = current_dir  # 项目根目录
whisper_path = project_root / "whisper-main"
if whisper_path.exists():
    sys.path.insert(0, str(whisper_path))

logger = logging.getLogger(__name__)

try:
    import whisper
except ImportError:
    logger.warning("whisper 未安装，请安装: pip install openai-whisper")
    whisper = None

try:
    from pydub import AudioSegment
    import numpy as np
    PYDUB_AVAILABLE = True
except ImportError:
    logger.warning("pydub 未安装，将尝试使用Whisper内置方法")
    PYDUB_AVAILABLE = False
    AudioSegment = None


def _find_ffmpeg() -> Optional[str]:
    """查找FFmpeg可执行文件"""
    # 方法1: 优先检查项目内的env/ffmpeg/ffmpeg.exe
    env_ffmpeg = project_root / "env" / "ffmpeg" / "ffmpeg.exe"
    if env_ffmpeg.exists():
        logger.info(f"[SubtitleGenerator] 在项目env目录中找到FFmpeg: {env_ffmpeg}")
        # 将FFmpeg目录添加到PATH（仅当前进程）
        ffmpeg_dir = str(env_ffmpeg.parent)
        os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
        return str(env_ffmpeg)
    
    # 方法2: 检查PATH
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        logger.info(f"[SubtitleGenerator] 在PATH中找到FFmpeg: {ffmpeg_path}")
        return ffmpeg_path
    
    # 方法3: 检查常见位置（包括剪映等软件的FFmpeg）
    common_paths = [
        "C:\\ffmpeg\\bin\\ffmpeg.exe",
        "C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe",
        "C:\\Program Files (x86)\\ffmpeg\\bin\\ffmpeg.exe",
        os.path.expanduser("~\\ffmpeg\\bin\\ffmpeg.exe"),
        # 剪映的FFmpeg
        "D:\\JianyingPro\\10.2.0.13877\\ffmpeg.exe",
        "D:\\JianyingPro\\*\\ffmpeg.exe",  # 通配符路径，需要特殊处理
    ]
    
    for path in common_paths:
        # 处理通配符路径
        if "*" in path:
            import glob
            matches = glob.glob(path)
            if matches:
                path = matches[0]
        
        if os.path.exists(path):
            logger.info(f"[SubtitleGenerator] 在常见位置找到FFmpeg: {path}")
            # 将FFmpeg目录添加到PATH（仅当前进程）
            ffmpeg_dir = os.path.dirname(path)
            os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
            return path
    
    # 方法4: 搜索整个D盘（剪映通常在D盘）
    try:
        import glob
        d_ffmpeg = glob.glob("D:\\JianyingPro\\*\\ffmpeg.exe")
        if d_ffmpeg:
            path = d_ffmpeg[0]
            logger.info(f"[SubtitleGenerator] 在D盘找到FFmpeg: {path}")
            ffmpeg_dir = os.path.dirname(path)
            os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
            return path
    except:
        pass
    
    logger.warning("[SubtitleGenerator] 未找到FFmpeg，请确保FFmpeg已安装并在PATH中")
    return None


def generate_subtitle(audio_path: str, output_dir: Optional[Path] = None) -> Optional[Path]:
    """
    从音频或视频生成字幕文件（Whisper可以直接处理视频）
    
    Args:
        audio_path: 音频或视频文件路径
        output_dir: 输出目录，默认为文件同目录
        
    Returns:
        生成的SRT字幕文件路径
    """
    logger.info(f"[SubtitleGenerator] 开始生成字幕: {audio_path}")
    
    if whisper is None:
        logger.error("[SubtitleGenerator] Whisper 未安装")
        return None
    
    # 查找FFmpeg（如果找不到，尝试使用pydub作为备选）
    ffmpeg_path = _find_ffmpeg()
    use_pydub = False
    if not ffmpeg_path:
        if PYDUB_AVAILABLE:
            logger.warning("[SubtitleGenerator] 未找到FFmpeg，尝试使用pydub处理音频")
            use_pydub = True
        else:
            logger.error("[SubtitleGenerator] 未找到FFmpeg，且pydub未安装")
            logger.error("[SubtitleGenerator] 请安装FFmpeg或pydub: pip install pydub")
            return None
    
    try:
        audio_path = Path(audio_path)
        if not audio_path.exists():
            logger.error(f"[SubtitleGenerator] 文件不存在: {audio_path}")
            return None
        
        # 设置输出目录
        if output_dir is None:
            output_dir = audio_path.parent
        else:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
        
        # 加载Whisper模型（使用base模型，速度较快）
        logger.info("[SubtitleGenerator] 加载Whisper模型...")
        model = whisper.load_model("base")
        
        # 转录音频
        logger.info("[SubtitleGenerator] 开始转录...")
        
        # 如果使用pydub，先转换音频格式
        if use_pydub:
            try:
                logger.info("[SubtitleGenerator] 使用pydub加载音频...")
                audio_segment = AudioSegment.from_file(str(audio_path))
                # 转换为numpy数组（16kHz单声道，float32）
                audio_array = np.array(audio_segment.set_frame_rate(16000).set_channels(1).get_array_of_samples(), dtype=np.float32)
                audio_array = audio_array / 32768.0  # 归一化到[-1, 1]
                
                logger.info(f"[SubtitleGenerator] 音频加载完成，长度: {len(audio_array)/16000:.2f}秒")
                result = model.transcribe(
                    audio_array,
                    language="zh",  # 中文
                    task="transcribe"
                )
            except Exception as pydub_error:
                logger.error(f"[SubtitleGenerator] pydub处理失败: {pydub_error}")
                logger.error("[SubtitleGenerator] 请安装FFmpeg: https://ffmpeg.org/download.html")
                return None
        else:
            # 使用Whisper内置方法（需要FFmpeg）
            result = model.transcribe(
                str(audio_path),
                language="zh",  # 中文
                task="transcribe"
            )
        
        # 生成SRT格式字幕
        srt_path = output_dir / f"{audio_path.stem}.srt"
        _write_srt(result["segments"], srt_path)
        
        # 同时保存完整文本到txt文件（方便提取文案）
        txt_path = output_dir / f"{audio_path.stem}.txt"
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(result["text"])
        logger.info(f"[SubtitleGenerator] 文案文本已保存: {txt_path}")
        
        logger.info(f"[SubtitleGenerator] 字幕生成完成: {srt_path}")
        return srt_path
        
    except Exception as e:
        logger.error(f"[SubtitleGenerator] 生成字幕时出错: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


def _write_srt(segments: list, output_path: Path):
    """将Whisper分段结果写入SRT文件"""
    with open(output_path, 'w', encoding='utf-8') as f:
        for i, segment in enumerate(segments, 1):
            start = _format_timestamp(segment['start'])
            end = _format_timestamp(segment['end'])
            text = segment['text'].strip()
            
            f.write(f"{i}\n")
            f.write(f"{start} --> {end}\n")
            f.write(f"{text}\n\n")


def _format_timestamp(seconds: float) -> str:
    """将秒数转换为SRT时间格式 (HH:MM:SS,mmm)"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

