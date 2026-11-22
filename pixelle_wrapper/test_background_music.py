#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试背景音乐功能 - 生成三个不同音量的视频
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
    print("背景音乐功能测试 - 生成三个不同音量的视频")
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
    
    # 生成三个不同音量的视频
    volumes = [
        (0.2, "20%"),  # 原声20%
        (0.3, "30%"),  # 原声30%
        (0.4, "40%")   # 原声40%
    ]
    
    print("[步骤] 开始生成三个不同音量的视频...")
    print(f"   - 视频: {zoom_video.name}")
    print(f"   - 背景音乐: {yema_mp3.name}")
    print(f"   - 原音频音量: 100%")
    print(f"   - 背景音乐音量: 20%, 30%, 40%")
    print(f"   - 循环播放: 是")
    print()
    
    results = []
    
    for music_vol, vol_label in volumes:
        output_name = f"{zoom_video.stem}_music_{vol_label.replace('%', '')}.mp4"
        output_path = zoom_video.parent / output_name
        
        print(f"[生成中] 背景音乐音量 {vol_label}...")
        
        try:
            result = add_background_music(
                video_path=str(zoom_video.absolute()),
                music_path=str(yema_mp3.absolute()),
                output_path=str(output_path),
                music_volume=music_vol,  # 背景音乐音量
                original_volume=1.0,      # 原音频音量100%
                fade_in=0.0,
                fade_out=0.0,
                loop=True  # 循环播放
            )
            
            if result and Path(result).exists():
                file_size = Path(result).stat().st_size / (1024*1024)
                print(f"   [OK] 成功生成: {Path(result).name} ({file_size:.2f} MB)")
                results.append((vol_label, result))
            else:
                print(f"   [ERROR] 生成失败")
                
        except Exception as e:
            print(f"   [ERROR] 生成失败: {e}")
            import traceback
            traceback.print_exc()
        
        print()
    
    # 总结
    print("=" * 70)
    print("[完成] 背景音乐功能测试完成！")
    print("=" * 70)
    
    if results:
        print("\n生成的视频文件:")
        for vol_label, result_path in results:
            print(f"  - {vol_label}音量: {Path(result_path).name}")
            print(f"    路径: {Path(result_path).absolute()}")
        print()
        print("[SUCCESS] 你可以打开这些文件查看不同音量的效果！")
    else:
        print("\n[ERROR] 没有成功生成任何视频")

if __name__ == "__main__":
    main()

