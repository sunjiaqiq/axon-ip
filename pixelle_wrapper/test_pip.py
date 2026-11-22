#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试画中画功能
"""
import os
import sys
from pathlib import Path
from datetime import datetime

# 添加路径
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

from ai_pipeline.video_editor import add_picture_in_picture

def find_desktop_video():
    """查找桌面上的测试展示视频"""
    desktop = Path.home() / "Desktop"
    
    # 查找包含"测试"或"展示"的MP4文件
    patterns = ["*测试*.mp4", "*展示*.mp4", "*test*.mp4", "*showcase*.mp4"]
    
    for pattern in patterns:
        videos = list(desktop.glob(pattern))
        if videos:
            return videos[0]
    
    # 查找所有MP4文件
    all_mp4s = list(desktop.glob("*.mp4"))
    if all_mp4s:
        print(f"[INFO] 找到桌面上的MP4文件:")
        for i, v in enumerate(all_mp4s, 1):
            print(f"  {i}. {v.name}")
        return all_mp4s[0]
    
    return None

def find_latest_host_video():
    """查找最新的口播视频（40多秒）"""
    output_dir = current_dir / "output"
    
    if not output_dir.exists():
        return None
    
    # 查找所有final.mp4文件
    final_videos = list(output_dir.rglob("final.mp4"))
    
    if not final_videos:
        return None
    
    # 按修改时间排序，最新的在前
    final_videos.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    
    # 检查视频时长（使用文件大小估算，或者直接返回最新的）
    for video in final_videos:
        # 先返回最新的，如果时长不对再找下一个
        return video
    
    return None

def get_video_duration(video_path):
    """获取视频时长（秒）"""
    try:
        from moviepy.editor import VideoFileClip
        clip = VideoFileClip(str(video_path))
        duration = clip.duration
        clip.close()
        return duration
    except:
        return None

def main():
    print("=" * 70)
    print("画中画功能测试")
    print("=" * 70)
    print()
    
    # 1. 查找桌面上的测试展示视频
    print("[步骤1] 查找桌面上的测试展示视频...")
    showcase_video = find_desktop_video()
    
    if not showcase_video:
        print("[ERROR] 未找到桌面上的测试展示视频！")
        print("请确保桌面上有一个MP4文件（包含'测试'或'展示'字样）")
        return
    
    print(f"[OK] 找到展示视频: {showcase_video}")
    print(f"     完整路径: {showcase_video.absolute()}")
    print()
    
    # 2. 查找最新的口播视频
    print("[步骤2] 查找最新的口播视频...")
    host_video = find_latest_host_video()
    
    if not host_video:
        print("[ERROR] 未找到口播视频！")
        return
    
    print(f"[OK] 找到口播视频: {host_video}")
    
    # 检查视频时长
    duration = get_video_duration(host_video)
    if duration:
        print(f"     视频时长: {duration:.2f}秒")
        if duration < 30:
            print(f"[WARNING] 视频时长较短（{duration:.2f}秒），可能不是40多秒的视频")
    print()
    
    # 3. 测试画中画功能
    print("[步骤3] 开始添加画中画效果...")
    print(f"   - 主视频: {host_video.name}")
    print(f"   - 展示视频: {showcase_video.name}")
    print(f"   - 开始时间: 3秒后")
    print(f"   - 结束时间: 结束前5秒")
    print(f"   - 位置: 右下角")
    print(f"   - 大小: 30%")
    print()
    
    # 生成输出路径
    output_dir = host_video.parent
    output_path = output_dir / f"{host_video.stem}_pip_test.mp4"
    
    try:
        result = add_picture_in_picture(
            host_video=str(host_video.absolute()),
            showcase_videos=[str(showcase_video.absolute())],
            output_path=str(output_path),
            start_time=3.0,
            end_before=5.0,
            position='bottom-right',
            size_ratio=0.3,
            loop=True
        )
        
        if result and Path(result).exists():
            print()
            print("=" * 70)
            print("[SUCCESS] 画中画功能测试成功！")
            print("=" * 70)
            print(f"输出文件: {result}")
            print(f"文件大小: {Path(result).stat().st_size / (1024*1024):.2f} MB")
            print()
            print("你可以打开这个文件查看画中画效果！")
        else:
            print("[ERROR] 画中画处理失败！")
            
    except Exception as e:
        print(f"[ERROR] 处理过程中出错: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()




