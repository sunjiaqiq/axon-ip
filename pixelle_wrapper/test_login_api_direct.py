"""
直接测试登录 API，模拟前端调用
"""
import requests
import json
import time
import logging

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def test_login_api():
    """测试登录 API（模拟前端调用）"""
    try:
        logger.info("=" * 70)
        logger.info("测试登录 API（模拟前端调用）")
        logger.info("=" * 70)
        
        # 这就是前端点击"登录"按钮时调用的 API
        url = "http://localhost:38810/api/browser/login"
        payload = {
            "platform": "douyin"
        }
        
        logger.info(f"\n[调用登录 API]")
        logger.info(f"URL: {url}")
        logger.info(f"Payload: {payload}")
        
        response = requests.post(url, json=payload, timeout=60)
        
        logger.info(f"\n[响应]")
        logger.info(f"状态码: {response.status_code}")
        
        if response.ok:
            result = response.json()
            logger.info(f"响应内容: {json.dumps(result, indent=2, ensure_ascii=False)}")
            
            logger.info("\n" + "=" * 70)
            logger.info("✅ API 调用成功！")
            logger.info("=" * 70)
            logger.info("\n请检查浏览器：")
            logger.info("1. 是否打开了浏览器")
            logger.info("2. 是否是之前成功发布的浏览器（有账号信息）")
            logger.info("3. 是否导航到了抖音创作者中心")
        else:
            logger.error(f"❌ API 调用失败: {response.status_code}")
            logger.error(f"错误信息: {response.text}")
            
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_login_api()
    logger.info("\n等待 10 秒后退出...")
    time.sleep(10)





