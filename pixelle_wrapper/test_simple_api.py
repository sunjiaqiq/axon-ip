"""
简单测试：检查后端是否响应
"""
import requests
import time

try:
    print("测试后端连接...")
    start = time.time()
    response = requests.get("http://localhost:38810/health", timeout=5)
    elapsed = time.time() - start
    print(f"后端响应成功: {response.status_code}, 耗时: {elapsed:.2f}秒")
    print(f"响应: {response.text}")
except requests.exceptions.Timeout:
    print("后端超时（5秒）")
except requests.exceptions.ConnectionError:
    print("后端连接失败（可能未运行）")
except Exception as e:
    print(f"错误: {e}")

