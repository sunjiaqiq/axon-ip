"""
验证：通过 API 调用后，检查浏览器是否正确打开（Profile 3，有账号信息）
"""
import requests
import json
import time
import logging
import douyin_publish_mcp

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def verify():
    """验证 API 调用后的浏览器状态"""
    try:
        logger.info("=" * 70)
        logger.info("验证：API 调用后的浏览器状态")
        logger.info("=" * 70)
        
        # 1. 调用登录 API
        url = "http://localhost:38810/api/browser/login"
        payload = {"platform": "douyin"}
        
        logger.info(f"\n[1. 调用登录 API]")
        logger.info(f"URL: {url}")
        
        response = requests.post(url, json=payload, timeout=5)
        logger.info(f"响应: {response.status_code}")
        
        if not response.ok:
            logger.error("API 调用失败")
            return
        
        result = response.json()
        logger.info(f"结果: {json.dumps(result, indent=2, ensure_ascii=False)}")
        
        # 2. 等待浏览器启动
        logger.info(f"\n[2. 等待浏览器启动（10秒）]")
        time.sleep(10)
        
        # 3. 检查浏览器状态
        logger.info(f"\n[3. 检查浏览器状态]")
        if not douyin_publish_mcp.driver:
            logger.error("Driver 未初始化")
            return
        
        current_url = douyin_publish_mcp.driver.current_url
        page_title = douyin_publish_mcp.driver.title
        
        logger.info(f"Driver: {douyin_publish_mcp.driver}")
        logger.info(f"当前 URL: {current_url}")
        logger.info(f"页面标题: {page_title}")
        
        # 4. 检查是否有账号信息
        logger.info(f"\n[4. 检查账号信息]")
        if 'login' not in current_url.lower() and 'passport' not in current_url.lower():
            logger.info("✅ 浏览器已登录（有账号信息）")
        else:
            logger.warning("⚠️ 浏览器未登录（空白界面）")
        
        # 5. 检查浏览器进程
        try:
            import psutil
            from pathlib import Path
            wrapper_dir = Path(__file__).parent
            user_data_dir = wrapper_dir / "browser_data" / "chrome_user_data"
            
            chrome_found = False
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                if proc.info['name'] and 'chrome.exe' in proc.info['name'].lower():
                    cmdline = proc.info.get('cmdline', [])
                    cmdline_str = ' '.join(cmdline) if cmdline else ''
                    if str(user_data_dir).replace('\\', '/').lower() in cmdline_str.replace('\\', '/').lower() and \
                       'Profile 3' in cmdline_str:
                        logger.info(f"✅ 找到使用 Profile 3 的 Chrome 进程 (PID: {proc.info['pid']})")
                        chrome_found = True
                        break
            
            if not chrome_found:
                logger.warning("⚠️ 未找到使用 Profile 3 的 Chrome 进程")
        except:
            pass
        
        logger.info("\n" + "=" * 70)
        logger.info("验证完成！")
        logger.info("=" * 70)
        
    except Exception as e:
        logger.error(f"错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    verify()





