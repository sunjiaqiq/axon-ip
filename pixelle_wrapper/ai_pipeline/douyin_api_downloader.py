"""
Douyin video download via TikTokDownloader Detail API + browser cookies.

Used when the legacy iesdouyin HTML/CDN path returns 404 or incomplete files.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/537.1"
)


def _find_tiktok_downloader_root() -> Optional[Path]:
    install = (os.environ.get("AXON_INSTALL_DIR") or "").strip()
    if install:
        candidate = Path(install) / "TikTokDownloader-master"
        if (candidate / "src" / "interface" / "detail.py").exists():
            return candidate
    here = Path(__file__).resolve()
    for base in (here.parents[2], here.parents[1]):
        for rel in ("TikTokDownloader-master", Path("downnn") / "TikTokDownloader-master"):
            candidate = base / rel
            if (candidate / "src" / "interface" / "detail.py").exists():
                return candidate
    return None


def load_douyin_cookie_str(cookies_path: Optional[Path] = None, *, sync_cache: bool = True) -> str:
    if cookies_path is not None:
        from ai_pipeline.douyin_cookie_store import _cookies_from_json

        data = _cookies_from_json(cookies_path)
        return "; ".join(f"{k}={v}" for k, v in data.items())

    from ai_pipeline.douyin_cookie_store import load_douyin_cookie_str as _load

    return _load(sync_cache=sync_cache)


def _resolve_aweme_id(share_link: str, cookie_str: str = "") -> str:
    headers = {"User-Agent": MOBILE_UA}
    if cookie_str:
        headers["Cookie"] = cookie_str
    resp = requests.get(share_link, headers=headers, allow_redirects=True, timeout=20)
    match = re.search(r"\b(\d{19})\b", resp.url)
    if match:
        return match.group(1)
    raise ValueError(f"无法从链接解析作品 ID: {share_link}")


def _collect_video_urls(aweme: dict) -> list[str]:
    video = aweme.get("video") or {}
    urls: list[str] = []
    for key in ("download_addr", "play_addr", "play_addr_h264"):
        addr = video.get(key) or {}
        for url in addr.get("url_list") or []:
            urls.append(url.replace("playwm", "play"))
    for br in video.get("bit_rate") or []:
        addr = br.get("play_addr") or {}
        for url in addr.get("url_list") or []:
            urls.append(url.replace("playwm", "play"))
    seen = set()
    out = []
    for url in urls:
        if url and url not in seen:
            seen.add(url)
            out.append(url)
    return out


def _download_urls_to_file(
    urls: list[str],
    dest: Path,
    *,
    aweme_id: str,
    cookie_str: str,
    min_bytes: int = 100_000,
) -> int:
    headers = {
        "User-Agent": MOBILE_UA,
        "Referer": f"https://www.douyin.com/video/{aweme_id}",
    }
    if cookie_str:
        headers["Cookie"] = cookie_str
    dest.parent.mkdir(parents=True, exist_ok=True)
    for url in urls:
        try:
            resp = requests.get(url, headers=headers, stream=True, timeout=120)
            if resp.status_code != 200:
                continue
            total = 0
            with dest.open("wb") as f:
                for chunk in resp.iter_content(65536):
                    if chunk:
                        f.write(chunk)
                        total += len(chunk)
            if total >= min_bytes:
                return total
            dest.unlink(missing_ok=True)
        except Exception as exc:
            logger.debug("[DouyinAPI] CDN try failed: %s", exc)
    return 0


async def _fetch_aweme_detail(aweme_id: str, cookie_str: str, tiktok_root: Path):
    if str(tiktok_root) not in sys.path:
        sys.path.insert(0, str(tiktok_root))
    from src.testers import Params
    from src.interface.detail import Detail

    async with Params() as params:
        params.cookie_str = cookie_str
        params.headers = dict(params.headers)
        params.headers["Cookie"] = cookie_str
        return await Detail(params, detail_id=aweme_id).run()


def fetch_aweme_from_link(
    share_link: str,
    *,
    cookies_path: Optional[Path] = None,
    aweme_id: Optional[str] = None,
) -> dict:
    """按分享链接 + Cookie 拉取作品详情（用于标题/ID，不下载文件）。"""
    tiktok_root = _find_tiktok_downloader_root()
    if not tiktok_root:
        raise RuntimeError("未找到 TikTokDownloader-master")
    cookie_str = load_douyin_cookie_str(cookies_path, sync_cache=True)
    if not cookie_str:
        raise RuntimeError("未找到 douyin.com Cookie")
    aweme_id = aweme_id or _resolve_aweme_id(share_link, cookie_str)
    aweme = asyncio.run(_fetch_aweme_detail(aweme_id, cookie_str, tiktok_root))
    if not aweme:
        raise RuntimeError(f"Detail API 未返回作品数据: {aweme_id}")
    desc = re.sub(r'[\\/:*?"<>|]', "_", ((aweme.get("desc") or "").strip() or f"douyin_{aweme_id}"))
    return {"video_id": aweme_id, "title": desc, "url": share_link, "aweme": aweme}


def download_douyin_video_api(
    share_link: str,
    output_dir: Path | str,
    *,
    cookies_path: Optional[Path] = None,
    aweme_id: Optional[str] = None,
) -> Path:
    """
    Download a Douyin share link using TikTokDownloader Detail API + cookies.
    Raises RuntimeError when download fails.
    """
    tiktok_root = _find_tiktok_downloader_root()
    if not tiktok_root:
        raise RuntimeError("未找到 TikTokDownloader-master，无法使用 Cookie API 下载")

    cookie_str = load_douyin_cookie_str(cookies_path, sync_cache=True)
    if not cookie_str:
        raise RuntimeError("未找到 douyin.com Cookie，请先在「设置」中登录抖音后再试")

    aweme_id = aweme_id or _resolve_aweme_id(share_link, cookie_str)
    aweme = asyncio.run(_fetch_aweme_detail(aweme_id, cookie_str, tiktok_root))
    if not aweme:
        raise RuntimeError(f"Detail API 未返回作品数据: {aweme_id}")

    urls = _collect_video_urls(aweme)
    if not urls:
        raise RuntimeError(f"Detail API 未返回可下载地址: {aweme_id}")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{aweme_id}.mp4"
    total = _download_urls_to_file(urls, dest, aweme_id=aweme_id, cookie_str=cookie_str)
    if total < 100_000:
        raise RuntimeError(f"Cookie API 下载失败或文件过小: {aweme_id} ({total} bytes)")
    logger.info("[DouyinAPI] 下载成功 %s (%d bytes)", aweme_id, total)
    return dest


def is_api_downloader_available() -> bool:
    from ai_pipeline.douyin_cookie_store import has_douyin_session

    return bool(_find_tiktok_downloader_root() and has_douyin_session())
