"""
从系统内置 Chrome 用户目录读取 douyin.com Cookie，并缓存到 browser_data/cookies.json。

优先级：
1. 已打开的 Selenium 浏览器（douyin_publish_mcp.driver）
2. browser_data/cookies.json（Playwright / 上次同步）
3. browser_data/chrome_user_data/<Profile>/Cookies（Chrome SQLite，含解密）
"""
from __future__ import annotations

import base64
import json
import logging
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Dict, Optional

import yaml

logger = logging.getLogger(__name__)

DOUYIN_DOMAIN_MARKERS = ("douyin.com", "iesdouyin.com", "amemv.com")


def _wrapper_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def _browser_data_dir() -> Path:
    return _wrapper_dir() / "browser_data"


def _cookies_json_path() -> Path:
    return _browser_data_dir() / "cookies.json"


def _load_profile_name() -> str:
    cfg_path = _wrapper_dir() / "config.yaml"
    if not cfg_path.is_file():
        return "Profile 3"
    try:
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        return (cfg.get("browser") or {}).get("profile_directory") or "Profile 3"
    except Exception:
        return "Profile 3"


def _chrome_user_data_dir() -> Path:
    return _browser_data_dir() / "chrome_user_data"


def _chrome_encryption_key(local_state: Path) -> Optional[bytes]:
    if not local_state.is_file():
        return None
    try:
        import win32crypt  # pywin32

        state = json.loads(local_state.read_text(encoding="utf-8"))
        enc_key = base64.b64decode(state["os_crypt"]["encrypted_key"])
        return win32crypt.CryptUnprotectData(enc_key[5:], None, None, None, 0)[1]
    except Exception as exc:
        logger.debug("[DouyinCookie] 读取 Chrome 加密密钥失败: %s", exc)
        return None


def _decrypt_chrome_cookie(raw: bytes, key: Optional[bytes]) -> str:
    if not raw:
        return ""
    if raw[:3] in (b"v10", b"v11") and key:
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            nonce = raw[3:15]
            payload = raw[15:]
            return AESGCM(key).decrypt(nonce, payload, None).decode("utf-8", errors="replace")
        except Exception as exc:
            logger.debug("[DouyinCookie] AES 解密失败: %s", exc)
    try:
        import win32crypt

        return win32crypt.CryptUnprotectData(raw, None, None, None, 0)[1].decode(
            "utf-8", errors="replace"
        )
    except Exception:
        return ""


def _is_douyin_domain(domain: str) -> bool:
    domain = (domain or "").lstrip(".").lower()
    return any(m in domain for m in DOUYIN_DOMAIN_MARKERS)


def _cookies_from_selenium() -> Dict[str, str]:
    try:
        import sys

        wrapper = str(_wrapper_dir())
        if wrapper not in sys.path:
            sys.path.insert(0, wrapper)
        import douyin_publish_mcp as mcp

        drv = getattr(mcp, "driver", None)
        if drv is None:
            return {}
        try:
            drv.current_url
        except Exception:
            return {}
        out: Dict[str, str] = {}
        for c in drv.get_cookies():
            domain = c.get("domain", "")
            if _is_douyin_domain(domain):
                out[c["name"]] = c["value"]
        if out:
            logger.info("[DouyinCookie] 从 Selenium 浏览器读取 %d 个 Cookie", len(out))
        return out
    except Exception as exc:
        logger.debug("[DouyinCookie] Selenium Cookie 不可用: %s", exc)
        return {}


def _cookies_from_json(path: Path) -> Dict[str, str]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        out: Dict[str, str] = {}
        for item in data:
            domain = item.get("domain", "")
            if _is_douyin_domain(domain):
                out[item["name"]] = item["value"]
        return out
    except Exception as exc:
        logger.debug("[DouyinCookie] 读取 cookies.json 失败: %s", exc)
        return {}


def _cookies_from_chrome_sqlite() -> Dict[str, str]:
    user_data = _chrome_user_data_dir()
    profile = _load_profile_name()
    cookies_db = user_data / profile / "Cookies"
    if not cookies_db.is_file():
        return {}

    local_state = user_data / "Local State"
    enc_key = _chrome_encryption_key(local_state)

    tmp = Path(tempfile.mkdtemp(prefix="douyin_ck_"))
    copied = tmp / "Cookies"
    try:
        shutil.copy2(cookies_db, copied)
    except Exception as exc:
        logger.debug("[DouyinCookie] 复制 Chrome Cookies 失败（浏览器可能占用）: %s", exc)
        shutil.rmtree(tmp, ignore_errors=True)
        return {}

    out: Dict[str, str] = {}
    try:
        conn = sqlite3.connect(str(copied))
        cur = conn.cursor()
        cur.execute(
            "SELECT host_key, name, encrypted_value, value FROM cookies "
            "WHERE host_key LIKE '%douyin%' OR host_key LIKE '%iesdouyin%' OR host_key LIKE '%amemv%'"
        )
        for host_key, name, enc_val, plain_val in cur.fetchall():
            val = plain_val or ""
            if not val and enc_val:
                val = _decrypt_chrome_cookie(enc_val, enc_key)
            if val and name:
                out[name] = val
        conn.close()
    except Exception as exc:
        logger.debug("[DouyinCookie] 解析 Chrome Cookies 失败: %s", exc)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if out:
        logger.info("[DouyinCookie] 从 Chrome 用户目录读取 %d 个 Cookie", len(out))
    return out


def _write_cookies_json(cookie_dict: Dict[str, str]) -> None:
    if not cookie_dict:
        return
    path = _cookies_json_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    items = []
    for name, value in cookie_dict.items():
        items.append(
            {
                "name": name,
                "value": value,
                "domain": ".douyin.com",
                "path": "/",
            }
        )
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("[DouyinCookie] 已同步 %d 个 Cookie 到 %s", len(items), path)


def sync_tiktok_downloader_ini(cookie_dict: Dict[str, str], install_root: Optional[Path] = None) -> None:
    """写入 TikTokDownloader Volume/test_cookie.ini，便于其 Detail API 复用。"""
    if not cookie_dict:
        return
    roots = []
    if install_root:
        roots.append(install_root)
    here = Path(__file__).resolve()
    for base in (here.parents[2], here.parents[1]):
        roots.append(base)
    cookie_str = "; ".join(f"{k}={v}" for k, v in cookie_dict.items())
    uifid = cookie_dict.get("UIFID", cookie_dict.get("uifid", ""))
    mstoken = cookie_dict.get("msToken", "")
    for root in roots:
        ini = root / "TikTokDownloader-master" / "Volume" / "test_cookie.ini"
        if not (root / "TikTokDownloader-master" / "src").is_dir():
            continue
        ini.parent.mkdir(parents=True, exist_ok=True)
        ini.write_text(
            f"[dy]\ncookie = {cookie_str}\nuifid = {uifid}\nmstoken = {mstoken}\n\n"
            f"[tk]\ncookie = \nmstoken = \n",
            encoding="utf-8",
        )
        logger.debug("[DouyinCookie] 已写入 %s", ini)
        break


def load_douyin_cookies(*, sync_cache: bool = True) -> Dict[str, str]:
    """聚合读取 douyin Cookie；可选写回 cookies.json 与 TikTokDownloader ini。"""
    merged: Dict[str, str] = {}
    for source in (_cookies_from_json(_cookies_json_path()), _cookies_from_chrome_sqlite(), _cookies_from_selenium()):
        merged.update(source)

    if not merged:
        return {}

    if sync_cache:
        _write_cookies_json(merged)
        sync_tiktok_downloader_ini(merged)
    return merged


def load_douyin_cookie_str(*, sync_cache: bool = True) -> str:
    cookies = load_douyin_cookies(sync_cache=sync_cache)
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


def has_douyin_session() -> bool:
    cookies = load_douyin_cookies(sync_cache=False)
    if not cookies:
        return False
    # sessionid / sid_guard / ttwid 任一存在通常表示已登录
    keys = {k.lower() for k in cookies}
    return bool(keys & {"sessionid", "sid_guard", "sid_tt", "ttwid", "passport_csrf_token"})
