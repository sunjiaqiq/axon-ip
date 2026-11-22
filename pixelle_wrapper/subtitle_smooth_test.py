#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
丝滑模式智能测试：以「换行 = 稿的一段」为顶层 ASR 时间边界（少切段、更贴你写的段结构），
段内仍用 jieba + 单行字数 + 最大片长 与主流程一致。

用法（在 pixelle_wrapper 目录下）:
  py subtitle_smooth_test.py --video path\\to\\无字幕.mp4 --script path\\to\\script.txt
  py subtitle_smooth_test.py   # 使用下方 DEFAULT_* 默认路径（若存在）

说明：若 script 全文无换行，则顶层只有 1 个时间块，段内会再拆；多写换行可拉出多段顶层边界。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 与 burn 主模块同目录
_WRAPPER = Path(__file__).resolve().parent
if str(_WRAPPER) not in sys.path:
    sys.path.insert(0, str(_WRAPPER))

from subtitle_burner import (  # noqa: E402
    SUBTITLE_MAX_CHARS_PER_LINE,
    SUBTITLE_ONELINE_MAX_CHARS,
    SUBTITLE_MAX_CHUNK_DURATION_SEC,
    burn_subtitle_precomputed_segments,
    get_whisper_timestamps,
    segments_from_script_paragraph_asr_alignment,
    _split_script_into_paragraphs_only,
)


# 可选：填你的常用测试目录，命令行未指定时使用
DEFAULT_DIR = _WRAPPER / "output" / "20260327_091857_0454fe45"


def _default_paths():
    if not DEFAULT_DIR.is_dir():
        return None, None, None
    script = DEFAULT_DIR / "script.txt"
    if not script.exists():
        return None, None, None
    cands = sorted(
        DEFAULT_DIR.glob("*.mp4"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    out_name = DEFAULT_DIR / "smooth_test_output.mp4"

    def _is_burn_output(n: str) -> bool:
        ln = n.lower()
        return any(
            x in ln
            for x in (
                "smooth_test_output",
                "final_subtitle",
                "with_subtitle",
                "_preview",
                "pip_final",
            )
        )

    # 1) 明确叫「无字幕」的源片
    for p in cands:
        if "无字幕" in p.name:
            return p, script, out_name
    # 2) 排除明显是成片/测试输出，避免把上次的 smooth_test 再当输入
    for p in cands:
        if p.resolve() == out_name.resolve():
            continue
        if _is_burn_output(p.name):
            continue
        return p, script, out_name
    if cands:
        return cands[-1], script, out_name
    return None, None, None


def main() -> int:
    dv, ds, dout = _default_paths()
    ap = argparse.ArgumentParser(description="段落优先 ASR 对齐字幕丝滑测试")
    ap.add_argument("--video", type=str, default=str(dv) if dv else None, help="输入无字幕 mp4")
    ap.add_argument("--script", type=str, default=str(ds) if ds else None, help="script.txt")
    ap.add_argument(
        "--output",
        type=str,
        default=str(dout) if dout else None,
        help="输出路径，默认 smooth_test_output.mp4",
    )
    args = ap.parse_args()
    if not args.video or not args.script:
        print("请指定 --video 与 --script，或把 DEFAULT_DIR 指到含 script.txt 的目录。")
        return 1
    v, s, o = Path(args.video), Path(args.script), Path(args.output or (Path(args.video).parent / "smooth_test_output.mp4"))
    if not v.exists():
        print(f"视频不存在: {v}")
        return 1
    if not s.exists():
        print(f"文案不存在: {s}")
        return 1

    text = s.read_text(encoding="utf-8", errors="replace")
    paras = _split_script_into_paragraphs_only(text)
    print(
        f"[丝滑测试] 顶层稿段数（换行）: {len(paras)}；"
        f"ASR 对齐后时间戳捎入成片；每条≤{SUBTITLE_ONELINE_MAX_CHARS} 字不拆，"
        f"超过再按词拆（每行≤{SUBTITLE_MAX_CHARS_PER_LINE}）；"
        f"片长≤{SUBTITLE_MAX_CHUNK_DURATION_SEC}s"
    )
    for i, p in enumerate(paras[:12], 1):
        preview = (p[:36] + "…") if len(p) > 36 else p
        print(f"  段{i}: {preview}")
    if len(paras) > 12:
        print(f"  … 共 {len(paras)} 段")

    temp_dir = v.parent / "temp_subtitle_smooth_test"
    temp_dir.mkdir(parents=True, exist_ok=True)
    print(f"[丝滑测试] ASR 时间戳… temp={temp_dir}")
    asr = get_whisper_timestamps(v, temp_dir)
    if not asr:
        print("[丝滑测试] ASR 失败，无法对齐")
        return 2

    segs = segments_from_script_paragraph_asr_alignment(
        text, asr, max_line_chars=SUBTITLE_MAX_CHARS_PER_LINE
    )
    if not segs:
        print("[丝滑测试] 段落对齐结果为空")
        return 3

    print(f"[丝滑测试] ASR 原始段数: {len(asr)} → 字幕时间片数: {len(segs)}（段内已按词/时长拆分）")

    out = burn_subtitle_precomputed_segments(str(v), segs, str(o))
    if not out:
        return 4
    print(f"[丝滑测试] 完成: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
