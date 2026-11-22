"""
视频下载模块 - 使用浏览器直接下载视频（支持抖音、快手等平台）
优先使用浏览器下载，如果失败则尝试yt-dlp
"""
import logging
import sys
import asyncio
from pathlib import Path
from typing import Optional
import time

# 添加 yt-dlp 路径
current_dir = Path(__file__).parent.parent.parent
yt_dlp_path = current_dir / "yt-dlp-master"
if yt_dlp_path.exists():
    sys.path.insert(0, str(yt_dlp_path))

logger = logging.getLogger(__name__)

try:
    import yt_dlp
except ImportError:
    logger.warning("yt-dlp 未安装，请安装: pip install yt-dlp")
    yt_dlp = None

try:
    from ai_pipeline.browser_manager import browser_manager
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    BROWSER_MANAGER_AVAILABLE = True
except ImportError:
    BROWSER_MANAGER_AVAILABLE = False
    browser_manager = None
    PlaywrightTimeoutError = None


async def _download_video_with_browser(url: str, output_dir: Path) -> Optional[Path]:
    """使用浏览器直接下载视频（优先使用当前打开的页面）"""
    if not BROWSER_MANAGER_AVAILABLE or browser_manager is None:
        return None
    
    try:
        await browser_manager.ensure_initialized()
        context = await browser_manager.get_page()
        
        # 优先使用当前打开的页面
        pages = context.pages
        page = None
        if pages:
            # 检查是否有页面已经打开了目标URL
            for p in pages:
                try:
                    current_url = p.url
                    if 'douyin.com' in current_url:
                        page = p
                        logger.info(f"[VideoDownloader] 使用已打开的页面: {current_url}")
                        # 如果URL不匹配，导航到目标URL
                        if url not in current_url:
                            logger.info(f"[VideoDownloader] 导航到目标URL: {url}")
                            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
                            await page.wait_for_timeout(5000)  # 等待页面和视频加载
                        break
                except:
                    continue
        
        # 如果没有找到合适的页面，创建新页面并打开URL
        if page is None:
            page = await context.new_page()
            logger.info(f"[VideoDownloader] 创建新页面并访问视频页面: {url}")
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await page.wait_for_timeout(5000)  # 等待页面和视频加载
        else:
            # 如果使用已有页面，等待一下确保视频加载
            await page.wait_for_timeout(3000)
        
        # 等待视频元素加载
        try:
            await page.wait_for_selector('video', timeout=10000)
        except:
            logger.warning("[VideoDownloader] 未找到video元素，继续尝试...")
        
        # 方法1: 通过监听网络请求捕获真实视频URL（最可靠的方法）
        video_url = None
        video_urls_captured = []
        
        def handle_response(response):
            """监听网络响应，捕获视频URL"""
            try:
                url = response.url
                content_type = response.headers.get('content-type', '')
                
                # 检查是否是视频文件
                if 'video' in content_type or url.endswith(('.mp4', '.m3u8', '.flv')):
                    # 排除一些明显不是视频的URL
                    if 'douyin' in url and ('video' in url or 'play' in url or 'mp4' in url):
                        video_urls_captured.append(url)
                        logger.info(f"[VideoDownloader] 捕获到视频URL: {url[:100]}...")
            except:
                pass
        
        # 监听网络响应
        page.on("response", handle_response)
        
        # 等待页面加载和视频请求
        await page.wait_for_timeout(5000)
        
        # 如果捕获到视频URL，使用最大的（通常是完整视频）
        if video_urls_captured:
            # 按URL长度排序，选择最长的（通常是完整视频）
            video_urls_captured.sort(key=len, reverse=True)
            video_url = video_urls_captured[0]
            logger.info(f"[VideoDownloader] 从网络请求中捕获到视频URL: {video_url[:100]}...")
        
        # 方法2: 如果网络拦截失败，尝试从video元素获取
        if not video_url:
            try:
                video_element = await page.query_selector('video')
                if video_element:
                    # 尝试获取currentSrc（当前播放的视频源）
                    video_url = await video_element.evaluate('el => el.currentSrc || el.src')
                    if video_url:
                        logger.info(f"[VideoDownloader] 从video元素获取到URL: {video_url[:100]}...")
            except Exception as e:
                logger.warning(f"[VideoDownloader] 从video元素获取URL失败: {e}")
        
        # 方法3: 从页面内容中提取视频URL
        if not video_url:
            content = await page.content()
            import re
            # 查找视频URL模式（更精确的匹配）
            video_urls = re.findall(r'https?://[^"\s<>]+\.(?:mp4|m3u8|flv)', content)
            if video_urls:
                # 过滤出抖音视频URL
                douyin_videos = [u for u in video_urls if 'douyin' in u and ('video' in u or 'play' in u)]
                if douyin_videos:
                    video_url = douyin_videos[0]
                    logger.info(f"[VideoDownloader] 从页面内容提取到视频URL: {video_url[:100]}...")
        
        if not video_url:
            logger.warning("[VideoDownloader] 无法从页面提取视频URL，尝试使用yt-dlp")
            return None
        
        logger.info(f"[VideoDownloader] 找到视频URL: {video_url[:100]}...")
        
        # 使用浏览器下载视频
        video_id = url.split('/video/')[-1].split('?')[0] if '/video/' in url else 'video'
        video_path = output_dir / f"{video_id}.mp4"
        
        # 使用浏览器请求视频并保存
        logger.info("[VideoDownloader] 开始下载视频流...")
        
        # 方法1: 使用Playwright的response.body()直接下载（最可靠）
        try:
            # 重新请求视频URL以获取响应
            response = await page.goto(video_url, wait_until='networkidle', timeout=60000)
            if response and response.ok:
                video_content = await response.body()
                
                if video_content:
                    # 保存到文件
                    with open(video_path, 'wb') as f:
                        f.write(video_content)
                    
                    if video_path.exists():
                        file_size = video_path.stat().st_size / (1024 * 1024)  # MB
                        logger.info(f"[VideoDownloader] 浏览器下载完成: {video_path} ({file_size:.2f} MB)")
                        return video_path
                    else:
                        logger.warning("[VideoDownloader] 浏览器下载失败，文件不存在")
        except Exception as e:
            logger.warning(f"[VideoDownloader] 方法1下载失败: {e}")
        
        # 方法2: 使用fetch API下载视频（通过浏览器上下文）
        try:
            # 先导航回视频页面（如果刚才跳转了）
            if 'douyin.com/video' not in page.url:
                await page.goto(url, wait_until='domcontentloaded', timeout=30000)
                await page.wait_for_timeout(2000)
            
            # 使用page.evaluate执行fetch下载
            video_content = await page.evaluate(f"""
                async () => {{
                    try {{
                        const response = await fetch('{video_url}', {{
                            method: 'GET',
                            headers: {{
                                'Referer': '{url}',
                                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                            }}
                        }});
                        if (!response.ok) {{
                            return null;
                        }}
                        const blob = await response.blob();
                        const arrayBuffer = await blob.arrayBuffer();
                        return Array.from(new Uint8Array(arrayBuffer));
                    }} catch (e) {{
                        console.error('Fetch error:', e);
                        return null;
                    }}
                }}
            """)
            
            if video_content and len(video_content) > 0:
                # 保存到文件
                with open(video_path, 'wb') as f:
                    f.write(bytes(video_content))
                
                if video_path.exists():
                    file_size = video_path.stat().st_size / (1024 * 1024)  # MB
                    logger.info(f"[VideoDownloader] 浏览器下载完成: {video_path} ({file_size:.2f} MB)")
                    return video_path
                else:
                    logger.warning("[VideoDownloader] 浏览器下载失败，文件不存在")
            else:
                logger.warning("[VideoDownloader] 无法获取视频内容（fetch返回空）")
        except Exception as e:
            logger.warning(f"[VideoDownloader] 方法2下载失败: {e}")
        
        # 如果都失败了
        logger.warning("[VideoDownloader] 所有浏览器下载方法都失败")
        return None
            
    except Exception as e:
        logger.warning(f"[VideoDownloader] 浏览器下载失败: {e}")
        try:
            await page.close()
        except:
            pass
        return None


def download_video(url: str, output_dir: Optional[Path] = None) -> Optional[Path]:
    """
    下载视频到指定目录
    优先使用浏览器下载，如果失败则尝试yt-dlp
    
    Args:
        url: 视频URL
        output_dir: 输出目录，默认为 materials/
        
    Returns:
        下载后的视频文件路径（mp4格式）
    """
    logger.info(f"[VideoDownloader] 开始下载视频: {url}")
    
    try:
        # 设置输出目录
        if output_dir is None:
            output_dir = Path(__file__).parent.parent / "materials"
        else:
            output_dir = Path(output_dir)
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 方法1: 优先使用浏览器下载（直接使用当前打开的页面）
        if BROWSER_MANAGER_AVAILABLE and browser_manager:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            logger.info("[VideoDownloader] 优先使用浏览器下载（使用当前打开的页面）...")
            result = loop.run_until_complete(_download_video_with_browser(url, output_dir))
            if result and result.exists():
                return result
        
        # 方法2: 如果浏览器下载失败，对于抖音链接使用yt-dlp
        if 'douyin.com' in url or 'tiktok.com' in url:
            logger.info("[VideoDownloader] 检测到抖音链接，尝试使用yt-dlp下载...")
            if yt_dlp is None:
                logger.warning("[VideoDownloader] yt-dlp 未安装")
            else:
                # 尝试yt-dlp
                # 从浏览器获取cookies
                cookies = None
                if BROWSER_MANAGER_AVAILABLE and browser_manager:
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    
                    async def _get_cookies():
                        await browser_manager.ensure_initialized()
                        context = await browser_manager.get_page()
                        return await context.cookies()
                    
                    try:
                        cookies = loop.run_until_complete(_get_cookies())
                        logger.info(f"[VideoDownloader] 从浏览器获取了 {len(cookies)} 个cookies")
                    except Exception as cookie_error:
                        logger.warning(f"[VideoDownloader] 获取cookies失败: {cookie_error}")
                        cookies = None
                
                # 配置 yt-dlp 选项
                import tempfile
                import os
                ydl_opts = {
                    'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                    'outtmpl': str(output_dir / '%(id)s.%(ext)s'),
                    'quiet': False,
                    'no_warnings': False,
                }
                
                # 如果有cookies，保存到临时文件
                cookie_file = None
                if cookies:
                    cookie_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
                    cookie_file.write("# Netscape HTTP Cookie File\n")
                    for cookie in cookies:
                        domain = cookie.get('domain', '.douyin.com')
                        if not domain.startswith('.'):
                            domain = '.' + domain
                        cookie_file.write(f"{domain}\tTRUE\t/\tFALSE\t0\t{cookie['name']}\t{cookie['value']}\n")
                    cookie_file.close()
                    ydl_opts['cookiefile'] = cookie_file.name
                    logger.info(f"[VideoDownloader] 已使用浏览器cookies")
                
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        # 提取视频信息
                        info = ydl.extract_info(url, download=False)
                        video_id = info.get('id', 'video')
                        ext = info.get('ext', 'mp4')
                        title = info.get('title', 'Unknown')
                        
                        logger.info(f"[VideoDownloader] 视频信息: {title}")
                        logger.info(f"[VideoDownloader] 视频ID: {video_id}")
                        
                        # 下载视频
                        ydl.download([url])
                        
                        # 返回下载的文件路径
                        video_path = output_dir / f"{video_id}.{ext}"
                        
                        if video_path.exists():
                            logger.info(f"[VideoDownloader] yt-dlp下载完成: {video_path}")
                            if cookie_file:
                                try:
                                    os.unlink(cookie_file.name)
                                except:
                                    pass
                            return video_path
                        else:
                            logger.warning(f"[VideoDownloader] yt-dlp下载失败，文件不存在")
                except Exception as ydl_error:
                    logger.warning(f"[VideoDownloader] yt-dlp下载失败: {ydl_error}")
                finally:
                    if cookie_file:
                        try:
                            import os
                            os.unlink(cookie_file.name)
                        except:
                            pass
        
        # 如果都失败了
        logger.warning("[VideoDownloader] 所有下载方法都失败")
        return None
                
    except Exception as e:
        logger.error(f"[VideoDownloader] 下载视频时出错: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None

