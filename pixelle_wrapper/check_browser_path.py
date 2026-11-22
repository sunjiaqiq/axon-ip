"""
检查当前浏览器使用的路径和配置
"""
import logging
import douyin_publish_mcp
from pathlib import Path
import os

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def main():
    """检查浏览器路径"""
    try:
        logger.info("=" * 70)
        logger.info("检查浏览器配置和路径")
        logger.info("=" * 70)
        
        # 读取配置
        browser_config = douyin_publish_mcp.load_browser_config()
        logger.info("\n[配置信息]")
        logger.info(f"Chrome 路径: {browser_config.get('chrome_path')}")
        logger.info(f"Profile 目录: {browser_config.get('profile_directory')}")
        
        # 计算 user_data_dir
        wrapper_dir = Path(__file__).parent
        user_data_dir = wrapper_dir / "browser_data" / "chrome_user_data"
        logger.info(f"\n[用户数据目录]")
        logger.info(f"独立 user_data_dir: {user_data_dir}")
        logger.info(f"是否存在: {user_data_dir.exists()}")
        
        if user_data_dir.exists():
            logger.info(f"\n[Profile 目录]")
            profile_dir = user_data_dir / browser_config.get('profile_directory', 'Profile 3')
            logger.info(f"Profile 路径: {profile_dir}")
            logger.info(f"是否存在: {profile_dir.exists()}")
            
            if profile_dir.exists():
                logger.info(f"\n[Profile 内容]")
                items = list(profile_dir.iterdir())
                logger.info(f"包含 {len(items)} 个项目")
                for item in items[:10]:  # 只显示前10个
                    logger.info(f"  - {item.name}")
        
        # 检查原始 Chrome User Data 目录
        original_chrome_user_data_dir = os.path.expanduser(
            os.path.join("~", "AppData", "Local", "Google", "Chrome", "User Data")
        )
        original_chrome_user_data_dir = os.path.expandvars(
            original_chrome_user_data_dir.replace("~", os.environ.get("USERPROFILE", ""))
        )
        original_profile_dir = os.path.join(original_chrome_user_data_dir, browser_config.get('profile_directory', 'Profile 3'))
        
        logger.info(f"\n[原始 Chrome User Data]")
        logger.info(f"原始 User Data 目录: {original_chrome_user_data_dir}")
        logger.info(f"是否存在: {os.path.exists(original_chrome_user_data_dir)}")
        logger.info(f"原始 Profile 目录: {original_profile_dir}")
        logger.info(f"是否存在: {os.path.exists(original_profile_dir)}")
        
        # 检查浏览器是否已启动
        if douyin_publish_mcp.driver:
            logger.info(f"\n[浏览器状态]")
            try:
                current_url = douyin_publish_mcp.driver.current_url
                logger.info(f"浏览器已启动")
                logger.info(f"当前 URL: {current_url}")
            except:
                logger.info(f"浏览器已启动但无法获取 URL")
        else:
            logger.info(f"\n[浏览器状态]")
            logger.info(f"浏览器未启动")
        
        logger.info("\n" + "=" * 70)
        
    except Exception as e:
        logger.error(f"错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()





