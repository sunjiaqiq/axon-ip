# -*- coding: utf-8 -*-
"""快速发布测试"""
import requests
import json

video = r"F:\shuziren\pixelle_wrapper\output\20260316_095606_5cb49fcc\final.mp4"
title = "AI生产力测试 - 带字幕视频"
description = "这是自动化生成的带字幕视频，测试发布功能"
cover_text = "AI测试"

print("=" * 70)
print("开始发布流程测试...")
print(f"视频: {video}")
print(f"标题: {title}")
print("=" * 70)

try:
    r = requests.post(
        'http://127.0.0.1:38810/api/publish/douyin',
        json={
            'video_path': video,
            'title': title,
            'description': description,
            'cover_text': cover_text
        },
        timeout=30
    )
    
    print(f"状态码: {r.status_code}")
    if r.status_code == 200:
        result = r.json()
        print("响应:")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print("=" * 70)
        print("发布任务已启动，请观察:")
        print("1. 后端控制台的日志输出")
        print("2. 浏览器窗口的发布进度")
        print("3. 如果卡住，查看后端日志中的错误信息")
    else:
        print(f"错误: {r.text[:500]}")
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()




