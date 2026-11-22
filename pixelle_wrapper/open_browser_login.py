"""
打开浏览器登录页面
"""
import requests
import json

def main():
    url = "http://localhost:38810/api/browser/login"
    data = {
        "platform": "douyin"
    }
    
    print("=" * 70)
    print("正在打开浏览器登录页面...")
    print("=" * 70)
    print()
    
    try:
        response = requests.post(url, json=data, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            print("✓ 浏览器登录页面已打开！")
            print(f"  平台: {result.get('platform', 'douyin')}")
            print(f"  URL: {result.get('url', '')}")
            print()
            print("请在浏览器中登录您的账号，登录完成后可以运行测试脚本搜索视频。")
        else:
            print(f"✗ 打开浏览器失败: {response.status_code}")
            print(response.text)
    except requests.exceptions.ConnectionError:
        print("✗ 无法连接到后端服务")
        print("  请确保FastAPI服务正在运行（端口38810）")
    except Exception as e:
        print(f"✗ 出错: {e}")

if __name__ == "__main__":
    main()







