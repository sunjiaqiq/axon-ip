#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
使用 douyin-mcp-server 下载视频，使用 Whisper 提取文案
"""
import sys
import os
from pathlib import Path

# 设置UTF-8编码
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 添加项目路径
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

# 添加 Whisper 路径
whisper_path = current_dir.parent / "whisper-main"
if whisper_path.exists():
    sys.path.insert(0, str(whisper_path))

# 添加 pixelle_wrapper 路径
pixelle_path = current_dir.parent / "pixelle_wrapper"
if pixelle_path.exists():
    sys.path.insert(0, str(pixelle_path))

# 设置 FFmpeg 路径
ffmpeg_dir = current_dir.parent / "env" / "ffmpeg"
if ffmpeg_dir.exists():
    ffmpeg_path = ffmpeg_dir / "ffmpeg.exe"
    if ffmpeg_path.exists():
        os.environ["PATH"] = str(ffmpeg_dir) + os.pathsep + os.environ.get("PATH", "")
        print(f"[INFO] 已设置 FFmpeg 路径: {ffmpeg_dir}")

# 导入 douyin-mcp-server 的下载器
import importlib.util
douyin_downloader_path = current_dir / "douyin-video" / "scripts" / "douyin_downloader.py"
spec = importlib.util.spec_from_file_location("douyin_downloader", douyin_downloader_path)
douyin_downloader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(douyin_downloader)
DouyinProcessor = douyin_downloader.DouyinProcessor

# 导入我们的音频提取和Whisper模块
from ai_pipeline.audio_extractor import extract_audio_from_video
from ai_pipeline.subtitle_generator import generate_subtitle

def extract_text_with_whisper(share_link: str, output_dir: str = "./output"):
    """
    使用 douyin-mcp-server 下载视频，使用 Whisper 提取文案
    """
    print("=" * 70)
    print("使用 douyin-mcp-server + Whisper 提取视频文案")
    print("=" * 70)
    print()
    
    # 1. 解析链接并下载视频
    print("步骤1: 解析链接并下载视频...")
    processor = DouyinProcessor("")  # 不需要API密钥来下载视频
    video_info = processor.parse_share_url(share_link)
    print(f"[OK] 视频信息: {video_info['title']}")
    print(f"[OK] 视频ID: {video_info['video_id']}")
    
    # 下载视频
    video_path = processor.download_video(video_info, show_progress=True)
    print(f"[OK] 视频下载完成: {video_path}")
    print()
    
    # 2. 设置输出目录
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # 3. 提取音频（使用我们自己的模块）
    print("步骤2: 提取音频...")
    audio_path = extract_audio_from_video(str(video_path), output_dir=output_path)
    if not audio_path:
        raise Exception("音频提取失败")
    print(f"[OK] 音频提取完成: {audio_path}")
    print()
    
    # 4. 使用 Whisper 提取文案
    print("步骤3: 使用 Whisper 提取文案...")
    
    # 使用我们的 Whisper 模块
    srt_path = generate_subtitle(str(audio_path), output_dir=output_path)
    if not srt_path:
        raise Exception("Whisper 提取文案失败")
    
    # 读取文案文本
    text_path = output_path / f"{audio_path.stem}.txt"
    if text_path.exists():
        with open(text_path, 'r', encoding='utf-8') as f:
            text_content = f.read()
    else:
        # 如果没有txt文件，从SRT文件提取
        with open(srt_path, 'r', encoding='utf-8') as f:
            srt_content = f.read()
        # 简单提取文本（去掉时间戳）
        lines = srt_content.split('\n')
        text_lines = [line for line in lines if line and line.strip() and not line.strip().isdigit() and '-->' not in line]
        text_content = '\n'.join(text_lines)
    
    print(f"[OK] 文案提取完成")
    print()
    
    # 4. 保存结果
    video_folder = output_path / video_info['video_id']
    video_folder.mkdir(parents=True, exist_ok=True)
    
    transcript_path = video_folder / "transcript.md"
    with open(transcript_path, 'w', encoding='utf-8') as f:
        f.write(f"# {video_info['title']}\n\n")
        f.write(f"| 属性 | 值 |\n")
        f.write(f"|------|----|\n")
        f.write(f"| 视频ID | `{video_info['video_id']}` |\n")
        f.write(f"| 下载链接 | [点击下载]({video_info['url']}) |\n\n")
        f.write(f"---\n\n")
        f.write(f"## 文案内容\n\n")
        f.write(text_content)
    
    print("=" * 70)
    print("提取完成!")
    print("=" * 70)
    print(f"视频ID: {video_info['video_id']}")
    print(f"标题: {video_info['title']}")
    print(f"保存位置: {video_folder}")
    print()
    print("文案内容:")
    print("-" * 70)
    print(text_content)
    print("-" * 70)
    
    # 清理临时文件
    processor.cleanup_files(video_path, audio_path)
    
    return {
        "video_info": video_info,
        "text": text_content,
        "output_path": str(video_folder)
    }


if __name__ == "__main__":
    # 测试链接
    test_link = "3.35 06/20 I@V.LW eOX:/ 入住5年才敢说：客厅阳台门千万别拆！# 装修踩坑 # 装修避坑 # 阳台装修 # 家装经验 # 装修干货  https://v.douyin.com/NeDMxbDh5iU/ 复制此链接，打开Dou音搜索，直接观看视频！"
    
    try:
        result = extract_text_with_whisper(test_link, output_dir="./output")
        print("\n[OK] 成功!")
    except Exception as e:
        print(f"\n[ERROR] 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

