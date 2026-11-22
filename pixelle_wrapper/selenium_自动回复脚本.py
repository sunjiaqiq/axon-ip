# -*- coding: utf-8 -*-
"""已迁移：请使用 hf_auto_reply.py。本文件仅作兼容转发，避免旧路径/快捷方式失效。"""
from __future__ import annotations

import runpy
from pathlib import Path

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).resolve().parent / "hf_auto_reply.py"), run_name="__main__")
