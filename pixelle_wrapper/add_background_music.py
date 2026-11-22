#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
添加背景音乐工具脚本
功能：给视频添加背景音乐，支持自定义音量、淡入淡出等参数
"""
import os
import sys
import argparse
from pathlib import Path

# 添加路径
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

from ai_pipeline.video_editor import add_background_music


def find_music_file(folder_path: Path, music_name: str = "野马.mp3") -> Path:
    """
    查找背景音乐文件
    
    Args:
        folder_path: 文件夹路径
        music_name: 音乐文件名，默认"野马.mp3"
        
    Returns:
        音乐文件路径
    """
    # 优先查找指定文件
    music_file = folder_path / music_name
    if music_file.exists():
        return music_file
    
    # 如果找不到，查找所有MP3文件
    mp3_files = list(folder_path.glob("*.mp3"))
    if mp3_files:
        return mp3_files[0]
    
    raise FileNotFoundError(f"在 {folder_path} 中未找到MP3文件")


def find_video_file(output_dir: Path, video_name: str = None) -> Path:
    """
    查找视频文件
    
    Args:
        output_dir: 输出目录
        video_name: 视频文件名，如果为None则查找最新的zoom视频
        
    Returns:
        视频文件路径
    """
    if video_name:
        video_file = output_dir / video_name
        if video_file.exists():
            return video_file
    
    # 查找所有包含"zoom"的MP4文件
    zoom_videos = list(output_dir.glob("*zoom*.mp4"))
    if zoom_videos:
        # 返回最新的文件（按修改时间）
        return max(zoom_videos, key=lambda p: p.stat().st_mtime)
    
    raise FileNotFoundError(f"在 {output_dir} 中未找到视频文件")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="给视频添加背景音乐",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 使用默认参数（桌面"成品"文件夹的"野马.mp3"，8%音量）
  python add_background_music.py
  
  # 指定音量
  python add_background_music.py --volume 0.15
  
  # 指定视频和音乐文件
  python add_background_music.py --video video.mp4 --music music.mp3 --volume 0.10
  
  # 添加淡入淡出效果
  python add_background_music.py --volume 0.08 --fade-in 2.0 --fade-out 2.0
        """
    )
    
    # 参数定义
    parser.add_argument(
        '--video',
        type=str,
        help='视频文件路径（如果不指定，自动查找最新的zoom视频）'
    )
    
    parser.add_argument(
        '--music',
        type=str,
        help='背景音乐文件路径（如果不指定，从桌面"成品"文件夹查找）'
    )
    
    parser.add_argument(
        '--music-folder',
        type=str,
        default=None,
        help='背景音乐文件夹路径（默认：桌面"成品"文件夹）'
    )
    
    parser.add_argument(
        '--music-name',
        type=str,
        default='野马.mp3',
        help='背景音乐文件名（默认：野马.mp3）'
    )
    
    parser.add_argument(
        '--volume',
        type=float,
        default=0.08,
        help='背景音乐音量（0.0-1.0），默认0.08（8%%）'
    )
    
    parser.add_argument(
        '--original-volume',
        type=float,
        default=1.0,
        help='原视频音频音量（0.0-1.0），默认1.0（100%%）'
    )
    
    parser.add_argument(
        '--fade-in',
        type=float,
        default=0.0,
        help='背景音乐淡入时长（秒），默认0.0（无淡入）'
    )
    
    parser.add_argument(
        '--fade-out',
        type=float,
        default=0.0,
        help='背景音乐淡出时长（秒），默认0.0（无淡出）'
    )
    
    parser.add_argument(
        '--no-loop',
        action='store_true',
        help='不循环播放背景音乐（如果音乐比视频短）'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        default=None,
        help='输出文件路径（如果不指定，自动生成）'
    )
    
    parser.add_argument(
        '--output-dir',
        type=str,
        default=None,
        help='输出目录（默认：和视频文件同目录）'
    )
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("添加背景音乐工具")
    print("=" * 70)
    print()
    
    try:
        # 1. 查找背景音乐文件
        if args.music:
            # 直接指定音乐文件
            music_path = Path(args.music)
            if not music_path.exists():
                raise FileNotFoundError(f"音乐文件不存在: {music_path}")
        else:
            # 从文件夹查找
            if args.music_folder:
                music_folder = Path(args.music_folder)
            else:
                # 默认：桌面"成品"文件夹
                desktop = Path.home() / "Desktop"
                music_folder = desktop / "成品"
            
            if not music_folder.exists():
                raise FileNotFoundError(f"音乐文件夹不存在: {music_folder}")
            
            print(f"[INFO] 查找背景音乐文件夹: {music_folder}")
            music_path = find_music_file(music_folder, args.music_name)
        
        print(f"[OK] 找到背景音乐: {music_path.name}")
        print(f"     完整路径: {music_path.absolute()}")
        print()
        
        # 2. 查找视频文件
        if args.video:
            # 直接指定视频文件
            video_path = Path(args.video)
            if not video_path.exists():
                raise FileNotFoundError(f"视频文件不存在: {video_path}")
        else:
            # 自动查找最新的zoom视频
            if args.output_dir:
                output_dir = Path(args.output_dir)
            else:
                # 默认：output目录下的最新文件夹
                output_base = current_dir / "output"
                output_dirs = [d for d in output_base.iterdir() if d.is_dir()]
                if not output_dirs:
                    raise FileNotFoundError(f"未找到输出目录: {output_base}")
                output_dir = max(output_dirs, key=lambda p: p.stat().st_mtime)
            
            print(f"[INFO] 查找视频文件目录: {output_dir}")
            video_path = find_video_file(output_dir)
        
        print(f"[OK] 找到视频文件: {video_path.name}")
        print(f"     完整路径: {video_path.absolute()}")
        print()
        
        # 3. 设置输出路径
        if args.output:
            output_path = Path(args.output)
        else:
            # 自动生成输出文件名
            volume_percent = int(args.volume * 100)
            output_name = f"{video_path.stem}_music_{volume_percent}.mp4"
            
            if args.output_dir:
                output_path = Path(args.output_dir) / output_name
            else:
                output_path = video_path.parent / output_name
        
        # 4. 显示参数信息
        print("[步骤] 开始添加背景音乐...")
        print(f"   - 视频文件: {video_path.name}")
        print(f"   - 背景音乐: {music_path.name}")
        print(f"   - 原音频音量: {args.original_volume * 100:.0f}%")
        print(f"   - 背景音乐音量: {args.volume * 100:.0f}%")
        print(f"   - 淡入时长: {args.fade_in:.1f}秒" if args.fade_in > 0 else "   - 淡入: 无")
        print(f"   - 淡出时长: {args.fade_out:.1f}秒" if args.fade_out > 0 else "   - 淡出: 无")
        print(f"   - 循环播放: {'是' if not args.no_loop else '否'}")
        print(f"   - 输出文件: {output_path.name}")
        print()
        
        # 5. 调用核心函数
        result = add_background_music(
            video_path=str(video_path.absolute()),
            music_path=str(music_path.absolute()),
            output_path=str(output_path),
            music_volume=args.volume,
            original_volume=args.original_volume,
            fade_in=args.fade_in,
            fade_out=args.fade_out,
            loop=not args.no_loop
        )
        
        # 6. 显示结果
        if result and Path(result).exists():
            file_size = Path(result).stat().st_size / (1024 * 1024)
            print()
            print("=" * 70)
            print("[SUCCESS] 视频生成成功！")
            print("=" * 70)
            print(f"输出文件: {Path(result).name}")
            print(f"文件大小: {file_size:.2f} MB")
            print(f"完整路径: {Path(result).absolute()}")
            print()
            print("[INFO] 你可以打开这个文件查看效果！")
            return 0
        else:
            print("[ERROR] 视频生成失败！")
            return 1
            
    except FileNotFoundError as e:
        print(f"[ERROR] {e}")
        return 1
    except Exception as e:
        print(f"[ERROR] 处理过程中出错: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())



