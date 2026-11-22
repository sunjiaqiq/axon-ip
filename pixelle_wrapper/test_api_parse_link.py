#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 API 接口：/api/copywriting/parse_link
使用 douyin-mcp-server（硅基流动 API）提取文案
"""
import requests
import json
import sys

# 设置UTF-8编码
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

def test_parse_link():
    """测试链接解析和文案提取"""
    url = "http://localhost:38810/api/copywriting/parse_link"
    
    # 测试链接
    test_link = "3.35 06/20 I@V.LW eOX:/ 入住5年才敢说：客厅阳台门千万别拆！# 装修踩坑 # 装修避坑 # 阳台装修 # 家装经验 # 装修干货  https://v.douyin.com/NeDMxbDh5iU/ 复制此链接，打开Dou音搜索，直接观看视频！"
    
    print("=" * 70)
    print("测试 API: /api/copywriting/parse_link")
    print("=" * 70)
    print()
    print(f"测试链接: {test_link[:80]}...")
    print()
    
    try:
        response = requests.post(
            url,
            json={"link": test_link},
            timeout=300  # 5分钟超时
        )
        
        if response.status_code == 200:
            result = response.json()
            print("[OK] 请求成功！")
            print()
            print("=" * 70)
            print("原文案（使用硅基流动 API 提取）:")
            print("=" * 70)
            original = result.get('original_script', {})
            print(f"完整文案: {original.get('full_script', '')}")
            print()
            print("=" * 70)
            print("改写后文案:")
            print("=" * 70)
            rewritten = result.get('rewritten_script', {})
            print(f"完整文案: {rewritten.get('full_script', '')}")
            print()
            print("=" * 70)
            print("视频信息:")
            print("=" * 70)
            video_info = result.get('video_info', {})
            print(f"视频ID: {video_info.get('video_id', '')}")
            print(f"标题: {video_info.get('title', '')}")
            print()
            print("[OK] 测试完成！")
            return True
        else:
            print(f"[ERROR] 请求失败，状态码: {response.status_code}")
            print(f"错误信息: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("[ERROR] 无法连接到服务器，请确保 FastAPI 服务正在运行")
        print("启动命令: uvicorn pixelle_wrapper.main:app --port 38810 --reload")
        return False
    except Exception as e:
        print(f"[ERROR] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_parse_link()







