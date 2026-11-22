"""
打开浏览器供用户查看
"""
import asyncio
import logging
from ai_pipeline.browser_manager import browser_manager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s'
)

async def main():
    """打开浏览器"""
    try:
        print("=" * 60)
        print("正在打开浏览器...")
        print("=" * 60)
        
        # 打开抖音创作者中心
        page = await browser_manager.open_login_page("https://creator.douyin.com/creator-micro/content/upload")
        
        print("\n[成功] 浏览器已打开！")
        print("[页面] https://creator.douyin.com/creator-micro/content/upload")
        print("\n浏览器将保持打开状态，您可以查看。")
        print("按 Ctrl+C 关闭浏览器...\n")
        
        # 保持浏览器打开
        try:
            while True:
                await asyncio.sleep(1)
                if not browser_manager.is_initialized():
                    print("\n浏览器已关闭")
                    break
        except KeyboardInterrupt:
            print("\n正在关闭浏览器...")
            await browser_manager.close()
            print("[成功] 浏览器已关闭")
            
    except Exception as e:
        print(f"\n[错误] {e}")
        import traceback
        traceback.print_exc()
        # 不关闭浏览器，让用户查看
        print("\n浏览器保持打开状态，您可以查看。")

if __name__ == "__main__":
    asyncio.run(main())

