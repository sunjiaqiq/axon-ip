"""
直接测试登录 API，确保使用正确的浏览器
"""
import requests
import json
import time

def test_login_api():
    """测试登录 API"""
    print("=" * 70)
    print("测试登录 API")
    print("=" * 70)
    
    # 调用登录 API（与前端完全相同的方式）
    url = "http://localhost:38810/api/browser/login"
    payload = {
        "platform": "douyin"
    }
    
    print(f"\n[测试] 调用登录 API: {url}")
    print(f"[测试] 请求参数: {payload}")
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        print(f"[测试] 响应状态码: {response.status_code}")
        
        if response.ok:
            result = response.json()
            print(f"[测试] 响应内容: {json.dumps(result, indent=2, ensure_ascii=False)}")
            print("\n" + "=" * 70)
            print("✅ 登录 API 调用成功！")
            print("=" * 70)
            print("\n请检查浏览器是否已打开，是否是之前成功发布的浏览器（有账号登录信息）")
        else:
            print(f"[测试] ❌ 登录 API 调用失败: {response.status_code}")
            print(f"[测试] 错误信息: {response.text}")
    except Exception as e:
        print(f"[测试] ❌ 登录 API 调用异常: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_login_api()
    print("\n等待 10 秒后退出...")
    time.sleep(10)





