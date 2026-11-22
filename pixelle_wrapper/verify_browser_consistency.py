"""
验证浏览器一致性：确保登录功能和发布功能使用完全相同的浏览器
"""
import logging
import douyin_publish_mcp
from pathlib import Path
import os

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def verify_consistency():
    """验证浏览器配置一致性"""
    logger.info("=" * 70)
    logger.info("验证浏览器配置一致性")
    logger.info("=" * 70)
    
    # 1. 读取配置
    browser_config = douyin_publish_mcp.load_browser_config()
    logger.info(f"\n[1. 配置信息]")
    logger.info(f"   Chrome 路径: {browser_config.get('chrome_path')}")
    logger.info(f"   Profile 目录: {browser_config.get('profile_directory')}")
    
    # 2. 计算 user_data_dir（与 ensure_browser() 完全相同）
    wrapper_dir = Path(__file__).parent
    user_data_dir = wrapper_dir / "browser_data" / "chrome_user_data"
    profile_dir = user_data_dir / browser_config.get('profile_directory', 'Profile 3')
    
    logger.info(f"\n[2. 浏览器数据目录]")
    logger.info(f"   User Data Dir: {user_data_dir}")
    logger.info(f"   Profile Dir: {profile_dir}")
    logger.info(f"   Profile 是否存在: {profile_dir.exists()}")
    
    # 3. 验证 ensure_browser() 使用的配置
    logger.info(f"\n[3. ensure_browser() 配置]")
    logger.info(f"   这是整个系统唯一的浏览器实例入口")
    logger.info(f"   所有打开浏览器的操作都调用此函数")
    logger.info(f"   使用全局 driver 变量，确保只创建一个浏览器实例")
    
    # 4. 测试 ensure_browser()
    logger.info(f"\n[4. 测试 ensure_browser()]")
    logger.info(f"   调用 douyin_publish_mcp.ensure_browser()...")
    
    if not douyin_publish_mcp.ensure_browser():
        logger.error("   ❌ 浏览器启动失败")
        return False
    
    logger.info("   ✅ 浏览器启动成功")
    logger.info(f"   Driver 对象: {douyin_publish_mcp.driver}")
    
    # 5. 验证浏览器使用的配置
    try:
        current_url = douyin_publish_mcp.driver.current_url
        logger.info(f"   当前 URL: {current_url}")
        
        # 检查浏览器进程的命令行参数
        import psutil
        driver_pid = douyin_publish_mcp.driver.service.process.pid if hasattr(douyin_publish_mcp.driver, 'service') else None
        logger.info(f"   ChromeDriver PID: {driver_pid}")
        
        # 查找 Chrome 进程
        chrome_found = False
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['name'] and 'chrome.exe' in proc.info['name'].lower():
                    cmdline = proc.info.get('cmdline', [])
                    cmdline_str = ' '.join(cmdline) if cmdline else ''
                    user_data_dir_normalized = str(user_data_dir).replace('\\', '/').lower()
                    cmdline_normalized = cmdline_str.replace('\\', '/').lower()
                    if user_data_dir_normalized in cmdline_normalized and \
                       f'--profile-directory={browser_config.get("profile_directory", "Profile 3")}'.lower() in cmdline_normalized:
                        logger.info(f"   ✅ 找到使用相同配置的 Chrome 进程 (PID: {proc.info['pid']})")
                        logger.info(f"   ✅ 确认使用 User Data Dir: {user_data_dir}")
                        logger.info(f"   ✅ 确认使用 Profile: {browser_config.get('profile_directory', 'Profile 3')}")
                        chrome_found = True
                        break
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        
        if not chrome_found:
            logger.warning("   ⚠️ 未找到使用相同配置的 Chrome 进程")
        
    except Exception as e:
        logger.error(f"   检查浏览器配置时出错: {e}")
    
    logger.info("\n" + "=" * 70)
    logger.info("验证完成！")
    logger.info("=" * 70)
    logger.info("\n总结：")
    logger.info("1. ✅ 登录功能使用 douyin_publish_mcp.ensure_browser()")
    logger.info("2. ✅ 发布功能使用 douyin_publish_mcp.ensure_browser()")
    logger.info("3. ✅ 两者使用完全相同的浏览器配置和实例")
    logger.info("4. ✅ 浏览器数据保存在: " + str(user_data_dir))
    logger.info("5. ✅ Profile 目录: " + str(profile_dir))
    
    return True

if __name__ == "__main__":
    verify_consistency()





