"""
豆包（火山方舟 OpenAI 兼容）最小客户端封装

系统内已有类似调用散落在 script_rewriter.py / compliance_checker.py；
这里抽出来方便“私信/评论/意向判定”等复用。
"""

from __future__ import annotations

import os
import time
import logging
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


DEFAULT_API_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
# 你们仓库里已有默认 key（测试用）；正式环境建议仅从环境变量/配置注入
DEFAULT_API_KEY = "5d24f49e-bec4-4af0-b527-015fef194fdb"

# 用户说的是“豆包1.8”，但不同环境模型名可能不同：
# - 若你们系统已配置 AI_MODEL，就优先用配置
# - 否则退回到你们现有脚本里能跑通的默认模型（seed-2.0 code preview）
DEFAULT_MODEL_FALLBACK = "doubao-seed-2-0-code-preview-260215"


def doubao_chat_completion(
    messages: List[Dict[str, str]],
    *,
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.7,
    timeout_s: int = 60,
    extra_headers: Optional[Dict[str, str]] = None,
) -> str:
    """
    调用豆包 chat.completions，返回 assistant 的 content 文本。
    """
    api_url = api_url or os.getenv("AI_API_URL", DEFAULT_API_URL)
    api_key = api_key or os.getenv("AI_API_KEY", DEFAULT_API_KEY)
    model = model or os.getenv("AI_MODEL", "") or DEFAULT_MODEL_FALLBACK

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    if extra_headers:
        headers.update(extra_headers)

    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }

    t0 = time.time()
    resp = requests.post(api_url, headers=headers, json=payload, timeout=timeout_s)
    dt = time.time() - t0
    if resp.status_code != 200:
        raise RuntimeError(f"豆包调用失败 status={resp.status_code} dt={dt:.2f}s body={resp.text[:800]}")

    data = resp.json()
    try:
        return (data["choices"][0]["message"]["content"] or "").strip()
    except Exception:
        raise RuntimeError(f"豆包返回结构异常 dt={dt:.2f}s data_keys={list(data.keys())}")





