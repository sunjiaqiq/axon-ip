#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试人设配置和二创文案生成
"""
import requests
import json
import sys

# 设置UTF-8编码
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

def test_persona_rewrite():
    """测试人设配置和二创文案生成"""
    url = "http://localhost:38810/api/copywriting/parse_link"
    
    # 测试链接
    test_link = "3.35 06/20 I@V.LW eOX:/ 入住5年才敢说：客厅阳台门千万别拆！# 装修踩坑 # 装修避坑 # 阳台装修 # 家装经验 # 装修干货  https://v.douyin.com/NeDMxbDh5iU/ 复制此链接，打开Dou音搜索，直接观看视频！"
    
    # 人设配置（根据截图）
    persona_config = {
        "consumptionRange": "100-500",
        "wechatId": "jgksdf111",
        "companyName": "嘿嘿",
        "targetMarket": "全国",
        "coreSolution": "我们可以帮助客户解决获客懒的问题",
        "companyAddress": "山东济南",
        "productYears": "5年",
        "productAdvantages": "全面,性价比高,效果好",
        "other": "我们的产品区别于市面上的产品"
    }
    
    print("=" * 70)
    print("测试人设配置和二创文案生成")
    print("=" * 70)
    print()
    print("人设配置:")
    for key, value in persona_config.items():
        print(f"  {key}: {value}")
    print()
    print(f"测试链接: {test_link[:80]}...")
    print()
    
    try:
        response = requests.post(
            url,
            json={
                "link": test_link,
                "persona_config": persona_config
            },
            timeout=300  # 5分钟超时
        )
        
        if response.status_code == 200:
            result = response.json()
            print("[OK] 请求成功！")
            print()
            print("=" * 70)
            print("原文案（从视频提取）:")
            print("=" * 70)
            original = result.get('original_script', {})
            print(original.get('full_script', ''))
            print()
            print("=" * 70)
            print("二创文案（根据人设配置改写）:")
            print("=" * 70)
            rewritten = result.get('rewritten_script', {})
            print(rewritten.get('full_script', ''))
            print()
            print("=" * 70)
            print("二创文案结构:")
            print("=" * 70)
            print(f"钩子: {rewritten.get('hook', '')}")
            print(f"问题: {rewritten.get('problem', '')}")
            print(f"方案: {rewritten.get('solution', '')}")
            print(f"行动: {rewritten.get('cta', '')}")
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
    test_persona_rewrite()







