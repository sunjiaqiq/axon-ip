"""
最终测试：通过 API 调用，检查浏览器是否正确打开
"""
import requests
import json
import time
import logging

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def test_api_final():
    """最终测试 API"""
    try:
        logger.info("=" * 70)
        logger.info("最终测试：通过 API 调用登录功能")
        logger.info("=" * 70)
        
        url = "http://localhost:38810/api/browser/login"
        payload = {"platform": "douyin"}
        
        logger.info(f"\n[调用登录 API]")
        logger.info(f"URL: {url}")
        logger.info(f"Payload: {payload}")
        
        start = time.time()
        response = requests.post(url, json=payload, timeout=5)
        elapsed = time.time() - start
        
        logger.info(f"\n[响应]")
        logger.info(f"状态码: {response.status_code}")
        logger.info(f"耗时: {elapsed:.2f}秒")
        
        if response.ok:
            result = response.json()
            logger.info(f"结果: {json.dumps(result, indent=2, ensure_ascii=False)}")
            logger.info("\n✅ API 调用成功！")
            
            # 等待浏览器启动
            logger.info("\n等待5秒，让浏览器启动...")
            time.sleep(5)
            
            # 检查浏览器
            try:
                import douyin_publish_mcp
                if douyin_publish_mcp.driver:
                    current_url = douyin_publish_mcp.driver.current_url
                    logger.info(f"\n[浏览器状态]")
                    logger.info(f"Driver: {douyin_publish_mcp.driver}")
                    logger.info(f"当前 URL: {current_url}")
                    
                    # 检查是否有账号信息
                    if 'login' not in current_url.lower() and 'passport' not in current_url.lower():
                        logger.info("✅ 浏览器已登录（有账号信息）")
                    else:
                        logger.warning("⚠️ 浏览器未登录（空白界面）")
                else:
                    logger.warning("⚠️ Driver 未初始化")
            except Exception as e:
                logger.warning(f"检查浏览器状态失败: {e}")
        else:
            logger.error(f"❌ API 调用失败: {response.status_code}")
            logger.error(f"错误: {response.text}")
            
    except requests.exceptions.Timeout:
        logger.error("❌ API 调用超时（5秒）")
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_api_final()





