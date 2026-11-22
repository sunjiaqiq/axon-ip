#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试画中画特效功能 - 生成三个版本
"""
import os
import sys
from pathlib import Path

# 添加路径
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

from ai_pipeline.video_editor import add_picture_in_picture

def main():
    print("=" * 70)
    print("画中画特效功能测试 - 生成三个版本")
    print("=" * 70)
    print()
    
    # 最新的口播视频
    host_video = current_dir / "output" / "20260316_095606_5cb49fcc" / "final.mp4"
    
    if not host_video.exists():
        print(f"[ERROR] 未找到口播视频: {host_video}")
        return
    
    print(f"[OK] 找到口播视频: {host_video.name}")
    print(f"     完整路径: {host_video.absolute()}")
    print()
    
    # 查找桌面上的测试视频
    desktop = Path.home() / "Desktop"
    showcase_videos = list(desktop.glob("*.mp4"))
    
    if not showcase_videos:
        print("[ERROR] 桌面上没有找到MP4文件！")
        return
    
    showcase_video = showcase_videos[0]
    print(f"[OK] 找到展示视频: {showcase_video.name}")
    print()
    
    # 生成三个版本的视频
    effects = [
        ('fade', '淡入淡出'),
        ('zoom', '缩放进入'),
        ('slide', '滑入动画')
    ]
    
    output_dir = host_video.parent
    
    for effect_type, effect_name in effects:
        print("=" * 70)
        print(f"生成版本 {effect_name} ({effect_type})")
        print("=" * 70)
        
        output_path = output_dir / f"{host_video.stem}_pip_{effect_type}.mp4"
        
        print(f"[步骤] 开始添加画中画效果...")
        print(f"   - 主视频: {host_video.name}")
        print(f"   - 展示视频: {showcase_video.name}")
        print(f"   - 特效: {effect_name}")
        print(f"   - 开始时间: 3秒后")
        print(f"   - 结束时间: 结束前5秒")
        print(f"   - 位置: 中间")
        print(f"   - 大小: 三分之二（66.7%）")
        print(f"   - 输出: {output_path.name}")
        print()
        
        try:
            result = add_picture_in_picture(
                host_video=str(host_video.absolute()),
                showcase_videos=[str(showcase_video.absolute())],
                output_path=str(output_path),
                start_time=3.0,
                end_before=5.0,
                position='center',
                size_ratio=0.67,
                loop=True,
                effect=effect_type
            )
            
            if result and Path(result).exists():
                file_size = Path(result).stat().st_size / (1024*1024)
                print(f"[SUCCESS] {effect_name} 版本生成成功！")
                print(f"   输出文件: {result}")
                print(f"   文件大小: {file_size:.2f} MB")
                print()
            else:
                print(f"[ERROR] {effect_name} 版本生成失败！")
                print()
                
        except Exception as e:
            print(f"[ERROR] {effect_name} 版本处理出错: {e}")
            import traceback
            traceback.print_exc()
            print()
    
    print("=" * 70)
    print("所有版本生成完成！")
    print("=" * 70)
    print()
    print("生成的视频文件：")
    print(f"  1. {host_video.stem}_pip_fade.mp4   - 淡入淡出效果")
    print(f"  2. {host_video.stem}_pip_zoom.mp4   - 缩放进入效果")
    print(f"  3. {host_video.stem}_pip_slide.mp4  - 滑入动画效果")
    print()
    print("文件位置: " + str(output_dir.absolute()))

if __name__ == "__main__":
    main()




