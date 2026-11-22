#!/usr/bin/env python3
"""dist/Axon_Program 环境：测试客户反馈失败的抖音链接下载（含 Cookie API 兜底）。"""
import importlib.util
import json
import os
import sys
import time
import tempfile
from pathlib import Path

ROOT = Path(os.environ.get("AXON_INSTALL_DIR") or Path(__file__).resolve().parents[1]).resolve()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pixelle_wrapper"))
os.environ.setdefault("AXON_INSTALL_DIR", str(ROOT))

LINKS = [
    ("OK_GhMUN", "https://v.douyin.com/GhMUNerLaBY/"),
    ("FAIL_Nekf", "https://v.douyin.com/NekfVpwWIvM/"),
    ("FAIL_92ZO", "https://v.douyin.com/92ZOS1N5pgM/"),
    ("FAIL_z0f8", "https://v.douyin.com/z0f8bOQRCkE/"),
]

MCP = ROOT / "douyin-mcp-server-main" / "douyin-video" / "scripts" / "douyin_downloader.py"


def main() -> int:
    from ai_pipeline.douyin_cookie_store import has_douyin_session, load_douyin_cookies

    cookies = load_douyin_cookies(sync_cache=True)
    print(f"install={ROOT}")
    print(f"tiktok={ (ROOT / 'TikTokDownloader-master').exists() }")
    print(f"cookies={len(cookies)} session={has_douyin_session()}")

    spec = importlib.util.spec_from_file_location("douyin_dl", MCP)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    proc = mod.DouyinProcessor()
    out = Path(tempfile.mkdtemp(prefix="dist_douyin_test_"))
    results = []
    for name, link in LINKS:
        row = {"name": name, "link": link}
        try:
            path = mod.download_video(link, str(out))
            sz = path.stat().st_size
            row.update({"ok": sz > 100_000, "bytes": sz, "video_id": path.stem})
        except Exception as exc:
            row.update({"ok": False, "error": str(exc)[:300]})
        results.append(row)
        print(f"{name}: {'OK' if row.get('ok') else 'FAIL'} {row.get('bytes', 0)} {row.get('error', '')[:80]}")
        time.sleep(3)

    out_json = ROOT / "douyin_download_test_results.json"
    out_json.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"written {out_json}")
    return 0 if all(r.get("ok") for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
