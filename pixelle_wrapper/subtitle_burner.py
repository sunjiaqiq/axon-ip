"""
字幕烧录模块 - 为视频添加动态字幕（根据语音时间戳同步显示）
字幕位置：底部居中
字幕样式：金色文字，28号字体，黑色边框
字幕内容：使用Whisper识别视频音频，获取精确时间戳，实现动态同步显示

【产品默认逻辑（2025-03 定版，勿随意改行为）】
- 定稿文案 + ASR：segments_from_script_proportional_to_asr_segments（仅 Whisper「段」级时间轴，
  不按词切碎；失败才回退 difflib 字级对齐）。
- 屏显：≤SUBTITLE_ONELINE_MAX_CHARS 字一条；超过再 jieba 拆行（≤SUBTITLE_MAX_CHARS_PER_LINE）。
- 依赖：jieba（requirements 已列）；勿删。
"""
import os
import sys
import subprocess
from pathlib import Path
from typing import Optional, List, Tuple

try:
    from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip, TextClip
    from PIL import Image, ImageDraw, ImageFont
    import numpy as np
    MOVIEPY_AVAILABLE = True
    PIL_AVAILABLE = True
except ImportError:
    MOVIEPY_AVAILABLE = False
    PIL_AVAILABLE = False

# 一条时间戳内：≤SUBTITLE_ONELINE_MAX_CHARS 字不拆屏（一条字幕一条时间片）；超过再按词拆到至多 SUBTITLE_MAX_CHARS_PER_LINE。
# jieba 在词边界内组行，不硬切词。
SUBTITLE_ONELINE_MAX_CHARS = 10
SUBTITLE_MAX_CHARS_PER_LINE = 12
# 口播文案队列与时间窗对齐时的估算（字/秒），仅用于从队列取字，不用于把行压成 5～8 字那种碎条
SUBTITLE_CHARS_PER_SEC_ESTIMATE = 4.5
# 口型优先：默认走 ASR 时间轴（并可用硅基纠错文本），不强制按整稿重铺时间
SUBTITLE_PREFER_ASR_TIMELINE = True

# 同一条时间片内若仍偏长，再按时长细分时，每小条最长停留（秒）；过短会闪得太快。
SUBTITLE_MAX_CHUNK_DURATION_SEC = 2.0

# 添加 Whisper 路径
# current_dir 是项目根目录（shuziren/）
current_dir = Path(__file__).parent.parent
project_root = current_dir  # 项目根目录
whisper_path = project_root / "whisper-main"
if whisper_path.exists():
    sys.path.insert(0, str(whisper_path))

# 配置FFmpeg路径（Whisper需要FFmpeg）
def find_ffmpeg_path():
    """查找FFmpeg可执行文件路径"""
    import shutil
    
    # 优先级1: 优先检查项目内的env/ffmpeg/ffmpeg.exe
    env_ffmpeg = project_root / "env" / "ffmpeg" / "ffmpeg.exe"
    if env_ffmpeg.exists():
        return str(env_ffmpeg.parent)
    
    # 优先级2: 检查系统PATH
    ffmpeg_cmd = shutil.which("ffmpeg")
    if ffmpeg_cmd:
        return str(Path(ffmpeg_cmd).parent)
    
    # 优先级3: 检查常见位置（包括剪映等软件的FFmpeg）
    common_paths = [
        project_root / "pixelle_wrapper" / "ffmpeg" / "bin" / "ffmpeg.exe",
        Path("C:\\ffmpeg\\bin\\ffmpeg.exe"),
        Path("C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe"),
        Path("C:\\Program Files (x86)\\ffmpeg\\bin\\ffmpeg.exe"),
        Path.home() / "ffmpeg" / "bin" / "ffmpeg.exe",
    ]
    
    for path in common_paths:
        if path.exists():
            return str(path.parent)
    
    return None

# 将FFmpeg路径添加到PATH环境变量
ffmpeg_dir = find_ffmpeg_path()
if ffmpeg_dir:
    current_path = os.environ.get("PATH", "")
    if ffmpeg_dir not in current_path:
        os.environ["PATH"] = ffmpeg_dir + os.pathsep + current_path
        print(f"[字幕] 已配置FFmpeg路径: {ffmpeg_dir}")
else:
    print("[字幕] 警告: 未找到FFmpeg，Whisper可能无法正常工作")

try:
    import whisper
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False
    whisper = None

try:
    from ai_pipeline.audio_extractor import extract_audio_from_video
    AUDIO_EXTRACTOR_AVAILABLE = True
except ImportError:
    AUDIO_EXTRACTOR_AVAILABLE = False


def _find_whisper_cpp() -> tuple[Optional[Path], Optional[Path]]:
    """
    查找 whisper.cpp 的可执行文件与模型文件。
    约定打包后放在：
      - {root}/tools/whispercpp/whisper-cli.exe
      - {root}/tools/whispercpp/models/ggml-base.bin
    """
    root = project_root
    tools = root / "tools" / "whispercpp"
    # 优先使用 Release 目录内的 whisper-cli.exe（与其 DLL 同目录，最不容易缺 dll）
    exe = tools / "Release" / "whisper-cli.exe"
    if not exe.exists():
        # 次优先：上一级（如果打包时把 dll 复制到了 tools\whispercpp\）
        exe = tools / "whisper-cli.exe"
    if not exe.exists():
        # 兼容：有些包里可能叫 main.exe / whisper.exe（避免硬崩）
        for cand in ["whisper-cli.exe", "main.exe", "whisper.exe"]:
            for c in [tools / cand, tools / "Release" / cand]:
                if c.exists():
                    exe = c
                    break
            if exe.exists():
                break
    model = tools / "models" / "ggml-base.bin"
    if not model.exists():
        # 兼容其它模型名
        for cand in ["ggml-small.bin", "ggml-tiny.bin", "ggml-base.bin"]:
            c = root / "tools" / "whispercpp" / "models" / cand
            if c.exists():
                model = c
                break
    return (exe if exe.exists() else None, model if model.exists() else None)


def _whispercpp_timestamps(audio_path: Path, temp_dir: Path) -> Optional[List[dict]]:
    """使用 whisper.cpp 生成 segment 时间戳（start/end），返回 whisper 风格 segments。"""
    exe, model = _find_whisper_cpp()
    if not exe or not model:
        print(f"[字幕] whisper.cpp 不可用：exe={exe} model={model}")
        return None

    temp_dir.mkdir(parents=True, exist_ok=True)
    out_prefix = temp_dir / "whispercpp"
    out_json = Path(str(out_prefix) + ".json")

    # whisper.cpp 更偏好 WAV，先转 16k mono wav（用我们已带的 ffmpeg）
    wav_path = temp_dir / "whispercpp_16k.wav"
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-i", str(audio_path), "-ar", "16000", "-ac", "1", str(wav_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        if r.returncode != 0 or not wav_path.exists():
            print("[字幕] whisper.cpp: WAV 转换失败，回退其他方案")
            print(f"[字幕][whisper.cpp][ffmpeg] returncode={r.returncode}")
            out = (r.stderr or r.stdout or "").strip()
            if out:
                for line in out.splitlines()[:10]:
                    print("[字幕][whisper.cpp][ffmpeg]", line)
            return None
    except Exception as e:
        print(f"[字幕] whisper.cpp: WAV 转换异常: {e}")
        return None

    try:
        # -oj 输出 json；-of 指定输出前缀
        # 强制中文识别，避免客户机出现英文字幕
        # -ng：禁用 GPU 后端；客户机常见无独显/驱动异常，避免 whisper 走 GPU 初始化路径
        cmd = [
            str(exe),
            "-m",
            str(model),
            "-f",
            str(wav_path),
            "-l",
            "zh",
            "-ng",
            "-oj",
            "-of",
            str(out_prefix),
        ]
        rr = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        if rr.returncode != 0 or not out_json.exists():
            print("[字幕] whisper.cpp: 运行失败，输出如下（截断）：")
            print(f"[字幕][whisper.cpp] cmd={' '.join(map(str, cmd))}")
            print(f"[字幕][whisper.cpp] returncode={rr.returncode}")
            # Windows: 0xC0000135 (-1073741515) = STATUS_DLL_NOT_FOUND，多为未装/损坏的 VC++ 2015-2022 x64
            if rr.returncode in (-1073741515, 3221225781):
                print(
                    "[字幕][whisper.cpp] 检测到 0xC0000135（缺 DLL）：请运行安装目录下的 vc_redist.x64.exe 安装/修复后重试。"
                )
            out = (rr.stderr or rr.stdout or "").strip()
            if not out:
                print("[字幕][whisper.cpp] (无输出) 可能原因：缺少 VC++ 运行库 / 文件被杀软拦截 / 被系统安全策略阻止")
                print("[字幕][whisper.cpp] 建议：重新运行安装包（会自动装 VC++ 2015-2022 x64）并确保安装目录已解锁（Unblock）")
            for line in out.splitlines()[:20]:
                print("[字幕][whisper.cpp]", line)
            # 额外：帮助确认 json 是否写到别的目录
            try:
                if wav_path.exists():
                    print(f"[字幕][whisper.cpp] wav_path={wav_path} size={wav_path.stat().st_size}")
            except Exception:
                pass
            return None

        import json
        raw = out_json.read_text(encoding="utf-8", errors="ignore")
        if not raw.strip():
            print("[字幕] whisper.cpp: json 输出为空，回退其他方案")
            return None
        data = json.loads(raw)
        segs: List[dict] = []

        # whisper.cpp 输出结构（不同版本可能略有差异）：
        # - { "transcription": [ { "timestamps": { "from":"00:00:00,000","to":"00:00:02,000" }, "text": "..." } ] }
        # - { "transcription": [ { "offsets": { "from":0,"to":2000 }, "text": "..." } ] }
        # - 也可能在外层是 segments/start/end 等
        items = data.get("transcription", []) or data.get("segments", []) or []
        for s in items:
            start = end = None

            # 1) 直接 start/end
            if "start" in s and "end" in s:
                start, end = float(s["start"]), float(s["end"])

            # 2) t0/t1（centiseconds）
            if start is None and "t0" in s and "t1" in s:
                start, end = float(s["t0"]) / 100.0, float(s["t1"]) / 100.0

            # 3) timestamps: {from/to}（格式 HH:MM:SS,mmm）
            if start is None and isinstance(s.get("timestamps"), dict):
                ts = s.get("timestamps") or {}
                f = ts.get("from")
                t = ts.get("to")
                if f and t:
                    start, end = srt_time_to_seconds(str(f)), srt_time_to_seconds(str(t))

            # 4) offsets: {from/to}（通常是毫秒）
            if start is None and isinstance(s.get("offsets"), dict):
                off = s.get("offsets") or {}
                f = off.get("from")
                t = off.get("to")
                if f is not None and t is not None:
                    start, end = float(f) / 1000.0, float(t) / 1000.0

            if start is None or end is None:
                continue

            segs.append({"start": float(start), "end": float(end), "text": (s.get("text") or "").strip()})
        if segs:
            print(f"[字幕] whisper.cpp 时间戳获取成功: {len(segs)} 段")
        return segs or None
    except Exception as e:
        print(f"[字幕] whisper.cpp 解析失败: {e}")
        return None

# 硅基流动语音识别（与 test_subtitle 一致：时间戳+按段识别，去标点去表情）
SILICONFLOW_TRANSCRIPTION_URL = "https://api.siliconflow.cn/v1/audio/transcriptions"
SILICONFLOW_ASR_MODEL = "FunAudioLLM/SenseVoiceSmall"
SILICONFLOW_SEGMENT_TIMEOUT_SEC = 240  # 规机/硅基单段识别超时（3-5 分钟建议：180~300）

# 字幕段密度兜底：当 whisper.cpp 切分过粗（例如只出 6 段）时，做一次轻量二次切分
# 目标：约 25 段/分钟（允许波动），避免极端“段数过少导致看不了”的效果
TARGET_SEGMENTS_PER_MIN = 25
MIN_SEGMENTS_PER_MIN_BEFORE_SPLIT = 18
MAX_SEGMENTS_PER_MIN_AFTER_SPLIT = 38


def _load_siliconflow_api_key():
    """从 config.yaml 或环境变量读取硅基 API Key"""
    key = os.environ.get("API_KEY", "").strip()
    if key:
        return key
    try:
        import yaml
        cfg = Path(__file__).parent / "config.yaml"
        if cfg.exists():
            with open(cfg, "r", encoding="utf-8") as f:
                c = yaml.safe_load(f)
            if c and isinstance(c.get("siliconflow"), dict):
                key = (c["siliconflow"].get("api_key") or "").strip()
                if key:
                    return key
    except Exception:
        pass
    return ""


def _sanitize_subtitle_text(text):
    """去标点、去表情，只保留中文/英文/数字（与 test_subtitle 一致）"""
    if not text:
        return ""
    import re
    text = re.sub(r"[\U0001F300-\U0001F9FF\U0001F600-\U0001F64F\U0001F1E0-\U0001F1FF]", "", text)
    text = re.sub(r"[\uFFFD\u25A0-\u25FF\u2600-\u26FF\u2700-\u27BF]", "", text)
    text = re.sub(r"[\u200B-\u200D\uFEFF\u2060]", "", text)
    text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", text)
    text = re.sub(r"[，。！？、；：""''（）【】《》\s,.\!?;:\"'\(\)\[\]\s\u3000]", "", text)
    return text.strip()


def _sanitize_subtitle_text_keep_punct(text: str) -> str:
    """
    硅基纠错后：用于“按标点切句/半句”的中间文本。
    去乱码/控制字符/表情，但保留中文标点（。，！？、；：等），供后续分句使用。
    """
    if not text:
        return ""
    import re
    text = re.sub(r"[\U0001F300-\U0001F9FF\U0001F600-\U0001F64F\U0001F1E0-\U0001F1FF]", "", text)
    text = re.sub(r"[\uFFFD\u25A0-\u25FF\u2600-\u26FF\u2700-\u27BF]", "", text)
    text = re.sub(r"[\u200B-\u200D\uFEFF\u2060]", "", text)
    text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", text)
    # 不删中文/英文常见标点，只清理空白
    text = re.sub(r"\s+", "", text)
    return text.strip()


def _split_text_into_sentence_or_half_units(text: str, max_unit_chars: int = SUBTITLE_ONELINE_MAX_CHARS) -> List[str]:
    """
    输入为“保留标点”的文本：切成“整句优先，超长再按逗号/分号切半句”，并确保每个 unit 用于上屏时 <= max_unit_chars。
    """
    import re
    raw = (text or "").strip()
    if not raw:
        return []

    # 1) 先按“句号类”切成句子块（保留句末标点）
    sentence_blocks = re.split(r"(?<=[。！？!?])", raw)
    sentence_blocks = [b for b in (x.strip() for x in sentence_blocks) if b]

    units: List[str] = []
    for sb in sentence_blocks:
        # 评估上屏长度（去标点后）
        disp_len = len(_strip_punctuation_for_display(sb))
        if disp_len <= max_unit_chars:
            units.append(sb)
            continue

        # 2) 句子太长：按“逗号/顿号/分号/冒号”切半句
        half_parts = re.split(r"(?<=[，、；：,;:])", sb)
        half_parts = [p for p in (x.strip() for x in half_parts) if p]
        if not half_parts:
            half_parts = [sb]

        cur = ""
        for p in half_parts:
            if not cur:
                cur = p
                continue
            if len(_strip_punctuation_for_display(cur + p)) <= max_unit_chars:
                cur += p
            else:
                units.append(cur)
                cur = p
        if cur:
            units.append(cur)

    # 3) 最后再做一遍“防碎”：unit 过短就并回前一个
    out: List[str] = []
    for u in units:
        uu = (u or "").strip()
        if not uu:
            continue
        if out and len(_strip_punctuation_for_display(uu)) < 2:
            out[-1] = out[-1] + uu
        else:
            out.append(uu)
    # 4) 确保最大长度约束：不允许“硬截丢字”，超长用 jieba 再拆成多条 unit
    final: List[str] = []
    for u in out:
        disp = _strip_punctuation_for_display(u)
        disp = (disp or "").strip()
        if not disp:
            continue
        if len(disp) <= max_unit_chars:
            final.append(disp)
            continue
        lines = _pack_words_to_lines(disp, max_unit_chars)
        lines = _merge_tiny_tail_lines(lines, min_chars=2)
        final.extend([x for x in lines if x])
    return [x for x in (z.strip() for z in final) if x]


def _split_text_evenly(text: str, n_parts: int) -> List[str]:
    """把文本均匀切成 n_parts 段（不引入标点）。"""
    text = (text or "").strip()
    if n_parts <= 1:
        return [text]
    if not text:
        return [""] * n_parts
    # 均分字符数，保证最后一段吃掉余量
    total = len(text)
    base = max(1, total // n_parts)
    parts: List[str] = []
    idx = 0
    for i in range(n_parts):
        if i == n_parts - 1:
            parts.append(text[idx:].strip())
        else:
            parts.append(text[idx:idx + base].strip())
        idx += base
    # 去空：若出现空段，用相邻段补一点（避免后续被“空文本过滤”吞掉）
    for i in range(len(parts)):
        if parts[i]:
            continue
        # 尝试从前一段匀一点
        if i > 0 and len(parts[i - 1]) > 1:
            parts[i] = parts[i - 1][-1:]
            parts[i - 1] = parts[i - 1][:-1]
        elif i + 1 < len(parts) and len(parts[i + 1]) > 1:
            parts[i] = parts[i + 1][:1]
            parts[i + 1] = parts[i + 1][1:]
    return parts


def _densify_segments_if_too_few(segments: List[dict], total_duration: float) -> List[dict]:
    """
    当 whisper.cpp 自动切分段数过少时，把“长段”按时长窗口拆细。
    - 不强制写死成固定段数；只在过少时触发，且限制最大密度
    - 尽量同步拆分 seg['text']（若为空也不阻塞）
    """
    if not segments or total_duration <= 0:
        return segments
    # 估算当前密度（段/分钟）
    seg_per_min = len(segments) / max(1e-6, (total_duration / 60.0))
    if seg_per_min >= MIN_SEGMENTS_PER_MIN_BEFORE_SPLIT:
        return segments

    target_total = int(round((total_duration / 60.0) * TARGET_SEGMENTS_PER_MIN))
    target_total = max(len(segments), target_total)
    max_total = int(round((total_duration / 60.0) * MAX_SEGMENTS_PER_MIN_AFTER_SPLIT))
    max_total = max(target_total, max_total)

    # 理想窗口（秒/段）
    ideal_win = total_duration / max(1, target_total)
    ideal_win = max(1.2, min(3.2, ideal_win))  # 防止太碎或太粗
    print(f"[字幕] whisper.cpp 段数偏少（{len(segments)} 段，{seg_per_min:.1f}段/分钟），启用二次切分兜底：目标≈{TARGET_SEGMENTS_PER_MIN}段/分钟，窗口≈{ideal_win:.2f}s")

    out: List[dict] = []
    for seg in segments:
        try:
            s = float(seg.get("start", 0))
            e = float(seg.get("end", s))
            if e <= s:
                continue
            dur = e - s
            # 拆分数量：长于 ideal_win 才拆
            n = int((dur / ideal_win) + 0.9999)
            n = max(1, min(6, n))  # 单段最多拆 6 份，避免极端爆炸
            # 若整体已经接近上限，停止拆分
            if len(out) >= max_total:
                break
            if n == 1:
                out.append(seg)
                continue

            texts = _split_text_evenly(str(seg.get("text") or ""), n)
            piece = dur / n
            for i in range(n):
                ss = s + i * piece
                ee = e if i == n - 1 else (s + (i + 1) * piece)
                out.append({"start": ss, "end": ee, "text": (texts[i] or "").strip()})
                if len(out) >= max_total:
                    break
        except Exception:
            out.append(seg)

    return out or segments


def _cut_audio_segment(ffmpeg_exe, full_audio_path, start_sec, duration_sec, output_path):
    """按时间段截取音频片段"""
    try:
        cmd = [
            ffmpeg_exe,
            "-y", "-i", str(full_audio_path),
            "-ss", str(start_sec), "-t", str(duration_sec),
            "-acodec", "libmp3lame", "-q:a", "0", str(output_path),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
        return r.returncode == 0 and Path(output_path).exists()
    except Exception:
        return False


def _transcribe_segment_siliconflow(audio_path, api_key, api_url=None, model=None):
    """硅基 SenseVoice 转录单段音频，返回识别文本"""
    api_url = api_url or SILICONFLOW_TRANSCRIPTION_URL
    model = model or SILICONFLOW_ASR_MODEL
    try:
        import requests
        with open(audio_path, "rb") as f:
            # 方案A：强化纠错提示（不改时间戳，只提升文字准确率）
            prompt = (
                "你是专业的中文听写与校对。请把这段口播转成清晰、规范的简体中文。"
                "要求：1) 严格纠正错别字、同音字；2) 不要乱码/生僻错误组合/无意义重复；"
                "3) 允许并保留中文标点（。，！？、；：），但不要输出多余解释；"
                "4) 只输出最终正文。"
            )
            files = {
                "file": (Path(audio_path).name, f, "audio/mpeg"),
                "model": (None, model),
                "prompt": (None, prompt),
                "temperature": (None, "0"),
                # 强制中文，避免返回英文
                "language": (None, "zh"),
            }
            headers = {"Authorization": f"Bearer {api_key}"}
            resp = requests.post(api_url, files=files, headers=headers, timeout=SILICONFLOW_SEGMENT_TIMEOUT_SEC)
        resp.raise_for_status()
        return (resp.json().get("text") or "").strip()
    except Exception:
        return ""


def _fill_segments_with_siliconflow(segments, full_audio_path, temp_dir, ffmpeg_exe, api_key):
    """
    用硅基按段识别填充 segments 的 text；不改变 start/end。
    成功返回 True，失败返回 False（调用方可回退到原逻辑）。
    """
    if not full_audio_path or not Path(full_audio_path).exists() or not segments or not api_key:
        return False
    segments_dir = Path(temp_dir) / "segments_silicon"
    segments_dir.mkdir(parents=True, exist_ok=True)
    try:
        import difflib
        import re

        def _looks_bad_text(text_keep_punct: str, orig_text: str, dur_s: float) -> bool:
            """硅基输出质量闸门：可疑则回退到原 Whisper 文本（不改 start/end）。"""
            t = (text_keep_punct or "").strip()
            if not t:
                return True
            disp = _strip_punctuation_for_display(t)
            if not disp:
                return True
            # 太短：长时间片却只有一两个字，通常是漏识别
            if dur_s >= 0.8 and len(disp) < 3:
                return True
            # 过度重复（像“哈哈哈哈”“呃呃呃呃”这种）
            if re.search(r"(.)\1{4,}", disp):
                return True
            # 非中英文数字占比过高（异常符号）
            bad = re.findall(r"[^\u4e00-\u9fffA-Za-z0-9]", disp)
            if len(bad) / max(1, len(disp)) > 0.15:
                return True
            # 与原 Whisper 差异过大时谨慎：宁可不改也不改坏
            o = _strip_punctuation_for_display(orig_text or "")
            if o:
                ratio = difflib.SequenceMatcher(a=o, b=disp, autojunk=False).ratio()
                if ratio < 0.22 and abs(len(disp) - len(o)) > max(4, int(0.6 * len(o))):
                    return True
            return False

        for i, seg in enumerate(segments):
            start = float(seg.get("start", 0))
            end = float(seg.get("end", start + 0.1))
            duration = max(0.01, end - start)
            seg_audio = segments_dir / f"seg_{i:04d}.mp3"
            if _cut_audio_segment(ffmpeg_exe, full_audio_path, start, duration, seg_audio):
                orig_text = str(seg.get("text") or "")
                text = _transcribe_segment_siliconflow(seg_audio, api_key)
                text = _sanitize_subtitle_text_keep_punct(text)
                if text and not _looks_bad_text(text, orig_text, duration):
                    seg["text"] = text
            if not seg.get("text"):
                seg["text"] = _sanitize_subtitle_text_keep_punct(seg.get("text") or "") or f"[{i+1}]"
        return True
    except Exception as e:
        print(f"[字幕] 硅基按段识别失败: {e}")
        return False


def srt_time_to_seconds(srt_time):
    """将SRT时间格式转换为秒数"""
    srt_time = srt_time.replace(',', '.')
    parts = srt_time.split(':')
    hours = int(parts[0])
    minutes = int(parts[1])
    seconds = float(parts[2])
    return hours * 3600 + minutes * 60 + seconds


def format_srt_time(seconds):
    """将秒数转换为SRT时间格式 (HH:MM:SS,mmm)"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def get_whisper_timestamps(video_path: Path, temp_dir: Path) -> Optional[List[dict]]:
    """
    使用Whisper识别视频音频，获取带时间戳的segments（仅用于时间戳，不用于文字）
    
    Returns:
        segments列表，每个segment包含: {'start': float, 'end': float, 'text': str}
        注意：text字段会被忽略，实际字幕文字使用原始文案
    """
    # 优先使用 whisper.cpp（避免 torch 在客户机上 DLL 初始化失败）
    # 若 whisper.cpp 缺失，再回退到 python whisper（仅开发机/可控环境建议）
    
    # 在调用 Whisper 之前，先检测一次 FFmpeg 是否可用，方便排查问题
    try:
        print("[字幕] 检测 FFmpeg 是否可用...")
        ffmpeg_check = subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if ffmpeg_check.returncode == 0:
            print("[字幕] FFmpeg 检测通过，版本信息如下（前几行）：")
            for line in ffmpeg_check.stdout.splitlines()[:3]:
                print("[字幕][FFmpeg]", line)
        else:
            print(f"[字幕] FFmpeg 检测失败，退出码: {ffmpeg_check.returncode}")
            # 打印少量错误信息帮助定位
            for line in ffmpeg_check.stderr.splitlines()[:5]:
                print("[字幕][FFmpeg 错误]", line)
    except FileNotFoundError:
        print("[字幕] 未在 PATH 中找到 ffmpeg 可执行文件，Whisper 可能会报错（请检查 env/ffmpeg 或系统 PATH 配置）")
    except Exception as e:
        print(f"[字幕] 检测 FFmpeg 时出错: {e}")
    
    try:
        print("[字幕] 开始提取视频音频...")
        # 提取音频
        audio_path = None
        if AUDIO_EXTRACTOR_AVAILABLE:
            audio_path = extract_audio_from_video(str(video_path), temp_dir)
        
        # 如果提取失败，直接使用视频文件（Whisper可以直接处理视频）
        if not audio_path or not Path(audio_path).exists():
            audio_path = str(video_path)
            print("[字幕] 音频提取失败，直接使用视频文件进行识别")
        else:
            print(f"[字幕] 音频提取成功: {audio_path}")
        
        # 1) whisper.cpp
        ts = None
        try:
            ts = _whispercpp_timestamps(Path(audio_path), temp_dir)
        except Exception as e:
            print(f"[字幕] whisper.cpp 时间戳调用异常: {e}")
            ts = None
        if ts:
            return ts

        # 2) python whisper fallback（可用时兜底）
        if not WHISPER_AVAILABLE:
            print("[字幕] whisper.cpp 时间戳获取失败（且 python whisper 不可用），已使用均匀分配降级方案")
            return None

        print("[字幕] whisper.cpp 时间戳获取失败，回退 python whisper（可能较慢且依赖 torch）...")
        print("[字幕] 加载Whisper模型（base模型）...")
        model = whisper.load_model("base")
        print("[字幕] 开始识别音频，获取段级时间戳（不按词切字幕）...")
        result = model.transcribe(
            str(audio_path), language="zh", task="transcribe", word_timestamps=False
        )
        segments = result.get("segments", [])
        print(f"[字幕] 识别完成，获取到 {len(segments)} 个时间段")
        return segments
        
    except Exception as e:
        print(f"[字幕] Whisper识别失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def create_dynamic_subtitle_clips(
    segments: List[dict],
    video_width: int,
    video_height: int,
    script_text: str = "",
) -> List:
    """
    根据Whisper返回的时间戳和原始文案创建动态字幕片段（单行显示，精准跳转）
    
    Args:
        segments: Whisper返回的segments列表，每个包含 {'start': float, 'end': float, 'text': str}
                 注意：只使用start和end时间戳，text字段会被忽略
        video_width: 视频宽度
        video_height: 视频高度
        script_text: 原始文案内容（用于字幕文字，而不是Whisper识别出的文字）
    
    Returns:
        字幕片段列表
    """
    if not MOVIEPY_AVAILABLE or not PIL_AVAILABLE:
        print("[字幕] MoviePy或PIL未安装，无法创建字幕")
        return []
    
    subtitle_clips = []
    # 字幕字号：人物口播页可读性优先（抖音 UI 会进一步压缩视觉高度）
    # 1080x1920 建议 52~58；这里按高度自适应给更大字号。
    font_size = 56 if video_height >= 1800 else (50 if video_height >= 1400 else 44)
    max_width = int(video_width * 0.9)  # 字幕宽度为视频的90%
    
    # 尝试加载字体
    try:
        font_paths = [
            "C:/Windows/Fonts/simhei.ttf",  # 黑体
            "C:/Windows/Fonts/msyh.ttc",     # 微软雅黑
            "C:/Windows/Fonts/simsun.ttc",   # 宋体
        ]
        font = None
        for fp in font_paths:
            if os.path.exists(fp):
                font = ImageFont.truetype(fp, font_size)
                break
        if font is None:
            font = ImageFont.load_default()
    except:
        font = ImageFont.load_default()
    
    # 计算单行高度
    line_height = int(font_size * 1.5)
    img_height = line_height + 20  # 上下留白
    # 距底边抬高（多行），减少被抖音底部 UI 遮挡
    y_position = video_height - img_height - 140
    
    print(f"[字幕] 开始创建字幕片段...")
    use_original_text = bool(script_text and script_text.strip())
    if use_original_text:
        print(f"[字幕] 使用原始文案作为字幕内容，Whisper仅用于时间戳")
    else:
        print(f"[字幕] 使用识别文本作为字幕内容")
    print(f"[字幕] 单行显示，精准跳转")
    
    chars_per_line = SUBTITLE_MAX_CHARS_PER_LINE
    print(
        f"[字幕] 展示: 以时间戳条数为准；每条≤{SUBTITLE_ONELINE_MAX_CHARS} 字整句一条；"
        f"超过再按词拆行（每行≤{chars_per_line}），避免碎字"
    )

    def split_by_punctuation(text, max_chars):
        """
        按标点符号分段，每段不超过max_chars字
        规则：
        1. 优先按句号、问号、感叹号分段（一句话一段）
        2. 如果一句话超过max_chars，再按逗号分段
        3. 移除所有标点符号（不显示在字幕中）
        4. 确保一句话完整，不要一句话后面还有零星的字
        """
        import re
        
        # 先按句号、问号、感叹号分段（一句话一段）
        sentence_endings = ['。', '！', '？', '.', '!', '?']
        sentences = []
        current_sentence = ""
        
        for char in text:
            current_sentence += char
            if char in sentence_endings:
                sentences.append(current_sentence.strip())
                current_sentence = ""
        
        # 添加最后一段（如果没有句号结尾）
        if current_sentence.strip():
            sentences.append(current_sentence.strip())
        
        segments_list = []
        
        for sentence in sentences:
            # 移除句末标点符号
            sentence = sentence.rstrip('。！？.!?')
            
            # 如果一句话超过max_chars，按逗号分段
            if len(sentence) <= max_chars:
                # 一句话可以完整显示
                # 移除所有标点符号
                clean_sentence = re.sub(r'[，,。！？、；：;:\.!?]', '', sentence)
                if clean_sentence.strip():
                    segments_list.append(clean_sentence.strip())
            else:
                # 一句话太长，需要按逗号分段
                # 但要确保每段都是完整的，不要有零星的字
                comma_marks = ['，', ',']
                parts = []
                current_part = ""
                
                # 先找到所有逗号位置
                comma_positions = []
                for i, char in enumerate(sentence):
                    if char in comma_marks:
                        comma_positions.append(i)
                
                # 如果没有逗号，直接按max_chars强制分段
                if not comma_positions:
                    clean_sentence = re.sub(r'[，,。！？、；：;:\.!?]', '', sentence)
                    while len(clean_sentence) > max_chars:
                        parts.append(clean_sentence[:max_chars])
                        clean_sentence = clean_sentence[max_chars:]
                    if clean_sentence.strip():
                        parts.append(clean_sentence.strip())
                else:
                    # 按逗号分段，但要确保最后一段不会太短
                    last_end = 0
                    for i, comma_pos in enumerate(comma_positions):
                        # 从上一个逗号到当前逗号
                        part_text = sentence[last_end:comma_pos]
                        clean_part = re.sub(r'[，,。！？、；：;:\.!?]', '', part_text).strip()
                        
                        if clean_part:
                            # 检查是否是最后一段
                            is_last = (i == len(comma_positions) - 1)
                            remaining_text = sentence[comma_pos + 1:]
                            remaining_clean = re.sub(r'[，,。！？、；：;:\.!?]', '', remaining_text).strip()
                            
                            # 如果当前段+剩余段不超过max_chars，合并（避免最后一段太短）
                            if is_last and remaining_clean:
                                combined = clean_part + remaining_clean
                                if len(combined) <= max_chars:
                                    parts.append(combined)
                                    break
                            
                            # 如果当前段不超过max_chars，添加
                            if len(clean_part) <= max_chars:
                                parts.append(clean_part)
                            else:
                                # 当前段太长，需要进一步分段
                                while len(clean_part) > max_chars:
                                    parts.append(clean_part[:max_chars])
                                    clean_part = clean_part[max_chars:]
                                if clean_part.strip():
                                    parts.append(clean_part)
                        
                        last_end = comma_pos + 1
                    
                    # 处理最后一段（逗号之后的内容）
                    if last_end < len(sentence):
                        remaining_text = sentence[last_end:]
                        remaining_clean = re.sub(r'[，,。！？、；：;:\.!?]', '', remaining_text).strip()
                        if remaining_clean:
                            # 如果最后一段太短（少于5个字），合并到前一段
                            if len(remaining_clean) < 5 and parts:
                                parts[-1] = parts[-1] + remaining_clean
                            elif len(remaining_clean) <= max_chars:
                                parts.append(remaining_clean)
                            else:
                                # 最后一段太长，强制分段
                                while len(remaining_clean) > max_chars:
                                    parts.append(remaining_clean[:max_chars])
                                    remaining_clean = remaining_clean[max_chars:]
                                if remaining_clean.strip():
                                    parts.append(remaining_clean)
                
                segments_list.extend(parts)
        
        return segments_list
    
    if use_original_text:
        # 清理原始文案（去掉 emoji/异常符号，避免出现“特别的字儿”）
        clean_text = _sanitize_subtitle_text(script_text.strip().replace('\n', '').replace('\r', ''))

        # 先按标点符号将整个文案分成短句（每句不超过 chars_per_line，且不显示标点）
        text_parts = split_by_punctuation(clean_text, chars_per_line)

        # 现在不做“把 parts 强行拟合到 segments 数量”的重切分，
        # 而是：时间戳保持不动；每个时间窗按时长动态取字数（上限 SUBTITLE_MAX_CHARS_PER_LINE）。
        if not segments:
            segments = [{'start': 0, 'end': 0, 'text': ''}]  # 占位符
    else:
        # 降级方案：使用Whisper识别出的文字
        text_parts = [segment.get('text', '').strip() for segment in segments]
    
    print(f"[字幕] 文案分段数: {len(text_parts)}, 时间片段数: {len(segments)}")
    
    # 使用队列分配字幕片段到每个时间窗
    text_parts_queue = list(text_parts) if use_original_text else []

    for i, segment in enumerate(segments):
        start_time = segment['start']
        end_time = segment['end']
        duration = end_time - start_time
        
        if duration <= 0:
            continue

        # 队列与时间窗对齐：单次至少取 SUBTITLE_ONELINE_MAX_CHARS（避免按秒估成 5～6 字把句切碎）
        desired_max_chars = max(
            SUBTITLE_ONELINE_MAX_CHARS,
            min(chars_per_line, int(duration * SUBTITLE_CHARS_PER_SEC_ESTIMATE)),
        )

        if use_original_text:
            if not text_parts_queue:
                text = ""
            else:
                part = (text_parts_queue[0] or "").strip()
                if not part:
                    text_parts_queue.pop(0)
                    text = ""
                elif len(part) <= desired_max_chars:
                    text = part
                    text_parts_queue.pop(0)
                else:
                    text = part[:desired_max_chars].strip()
                    rest = part[desired_max_chars:].strip()
                    text_parts_queue[0] = rest
        else:
            text = segment.get('text', '').strip()
        
        if not text:
            continue
        
        try:
            # Whisper/硅基路径：按“句/半句”切单位，每个单位 <= SUBTITLE_ONELINE_MAX_CHARS
            units = _split_text_into_sentence_or_half_units(text, max_unit_chars=SUBTITLE_ONELINE_MAX_CHARS)
            if not units:
                units = [text]
            sub_dur = duration / max(1, len(units))

            for li, unit in enumerate(units):
                if not (unit or "").strip():
                    continue
                display_text = _strip_punctuation_for_display(unit).strip()
                if not display_text:
                    continue
                t0 = start_time + li * sub_dur

                # 创建单行文字图片
                img = Image.new('RGBA', (max_width, img_height), (0, 0, 0, 0))
                draw = ImageDraw.Draw(img)

                y_offset = img_height // 2  # 垂直居中

                # 先绘制黑色描边（多次偏移模拟描边，描边宽度2）
                for dx in [-3, -2, -1, 0, 1, 2, 3]:
                    for dy in [-3, -2, -1, 0, 1, 2, 3]:
                        if dx != 0 or dy != 0:
                            draw.text((max_width//2 + dx, y_offset + dy), display_text,
                                     font=font, fill=(0, 0, 0, 255), anchor='mm')

                # 再绘制金色文字
                draw.text((max_width//2, y_offset), display_text,
                         font=font, fill=(255, 215, 0, 255), anchor='mm')  # #FFD700 = 255,215,0

                # 转换为numpy数组
                img_array = np.array(img)

                # 创建视频片段（根据实际时间戳设置开始时间和持续时间）
                clip = ImageClip(img_array, duration=sub_dur)
                clip = clip.set_start(t0)
                clip = clip.set_position(('center', y_position))

                subtitle_clips.append(clip)

            if (i + 1) % 10 == 0:
                print(f"[字幕] 已处理 {i + 1}/{len(segments)} 个时间片...")

        except Exception as e:
            print(f"[字幕] 创建字幕片段 {i+1} 失败: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    print(f"[字幕] 字幕片段创建完成，共 {len(subtitle_clips)} 个")
    return subtitle_clips


def _normalize_script_whitespace(text: str) -> str:
    """去掉用空格当停顿的情况，便于按标点分段。"""
    import re
    return re.sub(r"\s+", "", (text or "").strip())


def _strip_punctuation_for_display(text: str) -> str:
    """字幕显示文本：去标点、去空白，只保留可读正文。"""
    import re
    t = (text or "").strip()
    # 去掉中文/英文常见标点
    t = re.sub(r"[，。！？、；：,.!?;:\"'“”‘’（）()【】\[\]《》<>—…·]", "", t)
    # 去掉所有空白
    t = re.sub(r"\s+", "", t)
    return t.strip()


_jieba_status_logged = False


def _jieba_cut_words(text: str) -> List[str]:
    """中文分词；无 jieba 时退化为单字列表（仅作兜底）。"""
    global _jieba_status_logged
    t = (text or "").strip()
    if not t:
        return []
    try:
        import jieba
        import logging

        try:
            jieba.setLogLevel(logging.ERROR)
        except Exception:
            pass
        if not _jieba_status_logged:
            print("[字幕] 已启用 jieba 按词边界拆行（词语/成语尽量不断开）")
            _jieba_status_logged = True
        return [w.strip() for w in jieba.cut(t) if w and w.strip()]
    except Exception as e:
        if not _jieba_status_logged:
            print(f"[字幕] jieba 不可用（{e}），退化为按字拆行；请 pip install jieba")
            _jieba_status_logged = True
        return list(t)


def _pack_words_to_lines(text: str, max_chars: int) -> List[str]:
    """
    按词语边界组行，避免「词被拦腰切断」。
    单行超长词（极少见）才按字硬切。
    """
    words = _jieba_cut_words(text)
    if not words:
        return []
    lines: List[str] = []
    cur: List[str] = []
    cur_len = 0
    for w in words:
        if len(w) > max_chars:
            if cur:
                lines.append("".join(cur))
                cur = []
                cur_len = 0
            for i in range(0, len(w), max_chars):
                lines.append(w[i : i + max_chars])
            continue
        if cur_len + len(w) <= max_chars:
            cur.append(w)
            cur_len += len(w)
        else:
            if cur:
                lines.append("".join(cur))
            cur = [w]
            cur_len = len(w)
    if cur:
        lines.append("".join(cur))
    return lines


def _merge_tiny_tail_lines(lines: List[str], min_chars: int = 2) -> List[str]:
    """避免末行只剩 1 个字等过短条，合并到上一行。"""
    if not lines:
        return []
    out: List[str] = []
    for raw in lines:
        line = (raw or "").strip()
        if not line:
            continue
        if out and len(line) < min_chars:
            out[-1] = out[-1] + line
        else:
            out.append(line)
    return out


def _display_lines_for_subtitle_text(text: str) -> List[str]:
    """一条时间戳对应文案：≤10 字一条不拆；>10 再按词拆行（每行≤12），不按时长压成碎字。"""
    t = (text or "").strip()
    if not t:
        return []
    if len(t) <= SUBTITLE_ONELINE_MAX_CHARS:
        return [t]
    lines = _pack_words_to_lines(t, SUBTITLE_MAX_CHARS_PER_LINE)
    lines = _merge_tiny_tail_lines(lines, min_chars=2)
    return lines if lines else [t]


def _split_words_into_n_time_chunks(text: str, n: int) -> List[str]:
    """按词均分到 n 段时间片，避免按字比例切导致词被拆开。"""
    words = _jieba_cut_words(text)
    if not words:
        return [text] if text else []
    n = max(1, int(n))
    # 片数多于词数时：每词一条，避免空片
    if n >= len(words):
        return [w for w in words]
    if n <= 1:
        return ["".join(words)]
    chunks: List[str] = []
    total = len(words)
    start_idx = 0
    for i in range(n):
        if i == n - 1:
            end_idx = total
        else:
            end_idx = int(round((i + 1) * total / n))
        end_idx = max(start_idx, min(end_idx, total))
        part = "".join(words[start_idx:end_idx])
        if part:
            chunks.append(part)
        start_idx = end_idx
    return chunks if chunks else ["".join(words)]


def _split_script_into_semantic_parts(text: str) -> List[str]:
    """
    先按文案段落切分；若没有明显段落，再按句号类标点切分。
    产出的每段文本用于“先分段 -> 再铺时间戳”的第一步。
    """
    import re
    raw = (text or "").strip()
    if not raw:
        return []

    # 1) 优先按换行段落切（文案有几段就先几段）
    paras = [p.strip() for p in re.split(r"(?:\r?\n)+", raw) if p and p.strip()]
    if len(paras) > 1:
        return paras

    # 2) 无换行时，按句号类标点切分为“语义段”
    compact = _normalize_script_whitespace(raw)
    if not compact:
        return []
    parts = re.split(r"(?<=[。！？!?])", compact)
    parts = [p.strip() for p in parts if p and p.strip()]
    return parts if parts else [compact]


def _assign_proportional_times(parts: List[str], total_duration: float) -> List[dict]:
    lengths = [max(1, len(p)) for p in parts]
    ssum = float(sum(lengths))
    segs: List[dict] = []
    t = 0.0
    for i, p in enumerate(parts):
        dur = total_duration * (lengths[i] / ssum)
        if i == len(parts) - 1:
            end = total_duration
        else:
            end = min(total_duration, t + dur)
        segs.append({"start": t, "end": end, "text": p})
        t = end
    return segs


def _split_segment_if_over_chars(seg: dict, max_chars: int = SUBTITLE_MAX_CHARS_PER_LINE) -> List[dict]:
    """
    同一句内：≤SUBTITLE_ONELINE_MAX_CHARS 字不拆，保持一条时间片一条字幕；
    超过再按 jieba 拆到每行≤max_chars，避免按字硬切出单字条。
    """
    st, en, tx = float(seg["start"]), float(seg["end"]), str(seg.get("text", "") or "")
    tx = _strip_punctuation_for_display(tx)
    if not tx:
        return []
    if len(tx) <= SUBTITLE_ONELINE_MAX_CHARS:
        return [{"start": st, "end": en, "text": tx}]
    lines = _pack_words_to_lines(tx, max_chars)
    lines = _merge_tiny_tail_lines(lines, min_chars=2)
    if not lines:
        return [{"start": st, "end": en, "text": tx}]
    n = len(lines)
    span = max(0.0, en - st)
    out: List[dict] = []
    for i, chunk in enumerate(lines):
        a = st + span * (i / n)
        b = st + span * ((i + 1) / n) if i < n - 1 else en
        out.append({"start": a, "end": b, "text": chunk})
    return out


def _split_segment_if_over_duration(seg: dict, max_duration_sec: float = SUBTITLE_MAX_CHUNK_DURATION_SEC) -> List[dict]:
    """同一小句在时间上过长时再细分（不跨句）；按词切分时间片，避免字中断词。"""
    st = float(seg.get("start", 0.0))
    en = float(seg.get("end", 0.0))
    tx = _strip_punctuation_for_display(str(seg.get("text", "") or ""))
    dur = max(0.0, en - st)
    if dur <= max_duration_sec or len(tx) <= 2:
        return [{"start": st, "end": en, "text": tx}]

    n = max(2, int(np.ceil(dur / max_duration_sec)))
    parts = _split_words_into_n_time_chunks(tx, n)
    if not parts:
        return [{"start": st, "end": en, "text": tx}]
    span = dur
    out: List[dict] = []
    m = len(parts)
    for i in range(m):
        a = st + span * (i / m)
        b = st + span * ((i + 1) / m) if i < m - 1 else en
        out.append({"start": a, "end": b, "text": parts[i]})
    return out if out else [{"start": st, "end": en, "text": tx}]


def _build_asr_weighted_rows(asr_segments: List[dict]) -> List[Tuple[float, float, float]]:
    """
    构造 (start, end, weight)，仅使用 Whisper「段」级时间轴，绝不按词拆条。
    若按词拆会把稿切成一字一条，观感极差；口型对齐用段级已足够。
    weight = 该段识别字数（无字则用时长），用于把定稿按比例摊到各段。
    """
    rows: List[Tuple[float, float, float]] = []
    for s in asr_segments or []:
        try:
            st = float(s.get("start", 0.0))
            en = float(s.get("end", 0.0))
            if en <= st:
                continue
            tx = _strip_punctuation_for_display(str(s.get("text", "") or ""))
            wt = float(max(1, len(tx))) if tx else max(0.05, en - st)
            rows.append((st, en, wt))
        except Exception:
            continue
    return rows


def segments_from_script_proportional_to_asr_segments(
    script_text: str,
    asr_segments: List[dict],
    max_line_chars: int = SUBTITLE_MAX_CHARS_PER_LINE,
) -> List[dict]:
    """
    按 Whisper「段」级时间轴铺定稿：每条 start/end 与 ASR 段一致，稿按段权重比例切分。
    不使用词级时间，避免字幕一字一蹦。
    """
    script_clean = _strip_punctuation_for_display(script_text)
    if not script_clean:
        return []
    rows = _build_asr_weighted_rows(asr_segments)
    if not rows:
        return []
    tw = sum(r[2] for r in rows)
    if tw <= 0:
        return []
    total = len(script_clean)
    out: List[dict] = []
    pos = 0
    for i, (st, en, w) in enumerate(rows):
        if i == len(rows) - 1:
            take = total - pos
        else:
            take = int(round(total * (w / tw)))
            take = min(max(0, take), total - pos)
        chunk = script_clean[pos : pos + take]
        pos += take
        if not chunk.strip():
            continue
        for piece in _split_segment_if_over_chars({"start": st, "end": en, "text": chunk}, max_line_chars):
            out.append(piece)
    if pos < total and out:
        last = out[-1]
        last["text"] = (last.get("text") or "") + script_clean[pos:]
    return out


def segments_from_full_script_single_audio(
    script_text: str, total_duration: float, max_line_chars: int = SUBTITLE_MAX_CHARS_PER_LINE
) -> List[dict]:
    """
    整段口播、单条音频：
    1) 先按“文案段落/语义句”得到 N 段；
    2) 再按字数比例铺 [0, duration] 时间戳；
    3) 每段超过 max_line_chars 字再切分；
    4) 最终字幕文本不带标点。
    """
    parts = _split_script_into_semantic_parts(script_text)
    # 显示时去标点，避免“字幕里出现标点符号”
    parts = [_strip_punctuation_for_display(p) for p in parts]
    parts = [p for p in parts if p]
    if not parts:
        return []
    timed = _assign_proportional_times(parts, float(total_duration))
    final: List[dict] = []
    for seg in timed:
        final.extend(_split_segment_if_over_chars(seg, max_line_chars))
    return final


def segments_from_script_with_asr_alignment(
    script_text: str, asr_segments: List[dict], max_line_chars: int = SUBTITLE_MAX_CHARS_PER_LINE
) -> List[dict]:
    """
    备用：difflib 字级匹配稿与识别流，再插值时间（识别与稿差异大时易漂移）。
    主流程优先用 segments_from_script_proportional_to_asr_segments（Whisper 时间戳直铺）。
    """
    sentences = _split_script_into_semantic_parts(script_text)
    sentences = [_strip_punctuation_for_display(x) for x in sentences]
    sentences = [x for x in sentences if x]
    if not sentences:
        return []

    # 1) 把 ASR 切片展开成“字符时间流”
    asr_chars: List[str] = []
    asr_times: List[float] = []
    asr_start, asr_end = None, None
    for s in asr_segments or []:
        try:
            st = float(s.get("start", 0.0))
            en = float(s.get("end", 0.0))
            if en <= st:
                continue
            tx = _strip_punctuation_for_display(str(s.get("text", "") or ""))
            if not tx:
                continue
            if asr_start is None:
                asr_start = st
            asr_end = en
            n = len(tx)
            span = max(1e-6, en - st)
            for i, ch in enumerate(tx):
                asr_chars.append(ch)
                # 字符中心时间
                t = st + span * ((i + 0.5) / n)
                asr_times.append(t)
        except Exception:
            continue
    if not asr_chars or not asr_times:
        return []

    # 2) 脚本字符流（按句拼起来），记录每句边界
    script_sent_starts: List[int] = []
    script_sent_ends: List[int] = []
    script_chars = []
    pos = 0
    for sent in sentences:
        script_sent_starts.append(pos)
        script_chars.extend(list(sent))
        pos += len(sent)
        script_sent_ends.append(pos)
    if not script_chars:
        return []

    # 3) 用 SequenceMatcher 做字符级单调匹配，得到 script_idx -> time
    import difflib
    sm = difflib.SequenceMatcher(a=script_chars, b=asr_chars, autojunk=False)
    idx_to_time = {}
    for blk in sm.get_matching_blocks():
        ai, bi, size = blk.a, blk.b, blk.size
        if size <= 0:
            continue
        for k in range(size):
            si = ai + k
            bj = bi + k
            if 0 <= bj < len(asr_times):
                idx_to_time[si] = asr_times[bj]

    # 4) 对未匹配字符做邻域插值（保证每个字符都有时间）
    total_script = len(script_chars)
    if total_script == 0:
        return []
    # 前后最近匹配下标
    prev_match = [-1] * total_script
    last = -1
    for i in range(total_script):
        if i in idx_to_time:
            last = i
        prev_match[i] = last
    next_match = [-1] * total_script
    last = -1
    for i in range(total_script - 1, -1, -1):
        if i in idx_to_time:
            last = i
        next_match[i] = last

    start_t = asr_start if asr_start is not None else asr_times[0]
    end_t = asr_end if asr_end is not None else asr_times[-1]
    for i in range(total_script):
        if i in idx_to_time:
            continue
        li, ri = prev_match[i], next_match[i]
        if li != -1 and ri != -1 and ri != li:
            lt, rt = idx_to_time[li], idx_to_time[ri]
            r = (i - li) / float(ri - li)
            idx_to_time[i] = lt + (rt - lt) * r
        elif li != -1:
            idx_to_time[i] = idx_to_time[li]
        elif ri != -1:
            idx_to_time[i] = idx_to_time[ri]
        else:
            idx_to_time[i] = start_t + (end_t - start_t) * (i / max(1, total_script - 1))

    # 5) 严格按“句边界”取时间，再句内切分（绝不跨句）
    out: List[dict] = []
    last_end = start_t
    for sent, s_idx, e_idx in zip(sentences, script_sent_starts, script_sent_ends):
        if not sent:
            continue
        st = float(idx_to_time.get(s_idx, last_end))
        en = float(idx_to_time.get(max(s_idx, e_idx - 1), st)) + 0.05
        st = max(last_end, st)
        if en <= st:
            en = st + 0.15
        for piece in _split_segment_if_over_chars({"start": st, "end": en, "text": sent}, max_line_chars):
            out.append(piece)
        last_end = en
    return out


def _split_script_into_paragraphs_only(text: str) -> List[str]:
    """
    仅按换行切段（丝滑测试 / 稿段驱动）：有几段换行就有几段顶层时间边界。
    若全文无换行，则整篇视为 1 段（不再按句号切碎顶层）。
    """
    import re

    raw = (text or "").strip()
    if not raw:
        return []
    paras = [p.strip() for p in re.split(r"(?:\r?\n)+", raw) if p and p.strip()]
    if len(paras) > 1:
        out = [_normalize_script_whitespace(p) for p in paras]
        return [p for p in out if p]
    compact = _normalize_script_whitespace(raw)
    return [compact] if compact else []


def segments_from_script_paragraph_asr_alignment(
    script_text: str, asr_segments: List[dict], max_line_chars: int = SUBTITLE_MAX_CHARS_PER_LINE
) -> List[dict]:
    """
    丝滑测试：与主流程一致，按 Whisper 段/词时间轴比例铺稿（口型与识别时间一致）。
    """
    return segments_from_script_proportional_to_asr_segments(
        script_text, asr_segments, max_line_chars=max_line_chars
    )


def burn_subtitle_precomputed_segments(
    video_path: str,
    segments: List[dict],
    output_path: str,
) -> Optional[str]:
    """
    将已含 text/start/end 的 segments 烧录进视频（不跑 ASR）。
    每条用时间戳 [start,end] 捎入画面；屏上展示见 _display_lines_for_subtitle_text。
    """
    if not MOVIEPY_AVAILABLE or not PIL_AVAILABLE:
        print("[字幕] MoviePy或PIL未安装，无法添加字幕")
        return None
    try:
        vp = Path(video_path)
        if not vp.exists():
            print(f"[字幕] 视频文件不存在: {video_path}")
            return None
        out = str(Path(output_path))
        video = VideoFileClip(str(vp))
        if not segments:
            video.close()
            return None
        print(
            f"[字幕] 预计算时间戳捎入: 共 {len(segments)} 条；"
            f"每条≤{SUBTITLE_ONELINE_MAX_CHARS} 字一条，超过再按词拆（每行≤{SUBTITLE_MAX_CHARS_PER_LINE}）"
        )
        subtitle_clips = create_dynamic_subtitle_clips(segments, video.w, video.h, script_text="")
        if not subtitle_clips:
            video.close()
            return None
        print(f"[字幕] 合成视频和字幕（预计算时间轴）...")
        final_video = CompositeVideoClip([video] + subtitle_clips)
        print(f"[字幕] 开始渲染视频（这可能需要一些时间）...")
        final_video.write_videofile(
            out,
            codec="libx264",
            audio_codec="aac",
            fps=video.fps,
            preset="medium",
            bitrate="8000k",
            logger=None,
        )
        video.close()
        final_video.close()
        for clip in subtitle_clips:
            clip.close()
        print(f"[字幕] 动态字幕添加成功: {out}")
        return out
    except Exception as e:
        print(f"[字幕] burn_subtitle_precomputed_segments 出错: {e}")
        import traceback

        traceback.print_exc()
        return None


def _densify_segments_to_min_count(segments: List[dict], min_count: int) -> List[dict]:
    """
    强制把时间戳段数扩到 >= min_count。
    原因：whisper.cpp 有时会切得过粗（段数过少），导致字幕对口型体验很差。
    做法：优先拆分“时长最长”的段；拆分时同步把 text 按字符大致二分。
    """
    if not segments or min_count <= 0:
        return segments
    segs = []
    for s in segments:
        try:
            segs.append(
                {
                    "start": float(s.get("start", 0.0)),
                    "end": float(s.get("end", 0.0)),
                    "text": str(s.get("text", "") or ""),
                }
            )
        except Exception:
            continue

    def _duration(x: dict) -> float:
        return max(0.0, float(x["end"]) - float(x["start"]))

    # 仅保留有效时长段
    segs = [s for s in segs if _duration(s) > 0]
    if len(segs) >= min_count:
        return segs

    # 循环拆分最长段直到满足
    # 防止死循环：最多拆到 4x
    hard_cap = max(min_count, len(segs) * 4)
    while len(segs) < min_count and len(segs) < hard_cap:
        # 找最长段
        idx = max(range(len(segs)), key=lambda i: _duration(segs[i]))
        s = segs[idx]
        d = _duration(s)
        # 太短就不拆了
        if d < 0.35:
            break
        mid = float(s["start"]) + d / 2.0
        t = (s.get("text") or "").strip()
        if t:
            cut = max(1, len(t) // 2)
            t1 = t[:cut].strip()
            t2 = t[cut:].strip()
        else:
            t1, t2 = "", ""
        s1 = {"start": float(s["start"]), "end": mid, "text": t1}
        s2 = {"start": mid, "end": float(s["end"]), "text": t2}
        # 替换
        segs.pop(idx)
        segs.insert(idx, s2)
        segs.insert(idx, s1)

    return segs


def _compute_subtitle_segments_core(
    video,
    video_path: Path,
    script_text: str,
    temp_dir: Path,
):
    """Whisper+硅基+纠错+densify；不关闭 video、不删 temp。"""
    duration = float(video.duration or 0.0)
    # =============================
    # 字幕主流程（简化版，按需求固定）
    # 1) Whisper 仅负责时间戳
    # 2) 硅基接口仅负责纠错文本
    # 3) 直接烧录，不走文案铺轴/对齐的复杂分支
    # =============================
    script_stripped = (script_text or "").strip()
    script_clean_for_fix = _strip_punctuation_for_display(script_stripped) if script_stripped else ""
    segments = get_whisper_timestamps(video_path, temp_dir)
    if segments:
        api_key = _load_siliconflow_api_key()
        if api_key:
            full_audio = temp_dir / f"{video_path.stem}.mp3"
            if not full_audio.exists():
                if AUDIO_EXTRACTOR_AVAILABLE and extract_audio_from_video:
                    try:
                        full_audio = Path(extract_audio_from_video(str(video_path), temp_dir))
                    except Exception:
                        full_audio = None
            if not full_audio or not Path(full_audio).exists():
                full_audio = video_path.parent / "narration.mp3"
            ffmpeg_exe = (
                str(Path(ffmpeg_dir) / "ffmpeg.exe")
                if ffmpeg_dir and os.name == "nt"
                else (str(Path(ffmpeg_dir) / "ffmpeg") if ffmpeg_dir else None)
            )
            if full_audio and Path(full_audio).exists() and ffmpeg_exe and _fill_segments_with_siliconflow(segments, full_audio, temp_dir, ffmpeg_exe, api_key):
                print("[字幕] 已使用硅基二次识别/纠错填充字幕文字（时间戳来自 Whisper）")

        # 错别字专项：不动时间戳/断句，只对明显错字做 script 局部窗口校对（等长替换，避免口型漂）
        if script_clean_for_fix:
            try:
                import difflib
                import re

                def _looks_like_typo(disp: str) -> bool:
                    d = (disp or "").strip()
                    if not d:
                        return False
                    # 常见错别字触发词（可继续加）
                    if "霍客" in d or "过客" in d:
                        return True
                    if "抽口播" in d:
                        return True
                    # 出现明显不通顺组合（粗判：含“霍”且含“客”但不含“获客”）
                    if ("霍" in d and "客" in d and "获客" not in d):
                        return True
                    # 连续重复字太多也容易是识别错误
                    if re.search(r"(.)\1{4,}", d):
                        return True
                    return False

                # 逐段局部窗口匹配：同长度替换（不增删字）
                ref = script_clean_for_fix
                ref_pos = 0
                for seg in segments:
                    tx = str(seg.get("text") or "").strip()
                    disp = _strip_punctuation_for_display(tx)
                    if not disp:
                        continue
                    if not _looks_like_typo(disp):
                        ref_pos = min(len(ref), ref_pos + len(disp))
                        continue
                    n = len(disp)
                    if n <= 0 or n > len(ref):
                        continue
                    # 在 ref_pos 附近找最相似窗口（半径更大，允许纠错）
                    radius = 120
                    lo = max(0, ref_pos - radius)
                    hi = min(len(ref) - n, ref_pos + radius)
                    best_i = lo
                    best_r = -1.0
                    for i in range(lo, hi + 1):
                        cand = ref[i : i + n]
                        r = difflib.SequenceMatcher(a=disp, b=cand, autojunk=False).ratio()
                        if r > best_r:
                            best_r = r
                            best_i = i
                    best = ref[best_i : best_i + n]
                    # 只在相似度足够且能明显消除错字触发时替换
                    if best_r >= 0.55 and best and ("霍客" not in best and "抽口播" not in best):
                        seg["text"] = best  # 保持等长、时间戳不动
                        ref_pos = best_i + n
                    else:
                        ref_pos = min(len(ref), ref_pos + n)
            except Exception as e:
                print(f"[字幕] script 错别字校对失败（忽略）: {e}")
        try:
            segments = _densify_segments_if_too_few(segments, float(duration))
        except Exception:
            pass
        try:
            segments = _densify_segments_to_min_count(segments, 28)
        except Exception:
            pass
    
    if not segments:
        print("[字幕] 无法获取语音时间戳，使用文案文本均匀分配时间（降级方案）")
        # 降级方案：如果 Whisper 失败，才用文案均匀分配
        text = script_stripped.replace('\n', ' ').replace('\r', '')
        
        # 计算每行能显示的最大字符数（保守估计18字）
        font_size = 28
        max_width = int(video.w * 0.9)
        chars_per_line = min(18, int(max_width / (font_size * 0.9)))
        
        # 优先使用标点符号分段
        def split_by_punctuation(text, max_chars):
            """按标点符号分段，每段不超过max_chars字"""
            segments_list = []
            current_segment = ""
            
            # 标点符号列表（按优先级）
            punctuation_marks = ['。', '！', '？', '.', '!', '?', '，', ',', '；', ';', '：', ':', '、']
            
            i = 0
            while i < len(text):
                char = text[i]
                current_segment += char
                
                # 如果当前段长度达到或超过最大字符数
                if len(current_segment) >= max_chars:
                    # 尝试在标点符号处截断
                    found_punctuation = False
                    # 向前查找最近的标点符号（最多向前查找15个字符）
                    for j in range(len(current_segment) - 1, max(0, len(current_segment) - 15), -1):
                        if current_segment[j] in punctuation_marks:
                            # 在标点符号后截断
                            segments_list.append(current_segment[:j+1].strip())
                            current_segment = current_segment[j+1:]
                            found_punctuation = True
                            break
                    
                    # 如果没找到标点符号，在最大字符数处强制截断
                    if not found_punctuation:
                        # 尽量在空格或常见分隔符处截断
                        cut_pos = max_chars
                        for j in range(max_chars - 1, max(0, max_chars - 10), -1):
                            if current_segment[j] in [' ', '　', '\t']:
                                cut_pos = j + 1
                                break
                        segments_list.append(current_segment[:cut_pos].strip())
                        current_segment = current_segment[cut_pos:]
                
                i += 1
            
            # 添加最后一段
            if current_segment.strip():
                segments_list.append(current_segment.strip())
            
            return segments_list
        
        # 使用标点符号分段
        text_parts = split_by_punctuation(text, chars_per_line)
        
        # 确保至少6段，确保跳转精准
        if len(text_parts) < 6:
            # 如果分段太少，按字符数再细分
            num_segments_needed = max(6, int(len(text) / chars_per_line) + 1)
            chars_per_segment = len(text) / num_segments_needed
            text_parts = []
            for i in range(num_segments_needed):
                start_idx = int(i * chars_per_segment)
                end_idx = int((i + 1) * chars_per_segment) if i < num_segments_needed - 1 else len(text)
                segment_text = text[start_idx:end_idx].strip()
                # 如果超过最大字符数，在标点符号处截断
                if len(segment_text) > chars_per_line:
                    for j in range(chars_per_line - 1, max(0, chars_per_line - 15), -1):
                        if segment_text[j] in ['，', '。', '！', '？', '、', ',', '.', '!', '?', '：', '；', ':', ';']:
                            segment_text = segment_text[:j+1]
                            break
                    else:
                        segment_text = segment_text[:chars_per_line]
                text_parts.append(segment_text)
        
        # 均匀分配时间
        num_segments = len(text_parts)
        segment_duration = duration / num_segments
        segments = []
        
        for i, segment_text in enumerate(text_parts):
            start_time = i * segment_duration
            end_time = (i + 1) * segment_duration if i < num_segments - 1 else duration
            segments.append({'start': start_time, 'end': end_time, 'text': segment_text})
        
        print(f"[字幕] 降级方案：按标点符号分段为 {len(segments)} 段（每段最多{chars_per_line}字）")
    
    if not segments:
        return None
    return segments


def extract_subtitle_segments(video_path: str, script_text: str) -> Optional[List[dict]]:
    """
    仅生成字幕片段时间轴与文案（Whisper+硅基+纠错），不写视频文件。
    用于成品素材页展示/编辑后再次烧录。
    """
    if not MOVIEPY_AVAILABLE or not PIL_AVAILABLE:
        return None
    vp = Path(video_path)
    if not vp.exists():
        return None
    import shutil

    temp_dir = vp.parent / f"temp_subtitle_extract_{os.getpid()}"
    temp_dir.mkdir(exist_ok=True)
    video = None
    try:
        video = VideoFileClip(str(vp))
        segs = _compute_subtitle_segments_core(video, vp, script_text, temp_dir)
        if not segs:
            return None
        return [
            {"start": float(s.get("start", 0.0)), "end": float(s.get("end", 0.0)), "text": str(s.get("text", "") or "")}
            for s in segs
        ]
    finally:
        if video is not None:
            try:
                video.close()
            except Exception:
                pass
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass


def burn_subtitles_from_segments(
    video_path: str,
    segments: List[dict],
    output_path: Optional[str] = None,
) -> Optional[str]:
    """使用已确定的 segments（可经用户改过 text）烧录字幕，逻辑与 burn_subtitle_to_video 后半段一致。"""
    if not MOVIEPY_AVAILABLE or not PIL_AVAILABLE:
        return None
    if not segments:
        return None
    try:
        vp = Path(video_path)
        if not vp.exists():
            return None
        norm = []
        for s in segments:
            norm.append(
                {
                    "start": float(s.get("start", 0.0)),
                    "end": float(s.get("end", 0.0)),
                    "text": str(s.get("text", "") or ""),
                }
            )
        replace_original = output_path is None
        if output_path is None:
            out = str(vp.parent / f"{vp.stem}_with_subtitle{vp.suffix}")
        else:
            out = str(Path(output_path))
        video = VideoFileClip(str(vp))
        temp_dir = vp.parent / "temp_subtitle"
        temp_dir.mkdir(exist_ok=True)
        try:
            subtitle_clips = create_dynamic_subtitle_clips(norm, video.w, video.h, script_text="")
            if not subtitle_clips:
                video.close()
                return str(vp)
            final_video = CompositeVideoClip([video] + subtitle_clips)
            final_video.write_videofile(
                out,
                codec="libx264",
                audio_codec="aac",
                fps=video.fps,
                preset="medium",
                bitrate="8000k",
                logger=None,
            )
            video.close()
            final_video.close()
            for clip in subtitle_clips:
                clip.close()
            if replace_original and out != str(vp):
                try:
                    vp.unlink()
                    Path(out).rename(vp)
                    out = str(vp)
                except Exception as e:
                    print(f"[字幕] 替换原视频失败: {e}")
            try:
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass
            return out
        except Exception:
            try:
                video.close()
            except Exception:
                pass
            raise
    except Exception as e:
        print(f"[字幕] burn_subtitles_from_segments 失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def burn_subtitle_to_video(
    video_path: str,
    script_text: str,
    output_path: Optional[str] = None
) -> Optional[str]:
    """
    为视频添加动态字幕（根据语音时间戳同步显示）
    
    Args:
        video_path: 输入视频路径
        script_text: 原始文案内容（用于参考，实际使用Whisper识别的时间戳）
        output_path: 输出视频路径（如果为None，则覆盖原视频）
    
    Returns:
        输出视频路径，如果失败返回None
    """
    if not MOVIEPY_AVAILABLE or not PIL_AVAILABLE:
        print("[字幕] MoviePy或PIL未安装，无法添加字幕")
        return None
    
    try:
        video_path = Path(video_path)
        if not video_path.exists():
            print(f"[字幕] 视频文件不存在: {video_path}")
            return None
        
        # 设置输出路径
        replace_original = output_path is None
        if output_path is None:
            # 覆盖原视频，先保存到临时文件
            output_path = str(video_path.parent / f"{video_path.stem}_with_subtitle{video_path.suffix}")
        else:
            output_path = str(Path(output_path))
        
        print(f"[字幕] 开始为视频添加动态字幕...")
        print(f"[字幕] 输入视频: {video_path}")
        print(f"[字幕] 输出视频: {output_path}")
        print(f"[字幕] 文案内容: {script_text[:50]}...")
        
        # 加载视频
        video = VideoFileClip(str(video_path))
        duration = video.duration
        print(f"[字幕] 视频时长: {duration:.2f}秒")
        
        # 创建临时目录
        temp_dir = video_path.parent / "temp_subtitle"
        temp_dir.mkdir(exist_ok=True)

        segments = _compute_subtitle_segments_core(video, video_path, script_text, temp_dir)
        if not segments:
            print("[字幕] 无法创建字幕，返回原视频")
            video.close()
            try:
                import shutil
                shutil.rmtree(temp_dir)
            except Exception:
                pass
            return str(video_path)

        print(f"[字幕] 获取到 {len(segments)} 个字幕时间段")

        # 简化版固定：始终使用 segments[].text 作为展示文案（Whisper+硅基纠错）
        subtitle_clips = create_dynamic_subtitle_clips(
            segments,
            video.w,
            video.h,
            script_text="",
        )
        
        if not subtitle_clips:
            print("[字幕] 字幕片段创建失败，返回原视频")
            video.close()
            return str(video_path)
        
        # 合成视频和字幕
        print(f"[字幕] 合成视频和字幕...")
        final_video = CompositeVideoClip([video] + subtitle_clips)
        
        # 输出视频
        print(f"[字幕] 开始渲染视频（这可能需要一些时间）...")
        final_video.write_videofile(
            output_path,
            codec='libx264',
            audio_codec='aac',
            fps=video.fps,
            preset='medium',
            bitrate='8000k',
            logger=None  # 禁用详细日志
        )
        
        # 清理资源
        video.close()
        final_video.close()
        for clip in subtitle_clips:
            clip.close()
        
        # 仅在“未指定输出路径”的覆盖模式下替换原视频
        if replace_original and output_path != str(video_path):
            # 删除原视频，重命名新视频
            try:
                video_path.unlink()
                Path(output_path).rename(video_path)
                output_path = str(video_path)
                print(f"[字幕] 已替换原视频: {output_path}")
            except Exception as e:
                print(f"[字幕] 替换原视频失败: {e}")
                print(f"[字幕] 带字幕视频保存在: {output_path}")
        
        # 清理临时目录
        try:
            import shutil
            shutil.rmtree(temp_dir)
        except:
            pass
        
        print(f"[字幕] 动态字幕添加成功！")
        return output_path
        
    except Exception as e:
        print(f"[字幕] 添加字幕时出错: {e}")
        import traceback
        traceback.print_exc()
        return None

