"""
测试硅基流动 API 接口
"""
import requests
import json

api_key = "${SILICONFLOW_API_KEY}"
url = "https://api.siliconflow.cn/v1/chat/completions"

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {api_key}"
}

data = {
    "model": "zai-org/GLM-5.3",
    "messages": [
        {"role": "system", "content": "你是一个有用的助手"},
        {"role": "user", "content": "你好，请介绍一下你自己"}
    ]
}

print("=" * 70)
print("测试硅基流动 API")
print("=" * 70)
print(f"URL: {url}")
print(f"Model: {data['model']}")
print("=" * 70)

try:
    response = requests.post(url, headers=headers, json=data, timeout=30)
    print(f"状态码: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print("\n[成功] API 调用成功！")
        print(f"响应内容: {json.dumps(result, ensure_ascii=False, indent=2)}")
        
        if 'choices' in result and len(result['choices']) > 0:
            content = result['choices'][0]['message']['content']
            print(f"\nAI 回复: {content}")
    else:
        print(f"\n[失败] API 调用失败，状态码: {response.status_code}")
        print(f"错误信息: {response.text}")
        
except Exception as e:
    print(f"\n[异常] 请求异常: {e}")
    import traceback
    traceback.print_exc()

