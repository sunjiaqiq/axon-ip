"""
ASCII 入口（避免 Windows/PowerShell 对中文文件名的兼容问题）：
调用 `test_截流爆款_评论筛选_私信评论.py` 中的逻辑。
"""

from __future__ import annotations

import sys
import runpy
from pathlib import Path


def main() -> int:
    here = Path(__file__).resolve().parent
    # 确保能 import `ai_pipeline.*`
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))

    target = here / "test_截流爆款_评论筛选_私信评论.py"
    runpy.run_path(str(target), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


