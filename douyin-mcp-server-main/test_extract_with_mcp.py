#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
使用 douyin-mcp-server 提取视频文案（使用硅基流动 API）
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
extract_text = douyin_downloader.extract_text

def main():
    """使用 douyin-mcp-server 提取文案"""
    print("=" * 70)
    print("使用 douyin-mcp-server 提取视频文案")
    print("=" * 70)
    print()
    
    # 测试链接
    test_link = "3.35 06/20 I@V.LW eOX:/ 入住5年才敢说：客厅阳台门千万别拆！# 装修踩坑 # 装修避坑 # 阳台装修 # 家装经验 # 装修干货  https://v.douyin.com/NeDMxbDh5iU/ 复制此链接，打开Dou音搜索，直接观看视频！"
    
    # 使用硅基流动 API Key（从环境变量获取，或从配置文件读取）
    api_key = os.getenv('API_KEY', '')
    if not api_key:
        # 尝试从配置文件读取
        config_file = current_dir / "config.env"
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith('API_KEY='):
                        api_key = line.split('=', 1)[1].strip()
                        break
    
    if not api_key:
        print("[WARNING] 未设置 API_KEY 环境变量")
        print("[INFO] douyin-mcp-server 使用硅基流动 SenseVoice API")
        print("[INFO] 请设置环境变量: set API_KEY=your_siliconflow_api_key")
        print()
        print("尝试使用默认配置...")
    
    try:
        # 使用 douyin-mcp-server 的 extract_text 函数
        print("开始提取文案...")
        print()
        
        result = extract_text(
            test_link,
            api_key=api_key,
            output_dir="./output",
            save_video=False,
            show_progress=True
        )
        
        print()
        print("=" * 70)
        print("提取完成!")
        print("=" * 70)
        print(f"视频ID: {result['video_info']['video_id']}")
        print(f"标题: {result['video_info']['title']}")
        if result['output_path']:
            print(f"保存位置: {result['output_path']}")
        print()
        print("文案内容:")
        print("-" * 70)
        print(result['text'])
        print("-" * 70)
        
        # 读取保存的文件
        if result['output_path']:
            transcript_path = Path(result['output_path']) / "transcript.md"
            if transcript_path.exists():
                print()
                print(f"文案已保存到: {transcript_path}")
                with open(transcript_path, 'r', encoding='utf-8') as f:
                    print()
                    print("=" * 70)
                    print("完整文案文件内容:")
                    print("=" * 70)
                    print(f.read())
        
        return result
        
    except Exception as e:
        print(f"\n[ERROR] 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

