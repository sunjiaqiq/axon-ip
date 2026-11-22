"""
测试脚本：为视频添加动态字幕（抖音热门 - 金色文字样式）
字幕位置：底部
字幕样式：金色文字，黑色边框，56号字体

使用MoviePy库处理字幕（更可靠，不依赖FFmpeg滤镜支持）

【新流程】Whisper 时间戳 + 硅基按段识别：
  1. 用 Whisper 对口播视频跑一遍，只取每段的 start/end 时间戳
  2. 从视频提取整段音频，按时间戳切成多段
  3. 每段音频调用硅基流动 SenseVoice API 识别，得到该段正确文字
  4. 用「时间戳（Whisper）+ 文字（硅基）」生成 SRT，再烧录到视频
  这样字幕既对上时间，又避免乱码和文案分段错位。
"""
import os
import sys
import subprocess
from pathlib import Path
import shutil

try:
    from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip
    from PIL import Image, ImageDraw, ImageFont
    import numpy as np
    MOVIEPY_AVAILABLE = True
    PIL_AVAILABLE = True
except ImportError:
    MOVIEPY_AVAILABLE = False
    PIL_AVAILABLE = False
    print("[警告] MoviePy或PIL未安装，将尝试使用FFmpeg")

# 硅基流动语音识别 API（SenseVoice）
SILICONFLOW_TRANSCRIPTION_URL = "https://api.siliconflow.cn/v1/audio/transcriptions"
SILICONFLOW_ASR_MODEL = "FunAudioLLM/SenseVoiceSmall"


def sanitize_subtitle_text(text):
    """
    清洗字幕文本：不要标点、不要表情（emoji），只保留中文/英文/数字。
    """
    if not text:
        return ""
    import re
    # 去掉 emoji 及类似符号
    text = re.sub(r"[\U0001F300-\U0001F9FF\U0001F600-\U0001F64F\U0001F1E0-\U0001F1FF]", "", text)
    text = re.sub(r"[\uFFFD\u25A0-\u25FF\u2600-\u26FF\u2700-\u27BF]", "", text)
    # 去掉零宽字符、控制字符
    text = re.sub(r"[\u200B-\u200D\uFEFF\u2060]", "", text)
    text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", text)
    # 去掉所有标点（中英文、全角半角）
    text = re.sub(r"[，。！？、；：""''（）【】《》\s,.\!?;:\"'\(\)\[\]\s\u3000]", "", text)
    return text.strip()


def load_siliconflow_api_key():
    """从 config.yaml 或环境变量读取硅基 API Key（用于语音识别）"""
    api_key = os.environ.get("API_KEY", "").strip()
    if api_key:
        return api_key
    try:
        import yaml
        config_path = Path(__file__).parent / "config.yaml"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            if config and isinstance(config.get("siliconflow"), dict):
                api_key = (config["siliconflow"].get("api_key") or "").strip()
                if api_key:
                    return api_key
    except Exception:
        pass
    return ""


def cut_audio_segment(ffmpeg_path, full_audio_path, start_sec, duration_sec, output_path):
    """用 FFmpeg 从整段音频中截取 [start_sec, start_sec+duration_sec] 的一段"""
    try:
        cmd = [
            ffmpeg_path,
            "-y",
            "-i", str(full_audio_path),
            "-ss", str(start_sec),
            "-t", str(duration_sec),
            "-acodec", "libmp3lame",
            "-q:a", "0",
            str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
        return result.returncode == 0 and Path(output_path).exists()
    except Exception as e:
        print(f"[测试] 截取音频片段失败: {e}")
        return False


def transcribe_segment_siliconflow(audio_path, api_key, api_url=None, model=None):
    """
    用硅基流动 SenseVoice 转录单段音频，返回识别文本。
    失败返回空字符串。
    """
    api_url = api_url or SILICONFLOW_TRANSCRIPTION_URL
    model = model or SILICONFLOW_ASR_MODEL
    try:
        import requests
        with open(audio_path, "rb") as f:
            files = {"file": (Path(audio_path).name, f, "audio/mpeg"), "model": (None, model)}
            headers = {"Authorization": f"Bearer {api_key}"}
            resp = requests.post(api_url, files=files, headers=headers, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        return (data.get("text") or "").strip()
    except Exception as e:
        print(f"[测试] 硅基识别片段失败 {audio_path}: {e}")
        return ""


def get_whisper_timestamps(video_path, temp_dir):
    """调用 subtitle_burner 的 Whisper，只取时间戳 segments (start, end, text)。"""
    try:
        from subtitle_burner import get_whisper_timestamps as _get
        return _get(Path(video_path), Path(temp_dir))
    except Exception as e:
        print(f"[测试] 获取 Whisper 时间戳失败: {e}")
        return None


def extract_audio_from_video(video_path, temp_dir):
    """从视频提取整段音频为 MP3，供按段裁剪。"""
    try:
        from ai_pipeline.audio_extractor import extract_audio_from_video as _extract
        out = _extract(str(video_path), Path(temp_dir))
        return Path(out) if out and Path(out).exists() else None
    except Exception as e:
        print(f"[测试] 提取视频音频失败: {e}")
        return None


def build_srt_whisper_siliconflow(video_path, temp_dir, ffmpeg_path, api_key, srt_path):
    """
    新流程：Whisper 时间戳 + 硅基按段识别 → 生成 SRT。
    - video_path: 口播视频路径（如 final.mp4）
    - temp_dir: 临时目录，用于放音频和片段
    - ffmpeg_path: FFmpeg 可执行文件路径
    - api_key: 硅基流动 API Key
    - srt_path: 输出 SRT 文件路径
    成功返回 True，失败返回 False。
    """
    video_path = Path(video_path)
    temp_dir = Path(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)

    # 1. Whisper 获取时间戳
    print("[测试] 步骤1: 使用 Whisper 获取时间戳...")
    segments = get_whisper_timestamps(video_path, temp_dir)
    if not segments:
        print("[测试] 无法获取 Whisper 时间戳，请检查 Whisper 与 FFmpeg")
        return False
    print(f"[测试] 获取到 {len(segments)} 个时间段")

    # 2. 从视频提取整段音频
    print("[测试] 步骤2: 从视频提取音频...")
    full_audio = extract_audio_from_video(video_path, temp_dir)
    if not full_audio or not full_audio.exists():
        # 尝试用同目录的 narration.mp3（若与 final.mp4 对应）
        full_audio = video_path.parent / "narration.mp3"
        if not full_audio.exists():
            print("[测试] 无法获取音频，请确保视频有音轨或同目录有 narration.mp3")
            return False
    print(f"[测试] 使用音频: {full_audio}")

    # 3. 按段截取音频并用硅基识别
    segments_dir = temp_dir / "segments"
    segments_dir.mkdir(exist_ok=True)
    lines = []
    for i, seg in enumerate(segments):
        start = float(seg.get("start", 0))
        end = float(seg.get("end", start + 0.1))
        duration = max(0.01, end - start)
        segment_audio = segments_dir / f"seg_{i:04d}.mp3"
        if not cut_audio_segment(ffmpeg_path, full_audio, start, duration, segment_audio):
            text = (seg.get("text") or "").strip()  # 降级用 Whisper 文字
        else:
            text = transcribe_segment_siliconflow(segment_audio, api_key)
            if not text:
                text = (seg.get("text") or "").strip()
        text = sanitize_subtitle_text(text) or f"[片段{i+1}]"
        start_str = format_srt_time(start)
        end_str = format_srt_time(end)
        lines.append(f"{i+1}")
        lines.append(f"{start_str} --> {end_str}")
        lines.append(text)
        lines.append("")
        if (i + 1) % 5 == 0:
            print(f"[测试] 已识别 {i+1}/{len(segments)} 段...")

    with open(srt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[测试] 已生成 SRT（Whisper 时间戳 + 硅基文字）: {srt_path}")
    return True


def find_ffmpeg():
    """查找FFmpeg可执行文件"""
    # 方法0: 项目 env/ffmpeg（与 subtitle_burner 一致）
    wrapper_dir = Path(__file__).parent
    project_root = wrapper_dir.parent
    env_ffmpeg = project_root / "env" / "ffmpeg" / "ffmpeg.exe"
    if env_ffmpeg.exists():
        print(f"[测试] 找到项目 FFmpeg: {env_ffmpeg}")
        return str(env_ffmpeg)
    # 方法1: 检查PATH（优先使用系统FFmpeg，因为剪映的FFmpeg可能不支持编码）
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        # 检查是否是剪映的FFmpeg（通常不支持编码）
        if "JianyingPro" not in ffmpeg_path:
            print(f"[测试] 找到系统FFmpeg: {ffmpeg_path}")
            return ffmpeg_path
        else:
            print(f"[测试] 找到剪映FFmpeg（可能不支持编码）: {ffmpeg_path}")
            # 继续查找其他FFmpeg
    
    # 方法2: 检查常见位置（包括剪映等软件的FFmpeg）
    common_paths = [
        "C:\\ffmpeg\\bin\\ffmpeg.exe",
        "C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe",
        "C:\\Program Files (x86)\\ffmpeg\\bin\\ffmpeg.exe",
        os.path.expanduser("~\\ffmpeg\\bin\\ffmpeg.exe"),
        # 剪映的FFmpeg
        "D:\\JianyingPro\\10.2.0.13877\\ffmpeg.exe",
    ]
    
    for path in common_paths:
        if os.path.exists(path):
            print(f"[测试] 找到FFmpeg: {path}")
            return path
    
    # 方法3: 搜索D盘剪映
    try:
        import glob
        d_ffmpeg = glob.glob("D:\\JianyingPro\\*\\ffmpeg.exe")
        if d_ffmpeg:
            print(f"[测试] 找到FFmpeg: {d_ffmpeg[0]}")
            return d_ffmpeg[0]
    except:
        pass
    
    # 如果都没找到，尝试使用剪映的FFmpeg（虽然可能不支持编码，但可以尝试）
    if ffmpeg_path and "JianyingPro" in ffmpeg_path:
        print(f"[警告] 只找到剪映FFmpeg，可能不支持编码，将尝试使用")
        return ffmpeg_path
    
    print("[错误] 未找到FFmpeg，请确保FFmpeg已安装")
    return None


def get_video_duration(ffmpeg_path, video_path):
    """获取视频时长（秒）"""
    try:
        cmd = [
            ffmpeg_path,
            "-i", str(video_path),
            "-hide_banner"
        ]
        # FFmpeg的时长信息在stderr中
        result = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        
        # 从stderr中提取时长
        for line in result.stderr.split('\n'):
            if 'Duration:' in line:
                # 格式: Duration: 00:00:15.23, start: 0.000000, bitrate: 1234 kb/s
                duration_part = line.split('Duration:')[1].strip().split(',')[0].strip()
                time_parts = duration_part.split(':')
                hours = int(time_parts[0])
                minutes = int(time_parts[1])
                seconds = float(time_parts[2])
                total_seconds = hours * 3600 + minutes * 60 + seconds
                return total_seconds
    except Exception as e:
        print(f"[警告] 无法获取视频时长: {e}")
    
    return 10.0  # 默认10秒


def create_srt_from_text(text, duration, output_path):
    """
    从文案文本创建简单的SRT字幕文件
    将文案分成3-4段，均匀分布在整个视频时长中
    """
    # 清理文本
    text = text.strip().replace('\n', ' ').replace('\r', '')
    
    # 按句号、问号、感叹号分割
    sentences = []
    current = ""
    for char in text:
        current += char
        if char in ['。', '！', '？', '.', '!', '?']:
            if current.strip():
                sentences.append(current.strip())
                current = ""
    
    # 如果还有剩余文本
    if current.strip():
        sentences.append(current.strip())
    
    # 如果分割后句子太少，按逗号再分割
    if len(sentences) < 3:
        all_text = ' '.join(sentences) if sentences else text
        sentences = [s.strip() for s in all_text.split('，') if s.strip()]
        if not sentences:
            sentences = [text]
    
    # 限制最多4段
    if len(sentences) > 4:
        # 合并成4段
        chunk_size = len(sentences) // 4
        merged = []
        for i in range(0, len(sentences), chunk_size):
            merged.append(' '.join(sentences[i:i+chunk_size]))
        sentences = merged[:4]
    
    # 计算每段的时间
    num_segments = len(sentences)
    segment_duration = duration / num_segments
    
    # 生成SRT内容
    srt_content = []
    for i, sentence in enumerate(sentences):
        start_time = i * segment_duration
        end_time = (i + 1) * segment_duration
        
        # 转换为SRT时间格式 (HH:MM:SS,mmm)
        start_str = format_srt_time(start_time)
        end_str = format_srt_time(end_time)
        
        srt_content.append(f"{i+1}")
        srt_content.append(f"{start_str} --> {end_str}")
        srt_content.append(sentence)
        srt_content.append("")
    
    # 写入文件
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(srt_content))
    
    print(f"[测试] 已创建SRT字幕文件: {output_path}")
    print(f"[测试] 字幕分段数: {len(sentences)}")
    return output_path


def format_srt_time(seconds):
    """将秒数转换为SRT时间格式 (HH:MM:SS,mmm)"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def srt_time_to_seconds(srt_time):
    """将SRT时间格式转换为秒数"""
    # 格式: HH:MM:SS,mmm 或 HH:MM:SS.mmm
    srt_time = srt_time.replace(',', '.')
    parts = srt_time.split(':')
    hours = int(parts[0])
    minutes = int(parts[1])
    seconds = float(parts[2])
    return hours * 3600 + minutes * 60 + seconds


def srt_to_ass(srt_path, ass_path, video_width=1080, video_height=1920):
    """
    将SRT字幕转换为ASS格式，应用"抖音热门 - 金色文字"样式
    字幕位置：底部居中
    样式：金色文字(0xFFD700)，56号字体，黑色边框(5px)
    """
    # 读取SRT文件
    with open(srt_path, 'r', encoding='utf-8') as f:
        srt_content = f.read()
    
    # 解析SRT内容
    segments = []
    lines = srt_content.strip().split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.isdigit():
            # 序号行
            i += 1
            if i < len(lines):
                # 时间行
                time_line = lines[i].strip()
                if '-->' in time_line:
                    start_time, end_time = time_line.split('-->')
                    start_time = start_time.strip()
                    end_time = end_time.strip()
                    i += 1
                    # 文本行
                    text_lines = []
                    while i < len(lines) and lines[i].strip():
                        text_lines.append(lines[i].strip())
                        i += 1
                    if text_lines:
                        text = ' '.join(text_lines)
                        segments.append({
                            'start': start_time,
                            'end': end_time,
                            'text': text
                        })
        i += 1
    
    # 生成ASS文件
    # ASS格式说明：
    # - PrimaryColour: 主颜色 (BGR格式，0xFFD700 = 215,215,255)
    # - OutlineColour: 边框颜色 (BGR格式，黑色 = 0,0,0)
    # - Outline: 边框宽度 (5)
    # - FontSize: 字体大小 (56)
    # - Alignment: 对齐方式 (2=底部居中, 5=底部居中但更精确)
    
    ass_content = """[Script Info]
Title: 抖音热门字幕
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,56,&H00D7FF&,&H00D7FF&,&H000000&,&H000000&,0,0,0,0,100,100,0,0,1,5,0,2,10,10,30,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    # 转换时间格式：SRT (HH:MM:SS,mmm) -> ASS (H:MM:SS.mm)
    def srt_to_ass_time(srt_time):
        # SRT: 00:00:15,230
        # ASS: 0:00:15.23
        parts = srt_time.replace(',', ':').split(':')
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds_parts = parts[2].split(',') if ',' in srt_time else parts[2].split('.')
        seconds = int(seconds_parts[0])
        millis = int(seconds_parts[1]) if len(seconds_parts) > 1 else 0
        centiseconds = millis // 10  # 转换为百分秒
        return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"
    
    # 添加字幕事件
    for segment in segments:
        start_ass = srt_to_ass_time(segment['start'])
        end_ass = srt_to_ass_time(segment['end'])
        text = segment['text'].replace('\\', '\\\\').replace('{', '\\{').replace('}', '\\}')
        ass_content += f"Dialogue: 0,{start_ass},{end_ass},Default,,0,0,0,,{text}\n"
    
    # 写入ASS文件
    with open(ass_path, 'w', encoding='utf-8-sig') as f:  # utf-8-sig 包含BOM，某些播放器需要
        f.write(ass_content)
    
    print(f"[测试] 已创建ASS字幕文件: {ass_path}")
    print(f"[测试] 字幕段数: {len(segments)}")
    return ass_path


def burn_subtitle_moviepy(video_path, srt_path, output_path):
    """
    使用MoviePy烧录字幕（推荐方法）
    """
    if not MOVIEPY_AVAILABLE:
        return False
    
    print(f"[测试] 使用MoviePy烧录字幕...")
    print(f"[测试] 输入视频: {video_path}")
    print(f"[测试] 字幕文件: {srt_path}")
    print(f"[测试] 输出视频: {output_path}")
    
    try:
        # 加载视频
        video = VideoFileClip(str(video_path))
        
        def make_textclip_pil(txt, duration, video_width, video_height):
            """使用PIL创建文字图片，然后转换为视频片段"""
            # 字体大小：28号（原来56号的一半）
            font_size = 28
            max_width = int(video_width * 0.9)  # 字幕宽度为视频的90%
            
            # 尝试加载字体
            try:
                # Windows常见字体路径
                font_paths = [
                    "C:/Windows/Fonts/simhei.ttf",  # 黑体
                    "C:/Windows/Fonts/msyh.ttc",     # 微软雅黑
                    "C:/Windows/Fonts/simsun.ttc",   # 宋体
                ]
                font = None
                for fp in font_paths:
                    if os.path.exists(fp):
                        font = ImageFont.truetype(fp, font_size)
                        break
                if font is None:
                    font = ImageFont.load_default()
            except:
                font = ImageFont.load_default()
            
            # 一句话一行显示（不自动换行）
            # 如果文字太长，截断并加省略号
            lines = [txt]  # 只显示一行
            
            # 检查文字是否超出宽度，如果超出则截断
            bbox = font.getbbox(txt) if hasattr(font, 'getbbox') else font.getsize(txt)
            text_width = bbox[2] - bbox[0] if isinstance(bbox, tuple) and len(bbox) == 4 else bbox[0]
            
            if text_width > max_width:
                # 文字太长，需要截断
                truncated = txt
                while True:
                    bbox = font.getbbox(truncated + "...") if hasattr(font, 'getbbox') else font.getsize(truncated + "...")
                    width = bbox[2] - bbox[0] if isinstance(bbox, tuple) and len(bbox) == 4 else bbox[0]
                    if width <= max_width or len(truncated) <= 1:
                        break
                    truncated = truncated[:-1]
                lines = [truncated + "..."]
            
            # 计算图片高度（单行）
            line_height = int(font_size * 1.5)
            img_height = line_height + 20  # 上下留白
            img = Image.new('RGBA', (max_width, img_height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            
            # 绘制文字（带描边效果）- 只绘制一行，居中
            y_offset = img_height // 2
            line = lines[0]  # 只显示第一行
            
            # 先绘制黑色描边（多次偏移模拟描边，描边宽度2）
            for dx in [-2, -1, 0, 1, 2]:
                for dy in [-2, -1, 0, 1, 2]:
                    if dx != 0 or dy != 0:
                        draw.text((max_width//2 + dx, y_offset + dy), line, 
                                 font=font, fill=(0, 0, 0, 255), anchor='mm')
            # 再绘制金色文字
            draw.text((max_width//2, y_offset), line, 
                     font=font, fill=(255, 215, 0, 255), anchor='mm')  # #FFD700 = 255,215,0
            
            # 转换为numpy数组
            img_array = np.array(img)
            
            # 创建视频片段
            clip = ImageClip(img_array).set_duration(duration)
            # 位置：底部居中（距离底部30像素）
            clip = clip.set_position(('center', video_height - img_height - 30))
            
            return clip
        
        # 解析SRT文件
        segments = []
        with open(srt_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        lines = content.strip().split('\n')
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.isdigit():
                i += 1
                if i < len(lines) and '-->' in lines[i]:
                    time_line = lines[i].strip()
                    start_str, end_str = time_line.split('-->')
                    start_sec = srt_time_to_seconds(start_str.strip())
                    end_sec = srt_time_to_seconds(end_str.strip())
                    i += 1
                    text_lines = []
                    while i < len(lines) and lines[i].strip():
                        text_lines.append(lines[i].strip())
                        i += 1
                    if text_lines:
                        text = ' '.join(text_lines)
                        segments.append((start_sec, end_sec, text))
            i += 1
        
        print(f"[测试] 解析到 {len(segments)} 段字幕")
        
        # 创建字幕片段列表（使用PIL生成文字图片）
        subtitle_clips = []
        for start, end, text in segments:
            duration = end - start
            # 使用PIL创建文字图片
            txt_clip = make_textclip_pil(text, duration, video.w, video.h).set_start(start)
            subtitle_clips.append(txt_clip)
        
        # 合成视频和字幕
        final_video = CompositeVideoClip([video] + subtitle_clips)
        
        # 输出视频
        print(f"[测试] 开始渲染视频（这可能需要一些时间）...")
        final_video.write_videofile(
            str(output_path),
            codec='libx264',
            audio_codec='aac',
            fps=video.fps,
            preset='medium',
            bitrate='8000k'
        )
        
        # 清理资源
        video.close()
        final_video.close()
        for clip in subtitle_clips:
            clip.close()
        
        print(f"[测试] 字幕烧录成功！")
        return True
        
    except Exception as e:
        print(f"[错误] MoviePy处理失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def burn_subtitle(ffmpeg_path, video_path, srt_path, output_path, duration):
    """
    使用FFmpeg的drawtext滤镜烧录动态字幕到视频中
    由于剪映FFmpeg可能不支持subtitles滤镜，改用drawtext分段显示
    """
    print(f"[测试] 开始烧录字幕...")
    print(f"[测试] 输入视频: {video_path}")
    print(f"[测试] 字幕文件: {srt_path}")
    print(f"[测试] 输出视频: {output_path}")
    
    # 读取SRT文件，解析字幕段
    segments = []
    with open(srt_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    lines = content.strip().split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.isdigit():
            i += 1
            if i < len(lines) and '-->' in lines[i]:
                time_line = lines[i].strip()
                start_str, end_str = time_line.split('-->')
                start_str = start_str.strip()
                end_str = end_str.strip()
                i += 1
                text_lines = []
                while i < len(lines) and lines[i].strip():
                    text_lines.append(lines[i].strip())
                    i += 1
                if text_lines:
                    text = ' '.join(text_lines)
                    # 转换时间格式
                    start_sec = srt_time_to_seconds(start_str)
                    end_sec = srt_time_to_seconds(end_str)
                    segments.append((start_sec, end_sec, text))
        i += 1
    
    print(f"[测试] 解析到 {len(segments)} 段字幕")
    
    # 构建drawtext滤镜链（每段字幕一个drawtext）
    # 由于drawtext不支持多段，我们需要使用复杂滤镜
    # 或者使用overlay+drawtext的组合
    
    # 方法：使用多个drawtext，通过enable参数控制显示时间
    drawtext_filters = []
    for i, (start, end, text) in enumerate(segments):
        # 转义文本中的特殊字符
        text_escaped = text.replace('\\', '\\\\').replace(':', '\\:').replace("'", "\\'")
        # 底部居中：x=(w-text_w)/2, y=h-th-50 (距离底部50像素)
        drawtext = f"drawtext=text='{text_escaped}':fontcolor=0xFFD700:fontsize=56:x=(w-text_w)/2:y=h-th-50:borderw=5:bordercolor=black:enable='between(t,{start},{end})'"
        drawtext_filters.append(drawtext)
    
    # 组合所有drawtext滤镜
    if len(drawtext_filters) == 1:
        filter_complex = drawtext_filters[0]
    else:
        # 多个drawtext需要链式连接
        filter_complex = ','.join(drawtext_filters)
    
    # 检查是否是剪映FFmpeg
    is_jianying = "JianyingPro" in str(ffmpeg_path)
    
    if is_jianying:
        # 剪映FFmpeg，尝试硬件编码
        cmd = [
            ffmpeg_path,
            "-i", str(video_path),
            "-vf", filter_complex,
            "-c:v", "h264_qsv",
            "-b:v", "8000k",
            "-c:a", "copy",
            "-y",
            str(output_path)
        ]
    else:
        # 系统FFmpeg
        cmd = [
            ffmpeg_path,
            "-i", str(video_path),
            "-vf", filter_complex,
            "-c:v", "libx264",
            "-preset", "medium",
            "-b:v", "8000k",
            "-c:a", "copy",
            "-y",
            str(output_path)
        ]
    
    print(f"[测试] 执行命令: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore'
        )
        
        if result.returncode == 0:
            print(f"[测试] ✅ 字幕烧录成功！")
            print(f"[测试] 输出文件: {output_path}")
            if os.path.exists(output_path):
                file_size = os.path.getsize(output_path) / (1024 * 1024)
                print(f"[测试] 文件大小: {file_size:.2f} MB")
            return True
        else:
            print(f"[错误] FFmpeg执行失败:")
            print(f"[错误] 返回码: {result.returncode}")
            print(f"[错误] 错误输出: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"[错误] 执行FFmpeg时出错: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """
    主函数：对「最新一条口播视频」生成并烧录字幕。
    - 若已配置硅基 API Key：走「Whisper 时间戳 + 硅基按段识别」新流程，生成 SRT 后烧录。
    - 否则：用任务目录下 script.txt 文案按句均匀分段生成 SRT，或提示输入文案/从音频生成（可能乱码）。
    输出：temp_subtitle_test/video_with_subtitle.mp4（及同目录 subtitle.srt / subtitle.ass）。
    """
    print("=" * 60)
    print("视频字幕测试脚本 - 抖音热门金色文字样式")
    print("=" * 60)
    
    # 1. 查找FFmpeg
    ffmpeg_path = find_ffmpeg()
    if not ffmpeg_path:
        print("[错误] 请先安装FFmpeg")
        return
    
    # 2. 查找视频文件
    wrapper_dir = Path(__file__).parent
    output_dir = wrapper_dir / "output"
    
    # 查找最新的视频文件
    video_files = list(output_dir.rglob("final.mp4"))
    if not video_files:
        print("[错误] 未找到视频文件，请先生成一个视频")
        print(f"[提示] 查找目录: {output_dir}")
        return
    
    # 选择最新的视频
    latest_video = max(video_files, key=os.path.getmtime)
    print(f"[测试] 找到视频文件: {latest_video}")
    
    # 3. 获取视频时长
    duration = get_video_duration(ffmpeg_path, latest_video)
    print(f"[测试] 视频时长: {duration:.2f} 秒")
    
    # 4. 查找对应的原始文案（生成视频时使用的文案）
    video_dir = latest_video.parent
    audio_file = video_dir / "narration.mp3"
    
    # 查找保存的文案文件
    script_file = video_dir / "script.txt"
    original_text = None
    
    # 5. 创建临时目录与 SRT 路径
    temp_dir = wrapper_dir / "temp_subtitle_test"
    temp_dir.mkdir(exist_ok=True)
    srt_path = temp_dir / "subtitle.srt"

    # 【新流程】有硅基 API Key 时：Whisper 时间戳 + 硅基按段识别
    api_key = load_siliconflow_api_key()
    if api_key:
        print("[测试] 检测到硅基 API Key，使用新流程：Whisper 时间戳 + 硅基按段识别")
        if build_srt_whisper_siliconflow(latest_video, temp_dir, ffmpeg_path, api_key, srt_path):
            # 新流程成功，直接跳到烧录
            pass
        else:
            print("[测试] 新流程失败，回退到原有文案/均匀分段方式")
            api_key = ""  # 让下面走原有逻辑
    else:
        print("[测试] 未配置硅基 API Key（config.yaml 中 siliconflow.api_key 或环境变量 API_KEY），使用原有文案/均匀分段方式")

    # 未走新流程或新流程失败时：用原有文案或从音频生成 SRT（仅当尚未生成有效 SRT 时）
    need_srt = not srt_path.exists() or (srt_path.stat().st_size == 0)
    if need_srt:
        # 优先使用保存的原始文案
        if script_file.exists():
            print(f"[测试] 找到保存的原始文案文件: {script_file}")
            with open(script_file, 'r', encoding='utf-8') as f:
                original_text = f.read().strip()
            print(f"[测试] 使用原始文案: {original_text[:50]}...")
            create_srt_from_text(original_text, duration, srt_path)
        else:
            # 如果没有保存的文案文件，提示用户提供
            print(f"[测试] 未找到保存的文案文件（这个视频是之前生成的）")
            print(f"[提示] 请从浏览器控制台获取原始文案：")
            print(f"       1. 打开浏览器开发者工具（F12）")
            print(f"       2. 在Console中输入：localStorage.getItem('current_script') 或 localStorage.getItem('latest_script')")
            print(f"       3. 复制文案内容")
            print(f"\n[输入] 请粘贴原始文案（直接回车将使用从音频提取的字幕，可能有乱码）:")
            
            try:
                user_input = input().strip()
                if user_input:
                    original_text = user_input
                    print(f"[测试] 使用您提供的文案: {original_text[:50]}...")
                    create_srt_from_text(original_text, duration, srt_path)
                else:
                    if audio_file.exists():
                        print(f"[测试] 未提供文案，尝试从音频生成SRT（可能有乱码）...")
                        try:
                            from ai_pipeline.subtitle_generator import generate_subtitle
                            generated_srt = generate_subtitle(str(audio_file), temp_dir)
                            if generated_srt and Path(generated_srt).exists():
                                shutil.copy2(generated_srt, srt_path)
                                print(f"[测试] 已从音频生成SRT字幕: {srt_path}")
                                print(f"[警告] 从音频提取的字幕可能有乱码，建议使用原始文案")
                            else:
                                print(f"[错误] 无法生成字幕")
                                return
                        except Exception as e:
                            print(f"[错误] 从音频生成字幕失败: {e}")
                            return
                    else:
                        print(f"[错误] 未找到音频文件，无法生成字幕")
                        return
            except EOFError:
                if audio_file.exists():
                    print(f"[测试] 非交互式环境，尝试从音频生成SRT...")
                    try:
                        from ai_pipeline.subtitle_generator import generate_subtitle
                        generated_srt = generate_subtitle(str(audio_file), temp_dir)
                        if generated_srt and Path(generated_srt).exists():
                            shutil.copy2(generated_srt, srt_path)
                            print(f"[测试] 已从音频生成SRT字幕: {srt_path}")
                            print(f"[警告] 从音频提取的字幕可能有乱码")
                        else:
                            print(f"[错误] 无法生成字幕")
                            return
                    except Exception as e:
                        print(f"[错误] 从音频生成字幕失败: {e}")
                        return
                else:
                    print(f"[错误] 未找到音频文件，无法生成字幕")
                    return

    if not srt_path.exists() or srt_path.stat().st_size == 0:
        print("[错误] 未能生成 SRT 字幕文件")
        return

    # 6. 转换为ASS格式
    ass_path = temp_dir / "subtitle.ass"
    srt_to_ass(srt_path, ass_path)
    
    # 7. 烧录字幕到视频
    output_video = temp_dir / "video_with_subtitle.mp4"
    
    # 优先使用MoviePy（更可靠）
    if MOVIEPY_AVAILABLE:
        print(f"[测试] 使用MoviePy处理字幕...")
        success = burn_subtitle_moviepy(latest_video, srt_path, output_video)
    else:
        print(f"[测试] MoviePy不可用，尝试使用FFmpeg...")
        success = burn_subtitle(ffmpeg_path, latest_video, srt_path, output_video, duration)
    
    if success:
        print("\n" + "=" * 60)
        print("测试完成！")
        print(f"带字幕的视频已保存到: {output_video}")
        print(f"临时文件目录: {temp_dir}")
        print("=" * 60)
        print("\n[提示] 你可以用视频播放器打开查看效果")
        print(f"[提示] 文件路径: {output_video.absolute()}")
    else:
        print("\n[错误] 字幕烧录失败，请检查错误信息")


if __name__ == "__main__":
    main()

