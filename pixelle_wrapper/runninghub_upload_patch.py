# -*- coding: utf-8 -*-
"""
RunningHub 上传兼容补丁。

现象：部分新 Key（accountStatus 正常）调用旧接口 POST /task/openapi/upload
会返回 HTTP 401 ApiKey verification failed；新接口
POST /openapi/v2/media/upload/binary（Authorization: Bearer）可成功。

ComfyKit 0.1.x 仍走旧上传接口，导致 TTS/口播「上传本地文件失败」。
本补丁在运行时替换 RunningHubClient.upload_file：优先新接口，失败再回退旧接口。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PATCHED = False


async def _upload_file_v2_then_legacy(self, file_path: str) -> str:
    """优先 v2 Bearer 上传，失败再回退旧 apiKey 表单上传。"""
    import aiohttp

    if not Path(file_path).exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    filename = Path(file_path).name
    with open(file_path, "rb") as f:
        file_content = f.read()

    logger.info(f"[RH-Patch] Uploading via v2 first: {file_path}")

    # --- new API ---
    try:
        session = await self._get_session()
        form = aiohttp.FormData()
        form.add_field("file", file_content, filename=filename)
        url = f"{self.base_url}/openapi/v2/media/upload/binary"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with session.post(url, data=form, headers=headers) as response:
            text = await response.text()
            if response.status != 200:
                raise Exception(f"HTTP {response.status}: {text[:500]}")
            import json as _json

            result = _json.loads(text) if text else {}
            code = result.get("code")
            if code not in (0, "0", 200, "200"):
                raise Exception(
                    f"RunningHub v2 upload error: {result.get('msg') or result.get('message') or result}"
                )
            upload_data = result.get("data") or {}
            file_name = (
                upload_data.get("fileName")
                or upload_data.get("filename")
                or ""
            )
            if file_name:
                logger.info(f"[RH-Patch] v2 upload OK fileName={file_name}")
                return file_name
            file_url = upload_data.get("download_url") or upload_data.get("url") or ""
            if file_url:
                logger.warning(f"[RH-Patch] v2 no fileName, using URL")
                return file_url
            raise Exception(f"v2 upload missing fileName: {result}")
    except Exception as e:
        logger.warning(f"[RH-Patch] v2 upload failed, fallback to legacy: {e}")

    # --- legacy API ---
    data = {"apiKey": self.api_key}
    files = {"file": {"content": file_content, "filename": filename}}
    result = await self._make_request("POST", "/task/openapi/upload", data=data, files=files)
    upload_data = result.get("data", {}) or {}
    file_name = upload_data.get("fileName", "") or upload_data.get("filename", "")
    if file_name:
        logger.info(f"[RH-Patch] legacy upload OK fileName={file_name}")
        return file_name
    file_url = upload_data.get("url", "") or upload_data.get("download_url", "")
    if file_url:
        return file_url
    raise Exception("Neither fileName nor URL found in upload response")


def apply_runninghub_upload_patch() -> bool:
    """Idempotent monkeypatch. Returns True if patch applied/already on."""
    global _PATCHED
    if _PATCHED:
        return True
    try:
        from comfykit.comfyui.runninghub_client import RunningHubClient
    except Exception as e:
        logger.warning(f"[RH-Patch] comfykit not importable yet: {e}")
        return False

    # Avoid double-wrapping
    if getattr(RunningHubClient.upload_file, "__rh_upload_patched__", False):
        _PATCHED = True
        return True

    RunningHubClient.upload_file = _upload_file_v2_then_legacy  # type: ignore
    setattr(RunningHubClient.upload_file, "__rh_upload_patched__", True)
    _PATCHED = True
    logger.info("[RH-Patch] RunningHubClient.upload_file patched (v2 first)")
    print("[Wrapper] [OK] RunningHub 上传已切换为新接口（兼容新 API Key）")
    return True


def patch_comfykit_source_file(client_py: Path) -> bool:
    """Optional: rewrite installed runninghub_client.py on disk for pack/runtime_env."""
    if not client_py.is_file():
        return False
    text = client_py.read_text(encoding="utf-8")
    marker = "openapi/v2/media/upload/binary"
    if marker in text:
        return True
    # Lightweight: leave monkeypatch as primary; disk rewrite is best-effort via full replace of upload_file
    return False
