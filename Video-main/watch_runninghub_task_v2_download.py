import os
import time
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp
from urllib.parse import urlparse


QUERY_URL = "https://www.runninghub.cn/openapi/v2/query"
OUTPUT_DIR = Path(r"C:\Users\Administrator\Desktop\1.27")
TASK_ID = "2037102887439572993"


def _extract_urls(results: Any) -> List[str]:
    """
    Extract downloadable urls from RunningHub v2 query results.
    We try multiple possible field names to be robust.
    """
    urls: List[str] = []
    if not isinstance(results, list):
        return urls

    for item in results:
        if not isinstance(item, dict):
            continue
        # Common keys seen in similar APIs
        for key in ["url", "fileUrl", "downloadUrl"]:
            v = item.get(key)
            if isinstance(v, str) and v.startswith("http"):
                urls.append(v)
                break

    return urls


async def _download_file(session: aiohttp.ClientSession, url: str, dest_path: Path) -> None:
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    async with session.get(url) as resp:
        resp.raise_for_status()
        with open(dest_path, "wb") as f:
            async for chunk in resp.content.iter_chunked(1024 * 256):
                if not chunk:
                    continue
                f.write(chunk)


async def main() -> None:
    api_key = os.getenv("RUNNINGHUB_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("RUNNINGHUB_API_KEY environment variable is required.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    payload: Dict[str, Any] = {"taskId": TASK_ID}
    payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    timeout = aiohttp.ClientTimeout(total=None)  # downloads manage their own time
    async with aiohttp.ClientSession(timeout=timeout) as session:
        last_status: Optional[str] = None
        start = time.time()
        print(f"[task {TASK_ID}] start polling {QUERY_URL}", flush=True)

        while True:
            async with session.post(QUERY_URL, data=payload_bytes, headers=headers) as resp:
                resp.raise_for_status()
                data = await resp.json()

            status = data.get("status", "")
            error_code = data.get("errorCode", "")
            error_msg = data.get("errorMessage", "")
            results = data.get("results")

            if status != last_status:
                elapsed = int(time.time() - start)
                print(f"[task {TASK_ID}] status={status} (elapsed={elapsed}s)", flush=True)
                if error_code or error_msg:
                    print(f"  errorCode={error_code} errorMessage={error_msg}", flush=True)
                last_status = status

            if status == "SUCCESS":
                urls = _extract_urls(results)
                if not urls:
                    print("SUCCESS but no downloadable urls found in results.", flush=True)
                    print(
                        "results keys:",
                        list(results[0].keys()) if isinstance(results, list) and results else "N/A",
                        flush=True,
                    )
                    return

                print(f"SUCCESS: found {len(urls)} url(s). Downloading to: {OUTPUT_DIR}", flush=True)

                downloaded = 0
                for i, url in enumerate(urls):
                    ext = Path(urlparse(url).path).suffix if "urlparse" in globals() else ""
                    if not ext:
                        # best-effort common video suffix
                        ext = ".mp4"
                    dest = OUTPUT_DIR / f"runninghub_{TASK_ID}_{i}{ext}"
                    print(f"  downloading {i+1}/{len(urls)}: {dest.name}", flush=True)
                    await _download_file(session, url, dest)
                    downloaded += 1

                print(f"Download complete: {downloaded} file(s).", flush=True)
                return

            if status == "FAILED":
                print(f"FAILED. errorCode={error_code} errorMessage={error_msg}")
                return

            # QUEUED / RUNNING
            await asyncio.sleep(3)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

