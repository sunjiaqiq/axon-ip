"""
链接解析模块 - 从文本中提取抖音等平台的视频链接
"""
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def extract_douyin_url(text: str) -> Optional[str]:
    """
    从文本中提取抖音视频链接
    
    Args:
        text: 包含链接的文本
        
    Returns:
        提取到的抖音视频链接，如果没有则返回None
    """
    logger.info(f"[LinkParser] 开始解析链接: {text[:100]}...")
    
    # 匹配抖音短链接模式（短链 slug 可能含 _ - 等字符，不能只匹配字母数字）
    patterns = [
        r'https?://v\.douyin\.com/[A-Za-z0-9_-]+/?',  # https://v.douyin.com/ZYux8xA_ArQ/
        r'https?://www\.douyin\.com/video/\d+',     # https://www.douyin.com/video/1234567890
        r'https?://m\.douyin\.com/video/\d+',       # https://m.douyin.com/video/1234567890
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text)
        if matches:
            url = matches[0].rstrip('/')
            logger.info(f"[LinkParser] 找到抖音链接: {url}")
            return url
    
    logger.warning("[LinkParser] 未找到有效的抖音链接")
    return None


def extract_video_url(text: str) -> Optional[str]:
    """
    通用视频链接提取（支持多个平台）
    
    Args:
        text: 包含链接的文本
        
    Returns:
        提取到的视频链接
    """
    # 先尝试抖音
    url = extract_douyin_url(text)
    if url:
        return url
    
    # 可以扩展其他平台
    # 快手、小红书等...
    
    return None







