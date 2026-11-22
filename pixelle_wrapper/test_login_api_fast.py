"""
快速测试登录 API（3秒超时）
"""
import requests
import json
import time

try:
    print("=" * 70)
    print("测试登录 API（3秒超时）")
    print("=" * 70)
    
    url = "http://localhost:38810/api/browser/login"
    payload = {"platform": "douyin"}
    
    print(f"\n调用: {url}")
    print(f"Payload: {payload}")
    
    start = time.time()
    response = requests.post(url, json=payload, timeout=3)
    elapsed = time.time() - start
    
    print(f"\n响应: {response.status_code}, 耗时: {elapsed:.2f}秒")
    if response.ok:
        result = response.json()
        print(f"结果: {json.dumps(result, indent=2, ensure_ascii=False)}")
        print("\n成功！浏览器应该在后台启动中...")
    else:
        print(f"错误: {response.text}")
        
except requests.exceptions.Timeout:
    print("\n超时（3秒）- 后端可能卡住了")
except Exception as e:
    print(f"\n错误: {e}")





