#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成15%音量的背景音乐视频
"""
import os
import sys
from pathlib import Path

# 添加路径
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

from ai_pipeline.video_editor import add_background_music

def main():
    print("=" * 70)
    print("生成15%音量的背景音乐视频")
    print("=" * 70)
    print()
    
    # 查找桌面上的"成品"文件夹和"野马.mp3"
    desktop = Path.home() / "Desktop"
    chengpin_folder = desktop / "成品"
    
    if not chengpin_folder.exists():
        print(f"[ERROR] 未找到'成品'文件夹: {chengpin_folder}")
        return
    
    print(f"[OK] 找到'成品'文件夹: {chengpin_folder}")
    
    # 查找野马.mp3
    yema_mp3 = chengpin_folder / "野马.mp3"
    
    if not yema_mp3.exists():
        # 尝试查找所有MP3文件
        mp3_files = list(chengpin_folder.glob("*.mp3"))
        if mp3_files:
            yema_mp3 = mp3_files[0]
            print(f"[INFO] 未找到'野马.mp3'，使用第一个MP3文件: {yema_mp3.name}")
        else:
            print(f"[ERROR] '成品'文件夹中没有找到MP3文件！")
            return
    
    print(f"[OK] 找到背景音乐: {yema_mp3.name}")
    print(f"     完整路径: {yema_mp3.absolute()}")
    print()
    
    # 查找之前生成的zoom视频
    output_dir = current_dir / "output" / "20260316_095606_5cb49fcc"
    zoom_video = output_dir / "final_pip_zoom.mp4"
    
    if not zoom_video.exists():
        # 尝试查找其他可能的zoom视频
        zoom_videos = list(output_dir.glob("*zoom*.mp4"))
        if zoom_videos:
            zoom_video = zoom_videos[0]
        else:
            print(f"[ERROR] 未找到zoom视频: {zoom_video}")
            return
    
    print(f"[OK] 找到zoom视频: {zoom_video.name}")
    print(f"     完整路径: {zoom_video.absolute()}")
    print()
    
    # 生成15%音量的视频
    output_name = f"{zoom_video.stem}_music_15.mp4"
    output_path = zoom_video.parent / output_name
    
    print("[步骤] 开始生成15%音量的视频...")
    print(f"   - 视频: {zoom_video.name}")
    print(f"   - 背景音乐: {yema_mp3.name}")
    print(f"   - 原音频音量: 100%")
    print(f"   - 背景音乐音量: 15%")
    print(f"   - 循环播放: 是")
    print(f"   - 输出: {output_path.name}")
    print()
    
    try:
        result = add_background_music(
            video_path=str(zoom_video.absolute()),
            music_path=str(yema_mp3.absolute()),
            output_path=str(output_path),
            music_volume=0.15,  # 背景音乐音量15%
            original_volume=1.0,  # 原音频音量100%
            fade_in=0.0,
            fade_out=0.0,
            loop=True  # 循环播放
        )
        
        if result and Path(result).exists():
            file_size = Path(result).stat().st_size / (1024*1024)
            print()
            print("=" * 70)
            print("[SUCCESS] 视频生成成功！")
            print("=" * 70)
            print(f"输出文件: {Path(result).name}")
            print(f"文件大小: {file_size:.2f} MB")
            print(f"完整路径: {Path(result).absolute()}")
            print()
            print("[INFO] 你可以打开这个文件查看15%音量的效果！")
        else:
            print("[ERROR] 视频生成失败！")
            
    except Exception as e:
        print(f"[ERROR] 生成失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()



