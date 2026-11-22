#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""复制默认背景音乐文件"""
import os
import shutil
import sys
from pathlib import Path

# 设置UTF-8输出
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

def copy_default_music():
    """复制默认背景音乐文件"""
    # 源文件路径
    desktop = Path.home() / "Desktop" / "成品"
    source_files = ["轻快.mp3", "野马.mp3", "33.mp3"]
    
    # 目标目录
    target_dir = Path(__file__).parent / "data" / "background_music"
    target_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"目标目录: {target_dir}")
    
    # 复制文件
    for filename in source_files:
        source_path = desktop / filename
        target_path = target_dir / filename
        
        if source_path.exists():
            shutil.copy2(source_path, target_path)
            print(f"✓ 已复制: {filename}")
        else:
            print(f"✗ 文件不存在: {source_path}")
    
    print("默认背景音乐文件复制完成！")

if __name__ == "__main__":
    copy_default_music()

