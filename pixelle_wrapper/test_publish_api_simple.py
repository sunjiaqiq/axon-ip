"""
测试抖音发布API
"""
import requests
import json
import time
import logging

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def test_publish_api():
    """测试发布API"""
    logger.info("=" * 70)
    logger.info("测试：抖音发布API")
    logger.info("=" * 70)
    
    # 等待后台服务启动
    logger.info("\n等待后台服务启动（5秒）...")
    time.sleep(5)
    
    # API地址
    url = "http://127.0.0.1:38810/api/publish/douyin"
    
    # 请求数据（提供封面路径，避免封面提取失败）
    data = {
        "video_path": "output/20260314_193109_1a06fb65/final.mp4",
        "title": "测试视频标题-点击确定测试",
        "description": "这是测试视频的描述内容，用于测试点击确定按钮功能"
    }
    
    logger.info(f"\n请求URL: {url}")
    logger.info(f"请求数据: {json.dumps(data, ensure_ascii=False, indent=2)}")
    
    try:
        logger.info("\n发送POST请求...")
        response = requests.post(url, json=data, timeout=300)
        
        logger.info(f"\n响应状态码: {response.status_code}")
        logger.info(f"响应内容: {response.text}")
        
        if response.status_code == 200:
            logger.info("\n✅ API调用成功！")
            result = response.json()
            logger.info(f"结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
        else:
            logger.error(f"\n❌ API调用失败，状态码: {response.status_code}")
            
    except requests.exceptions.ConnectionError:
        logger.error("❌ 无法连接到后台服务，请确保后台服务已启动")
    except Exception as e:
        logger.error(f"❌ 请求失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_publish_api()

