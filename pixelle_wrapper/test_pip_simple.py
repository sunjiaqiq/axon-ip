#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试画中画功能 - 简化版
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
    print("画中画功能测试")
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
    print(f"[INFO] 查找桌面路径: {desktop}")
    
    # 查找所有MP4文件
    showcase_videos = list(desktop.glob("*.mp4"))
    
    if not showcase_videos:
        print("[ERROR] 桌面上没有找到MP4文件！")
        print("请确保桌面上有一个测试展示的MP4视频文件")
        return
    
    # 使用第一个找到的MP4文件
    showcase_video = showcase_videos[0]
    print(f"[OK] 找到展示视频: {showcase_video.name}")
    print(f"     完整路径: {showcase_video.absolute()}")
    print()
    
    # 如果有多个，列出所有
    if len(showcase_videos) > 1:
        print(f"[INFO] 桌面上找到 {len(showcase_videos)} 个MP4文件:")
        for i, v in enumerate(showcase_videos, 1):
            print(f"  {i}. {v.name}")
        print(f"使用第一个: {showcase_video.name}")
        print()
    
    # 生成输出路径
    output_dir = host_video.parent
    output_path = output_dir / f"{host_video.stem}_pip_test.mp4"
    
    print("[步骤] 开始添加画中画效果...")
    print(f"   - 主视频: {host_video.name}")
    print(f"   - 展示视频: {showcase_video.name}")
    print(f"   - 开始时间: 3秒后")
    print(f"   - 结束时间: 结束前5秒")
    print(f"   - 位置: 中间")
    print(f"   - 大小: 三分之二（66.7%）")
    print(f"   - 特效: 缩放进入（zoom）")
    print(f"   - 音频: 画中画静音")
    print(f"   - 输出: {output_path.name}")
    print()
    
    try:
        result = add_picture_in_picture(
            host_video=str(host_video.absolute()),
            showcase_videos=[str(showcase_video.absolute())],
            output_path=str(output_path),
            start_time=3.0,
            end_before=5.0,
            position='center',      # 中间位置
            size_ratio=2/3,         # 三分之二大小（66.7%）
            loop=True,
            effect='zoom'          # 缩放进入特效（默认）
        )
        
        if result and Path(result).exists():
            print()
            print("=" * 70)
            print("[SUCCESS] 画中画功能测试成功！")
            print("=" * 70)
            print(f"输出文件: {result}")
            file_size = Path(result).stat().st_size / (1024*1024)
            print(f"文件大小: {file_size:.2f} MB")
            print()
            print("✅ 你可以打开这个文件查看画中画效果！")
            print(f"   文件位置: {Path(result).absolute()}")
        else:
            print("[ERROR] 画中画处理失败！")
            
    except Exception as e:
        print(f"[ERROR] 处理过程中出错: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()

