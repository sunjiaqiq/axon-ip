"""
测试链接解析和文案改写功能
"""
import requests
import json

def test_parse_link():
    """测试链接解析API"""
    url = "http://localhost:38810/api/copywriting/parse_link"
    
    # 测试链接
    test_link = """3.35 06/20 I@V.LW eOX:/ 入住5年才敢说：客厅阳台门千万别拆！# 装修踩坑 # 装修避坑 # 阳台装修 # 家装经验 # 装修干货  https://v.douyin.com/NeDMxbDh5iU/ 复制此链接，打开Dou音搜索，直接观看视频！"""
    
    print("=" * 70)
    print("测试链接解析和文案改写")
    print("=" * 70)
    print(f"\n输入链接: {test_link[:100]}...\n")
    
    try:
        response = requests.post(url, json={"link": test_link}, timeout=300)
        
        if response.status_code == 200:
            data = response.json()
            print("✓ 成功！")
            print("\n原文案:")
            print("-" * 70)
            print(data.get('original_script', {}).get('full_text', '')[:500])
            print("\n改写后文案:")
            print("-" * 70)
            print(data.get('rewritten_script', {}).get('full_script', '')[:500])
            print("\n" + "=" * 70)
        else:
            print(f"✗ 失败: {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"✗ 错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_parse_link()







