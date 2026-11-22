"""
15秒测试登录 API
"""
import requests
import json
import time
import logging

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def test_login_api():
    """测试登录 API（15秒超时）"""
    try:
        logger.info("=" * 70)
        logger.info("测试登录 API（15秒超时）")
        logger.info("=" * 70)
        
        url = "http://localhost:38810/api/browser/login"
        payload = {"platform": "douyin"}
        
        logger.info(f"\n[调用登录 API]")
        logger.info(f"URL: {url}")
        logger.info(f"Payload: {payload}")
        
        start_time = time.time()
        response = requests.post(url, json=payload, timeout=15)
        elapsed = time.time() - start_time
        
        logger.info(f"\n[响应]")
        logger.info(f"状态码: {response.status_code}")
        logger.info(f"耗时: {elapsed:.2f}秒")
        
        if response.ok:
            result = response.json()
            logger.info(f"响应: {json.dumps(result, indent=2, ensure_ascii=False)}")
            logger.info("\n✅ API 调用成功！")
            logger.info("请检查浏览器是否已打开，是否有账号信息")
        else:
            logger.error(f"❌ API 调用失败: {response.status_code}")
            logger.error(f"错误: {response.text}")
            
    except requests.exceptions.Timeout:
        logger.error("❌ API 调用超时（15秒）")
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}")

if __name__ == "__main__":
    test_login_api()





