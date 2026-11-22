"""
Pixelle-Video FastAPI Wrapper
为 PyQt UI 提供稳定的 REST API 接口

架构：
PyQt UI → HTTP → FastAPI Wrapper → Pixelle-Video 内部生成逻辑
"""
import os
import sys
import uuid
import asyncio
import threading
import re
import logging
import json
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
import random
import time
import subprocess
import mimetypes
from collections import deque

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Body, Request, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# 本服务自身 Base URL（用于内部 requests 调用自身 API，支持打包后端口变更）
try:
    # 客户交付版默认端口：33710（启动器也会注入 AXON_PORT=33710）
    _SELF_PORT = int(os.environ.get("AXON_PORT", "33710"))
except Exception:
    _SELF_PORT = 33710
SELF_BASE_URL = f"http://127.0.0.1:{_SELF_PORT}"

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# 任务 step 百分比辅助（仅用于 UI 文案提示，不改变核心业务）
# ============================================================================
def _run_with_step_percent(task_id: str, label: str, fn, *, start: int = 0, cap: int = 95, tick_sec: float = 1.0):
    """
    在执行耗时函数时，后台持续更新 TASKS[task_id]['step'] = f'{label} {pct}%'
    - pct 会缓慢增长到 cap（默认 95%），函数结束后设置为 100%
    - 只影响前端展示文案，不影响核心生成逻辑
    """
    stop = threading.Event()

    def _ticker():
        pct = max(0, int(start))
        try:
            while not stop.is_set():
                # 轻微抖动的增长，避免长时间卡在同一个数字
                inc = 1 if pct < 30 else (1 if random.random() < 0.7 else 2)
                pct = min(int(cap), pct + inc)
                if task_id in TASKS and TASKS[task_id].get("status") == "running":
                    TASKS[task_id]["step"] = f"{label} {pct}%"
                time.sleep(max(0.2, float(tick_sec)))
        except Exception:
            return

    t = threading.Thread(target=_ticker, daemon=True)
    t.start()
    try:
        if task_id in TASKS and TASKS[task_id].get("status") == "running":
            TASKS[task_id]["step"] = f"{label} {max(0, int(start))}%"
        return fn()
    finally:
        stop.set()
        try:
            t.join(timeout=1.5)
        except Exception:
            pass
        if task_id in TASKS and TASKS[task_id].get("status") == "running":
            TASKS[task_id]["step"] = f"{label} 100%"

# ============================================================================
# 路径自动检测函数
# ============================================================================
def detect_pixelle_video_path():
    """
    自动检测 Pixelle-Video 项目路径
    
    检测顺序：
    1. 配置文件 config.json（在 wrapper 目录下）
    2. 环境变量 PIXELLE_VIDEO_ROOT 或 PIXELLE_VIDEO_PATH
    3. 检查常见路径（Y:/Video-main, D:/Video-main 等）
    4. 检查 pixelle_wrapper 目录的父目录（开发环境）
    5. 检查 pixelle_wrapper 目录的同级目录（打包环境）
    6. 检查当前工作目录
    7. 如果都找不到，返回 None（将使用相对路径）
    """
    # 0) bootstrap/启动器注入的安装根（先于 __file__/cwd）：避免偶发路径漂移导致 Pixelle 导入失败、素材页长期未连接
    for _env_key in ("AXON_INSTALL_DIR", "AXON_ROOT"):
        _raw = os.environ.get(_env_key)
        if not _raw:
            continue
        _root = Path(_raw).resolve()
        if not _root.is_dir():
            continue
        for _nm in ("Video-main", "Video", "pixelle-video", "Pixelle-Video"):
            _cand = _root / _nm
            if _cand.is_dir() and (_cand / "pixelle_video").exists():
                print(f"[Wrapper] 从 {_env_key} 安装根解析到 Pixelle-Video: {_cand}")
                return _cand.resolve()

    # 处理打包后的路径问题
    if getattr(sys, 'frozen', False):
        # 打包后的环境：PixelleWrapper.exe 在 dist/Axon_Program/pixelle_wrapper/PixelleWrapper.exe
        # sys.executable 指向 PixelleWrapper.exe 的路径
        exe_path = Path(sys.executable)
        # wrapper_dir 应该是 EXE 所在的目录（pixelle_wrapper 目录）
        wrapper_dir = exe_path.parent
        print(f"[Wrapper] 打包环境：EXE 路径: {exe_path}")
        print(f"[Wrapper] 打包环境：Wrapper 目录: {wrapper_dir}")
    else:
        # 开发环境：正常使用 __file__
        current_file = Path(__file__).resolve()
        wrapper_dir = current_file.parent  # pixelle_wrapper 目录
        print(f"[Wrapper] 开发环境：Wrapper 目录: {wrapper_dir}")
    
    # 方法1: 检查配置文件（pixelle_wrapper/config.json）
    config_file = wrapper_dir / "config.json"
    if config_file.exists():
        try:
            import json
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                if 'pixelle_video_path' in config and config['pixelle_video_path']:
                    path_str = config['pixelle_video_path']
                    path = Path(path_str)
                    
                    # 如果是相对路径，基于项目根目录解析
                    if not path.is_absolute():
                        project_root = wrapper_dir.parent
                        path = project_root / path_str
                    
                    if path.exists():
                        print(f"[Wrapper] 从配置文件检测到 Pixelle-Video 路径: {path}")
                        return path.resolve()
        except Exception as e:
            print(f"[Wrapper] 读取配置文件失败: {e}")
    
    # 方法2: 检查环境变量
    env_path = os.environ.get("PIXELLE_VIDEO_ROOT") or os.environ.get("PIXELLE_VIDEO_PATH")
    if env_path:
        path = Path(env_path)
        if path.exists():
            print(f"[Wrapper] 从环境变量检测到 Pixelle-Video 路径: {path}")
            return path.resolve()
    
    # 方法3: 优先检查打包目录内的路径（打包后应该在这里）
    # 打包后结构：dist/Axon_Program/pixelle_wrapper/PixelleWrapper.exe
    if getattr(sys, 'frozen', False):
        # 打包环境：优先检查打包目录内的 pixelle_video 模块
        exe_dir = Path(sys.executable).parent  # pixelle_wrapper 目录
        
        # 最优先：检查 pixelle_wrapper 目录内（如果复制了模块）
        inner_module = exe_dir / "pixelle_video"
        if inner_module.exists() and (inner_module / "__init__.py").exists():
            print(f"[Wrapper] [优先] 从打包目录内检测到 pixelle_video 模块: {exe_dir}")
            return exe_dir.resolve()
        
        # 其次：检查 Axon_Program 目录内
        parent_dir = exe_dir.parent  # Axon_Program 目录
        possible_names = ["Video-main", "Video", "pixelle-video", "Pixelle-Video"]
        for name in possible_names:
            inner_dir = parent_dir / name
            if inner_dir.exists() and (inner_dir / "pixelle_video").exists():
                print(f"[Wrapper] [优先] 从打包目录内检测到 Pixelle-Video 路径: {inner_dir}")
                return inner_dir.resolve()
        
        # 再次：检查同级目录（Axon_Program 同级）
        for name in possible_names:
            sibling_dir = parent_dir.parent / name
            if sibling_dir.exists() and (sibling_dir / "pixelle_video").exists():
                print(f"[Wrapper] [优先] 从打包目录同级检测到 Pixelle-Video 路径: {sibling_dir}")
                return sibling_dir.resolve()
    
    # 方法3.5: 检查常见路径（Windows 常见盘符）- 作为后备方案
    common_paths = [
        Path("F:/Axon21/Video-main"),  # 添加 Axon21 项目路径
        Path("F:\\Axon21\\Video-main"),
        Path("Y:/Video-main"),
        Path("Y:\\Video-main"),
        Path("D:/Video-main"),
        Path("D:\\Video-main"),
        Path("C:/Video-main"),
        Path("C:\\Video-main"),
        Path("E:/Video-main"),
        Path("E:\\Video-main"),
    ]
    for path in common_paths:
        if path.exists() and (path / "pixelle_video").exists():
            print(f"[Wrapper] 从常见路径检测到 Pixelle-Video 路径（后备方案）: {path}")
            return path.resolve()
    
    # 方法4: 从当前文件位置推断（pixelle_wrapper/main.py）
    # 检查父目录（开发环境：pixelle_wrapper 在项目根目录下）
    parent_dir = wrapper_dir.parent
    if (parent_dir / "pixelle_video").exists() or (parent_dir / "src" / "pixelle_video").exists():
        print(f"[Wrapper] 从父目录检测到 Pixelle-Video 路径: {parent_dir}")
        return parent_dir.resolve()
    
    # 检查同级目录（打包环境：pixelle_wrapper 和 Video-main 在同一级）
    possible_names = ["Video-main", "Video", "pixelle-video", "Pixelle-Video"]
    for name in possible_names:
        sibling_dir = wrapper_dir.parent / name
        if sibling_dir.exists() and (sibling_dir / "pixelle_video").exists():
            print(f"[Wrapper] 从同级目录检测到 Pixelle-Video 路径: {sibling_dir}")
            return sibling_dir.resolve()
    
    # 方法5: 检查当前工作目录
    cwd = Path.cwd()
    if (cwd / "pixelle_video").exists() or (cwd / "src" / "pixelle_video").exists():
        print(f"[Wrapper] 从工作目录检测到 Pixelle-Video 路径: {cwd}")
        return cwd.resolve()
    
    # 方法6: 如果打包后，pixelle_video 可能已经作为包安装，尝试导入
    try:
        import pixelle_video
        if hasattr(pixelle_video, '__file__'):
            module_path = Path(pixelle_video.__file__).parent.parent
            if module_path.exists():
                print(f"[Wrapper] 从已安装模块检测到 Pixelle-Video 路径: {module_path}")
                return module_path.resolve()
    except ImportError:
        pass
    
    # 如果都找不到，返回 None（而不是 wrapper 目录）
    print(f"[Wrapper] 警告: 未检测到 Pixelle-Video 路径")
    print(f"[Wrapper] 提示: 请设置环境变量 PIXELLE_VIDEO_ROOT 或在 pixelle_wrapper/config.json 中配置 pixelle_video_path")
    return None


# ============================================================================
# 添加 Pixelle-Video 项目路径到 sys.path
# ============================================================================
PIXELLE_VIDEO_PATH = detect_pixelle_video_path()

# 如果检测到的路径包含 pixelle_video 模块，添加到 sys.path
if PIXELLE_VIDEO_PATH and (PIXELLE_VIDEO_PATH / "pixelle_video").exists():
    if str(PIXELLE_VIDEO_PATH) not in sys.path:
        sys.path.insert(0, str(PIXELLE_VIDEO_PATH))
    # 设置 PIXELLE_VIDEO_ROOT 环境变量（Pixelle-Video 需要这个来找到 workflows 目录）
    os.environ["PIXELLE_VIDEO_ROOT"] = str(PIXELLE_VIDEO_PATH.resolve())
    print(f"[Wrapper] 已设置 PIXELLE_VIDEO_ROOT: {os.environ['PIXELLE_VIDEO_ROOT']}")
elif PIXELLE_VIDEO_PATH:
    # 即使没有 pixelle_video 目录，也设置环境变量（可能 workflows 在其他地方）
    os.environ["PIXELLE_VIDEO_ROOT"] = str(PIXELLE_VIDEO_PATH.resolve())
    print(f"[Wrapper] 已设置 PIXELLE_VIDEO_ROOT: {os.environ['PIXELLE_VIDEO_ROOT']}")
else:
    # 如果完全找不到，使用当前 wrapper 目录（但会显示警告）
    wrapper_dir = Path(__file__).parent.resolve()
    os.environ["PIXELLE_VIDEO_ROOT"] = str(wrapper_dir)
    print(f"[Wrapper] 警告: 未找到 Pixelle-Video 项目，使用 wrapper 目录作为 PIXELLE_VIDEO_ROOT: {wrapper_dir}")
    print(f"[Wrapper] 这将导致无法导入 pixelle_video 模块，请配置正确的路径")

# ============================================================================
# FFmpeg 自动配置（在加载 Pixelle-Video 之前）
# ============================================================================
def setup_ffmpeg():
    """
    自动配置 FFmpeg，确保 Pixelle-Video 能正常加载
    
    逻辑：
    1. 检查项目里有没有 ffmpeg/bin/ffmpeg.exe
    2. 没有的话，从 imageio_ffmpeg 复制 ffmpeg 到项目的 ffmpeg/bin/ffmpeg.exe
    3. 把 ffmpeg/bin 加到当前进程的 PATH
    """
    # 获取 wrapper 目录
    if getattr(sys, 'frozen', False):
        wrapper_dir = Path(sys.executable).parent
    else:
        wrapper_dir = Path(__file__).parent
    
    ffmpeg_dir = wrapper_dir / "ffmpeg" / "bin"
    ffmpeg_exe = ffmpeg_dir / "ffmpeg.exe"
    
    # 如果已经存在，直接添加到 PATH
    if ffmpeg_exe.exists():
        ffmpeg_bin_path = str(ffmpeg_dir.resolve())
        if ffmpeg_bin_path not in os.environ.get("PATH", ""):
            os.environ["PATH"] = ffmpeg_bin_path + os.pathsep + os.environ.get("PATH", "")
            print(f"[Wrapper] [FFmpeg] 已找到项目内的 FFmpeg: {ffmpeg_exe}")
            print(f"[Wrapper] [FFmpeg] 已添加到 PATH: {ffmpeg_bin_path}")
        return True
    
    # 如果不存在，尝试从 imageio_ffmpeg 复制
    try:
        import imageio_ffmpeg
        # 获取 imageio_ffmpeg 自带的 ffmpeg 路径
        imageio_ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        
        if imageio_ffmpeg_path and os.path.exists(imageio_ffmpeg_path):
            # 创建目录
            ffmpeg_dir.mkdir(parents=True, exist_ok=True)
            
            # 复制 ffmpeg.exe
            import shutil
            shutil.copy2(imageio_ffmpeg_path, ffmpeg_exe)
            print(f"[Wrapper] [FFmpeg] 已从 imageio_ffmpeg 复制 FFmpeg 到: {ffmpeg_exe}")
            
            # 添加到 PATH
            ffmpeg_bin_path = str(ffmpeg_dir.resolve())
            os.environ["PATH"] = ffmpeg_bin_path + os.pathsep + os.environ.get("PATH", "")
            print(f"[Wrapper] [FFmpeg] 已添加到 PATH: {ffmpeg_bin_path}")
            return True
        else:
            print(f"[Wrapper] [FFmpeg] 警告: imageio_ffmpeg 未找到 FFmpeg 可执行文件")
    except ImportError:
        print(f"[Wrapper] [FFmpeg] 警告: imageio_ffmpeg 未安装，无法自动配置 FFmpeg")
    except Exception as e:
        print(f"[Wrapper] [FFmpeg] 配置失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 检查系统 PATH 中是否有 ffmpeg
    import shutil
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        print(f"[Wrapper] [FFmpeg] 在系统 PATH 中找到 FFmpeg: {system_ffmpeg}")
        return True
    
    print(f"[Wrapper] [FFmpeg] 警告: 未找到 FFmpeg，Pixelle-Video 可能无法正常加载")
    print(f"[Wrapper] [FFmpeg] 提示: 请安装 FFmpeg 或 imageio_ffmpeg (pip install imageio-ffmpeg)")
    return False

# 在导入 Pixelle-Video 之前配置 FFmpeg
print("[Wrapper] 正在配置 FFmpeg...")
setup_ffmpeg()

# ============================================================================
# 导入 Pixelle-Video 原生逻辑（不修改）
# ============================================================================
try:
    from pixelle_video.service import PixelleVideoCore
    from pixelle_video.config import config_manager
    from pixelle_video.models.progress import ProgressEvent
    PIXELLE_AVAILABLE = True
    print(f"[Wrapper] [OK] Pixelle-Video 导入成功")
except ImportError as e:
    print(f"[警告] 无法导入 Pixelle-Video: {e}")
    print(f"[警告] 请确保 Pixelle-Video 项目路径正确: {PIXELLE_VIDEO_PATH}")
    print(f"[警告] 请确保已安装所有依赖（包括 comfykit）")
    PIXELLE_AVAILABLE = False
    # 创建一个占位符类，避免 NameError
    class PixelleVideoCore:
        def __init__(self):
            raise RuntimeError("Pixelle-Video 不可用")
        async def initialize(self):
            pass
        async def cleanup(self):
            pass
    # 创建一个占位符的 config_manager
    class ConfigManager:
        class Config:
            def to_dict(self):
                return {}
        config = Config()
    config_manager = ConfigManager()

# ============================================================================
# Wrapper 状态管理（新加的代码）
# ============================================================================
CURRENT_STATE: Dict[str, Any] = {
    "avatar_path": None,
    "text": None,
    "api_key": None,
    "audio_path": None,  # 上传的音频文件路径
    "product_path": None,  # 上传的产品图片路径（用于带货模式）
    "showcase_video_path": None,  # 兼容旧逻辑：始终同步为「首个已上传槽位」路径
    "showcase_video_paths": [None, None, None],  # 环境演示最多 3 段，画中画按序拼接+循环
    "background_music_path": None,
}

TASKS: Dict[str, Dict[str, Any]] = {}

# 从config.yaml读取的RunningHub Key（全局变量）
_runninghub_key_from_config: Optional[str] = None

# 全局 Pixelle-Video 实例
_pixelle_video: Optional[PixelleVideoCore] = None
# 启动阶段 init 失败时，由 /api/connection_status 按冷却时间反复懒加载（不设永久上限，避免「试 5 次就再也不连」）
_pixelle_last_lazy_init_attempt: float = 0.0
_PIXELLE_LAZY_INIT_COOLDOWN_SEC: float = 6.0
_pixelle_connection_init_lock = asyncio.Lock()

# Wrapper 基础目录（用于存储数据文件）
# 处理打包后的路径问题
if getattr(sys, 'frozen', False):
    # 打包后的环境：PixelleWrapper.exe 在 dist/Axon_Program/pixelle_wrapper/PixelleWrapper.exe
    # WRAPPER_BASE_DIR 应该是 EXE 所在的目录（pixelle_wrapper 目录）
    WRAPPER_BASE_DIR = Path(sys.executable).parent
    print(f"[Wrapper] 打包环境：EXE 路径: {sys.executable}")
    print(f"[Wrapper] 打包环境：Wrapper 基础目录: {WRAPPER_BASE_DIR}")
else:
    # 开发环境：正常使用 __file__
    WRAPPER_BASE_DIR = Path(__file__).parent.resolve()
    print(f"[Wrapper] 开发环境：Wrapper 基础目录: {WRAPPER_BASE_DIR}")
print(f"[Wrapper] Wrapper 基础目录: {WRAPPER_BASE_DIR}")

# 项目根（shuziren）：用于定位 env/ffmpeg/ffprobe（与 WRAPPER 是否在 pixelle_wrapper 无关）
_PROJECT_ROOT_DIR = Path(__file__).resolve().parent.parent
_FFPROBE_EXE = _PROJECT_ROOT_DIR / "env" / "ffmpeg" / "ffprobe.exe"
SHOWCASE_MAX_DURATION_SEC = 40.0  # 单段须 < 40 秒


def _ensure_showcase_paths_list() -> List[Optional[str]]:
    lst = CURRENT_STATE.get("showcase_video_paths")
    if not isinstance(lst, list) or len(lst) != 3:
        CURRENT_STATE["showcase_video_paths"] = [None, None, None]
    return CURRENT_STATE["showcase_video_paths"]  # type: ignore[return-value]


def _sync_showcase_legacy_path() -> None:
    """单路径 showcase_video_path 与三槽位保持兼容（取首个存在的槽）。"""
    first: Optional[str] = None
    for p in _ensure_showcase_paths_list():
        if not p:
            continue
        try:
            pp = Path(str(p)).resolve()
            if pp.is_file():
                first = str(pp)
                break
        except Exception:
            continue
    CURRENT_STATE["showcase_video_path"] = first


def _migrate_legacy_showcase_if_needed() -> None:
    """旧版仅 showcase_video_path 时，迁移到槽 0。"""
    lst = _ensure_showcase_paths_list()
    legacy = CURRENT_STATE.get("showcase_video_path")
    if legacy and isinstance(legacy, str) and not any(lst):
        lst[0] = legacy
        print("[Wrapper] 已将单路径环境视频迁移到槽位 0")


def _collect_existing_showcase_files() -> List[str]:
    """按槽 0→1→2 返回存在的文件路径（用于画中画拼接）。"""
    _migrate_legacy_showcase_if_needed()
    out: List[str] = []
    for p in _ensure_showcase_paths_list():
        if not p:
            continue
        try:
            pp = Path(str(p)).resolve()
            if pp.is_file():
                out.append(str(pp))
        except Exception:
            continue
    return out


def _ffprobe_duration_seconds(video_path: Path) -> Optional[float]:
    exe: Optional[Path] = _FFPROBE_EXE if _FFPROBE_EXE.is_file() else None
    if not exe:
        import shutil
        w = shutil.which("ffprobe")
        exe = Path(w) if w else None
    if not exe or not video_path.is_file():
        return None
    try:
        r = subprocess.run(
            [str(exe), "-v", "error", "-show_entries", "format=duration", "-of", "json", str(video_path)],
            capture_output=True,
            text=True,
            timeout=90,
        )
        if r.returncode != 0:
            return None
        j = json.loads(r.stdout or "{}")
        d = (j.get("format") or {}).get("duration")
        return float(d) if d is not None else None
    except Exception:
        return None


def _apply_showcase_pip_chain(host_path: str) -> str:
    """
    画中画时间轴：0~8 无；8~15 有（7s，多段顺序拼接+循环填满）；15~27 无；27~片尾有（多段拼接+循环铺满）。
    返回合成后的路径；无环境视频或失败时返回 host_path。
    """
    paths = _collect_existing_showcase_files()
    if not paths:
        return host_path
    try:
        from ai_pipeline.video_editor import add_picture_in_picture
    except Exception as e:
        print(f"[Wrapper] 导入 add_picture_in_picture 失败: {e}")
        return host_path

    d = os.path.dirname(host_path)
    base = os.path.splitext(os.path.basename(host_path))[0]
    seg1 = os.path.join(d, f"{base}_pip_seg1.mp4")
    outp = os.path.join(d, f"{base}_pip.mp4")
    sv = [str(x) for x in paths]

    try:
        pip_video_path_seg1 = add_picture_in_picture(
            host_video=str(host_path),
            showcase_videos=sv,
            output_path=str(seg1),
            start_time=8.0,
            end_time=15.0,
            position="center",
            size_ratio=2 / 3,
            loop=True,
            effect="zoom",
        )
        host_for_seg2 = str(host_path)
        if pip_video_path_seg1 and os.path.exists(str(pip_video_path_seg1)):
            host_for_seg2 = str(pip_video_path_seg1)
        pip_video_path_seg2 = add_picture_in_picture(
            host_video=host_for_seg2,
            showcase_videos=sv,
            output_path=str(outp),
            start_time=27.0,
            end_before=0.0,
            position="center",
            size_ratio=2 / 3,
            loop=True,
            effect="zoom",
        )
        if pip_video_path_seg2 and os.path.exists(str(pip_video_path_seg2)):
            return str(pip_video_path_seg2)
        if pip_video_path_seg1 and os.path.exists(str(pip_video_path_seg1)):
            return str(pip_video_path_seg1)
    except Exception as e:
        print(f"[Wrapper] 画中画处理异常: {e}")
        import traceback
        traceback.print_exc()
    return host_path


def find_config_yaml():
    """
    查找 config.yaml 文件
    
    查找顺序：
    1. PIXELLE_VIDEO_PATH / config.yaml
    2. WRAPPER_BASE_DIR / config.yaml
    3. 当前工作目录 / config.yaml
    """
    # 方法1: 从 PIXELLE_VIDEO_PATH 查找
    if PIXELLE_VIDEO_PATH:
        config_path = PIXELLE_VIDEO_PATH / "config.yaml"
        if config_path.exists():
            return config_path
    
    # 方法2: 从 wrapper 目录查找
    config_path = WRAPPER_BASE_DIR / "config.yaml"
    if config_path.exists():
        return config_path
    
    # 方法3: 从当前工作目录查找
    config_path = Path.cwd() / "config.yaml"
    if config_path.exists():
        return config_path
    
    return None

def find_output_dir():
    """
    查找输出目录
    
    查找顺序：
    1. PIXELLE_VIDEO_PATH / output
    2. PIXELLE_VIDEO_PATH / outputs
    3. WRAPPER_BASE_DIR / output
    4. WRAPPER_BASE_DIR / outputs
    """
    # 方法1: 从 PIXELLE_VIDEO_PATH 查找
    if PIXELLE_VIDEO_PATH:
        for dir_name in ["output", "outputs"]:
            output_dir = PIXELLE_VIDEO_PATH / dir_name
            if output_dir.exists():
                return output_dir
    
    # 方法2: 从 wrapper 目录查找
    for dir_name in ["output", "outputs"]:
        output_dir = WRAPPER_BASE_DIR / dir_name
        if output_dir.exists():
            return output_dir
    
    # 如果都找不到，返回 wrapper 目录下的 output（会自动创建）
    return WRAPPER_BASE_DIR / "output"


def _material_basename(path_str: Optional[str]) -> Optional[str]:
    if not path_str:
        return None
    try:
        return Path(path_str).name
    except Exception:
        return None


def _path_is_under_data_root(p: Path) -> bool:
    try:
        resolved = p.resolve()
        root = (WRAPPER_BASE_DIR / "data").resolve()
        resolved.relative_to(root)
        return True
    except (ValueError, OSError):
        return False


def _unlink_material_file(path_str: Optional[str]) -> None:
    """物理删除 data/ 下的素材文件；路径不在 data 下则跳过。"""
    if not path_str:
        return
    try:
        p = Path(path_str).resolve()
        if not _path_is_under_data_root(p):
            logger.warning(f"[Wrapper] 跳过删除（不在 data 目录下）: {path_str}")
            return
        if p.is_file():
            p.unlink()
            logger.info(f"[Wrapper] 已删除素材文件: {p}")
    except OSError as e:
        logger.warning(f"[Wrapper] 删除素材文件失败: {path_str} {e}")


# 口播素材：预览/清除 kind → CURRENT_STATE 键名
_MATERIAL_KIND_TO_STATE_KEY: Dict[str, str] = {
    "avatar": "avatar_path",
    "product": "product_path",
    "audio": "audio_path",
    "showcase": "showcase_video_path",
    "showcase_video": "showcase_video_path",
    "background_music": "background_music_path",
    "bgm": "background_music_path",
}


def _ordered_publish_platforms(platforms: List[str]) -> List[str]:
    """
    多平台发布顺序：与前端「抖音、快手、小红书、视频号」一致，依次占用浏览器自动化锁。
    """
    if not platforms:
        return []
    priority = ("douyin", "kuaishou", "xhs", "sph")
    seen = set()
    out: List[str] = []
    for p in priority:
        if p in platforms and p not in seen:
            out.append(p)
            seen.add(p)
    for p in platforms:
        if p not in seen:
            out.append(p)
            seen.add(p)
    return out


# ============================================================================
# FastAPI 应用初始化（新加的代码）
# ============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理（启动和关闭）"""
    # 启动时执行
    default_api_key = os.environ.get("PIXELLE_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""
    if default_api_key and not os.environ.get("PIXELLE_API_KEY"):
        os.environ["PIXELLE_API_KEY"] = default_api_key
        CURRENT_STATE["api_key"] = default_api_key
        print(f"[Wrapper] 已自动设置 API Key (长度: {len(default_api_key)})")
    elif not default_api_key:
        print("[Wrapper] 未检测到 PIXELLE_API_KEY / OPENAI_API_KEY，请在 config.yaml 或环境变量中配置")
    # 预热 HF 相关 sys.path（与 env_check / worker 一致），减少首屏检测全红
    try:
        _ensure_hf_wrapper_on_syspath()
    except Exception:
        pass

    # 从 config.yaml 加载硅基 Key 到 API_KEY，供链接解析、字幕识别等使用
    try:
        cfg_path = find_config_yaml()
        if cfg_path and cfg_path.exists():
            import yaml
            with open(cfg_path, 'r', encoding='utf-8') as f:
                cfg = yaml.safe_load(f) or {}
            if cfg.get('siliconflow') and cfg['siliconflow'].get('api_key'):
                sk = cfg['siliconflow']['api_key'].strip()
                os.environ["API_KEY"] = sk
                print(f"[Wrapper] 已从 config.yaml 加载硅基 API Key 到环境变量")
    except Exception as e:
        print(f"[Wrapper] 加载 config 硅基 Key 时忽略: {e}")

    try:
        _migrate_legacy_showcase_if_needed()
        _sync_showcase_legacy_path()
    except Exception:
        pass

    if PIXELLE_AVAILABLE:
        try:
            await init_pixelle_video()
        except Exception as e:
            print(f"[警告] Pixelle-Video 初始化失败: {e}")
            print("[提示] 健康检查接口仍可用，但生成功能将不可用")
            print(f"[提示] 错误详情: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("[警告] Pixelle-Video 不可用，仅健康检查接口可用")
        print("[提示] 请检查：")
        print(f"  1. Pixelle-Video 路径: {PIXELLE_VIDEO_PATH}")
        print("  2. 是否已安装所有依赖（pip install -r requirements.txt）")
        print("  3. 是否缺少 comfykit 模块")

    # 启动时核对素材预览/清除是否已进路由表（便于排查 404/405）
    try:
        hits: List[str] = []
        for r in app.routes:
            p = getattr(r, "path", None)
            methods = getattr(r, "methods", None)
            if not p or not methods:
                continue
            if p in ("/api/material_preview", "/api/clear_material"):
                hits.extend(f"{m} {p}" for m in methods)
        if hits:
            print(f"[Wrapper] 素材 API 路由: {', '.join(sorted(hits))}")
        else:
            print("[Wrapper] 【警告】未在路由表中发现 /api/material_preview 或 /api/clear_material，查看/清除将 404/405")
    except Exception as _e:
        print(f"[Wrapper] 路由自检跳过: {_e}")

    yield  # 应用运行期间
    
    # 关闭时执行
    global _pixelle_video
    if _pixelle_video:
        await _pixelle_video.cleanup()
        _pixelle_video = None

app = FastAPI(
    title="Pixelle-Video Wrapper API",
    description="为 PyQt UI 提供稳定的 REST API 接口",
    version="1.0.0",
    lifespan=lifespan
)

# 添加 CORS 支持
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _resolve_project_root() -> Path:
    """
    打包后由 runpy 执行 main.pyc 时，__file__ 可能不可靠，导致 web/ 挂载到错误目录、界面仍是旧版。
    优先使用启动器 / bootstrap 注入的安装根目录（与 Axon_Launcher.exe 同级）。
    """
    for key in ("AXON_INSTALL_DIR", "AXON_ROOT"):
        raw = os.environ.get(key)
        if not raw:
            continue
        p = Path(raw).resolve()
        if not p.is_dir():
            continue
        if (p / "web").is_dir():
            return p
        # 杀软/拷贝未完成时 web 可能短暂不可见；有 pixelle_wrapper 仍视为安装根（避免 HF 路径飘到错误目录）
        if (p / "pixelle_wrapper").is_dir():
            return p
    return Path(__file__).resolve().parent.parent


PROJECT_ROOT = _resolve_project_root()
FRONTEND_DIR = PROJECT_ROOT / "web"


def _resolve_pixelle_wrapper_dir() -> Path:
    """
    HF 私信 / output / hf_auto_reply 等均以该目录为根，与安装包布局一致：
    {AXON_INSTALL_DIR}/pixelle_wrapper/（客户机）或 {项目根}/pixelle_wrapper/（开发）。
    不依赖 runpy 下 __file__ 是否异常；与 FRONTEND_DIR 同源（同属 PROJECT_ROOT）。
    """
    cand = PROJECT_ROOT / "pixelle_wrapper"
    if cand.is_dir() and (
        (cand / "main.py").is_file() or (cand / "main.pyc").is_file()
    ):
        return cand
    return Path(__file__).resolve().parent


# ============================================================================
# 初始化 Pixelle-Video（新加的代码）
# ============================================================================

def _update_llm_service_config(api_key: str):
    """更新 LLM 服务的配置（API Key、base_url、model）"""
    global _pixelle_video
    
    if not _pixelle_video:
        print("[Wrapper] _pixelle_video 对象不存在，跳过配置更新")
        return
    
    qwen_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model = "qwen3.8-max"
    
    print(f"[Wrapper] ========== 开始更新 LLM 服务配置 ==========")
    print(f"[Wrapper] _pixelle_video 类型: {type(_pixelle_video)}")
    print(f"[Wrapper] _pixelle_video 所有属性: {[attr for attr in dir(_pixelle_video) if not attr.startswith('__')]}")
    
    # 方法1: 尝试通过 llm 属性访问（Pixelle-Video 使用 llm，不是 llm_service）
    llm_service = None
    if hasattr(_pixelle_video, 'llm'):
        llm_service = _pixelle_video.llm
        print(f"[Wrapper] 找到 llm 属性: {llm_service}")
    elif hasattr(_pixelle_video, 'llm_service'):
        llm_service = _pixelle_video.llm_service
        print(f"[Wrapper] 找到 llm_service 属性: {llm_service}")
    elif hasattr(_pixelle_video, '_llm_service'):
        llm_service = _pixelle_video._llm_service
        print(f"[Wrapper] 找到 _llm_service 属性: {llm_service}")
    
    # 方法2: 尝试通过 pipeline 访问 LLM 服务
    if not llm_service:
        print("[Wrapper] 尝试通过 pipeline 访问 LLM 服务...")
        if hasattr(_pixelle_video, 'pipelines'):
            pipelines = _pixelle_video.pipelines
            print(f"[Wrapper] pipelines: {pipelines}")
            if pipelines and len(pipelines) > 0:
                # 获取第一个 pipeline
                first_pipeline = list(pipelines.values())[0] if isinstance(pipelines, dict) else pipelines[0]
                print(f"[Wrapper] 第一个 pipeline 类型: {type(first_pipeline)}")
                if hasattr(first_pipeline, 'llm'):
                    llm_service = first_pipeline.llm
                    print(f"[Wrapper] 通过 pipeline.llm 找到 LLM 服务: {llm_service}")
                elif hasattr(first_pipeline, 'llm_service'):
                    llm_service = first_pipeline.llm_service
                    print(f"[Wrapper] 通过 pipeline.llm_service 找到 LLM 服务: {llm_service}")
    
    if not llm_service:
        print("[Wrapper] 无法找到 LLM 服务，尝试直接更新环境变量和配置管理器")
        # 至少确保环境变量和配置管理器已更新
        os.environ["OPENAI_API_KEY"] = api_key
        print(f"[Wrapper] 已更新环境变量 OPENAI_API_KEY")
        return
    
    try:
        # llm_service 已经在上面找到了（通过 llm 属性）
        qwen_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        qwen_model = "qwen3.8-max"
        
        print(f"[Wrapper] ========== 开始更新 LLM 服务配置 ==========")
        print(f"[Wrapper] LLM 服务类型: {type(llm_service)}")
        print(f"[Wrapper] LLM 服务所有属性: {[attr for attr in dir(llm_service) if not attr.startswith('__')]}")
        
        # 方法1: 尝试直接设置属性（如果存在）
        updated = False
        
        # 尝试设置 model
        if hasattr(llm_service, 'model'):
            try:
                old_model = getattr(llm_service, 'model', None)
                llm_service.model = qwen_model
                print(f"[Wrapper] 已更新 llm_service.model: {old_model} -> {qwen_model}")
                updated = True
            except Exception as e:
                print(f"[Wrapper] 无法设置 llm_service.model: {e}")
        
        # 尝试设置 base_url
        if hasattr(llm_service, 'base_url'):
            try:
                old_url = getattr(llm_service, 'base_url', None)
                llm_service.base_url = qwen_base_url
                print(f"[Wrapper] 已更新 llm_service.base_url: {old_url} -> {qwen_base_url}")
                updated = True
            except Exception as e:
                print(f"[Wrapper] 无法设置 llm_service.base_url: {e}")
        
        # 尝试设置 api_key
        if hasattr(llm_service, 'api_key'):
            try:
                old_key = getattr(llm_service, 'api_key', None)
                llm_service.api_key = api_key
                print(f"[Wrapper] 已更新 llm_service.api_key: {old_key[:10] if old_key else 'None'}... -> {api_key[:10]}...")
                updated = True
            except Exception as e:
                print(f"[Wrapper] 无法设置 llm_service.api_key: {e}")
        
        # 方法2: 更新 client 属性（如果存在）
        if hasattr(llm_service, 'client') and llm_service.client:
            client = llm_service.client
            print(f"[Wrapper] Client 类型: {type(client)}")
            
            # 更新 API Key
            if hasattr(client, 'api_key'):
                old_key = getattr(client, 'api_key', None)
                client.api_key = api_key
                print(f"[Wrapper] 已更新 client.api_key: {old_key[:10] if old_key else 'None'}... -> {api_key[:10]}...")
            elif hasattr(client, '_api_key'):
                old_key = getattr(client, '_api_key', None)
                client._api_key = api_key
                print(f"[Wrapper] 已更新 client._api_key: {old_key[:10] if old_key else 'None'}... -> {api_key[:10]}...")
            
            # 更新 base_url
            if hasattr(client, 'base_url'):
                old_url = str(getattr(client, 'base_url', None))
                client.base_url = qwen_base_url
                print(f"[Wrapper] 已更新 client.base_url: {old_url} -> {qwen_base_url}")
            elif hasattr(client, '_base_url'):
                old_url = str(getattr(client, '_base_url', None))
                client._base_url = qwen_base_url
                print(f"[Wrapper] 已更新 client._base_url: {old_url} -> {qwen_base_url}")
        
        # 方法3: 更新 config（如果存在）
        if hasattr(llm_service, 'config'):
            try:
                config = llm_service.config
                if hasattr(config, 'model'):
                    old_model = getattr(config, 'model', None)
                    config.model = qwen_model
                    print(f"[Wrapper] 已更新 config.model: {old_model} -> {qwen_model}")
                    updated = True
                if hasattr(config, 'base_url'):
                    old_url = getattr(config, 'base_url', None)
                    config.base_url = qwen_base_url
                    print(f"[Wrapper] 已更新 config.base_url: {old_url} -> {qwen_base_url}")
                    updated = True
            except Exception as e:
                print(f"[Wrapper] 无法更新 config: {e}")
        
        # 方法5: 尝试调用 _create_client 重新创建 client（如果存在）
        if hasattr(llm_service, '_create_client'):
            try:
                print(f"[Wrapper] 尝试调用 _create_client 重新创建 client...")
                # 先更新 config_manager 的配置（_create_client 会从 config_manager 读取）
                from pixelle_video.config import config_manager
                if hasattr(config_manager, 'config') and hasattr(config_manager.config, 'llm'):
                    config_manager.config.llm.api_key = api_key
                    config_manager.config.llm.base_url = qwen_base_url
                    config_manager.config.llm.model = qwen_model
                    print(f"[Wrapper] 已更新 config_manager.config.llm: api_key, base_url, model")
                
                # 调用 _create_client 重新创建（传入参数确保使用正确的配置）
                new_client = llm_service._create_client(api_key=api_key, base_url=qwen_base_url)
                if new_client:
                    llm_service._client = new_client
                    print(f"[Wrapper] 已通过 _create_client 重新创建 client (api_key={api_key[:10]}..., base_url={qwen_base_url})")
                    updated = True
            except Exception as e:
                print(f"[Wrapper] 无法调用 _create_client: {e}")
                import traceback
                print(f"[Wrapper] _create_client 错误详情: {traceback.format_exc()}")
        
        # 方法6: 尝试通过环境变量强制设置（作为后备方案）
        if not updated:
            print(f"[Wrapper] 警告: 所有直接设置方法都失败了，尝试环境变量...")
            # 尝试通过环境变量强制设置
            os.environ["OPENAI_API_KEY"] = api_key
            os.environ["OPENAI_BASE_URL"] = qwen_base_url
            os.environ["OPENAI_MODEL"] = qwen_model
            print(f"[Wrapper] 已设置环境变量: OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL")
        
        # 方法7: 尝试通过 _get_config_value 更新配置（如果存在）
        if hasattr(llm_service, '_get_config_value'):
            try:
                print(f"[Wrapper] 尝试通过 _get_config_value 检查配置...")
                # 这个方法可能用于读取配置，我们需要确保环境变量已设置
                model_from_config = llm_service._get_config_value('model', qwen_model)
                base_url_from_config = llm_service._get_config_value('base_url', qwen_base_url)
                api_key_from_config = llm_service._get_config_value('api_key', api_key)
                print(f"[Wrapper] 配置值: model={model_from_config}, base_url={base_url_from_config}, api_key={api_key_from_config[:10] if api_key_from_config else 'None'}...")
            except Exception as e:
                print(f"[Wrapper] 无法通过 _get_config_value 检查配置: {e}")
        
        print(f"[Wrapper] ========== LLM 服务配置更新完成 ==========")
        
    except Exception as e:
        print(f"[Wrapper] 更新 LLM 服务配置失败: {e}")
        import traceback
        print(f"[Wrapper] 错误详情: {traceback.format_exc()}")

async def init_pixelle_video():
    """初始化 Pixelle-Video 核心服务"""
    global _pixelle_video
    
    if not PIXELLE_AVAILABLE:
        raise RuntimeError("Pixelle-Video 不可用，请检查导入路径")
    
    if _pixelle_video is None:
        print("[Wrapper] 正在初始化 Pixelle-Video...")
        
        # 确保 API Key 在环境变量中（必须在初始化前设置！）
        api_key = CURRENT_STATE.get("api_key") or os.environ.get("PIXELLE_API_KEY")
        if api_key:
            os.environ["PIXELLE_API_KEY"] = api_key
            os.environ["OPENAI_API_KEY"] = api_key  # 强制设置，覆盖默认值
            print(f"[Wrapper] 初始化前设置 OPENAI_API_KEY (长度: {len(api_key)})")
            print(f"[Wrapper] OPENAI_API_KEY 前10个字符: {api_key[:10]}...")
        
        # 尝试通过 config_manager 设置 API Key 和模型配置（在初始化前）
        try:
            from pixelle_video.config import config_manager
            if hasattr(config_manager, 'config'):
                if api_key:
                    # 尝试设置各种可能的配置路径
                    if hasattr(config_manager.config, 'api_keys'):
                        if not isinstance(config_manager.config.api_keys, dict):
                            config_manager.config.api_keys = {}
                        config_manager.config.api_keys['openai'] = api_key
                        config_manager.config.api_keys['default'] = api_key
                        config_manager.config.api_keys['qwen'] = api_key  # Qwen 模型
                        print(f"[Wrapper] 已通过 config_manager.config.api_keys 设置 API Key")
                    
                    # 尝试直接设置 config 属性
                    if hasattr(config_manager.config, 'openai_api_key'):
                        config_manager.config.openai_api_key = api_key
                        print(f"[Wrapper] 已设置 config_manager.config.openai_api_key")
                    
                    if hasattr(config_manager.config, 'api_key'):
                        config_manager.config.api_key = api_key
                        print(f"[Wrapper] 已设置 config_manager.config.api_key")
                    
                    # 配置 Qwen 模型（与交付版一致）
                    if hasattr(config_manager.config, 'llm'):
                        if not hasattr(config_manager.config.llm, '__dict__'):
                            try:
                                setattr(config_manager.config.llm, 'model', 'qwen3.8-max')
                                setattr(config_manager.config.llm, 'provider', 'qwen')
                                print(f"[Wrapper] 已设置模型为 qwen3.8-max")
                            except Exception:
                                pass
                    
                    if hasattr(config_manager.config, 'model'):
                        config_manager.config.model = 'qwen3.8-max'
                        print(f"[Wrapper] 已设置 config.model 为 qwen3.8-max")
                    
                    if hasattr(config_manager.config, 'llm_model'):
                        config_manager.config.llm_model = 'qwen3.8-max'
                        print(f"[Wrapper] 已设置 config.llm_model 为 qwen3.8-max")
        except Exception as e:
            print(f"[Wrapper] 通过 config_manager 设置配置失败: {e}")
            import traceback
            print(f"[Wrapper] 错误详情: {traceback.format_exc()}")
        
        _pixelle_video = PixelleVideoCore()
        await _pixelle_video.initialize()
        
        # 初始化后，配置 RunningHub 云端服务（使用云端，不使用本地 ComfyUI）
        try:
            from pixelle_video.config import config_manager
            if hasattr(config_manager, 'config') and hasattr(config_manager.config, 'comfyui'):
                # 1. 设置 image workflow 为 RunningHub 云端
                image_workflow = getattr(config_manager.config.comfyui.image, 'default_workflow', None)
                if not image_workflow or not image_workflow.startswith('runninghub/'):
                    try:
                        config_manager.config.comfyui.image.default_workflow = "runninghub/image_flux.json"
                        print(f"[Wrapper] 已设置 image workflow: runninghub/image_flux.json (云端)")
                    except Exception as e:
                        print(f"[Wrapper] 无法设置 image workflow: {e}")
                else:
                    print(f"[Wrapper] image workflow 已配置: {image_workflow}")
                
                # 2. 设置 video workflow 为 RunningHub 云端（如果需要）
                video_workflow = getattr(config_manager.config.comfyui.video, 'default_workflow', None)
                if not video_workflow or not video_workflow.startswith('runninghub/'):
                    try:
                        config_manager.config.comfyui.video.default_workflow = "runninghub/video_wan2.1_fusionx.json"
                        print(f"[Wrapper] 已设置 video workflow: runninghub/video_wan2.1_fusionx.json (云端)")
                    except Exception as e:
                        print(f"[Wrapper] 无法设置 video workflow: {e}")
                else:
                    print(f"[Wrapper] video workflow 已配置: {video_workflow}")
                
                # 3. 确保 RunningHub API Key 已设置（优先使用从config.yaml读取的）
                runninghub_key_from_config = getattr(config_manager.config.comfyui, 'runninghub_api_key', None)
                if not runninghub_key_from_config:
                    # 尝试从 config.yaml 文件直接读取
                    try:
                        import yaml
                        config_yaml_path = find_config_yaml()
                        if config_yaml_path:
                            with open(config_yaml_path, 'r', encoding='utf-8') as f:
                                yaml_config = yaml.safe_load(f)
                                if yaml_config and 'comfyui' in yaml_config:
                                    yaml_runninghub_key = yaml_config['comfyui'].get('runninghub_api_key', '').strip()
                                    if yaml_runninghub_key:
                                        config_manager.config.comfyui.runninghub_api_key = yaml_runninghub_key
                                        print(f"[Wrapper] 已从 config.yaml 读取 RunningHub API Key (长度: {len(yaml_runninghub_key)})")
                                        runninghub_key_from_config = yaml_runninghub_key
                    except Exception as e:
                        print(f"[Wrapper] 无法从 config.yaml 读取 RunningHub API Key: {e}")
                
                # 使用从init_pixelle_video读取的runninghub_key（如果存在）
                global _runninghub_key_from_config
                if _runninghub_key_from_config and _runninghub_key_from_config.strip():
                    config_manager.config.comfyui.runninghub_api_key = _runninghub_key_from_config
                    print(f"[Wrapper] 使用初始化时读取的RunningHub Key (长度: {len(_runninghub_key_from_config)})")
                    runninghub_key_from_config = _runninghub_key_from_config
                
                if runninghub_key_from_config and runninghub_key_from_config.strip():
                    print(f"[Wrapper] [OK] RunningHub API Key 已配置 (长度: {len(runninghub_key_from_config)})")
                else:
                    print(f"[Wrapper] [警告] RunningHub API Key 未配置，图片生成可能会失败")
                    print(f"[Wrapper] 提示: 请在 config.yaml 中设置 comfyui.runninghub_api_key")
                
                # 4. 确保 comfyui_url 为空或指向云端（不使用本地 ComfyUI）
                comfyui_url = getattr(config_manager.config.comfyui, 'comfyui_url', None)
                if comfyui_url and comfyui_url.startswith('http://localhost') or comfyui_url.startswith('http://127.0.0.1'):
                    try:
                        config_manager.config.comfyui.comfyui_url = None  # 使用云端，不设置本地 URL
                        print(f"[Wrapper] 已清除本地 ComfyUI URL，使用云端服务")
                    except Exception as e:
                        print(f"[Wrapper] 无法清除本地 ComfyUI URL: {e}")
                else:
                    print(f"[Wrapper] ComfyUI URL 配置: {comfyui_url or '使用云端服务'}")
                
                # 5. 设置 TTS 的 default_workflow（用于语音克隆）
                if hasattr(config_manager.config.comfyui, 'tts'):
                    tts_workflow = getattr(config_manager.config.comfyui.tts, 'default_workflow', None)
                    if not tts_workflow or not tts_workflow.startswith('runninghub/'):
                        try:
                            # 使用 runninghub/tts_index2.json，这个workflow支持语音克隆
                            config_manager.config.comfyui.tts.default_workflow = "runninghub/tts_index2.json"
                            print(f"[Wrapper] 已设置 TTS workflow: runninghub/tts_index2.json (支持语音克隆)")
                        except Exception as e:
                            print(f"[Wrapper] 无法设置 TTS workflow: {e}")
                    else:
                        print(f"[Wrapper] TTS workflow 已配置: {tts_workflow}")
        except Exception as e:
            print(f"[Wrapper] 配置 RunningHub 云端服务时出错: {e}")
            import traceback
            print(f"[Wrapper] 错误详情: {traceback.format_exc()}")
        
        # 初始化后，尝试直接更新 LLM 服务的 API Key、base_url 和 model
        _update_llm_service_config(api_key)
        
        # RunningHub：新 Key 对旧 /task/openapi/upload 会 401，先打上传补丁
        try:
            from runninghub_upload_patch import apply_runninghub_upload_patch
            apply_runninghub_upload_patch()
        except Exception as e:
            print(f"[Wrapper] [警告] RunningHub 上传补丁未生效: {e}")

        # 验证RunningHub连接（尝试获取ComfyKit实例）
        try:
            print("[Wrapper] 正在验证RunningHub连接...")
            kit = await _pixelle_video._get_or_create_comfykit()
            if kit:
                print("[Wrapper] [OK] RunningHub ComfyKit 连接成功")
                print(f"[Wrapper] [OK] ComfyKit类型: {type(kit)}")
            else:
                print("[Wrapper] [警告] RunningHub ComfyKit 连接失败（返回None）")
        except Exception as e:
            print(f"[Wrapper] [警告] RunningHub ComfyKit 连接检查失败: {e}")
            import traceback
            traceback.print_exc()
        
        print("[Wrapper] [OK] Pixelle-Video 初始化完成")
        print("[Wrapper] [OK] 所有服务已就绪，可以开始生成")

# ============================================================================
# API 接口实现（新加的代码）
# ============================================================================

@app.get("/health")
async def health_check():
    """
    健康检查接口（仅检查FastAPI服务）
    
    返回：
        {"status": "ok"}
    """
    return {"status": "ok"}


# --- Web「自动化」页：HF 抖音私信 / 环境检查（仅本组接口，勿与主流程混用）---
_HF_WRAPPER_ROOT = _resolve_pixelle_wrapper_dir()
_HF_STATS_JSON = _HF_WRAPPER_ROOT / "output" / "hf_dm_reply_stats.json"
_hf_dm_lock = threading.Lock()


def _ensure_hf_wrapper_on_syspath() -> None:
    """把 pixelle_wrapper、安装根、runtime site-packages 加入 sys.path，确保 HF / selenium 可 import。
    从项目根启动或杀软延迟解锁 .pyd 时，多路径可减少「检测红、实际又能跑」的错觉。"""
    p = str(_HF_WRAPPER_ROOT.resolve())
    if p not in sys.path:
        sys.path.insert(0, p)
    try:
        pr = str(PROJECT_ROOT.resolve())
        if pr not in sys.path:
            sys.path.insert(0, pr)
        _sp = PROJECT_ROOT / "runtime_env" / "python" / "Lib" / "site-packages"
        if _sp.is_dir():
            sps = str(_sp.resolve())
            if sps not in sys.path:
                sys.path.insert(0, sps)
    except Exception:
        pass
_hf_dm_task: Dict[str, Any] = {"running": False, "queued": False, "last_exit": None, "last_err": None}
# 下一次 HF 线程使用的拟人停顿（秒）；在启动线程前写入
_hf_dm_next_min_pause: float = 3.0
_hf_dm_next_max_pause: float = 5.0
# 下一次运行合并到 hf_auto_reply 的人设占位符（与文案页 personaConfig 对齐）
_hf_dm_next_persona_kb: Optional[Dict[str, str]] = None


class HfDmPersonaUI(BaseModel):
    """与「文案创作」人设弹窗保存的 personaConfig 字段一致，由前端随 run_once / 截流 传入。"""

    consumptionRange: str = ""
    wechatId: str = ""
    companyName: str = ""
    targetMarket: str = ""
    coreSolution: str = ""
    companyAddress: str = ""
    productYears: str = ""
    productAdvantages: str = ""
    other: str = ""
    # 截流脚本用（私信自动回复忽略即可）
    industryKeywords: str = ""
    commentExample: str = ""
    intentKeywords: str = ""


class HfDmRunOnceBody(BaseModel):
    """POST /api/hf_dm/run_once：quick、人设与「开启自动回复」定时任务保持一致。"""

    quick: bool = False
    persona: Optional[HfDmPersonaUI] = None


def _hf_persona_ui_to_kb(ui: Optional[HfDmPersonaUI]) -> Optional[Dict[str, str]]:
    """将前端人设转为 hf_auto_reply 模板占位符键（与 _load_persona_from_config 一致）。"""
    if ui is None:
        return None
    d = ui.model_dump() if hasattr(ui, "model_dump") else ui.dict()
    parts = [str(d.get("coreSolution") or "").strip(), str(d.get("productAdvantages") or "").strip()]
    kf = "\n".join(p for p in parts if p)
    kb = {
        "priceRange": str(d.get("consumptionRange") or "").strip(),
        "wechatId": str(d.get("wechatId") or "").strip(),
        "companyName": str(d.get("companyName") or "").strip(),
        "serviceRegion": str(d.get("targetMarket") or "").strip(),
        "targetAudience": str(d.get("targetMarket") or "").strip(),
        "companyAddress": str(d.get("companyAddress") or "").strip(),
        "businessYear": str(d.get("productYears") or "").strip(),
        "keyFeatures": kf,
        "relatedNotes": str(d.get("other") or "").strip(),
    }
    if not any(v for v in kb.values()):
        return None
    return kb


def _intercept_persona_overlay_from_ui(ui: Optional[HfDmPersonaUI]) -> Dict[str, str]:
    """合并 HF 人设键与截流专用键，写入 overlay JSON；空字段不写。"""
    base = _hf_persona_ui_to_kb(ui)
    out: Dict[str, str] = dict(base) if base else {}
    if ui is None:
        return out
    d = ui.model_dump() if hasattr(ui, "model_dump") else ui.dict()
    ik = str(d.get("industryKeywords") or "").strip()
    if ik:
        out["industryKeywords"] = ik
    ce = str(d.get("commentExample") or "").strip()
    if ce:
        out["commentExample"] = ce
    it = str(d.get("intentKeywords") or "").strip()
    if it:
        out["intentKeywordsCustom"] = it
    return out


# --- Web「挖掘客户」：子进程跑 test_intercept_selenium（交付包 compileall -b 后仅保留 .pyc） ---
_INTERCEPT_LOG_MAX = 500
_intercept_lock = threading.Lock()
# 截流子进程与 HF 自动回复共用同一 Chrome user-data-dir，严禁并行；一方持锁至本轮结束（HF 一轮 / 截流子进程退出）
_browser_automation_lock = threading.Lock()
_intercept_proc: Optional[subprocess.Popen] = None
_intercept_log: deque = deque(maxlen=_INTERCEPT_LOG_MAX)

# --- 发布期调度控制 ---
# publish 开始后：新起的截流/HF 等待；同时可通过终止截流子进程来尽快释放浏览器锁。
# 通过 publish_batch_id 将多平台发布聚合成一次“发布批次”，批次完成后再补一次 HF 回复并恢复截流。
_publish_active = threading.Event()
_publish_batch_lock = threading.Lock()
_publish_batch_remaining: Dict[str, int] = {}


def _wait_publish_subbatch_done(batch_id: str, timeout: float = 900.0) -> bool:
    """
    等待单次 /api/publish/* 对应的后台线程跑完（该 batch_id 从 _publish_batch_remaining 中清除）。
    用于自动化流水线内多平台严格串行：上一平台结束后再请求下一平台，避免多线程抢锁顺序不确定。
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        with _publish_batch_lock:
            if batch_id not in _publish_batch_remaining:
                return True
        time.sleep(1.0)
    logger.warning("[PublishBatch] 等待子批次完成超时: %s", batch_id)
    return False


def _run_global_publish_teardown(hf_enabled: bool, mining_enabled: bool) -> None:
    """整波发布结束：清发布态、按需恢复 HF / 截流（与各 publish 线程 finally 逻辑一致）。"""
    try:
        _publish_active.clear()
        if hf_enabled:
            with _hf_dm_lock:
                _hf_dm_next_min_pause = 1.2
                _hf_dm_next_max_pause = 2.0
                if _hf_dm_task.get("running"):
                    _hf_dm_task["queued"] = True
                else:
                    t = threading.Thread(target=_hf_dm_worker_loop, daemon=True)
                    t.start()
        if mining_enabled and _intercept_should_run and _intercept_last_body is not None:
            threading.Thread(
                target=_intercept_start_sync,
                args=(_intercept_last_body,),
                daemon=True,
            ).start()
    except Exception:
        pass

# --- 截流恢复所需状态 ---
_intercept_should_run: bool = False
_intercept_last_body: Optional[Any] = None

_INTERCEPT_SCRIPT_PY = _HF_WRAPPER_ROOT / "test_intercept_selenium.py"
_INTERCEPT_SCRIPT_PYC = _HF_WRAPPER_ROOT / "test_intercept_selenium.pyc"
_INTERCEPT_OVERLAY_JSON = _HF_WRAPPER_ROOT / "output" / "intercept_persona_overlay.json"
_INTERCEPT_DM_JSONL = _HF_WRAPPER_ROOT / "data" / "dm_sent.jsonl"
_INTERCEPT_COMMENT_JSONL = _HF_WRAPPER_ROOT / "data" / "intercept_comments.jsonl"


class InterceptStartBody(BaseModel):
    human_delay_min: float = 3.0
    human_delay_max: float = 7.0
    start_delay_seconds: float = 0.0
    ai_intent: bool = True
    persona: Optional[HfDmPersonaUI] = None


def _resolve_intercept_script_path() -> Optional[Path]:
    """开发环境多为 .py；发布目录 compileall -b 后删除 .py，仅保留同目录 .pyc。"""
    if _INTERCEPT_SCRIPT_PY.is_file():
        return _INTERCEPT_SCRIPT_PY
    if _INTERCEPT_SCRIPT_PYC.is_file():
        return _INTERCEPT_SCRIPT_PYC
    return None


def _hf_dm_is_running_sync() -> bool:
    with _hf_dm_lock:
        return bool(_hf_dm_task.get("running"))


def _intercept_subprocess_alive_sync() -> bool:
    """截流子进程仍在跑（已结束的会 reap 掉）。"""
    _intercept_reap_if_done()
    with _intercept_lock:
        p = _intercept_proc
        return p is not None and p.poll() is None


def _intercept_reap_if_done() -> None:
    global _intercept_proc
    with _intercept_lock:
        p = _intercept_proc
        if p is None:
            return
        if p.poll() is not None:
            rc = int(p.returncode if p.returncode is not None else -1)
            _intercept_proc = None
            _intercept_log.append(f"[系统] 截流进程已结束，退出码 {rc}")


def _intercept_count_jsonl_success_on_date(path: Path, day_prefix: str) -> int:
    c = 0
    if not path.is_file():
        return 0
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            if o.get("success") is False:
                continue
            ts = str(o.get("ts") or "")
            if len(ts) >= 10 and ts[:10] == day_prefix[:10]:
                c += 1
    except Exception:
        return c
    return c


def _intercept_count_jsonl_success_total(path: Path) -> int:
    c = 0
    if not path.is_file():
        return 0
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            if o.get("success") is False:
                continue
            c += 1
    except Exception:
        return c
    return c


def _intercept_reader_loop(proc: subprocess.Popen) -> None:
    try:
        stdout = proc.stdout
        if stdout is None:
            return
        for line in stdout:
            line = (line or "").rstrip("\n\r")
            if line:
                with _intercept_lock:
                    _intercept_log.append(line)
    except Exception as e:
        with _intercept_lock:
            _intercept_log.append(f"[系统] 日志读取异常: {str(e)[:200]}")


def _humanize_intercept_log_line(line: str) -> Optional[str]:
    """
    把截流子进程 stdout 的“代码/星号/Traceback”过滤掉，只保留客户看得懂的步骤描述。
    """
    s = (line or "").strip()
    if not s:
        return None

    # 纯星号/分隔线类噪声直接丢弃
    if len(s) >= 3 and set(s) <= set("*-=_"):
        return None

    # Python 报错与堆栈丢弃（对客户不可读）
    if "Traceback" in s or "File \"" in s or s.startswith("  File "):
        return None

    # selenium/chromedriver 常见噪声丢弃
    sl = s.lower()
    if "selenium" in sl and ("exception" in sl or "error" in sl or "traceback" in sl):
        return None
    if "chromedriver" in sl and ("error" in sl or "warning" in sl):
        return None

    # 业务关键日志：保留后处理过的标签消息
    if "[SeleniumIntercept]" in s:
        return s.replace("[SeleniumIntercept] ", "")

    # 系统提示保留
    if s.startswith("[系统]"):
        return s

    # 其它：尽量保留“动作步骤”相关的自然语言
    key_words = ["打开", "搜索", "点击", "已点击", "筛选", "视频", "私信", "评论", "结束", "运行", "完成", "结束", "跳过", "等待"]
    if any(k in s for k in key_words):
        return s

    return None


def _intercept_start_sync(body: InterceptStartBody) -> Dict[str, Any]:
    """
    启动截流子进程。与 HF 自动回复互斥：先等 HF 跑完，再占 _browser_automation_lock 直至子进程退出（由守护线程 wait 后 release）。
    """
    global _intercept_proc
    _intercept_reap_if_done()
    # 发布期：等待发布批次结束，避免浏览器自动化抢占
    while _publish_active.is_set():
        time.sleep(0.5)

    # 记录“期望运行状态”（用于发布结束后自动恢复）
    global _intercept_should_run, _intercept_last_body
    _intercept_should_run = True
    _intercept_last_body = body

    while _hf_dm_is_running_sync():
        time.sleep(1.5)

    _browser_automation_lock.acquire()
    release_via_wait_thread = False
    try:
        with _intercept_lock:
            if _intercept_proc is not None and _intercept_proc.poll() is None:
                return {"ok": False, "message": "截流已在运行中", "running": True}
            intercept_script = _resolve_intercept_script_path()
            if intercept_script is None:
                return {
                    "ok": False,
                    "message": (
                        "未找到截流脚本（已查找 .py / .pyc）: "
                        f"{_INTERCEPT_SCRIPT_PY} 或 {_INTERCEPT_SCRIPT_PYC}"
                    ),
                    "running": False,
                }

        lo = max(0.0, float(body.human_delay_min))
        hi = max(lo, float(body.human_delay_max))
        sd = max(0.0, float(body.start_delay_seconds or 0.0))
        cmd: List[str] = [
            sys.executable,
            str(intercept_script),
            "--human-delay-min",
            str(lo),
            "--human-delay-max",
            str(hi),
            "--start-delay-seconds",
            str(sd),
        ]
        if body.ai_intent:
            cmd.append("--ai-intent")
        overlay = _intercept_persona_overlay_from_ui(body.persona)
        out_dir = _HF_WRAPPER_ROOT / "output"
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return {"ok": False, "message": f"无法创建 output 目录: {e}", "running": False}
        if overlay:
            try:
                _INTERCEPT_OVERLAY_JSON.write_text(
                    json.dumps(overlay, ensure_ascii=False),
                    encoding="utf-8",
                )
                cmd.extend(["--persona-overlay-json", str(_INTERCEPT_OVERLAY_JSON)])
            except Exception as e:
                return {"ok": False, "message": f"写入人设覆盖文件失败: {e}", "running": False}

        flags = 0
        if sys.platform == "win32":
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        sub_env = os.environ.copy()
        sub_env["INTERCEPT_WDM_FIRST"] = "0"
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(_HF_WRAPPER_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=flags,
                env=sub_env,
            )
        except Exception as e:
            return {"ok": False, "message": str(e)[:400], "running": False}

        with _intercept_lock:
            if _intercept_proc is not None and _intercept_proc.poll() is None:
                try:
                    proc.terminate()
                except OSError:
                    pass
                return {"ok": False, "message": "截流已在运行中", "running": True}
            _intercept_proc = proc

        def _intercept_wait_release_lock() -> None:
            try:
                proc.wait()
            except Exception:
                pass
            finally:
                try:
                    _browser_automation_lock.release()
                except RuntimeError:
                    pass

        threading.Thread(target=_intercept_reader_loop, args=(proc,), daemon=True).start()
        threading.Thread(target=_intercept_wait_release_lock, daemon=True).start()
        release_via_wait_thread = True
        with _intercept_lock:
            _intercept_log.clear()
            _intercept_log.append(f"[系统] 已启动截流子进程 (PID {proc.pid})")
        return {"ok": True, "message": "已启动", "running": True, "pid": proc.pid}
    finally:
        if not release_via_wait_thread:
            try:
                _browser_automation_lock.release()
            except RuntimeError:
                pass


def _intercept_stop_sync() -> Dict[str, Any]:
    global _intercept_proc
    _intercept_reap_if_done()
    with _intercept_lock:
        p = _intercept_proc
        if p is None:
            return {"ok": True, "message": "当前无运行中的截流", "running": False}
        if p.poll() is not None:
            _intercept_proc = None
            return {"ok": True, "message": "进程已结束", "running": False}
        try:
            p.terminate()
        except Exception as e:
            return {"ok": False, "message": str(e)[:200], "running": True}
    try:
        p.wait(timeout=10.0)
    except subprocess.TimeoutExpired:
        try:
            p.kill()
        except Exception:
            pass
    with _intercept_lock:
        _intercept_proc = None
        _intercept_log.append("[系统] 已请求停止截流")

    # 用户主动关闭截流：不再在发布结束后自动恢复
    global _intercept_should_run, _intercept_last_body
    _intercept_should_run = False
    _intercept_last_body = None
    return {"ok": True, "message": "已停止", "running": False}


@app.post("/api/intercept/start")
async def api_intercept_start(body: Optional[InterceptStartBody] = Body(default=None)):
    """启动 test_intercept_selenium 子进程；人设来自文案页 personaConfig（可选覆盖 config.yaml）。"""
    await asyncio.sleep(0)
    b = body if body is not None else InterceptStartBody()
    return await asyncio.to_thread(_intercept_start_sync, b)


@app.post("/api/intercept/stop")
async def api_intercept_stop():
    await asyncio.sleep(0)
    return await asyncio.to_thread(_intercept_stop_sync)


@app.get("/api/intercept/status")
async def api_intercept_status():
    await asyncio.sleep(0)
    _intercept_reap_if_done()
    with _intercept_lock:
        p = _intercept_proc
        running = p is not None and p.poll() is None
        pid = p.pid if running and p else None
        logs = list(_intercept_log)

    raw_tail = logs[-120:]
    formatted: List[str] = []
    for l in raw_tail:
        nl = _humanize_intercept_log_line(l)
        if nl:
            formatted.append(nl)

    # 如果过滤后过少，至少返回最近一些原始行，避免 UI 空白
    if not formatted:
        formatted = raw_tail[-20:]

    return {"running": running, "pid": pid, "logs": formatted[-120:]}


@app.get("/api/intercept/stats")
async def api_intercept_stats():
    """今日/累计：私信成功、评论成功（与截流 jsonl 一致）；曝光未对接，另返回说明。"""
    await asyncio.sleep(0)
    day = time.strftime("%Y-%m-%d")
    today_dm = _intercept_count_jsonl_success_on_date(_INTERCEPT_DM_JSONL, day)
    today_comment = _intercept_count_jsonl_success_on_date(_INTERCEPT_COMMENT_JSONL, day)
    total_dm = _intercept_count_jsonl_success_total(_INTERCEPT_DM_JSONL)
    total_comment = _intercept_count_jsonl_success_total(_INTERCEPT_COMMENT_JSONL)
    return {
        "calendar_date": day,
        "today_dm": today_dm,
        "today_comment": today_comment,
        "total_dm": total_dm,
        "total_comment": total_comment,
        "play_count_note": "播放量/曝光未对接 DOM，日志与 jsonl 中 play_count 恒为 0",
    }


def _hf_dm_customer_env_summary(out: Dict[str, Any]) -> List[str]:
    """给客户看的自然语言环境结论：全通过时简短明确；有失败时只列硬性未通过项。"""
    lines: List[str] = []
    if out.get("all_ok"):
        lines.append("检测完成：自动回复环境正常，可以直接使用。")
        # 非硬性项未通过时给一句安抚，避免客户以为「又不正常了」
        soft_issues: List[str] = []
        if not out.get("psutil_ok"):
            soft_issues.append("系统进程辅助")
        if not out.get("webdriver_manager_ok"):
            soft_issues.append("在线驱动下载")
        if soft_issues:
            lines.append(
                "提示："
                + "、".join(soft_issues)
                + "检测未通过，一般不影响私信自动回复；若其它功能异常再联系技术支持。"
            )
        return lines

    problems: List[str] = []
    if not out.get("hf_module_ok"):
        problems.append("未找到私信自动回复程序文件，请确认安装包完整。")
    elif not out.get("hf_import_ok"):
        problems.append("私信自动回复程序无法加载，请重新安装或联系技术支持。")
    if not out.get("selenium_ok"):
        problems.append("浏览器自动化环境未就绪，请按安装说明补全依赖。")
    if not out.get("douyin_publish_mcp_ok"):
        problems.append("抖音浏览器组件未就绪，请确认软件为完整安装版。")
    if not (out.get("pyyaml_ok") and out.get("requests_ok")):
        problems.append("配置或网络相关依赖未就绪，请检查安装是否完整。")
    if not out.get("output_dir_ok"):
        problems.append("回复数据无法写入磁盘，请检查安装目录权限或磁盘空间。")

    lines.append("检测完成：以下问题需要先处理，否则自动回复可能无法使用。")
    lines.extend(problems)
    if not problems:
        lines.append("存在未知异常，请重新安装软件包或联系技术支持。")
    return lines


def _hf_dm_module_resolvable() -> bool:
    """打包后仅有 hf_auto_reply.pyc 时也应为 True。"""
    p = _HF_WRAPPER_ROOT / "hf_auto_reply.py"
    c = _HF_WRAPPER_ROOT / "hf_auto_reply.pyc"
    return p.is_file() or c.is_file()


def _hf_dm_worker_loop() -> None:
    """
    后台线程：同进程执行 HF，复用 douyin_publish_mcp 全局浏览器（与登录/发布同一实例）。
    单次任务结束后 quit_browser=True，与独立脚本一致关闭窗口；下次 ensure_driver 仍用同一持久化
    user-data-dir（browser_data/chrome_user_data），一般仍保持站点登录态。
    若排队则连续跑第二轮（允许排队，最多多跑 1 次）。

    与「挖掘客户」截流子进程互斥：每轮开始前占 _browser_automation_lock，并等待截流子进程结束，
    避免与截流并行占用同一 Chrome user-data-dir。
    """
    import importlib

    while True:
        do_again = False
        # 发布期：等待发布批次结束后再执行 HF
        while _publish_active.is_set():
            time.sleep(0.5)
        _browser_automation_lock.acquire()
        try:
            while _intercept_subprocess_alive_sync():
                time.sleep(1.5)

            with _hf_dm_lock:
                _hf_dm_task["running"] = True
                _hf_dm_task["last_err"] = None
            try:
                if not _hf_dm_module_resolvable():
                    with _hf_dm_lock:
                        _hf_dm_task["last_err"] = "missing hf_auto_reply module (.py/.pyc)"
                        _hf_dm_task["last_exit"] = -1
                else:
                    _ensure_hf_wrapper_on_syspath()
                    hf = importlib.import_module("hf_auto_reply")
                    with _hf_dm_lock:
                        mp = float(_hf_dm_next_min_pause)
                        xp = float(_hf_dm_next_max_pause)
                        kb = dict(_hf_dm_next_persona_kb) if _hf_dm_next_persona_kb else None
                    hf.run_hf_dm_once_shared(
                        setup_log=False,
                        quit_browser=True,
                        min_pause=mp,
                        max_pause=xp,
                        persona_kb_override=kb,
                    )
                    with _hf_dm_lock:
                        _hf_dm_task["last_exit"] = 0
            except Exception as e:
                with _hf_dm_lock:
                    _hf_dm_task["last_exit"] = -1
                    _hf_dm_task["last_err"] = str(e)[:800]
            finally:
                with _hf_dm_lock:
                    _hf_dm_task["running"] = False
                    do_again = bool(_hf_dm_task.get("queued"))
                    if do_again:
                        _hf_dm_task["queued"] = False
        finally:
            _browser_automation_lock.release()

        if not do_again:
            break


@app.get("/api/hf_dm/stats")
async def api_hf_dm_stats():
    """读取 output/hf_dm_reply_stats.json（自然日今日 / 累计）。"""
    await asyncio.sleep(0)
    if not _HF_STATS_JSON.is_file():
        return {"calendar_date": "", "today_replies": 0, "total_replies": 0, "exists": False}
    try:
        data = json.loads(_HF_STATS_JSON.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
        return {
            "exists": True,
            "calendar_date": str(data.get("calendar_date", "") or ""),
            "today_replies": int(data.get("today_replies", 0) or 0),
            "total_replies": int(data.get("total_replies", 0) or 0),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200])


def _hf_retry_import(fn, *, attempts: int = 6) -> tuple[bool, str]:
    """冷启动/杀软扫盘时 import 可能偶发失败，短重试可减少「一会行一会不行」。"""
    last_err = ""
    for i in range(attempts):
        try:
            fn()
            return True, ""
        except Exception as e:
            last_err = str(e)[:240]
            time.sleep(0.18 * (i + 1))
    return False, last_err


def _hf_dm_env_check_sync() -> Dict[str, Any]:
    """同步环境探测（须在线程中运行，避免阻塞 uvicorn 事件循环）。"""
    # 必须先保证本目录在 path 上，否则 `import douyin_publish_mcp` / `hf_auto_reply`
    # 在「从项目根起服务」时会误失败，进而整页红框（实际 worker 里会先 ensure 故能跑）。
    _ensure_hf_wrapper_on_syspath()
    try:
        pr = str(PROJECT_ROOT.resolve())
        if pr not in sys.path:
            sys.path.insert(0, pr)
    except Exception:
        pass
    out: Dict[str, Any] = {
        "hf_module_ok": _hf_dm_module_resolvable(),
        "shared_browser_note": "HF 与登录/发布共用 douyin_publish_mcp 单例浏览器（同进程，不另起 Chrome）",
        "python_exe": sys.executable,
        "selenium_ok": False,
        "pyyaml_ok": False,
        "requests_ok": False,
        "psutil_ok": False,
        "webdriver_manager_ok": False,
        "fastmcp_ok": False,
        "douyin_publish_mcp_ok": False,
        "hf_import_ok": False,
        "output_dir_ok": False,
        "output_dir": str(_HF_WRAPPER_ROOT / "output"),
    }
    def _imp_sel():
        import selenium  # noqa: F401

    ok, err = _hf_retry_import(_imp_sel)
    if ok:
        out["selenium_ok"] = True
    else:
        out["selenium_error"] = err
    try:
        import yaml  # noqa: F401

        out["pyyaml_ok"] = True
    except Exception as e:
        out["pyyaml_error"] = str(e)[:200]
    try:
        import requests  # noqa: F401

        out["requests_ok"] = True
    except Exception as e:
        out["requests_error"] = str(e)[:200]
    try:
        import psutil  # noqa: F401

        out["psutil_ok"] = True
    except Exception as e:
        out["psutil_error"] = str(e)[:200]
    try:
        import webdriver_manager  # noqa: F401

        out["webdriver_manager_ok"] = True
    except Exception as e:
        out["webdriver_manager_error"] = str(e)[:200]
    try:
        import fastmcp  # noqa: F401

        out["fastmcp_ok"] = True
    except Exception as e:
        out["fastmcp_error"] = str(e)[:200]

    def _imp_douyin():
        import douyin_publish_mcp  # noqa: F401

    ok, err = _hf_retry_import(_imp_douyin)
    if ok:
        out["douyin_publish_mcp_ok"] = True
    else:
        out["douyin_publish_mcp_error"] = err

    def _imp_hf():
        import importlib

        _ensure_hf_wrapper_on_syspath()
        importlib.import_module("hf_auto_reply")

    ok, err = _hf_retry_import(_imp_hf)
    if ok:
        out["hf_import_ok"] = True
    else:
        out["hf_import_error"] = err
    try:
        od = _HF_WRAPPER_ROOT / "output"
        od.mkdir(parents=True, exist_ok=True)
        testp = od / ".hf_env_write_test"
        testp.write_text("ok", encoding="utf-8")
        try:
            testp.unlink()
        except OSError:
            pass
        out["output_dir_ok"] = True
    except Exception as e:
        out["output_dir_error"] = str(e)[:200]
    # 仅将「私信自动回复实际会用到」的项作为硬性通过条件。
    # psutil / 单独 fastmcp / webdriver_manager 不纳入：hf 不直接用 psutil；douyin 已 import 则已含 fastmcp；
    # 无 webdriver_manager 时仍可用包内 chromedriver，此前任一失败会导致全绿误判为异常。
    out["all_ok"] = bool(
        out["hf_module_ok"]
        and out["hf_import_ok"]
        and out["selenium_ok"]
        and out["pyyaml_ok"]
        and out["requests_ok"]
        and out["douyin_publish_mcp_ok"]
        and out["output_dir_ok"]
    )
    out["customer_messages"] = _hf_dm_customer_env_summary(out)
    return out


@app.get("/api/hf_dm/env_check")
async def api_hf_dm_env_check():
    """检查 HF 与同进程浏览器栈所需环境（与 UI「环境检查」一致）。
    首次偶发失败时自动间隔重测一次，缓解杀软/磁盘延迟导致的误报。"""
    first = await asyncio.to_thread(_hf_dm_env_check_sync)
    if first.get("all_ok"):
        return first
    await asyncio.sleep(0.5)
    second = await asyncio.to_thread(_hf_dm_env_check_sync)
    if second.get("all_ok"):
        return second
    second["env_check_retry"] = True
    second["first_attempt_all_ok"] = False
    return second


@app.get("/api/hf_dm/status")
async def api_hf_dm_status():
    """HF 子进程是否在跑、是否排队。"""
    await asyncio.sleep(0)
    with _hf_dm_lock:
        return dict(_hf_dm_task)


@app.post("/api/hf_dm/run_once")
async def api_hf_dm_run_once(body: Optional[HfDmRunOnceBody] = Body(default=None)):
    """启动一次 hf_auto_reply；若已在运行则标记排队（下一轮）。
    body.quick：true 时步骤间等待 1.2~2.0s（立即执行）；false 为 3~5s（定时自动回复）。
    persona 应与两种入口一致，仅 quick 区分停顿；AI 提示词与回复逻辑在后端相同。
    body.persona：与文案创作页人设一致；与定时任务应传同一内容以保证回复风格一致。
    """
    global _hf_dm_next_min_pause, _hf_dm_next_max_pause, _hf_dm_next_persona_kb
    await asyncio.sleep(0)
    quick = bool(body.quick) if body is not None else False
    kb = _hf_persona_ui_to_kb(body.persona) if body is not None else None
    mp, xp = (1.2, 2.0) if quick else (3.0, 5.0)
    with _hf_dm_lock:
        _hf_dm_next_min_pause = mp
        _hf_dm_next_max_pause = xp
        _hf_dm_next_persona_kb = kb
        if _hf_dm_task["running"]:
            _hf_dm_task["queued"] = True
            return {"ok": True, "queued": True, "message": "已在运行，已排队下一轮", "quick": quick}
        t = threading.Thread(target=_hf_dm_worker_loop, daemon=True)
    t.start()
    return {"ok": True, "queued": False, "quick": quick}


@app.get("/api/current_state")
async def get_current_state():
    """
    查询当前状态（头像、音频、文案等）
    
    返回：
    - avatar_path: 头像路径（如果已上传）
    - audio_path: 音频路径（如果已上传）
    - text: 文案内容（如果已设置）
    - product_path: 产品图片路径（如果已上传）
    - current_task_id: 当前运行中的任务ID（如果有）
    """
    # 使用 asyncio.sleep(0) 让出控制权，避免阻塞
    await asyncio.sleep(0)
    
    avatar_path = CURRENT_STATE.get("avatar_path")
    audio_path = CURRENT_STATE.get("audio_path")
    text = CURRENT_STATE.get("text")
    product_path = CURRENT_STATE.get("product_path")
    bgm_path = CURRENT_STATE.get("background_music_path")

    def _exists(p: Optional[str]) -> bool:
        try:
            return bool(p) and Path(p).exists()
        except Exception:
            return False

    _migrate_legacy_showcase_if_needed()
    _sync_showcase_legacy_path()
    showcase_path = CURRENT_STATE.get("showcase_video_path")
    spaths = _ensure_showcase_paths_list()
    showcase_slots: List[Dict[str, Any]] = []
    for i in range(3):
        p = spaths[i] if i < len(spaths) else None
        ex = _exists(p)
        showcase_slots.append(
            {
                "path": p,
                "exists": ex,
                "uploaded": p is not None,
                "filename": _material_basename(p) if p else None,
            }
        )
    agg_path: Optional[str] = None
    for s in showcase_slots:
        if s.get("path") and s.get("exists"):
            agg_path = str(s["path"])
            break
    if not agg_path:
        for s in showcase_slots:
            if s.get("path"):
                agg_path = str(s["path"])
                break

    avatar_exists = _exists(avatar_path)
    audio_exists = _exists(audio_path)
    product_exists = _exists(product_path)
    showcase_exists = any(bool(s.get("exists")) for s in showcase_slots)
    bgm_exists = _exists(bgm_path)

    # 获取最新的运行中任务ID
    current_task_id = None
    try:
        # 找到最新的运行中任务
        running_tasks = [
            (task_id, task)
            for task_id, task in TASKS.items()
            if task.get("status") == "running"
        ]
        if running_tasks:
            # 按创建时间排序，取最新的
            running_tasks.sort(key=lambda x: x[1].get("created_at", ""), reverse=True)
            current_task_id = running_tasks[0][0]
    except Exception:
        pass

    can_generate_oral = avatar_exists and audio_exists

    return {
        "avatar": {
            "path": avatar_path,
            "exists": avatar_exists,
            "uploaded": avatar_path is not None,
            "filename": _material_basename(avatar_path) if avatar_path else None,
        },
        "audio": {
            "path": audio_path,
            "exists": audio_exists,
            "uploaded": audio_path is not None,
            "filename": _material_basename(audio_path) if audio_path else None,
        },
        "text": {
            "content": text,
            "length": len(text) if text else 0,
            "set": text is not None,
        },
        "product": {
            "path": product_path,
            "exists": product_exists,
            "uploaded": product_path is not None,
            "filename": _material_basename(product_path) if product_path else None,
        },
        "showcase": {
            "path": agg_path or showcase_path,
            "exists": showcase_exists,
            "uploaded": any(s.get("path") is not None for s in showcase_slots),
            "filename": _material_basename(agg_path or showcase_path)
            if (agg_path or showcase_path)
            else None,
        },
        "showcase_slots": showcase_slots,
        "background_music": {
            "path": bgm_path,
            "exists": bgm_exists,
            "uploaded": bgm_path is not None,
            "filename": _material_basename(bgm_path) if bgm_path else None,
        },
        "ready_for_automation": avatar_path is not None and audio_path is not None,
        "can_generate_oral": can_generate_oral,
        "current_task_id": current_task_id,
    }


@app.get("/api/connection_status")
async def connection_status():
    """
    口播/素材生产页用的连接状态：Pixelle + 通义 Key 就绪即标为已连接。
    RunningHub 改为可选（仅影响云端 Comfy），避免因缺一项整页「未连接」。
    若启动时 init 失败，本接口按冷却时间反复尝试懒加载 Pixelle（不会「试几次就放弃」）。
    """
    await asyncio.sleep(0)
    global _pixelle_video, _pixelle_last_lazy_init_attempt

    status: Dict[str, Any] = {
        "status": "disconnected",
        "pixelle_available": PIXELLE_AVAILABLE,
        "qwen_key_configured": False,
        "runninghub_key_configured": False,
        "message": "",
        "details": [],
    }

    if not PIXELLE_AVAILABLE:
        status["message"] = "Pixelle-Video 不可用"
        status["details"].append("请确认安装目录含 Video-main 且依赖完整")
        logger.warning("[连接状态] Pixelle-Video 不可用 path=%s", PIXELLE_VIDEO_PATH)
        return status

    now = time.time()
    if _pixelle_video is None and (now - _pixelle_last_lazy_init_attempt) >= _PIXELLE_LAZY_INIT_COOLDOWN_SEC:
        async with _pixelle_connection_init_lock:
            now2 = time.time()
            if _pixelle_video is None and (now2 - _pixelle_last_lazy_init_attempt) >= _PIXELLE_LAZY_INIT_COOLDOWN_SEC:
                _pixelle_last_lazy_init_attempt = now2
                try:
                    logger.info("[连接状态] 尝试懒加载 Pixelle …")
                    await init_pixelle_video()
                except Exception as e:
                    logger.warning("[连接状态] Pixelle 懒加载失败: %s", e)

    if _pixelle_video is None:
        status["message"] = "Pixelle-Video 未初始化"
        status["details"].append("数字人核心未就绪，请查看后端日志；将自动重试或请重启软件")
        logger.warning("[连接状态] Pixelle-Video 仍未初始化")
        return status

    qwen_key = CURRENT_STATE.get("api_key") or os.environ.get("PIXELLE_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if qwen_key:
        status["qwen_key_configured"] = True
    else:
        status["message"] = "通义千问 API Key 未配置"
        status["details"].append("请在配置中设置 llm.api_key 或环境变量 PIXELLE_API_KEY")
        logger.warning("[连接状态] 通义 API Key 未配置")
        return status

    runninghub_key = None
    try:
        try:
            from pixelle_video.config import config_manager

            if hasattr(config_manager, "config") and hasattr(config_manager.config, "comfyui"):
                runninghub_key = getattr(config_manager.config.comfyui, "runninghub_api_key", None)
                if runninghub_key:
                    runninghub_key = str(runninghub_key).strip()
        except Exception:
            pass
        if not runninghub_key:
            try:
                config_yaml_path = find_config_yaml()
                if config_yaml_path and config_yaml_path.exists():
                    import yaml

                    with open(config_yaml_path, "r", encoding="utf-8") as f:
                        yaml_config = yaml.safe_load(f) or {}
                    if isinstance(yaml_config, dict) and "comfyui" in yaml_config:
                        cu = yaml_config["comfyui"]
                        if isinstance(cu, dict):
                            runninghub_key = str(cu.get("runninghub_api_key", "") or "").strip()
            except Exception as e:
                print(f"[Wrapper] connection_status 读 config.yaml RunningHub: {e}")
    except Exception as e:
        status["details"].append(f"读取 RunningHub 配置时异常（已忽略）: {str(e)[:80]}")

    status["runninghub_key_configured"] = bool(runninghub_key)
    status["status"] = "connected"
    if status["runninghub_key_configured"]:
        status["message"] = "连接正常"
    else:
        status["message"] = "连接正常（未配置 RunningHub，云端生成可能不可用）"
        status["details"].append("可在 config.yaml 的 comfyui.runninghub_api_key 中填写 RunningHub Key")
    return status

# ============================================================================
# 账号系统对接：仅调用远端已有 POST /api/setUser（写 userinfo.date 到期时间），不修改远端进程
# ============================================================================


def _account_api_base_from_config() -> str:
    u = (os.environ.get("ACCOUNT_API_BASE") or "").strip()
    if u:
        if not u.startswith(("http://", "https://")):
            u = "http://" + u
        return u.rstrip("/")
    try:
        p = find_config_yaml()
        if p and p.exists():
            import yaml

            with open(p, "r", encoding="utf-8") as f:
                y = yaml.safe_load(f) or {}
            acc = y.get("account")
            if isinstance(acc, dict):
                u = str(acc.get("api_base") or "").strip()
                if u:
                    if not u.startswith(("http://", "https://")):
                        u = "http://" + u
                    return u.rstrip("/")
    except Exception:
        pass
    return ""


def _account_provision_key_expected() -> Optional[str]:
    k = (os.environ.get("ACCOUNT_PROVISION_KEY") or "").strip()
    if k:
        return k
    try:
        p = find_config_yaml()
        if p and p.exists():
            import yaml

            with open(p, "r", encoding="utf-8") as f:
                y = yaml.safe_load(f) or {}
            acc = y.get("account")
            if isinstance(acc, dict):
                k = str(acc.get("provision_key") or "").strip()
                if k:
                    return k
    except Exception:
        pass
    return None


def _format_account_expiry(days_valid: int) -> str:
    dt = datetime.now() + timedelta(days=max(1, int(days_valid)))
    return dt.strftime("%Y-%m-%d %H:%M:%S")


class AccountProvisionRequest(BaseModel):
    """本机调用远端 setUser：username/password + 自动计算 date（到期时间）"""

    username: str
    password: str
    days_valid: int = 365
    provision_key: str


@app.post("/api/account/provision")
async def account_provision(request: AccountProvisionRequest):
    """
    向远端账号服务 POST /api/setUser，自动附带 date（当前时间 + days_valid）。
    需在环境变量 ACCOUNT_PROVISION_KEY 或 config.yaml 的 account.provision_key 配置密钥，否则接口禁用。
    说明：远端 setUser 在「用户已存在」时要求 body.password 与库中密码一致才会更新 date；新开用户则直接插入。
    """
    expected = _account_provision_key_expected()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="未配置开通密钥：请设置环境变量 ACCOUNT_PROVISION_KEY 或 config.yaml 中 account.provision_key",
        )

    if (request.provision_key or "").strip() != expected:
        raise HTTPException(status_code=403, detail="provision_key 无效")

    u = request.username.strip()
    pwd = request.password
    if not u or not pwd:
        raise HTTPException(status_code=400, detail="username 与 password 不能为空")

    base = _account_api_base_from_config().rstrip("/")
    date_str = _format_account_expiry(request.days_valid)
    url = f"{base}/api/setUser"
    payload = {"username": u, "password": pwd, "date": date_str}

    import httpx

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            r = await client.post(url, json=payload)
        except Exception as e:
            logger.exception("[AccountProvision] 连接账号服务失败: %s", e)
            raise HTTPException(status_code=502, detail=f"无法连接账号服务: {e!s}") from e

    try:
        data = r.json()
    except Exception:
        raise HTTPException(status_code=502, detail=f"账号服务返回非 JSON: {r.text[:200]!r}")

    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail=str(data)[:500])

    if data.get("code") != 0:
        raise HTTPException(status_code=400, detail=str(data.get("msg") or data))

    logger.info("[AccountProvision] 已提交 setUser user=%s expiry=%s", u, date_str)
    return {"success": True, "expiry": date_str, "upstream": data}


class SetKeyRequest(BaseModel):
    """设置 API Key 请求"""
    api_key: str

@app.post("/api/set_key")
async def set_key(request: SetKeyRequest):
    """
    设置 API Key（只写内存或 env，不直接改 config.yaml）
    
    行为：
        - 写入 os.environ
        - 存储到 CURRENT_STATE
        - 用于后续生成
    """
    api_key = request.api_key.strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="API Key 不能为空")
    
    # 写入环境变量
    os.environ["PIXELLE_API_KEY"] = api_key
    os.environ["OPENAI_API_KEY"] = api_key  # Pixelle-Video 的 LLM 服务使用这个
    print(f"[Wrapper] 已更新环境变量 OPENAI_API_KEY (长度: {len(api_key)})")
    
    # 更新配置管理器（如果支持）
    try:
        if PIXELLE_AVAILABLE:
            # 更新配置（不直接写文件，通过配置管理器）
            config = config_manager.config.to_dict()
            if "llm" not in config:
                config["llm"] = {}
            config["llm"]["api_key"] = api_key
            config["llm"]["model"] = "qwen"  # 设置模型为 Qwen
            config["llm"]["provider"] = "qwen"  # 设置提供商为 Qwen
            print(f"[Wrapper] 已更新配置：API Key 和模型（Qwen）")
            # 注意：这里不直接写文件，而是更新内存中的配置
            # 如果需要持久化，可以通过配置管理器的 API
    except Exception as e:
        print(f"[Wrapper] 更新配置失败: {e}")
    
    # 存储到状态
    CURRENT_STATE["api_key"] = api_key
    
    return {
        "success": True,
        "message": "API Key 已设置"
    }

# ============================================================================
# 配置管理API
# ============================================================================

class ConfigSaveRequest(BaseModel):
    """配置保存请求"""
    llm: Optional[Dict[str, Any]] = None
    comfyui: Optional[Dict[str, Any]] = None
    siliconflow: Optional[Dict[str, Any]] = None
    doubao: Optional[Dict[str, Any]] = None

class ConfigTestRequest(BaseModel):
    """配置测试请求"""
    api_type: str
    api_key: str
    api_url: Optional[str] = None

@app.get("/api/config/get")
async def get_config():
    """获取当前配置"""
    try:
        config_path = find_config_yaml()
        if not config_path or not config_path.exists():
            return {}
        
        import yaml
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
        
        return config
    except Exception as e:
        logger.error(f"[Config] 获取配置失败: {e}")
        return {}

@app.post("/api/config/save")
async def save_config(request: ConfigSaveRequest):
    """保存配置到config.yaml"""
    try:
        config_path = find_config_yaml()
        if not config_path:
            config_path = WRAPPER_BASE_DIR / "config.yaml"
        
        import yaml
        # 读取现有配置
        config = {}
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
        
        # 更新配置
        if request.llm:
            if 'llm' not in config:
                config['llm'] = {}
            config['llm'].update(request.llm)
            # 固定使用当前交付版通义模型，避免客户机残留旧 model 名
            config['llm']['model'] = request.llm.get('model') or 'qwen3.8-max'
            if request.llm.get('base_url'):
                config['llm']['base_url'] = request.llm['base_url']
        
        if request.comfyui:
            if 'comfyui' not in config:
                config['comfyui'] = {}
            config['comfyui'].update(request.comfyui)
        
        if request.siliconflow:
            sf = dict(request.siliconflow)
            sf['model'] = sf.get('model') or 'zai-org/GLM-5.3'
            if not sf.get('api_base'):
                sf['api_base'] = 'https://api.siliconflow.cn/v1'
            config['siliconflow'] = sf
            # 同步到环境变量，供链接解析、字幕硅基识别等使用
            if sf.get('api_key'):
                os.environ["API_KEY"] = sf['api_key'].strip()
        
        if request.doubao:
            config['doubao'] = request.doubao
        
        # 保存到文件
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
        
        # 更新环境变量（用于通义千问）
        if request.llm and request.llm.get('api_key'):
            os.environ["PIXELLE_API_KEY"] = request.llm['api_key']
            os.environ["OPENAI_API_KEY"] = request.llm['api_key']
            CURRENT_STATE["api_key"] = request.llm['api_key']
            if PIXELLE_AVAILABLE:
                _update_llm_service_config(request.llm['api_key'])
        
        # 更新豆包环境变量
        if request.doubao and request.doubao.get('api_key'):
            os.environ["AI_API_KEY"] = request.doubao['api_key']
            if request.doubao.get('api_url'):
                os.environ["AI_API_URL"] = request.doubao['api_url']
        
        logger.info(f"[Config] 配置已保存到: {config_path}")
        
        return {
            "success": True,
            "message": "配置保存成功"
        }
    except Exception as e:
        logger.error(f"[Config] 保存配置失败: {e}")
        raise HTTPException(status_code=500, detail=f"保存配置失败: {str(e)}")

def _classify_api_test_failure(
    *,
    api_type: str,
    status_code: Optional[int] = None,
    body_text: str = "",
    exc: Optional[BaseException] = None,
) -> str:
    """把连接失败归类成客户能看懂的原因。"""
    text = (body_text or "").strip()
    err = str(exc or "").strip()
    joined = f"{text} {err}".lower()
    code = status_code

    if exc is not None:
        name = type(exc).__name__
        if name in ("ConnectTimeout", "ReadTimeout", "Timeout", "TimeoutError") or "timed out" in joined:
            return "网络超时：连不上服务商服务器。请检查本机网络、代理、防火墙，或稍后重试。"
        if name in ("ConnectionError", "ProxyError", "SSLError") or "name or service not known" in joined or "failed to resolve" in joined:
            return "网络问题：无法解析/连接服务商地址。请检查是否能上网、DNS、VPN/代理是否正常。"
        if "certificate" in joined or "ssl" in joined:
            return "网络/证书问题：HTTPS 校验失败。请检查系统时间、代理或杀软是否拦截了 HTTPS。"

    if code in (401, 403) or "unauthorized" in joined or "invalid api" in joined or "api key" in joined and ("invalid" in joined or "incorrect" in joined):
        return "API Key 无效或已过期：请到服务商控制台重新复制密钥后保存再测。"
    if code == 404 or "model not exist" in joined or "model_not_found" in joined or "model does not exist" in joined or "model disabled" in joined:
        return "模型不可用：当前模型名已下线或无权访问。请联系交付方更新模型配置。"
    if code == 429 or "rate" in joined or "limit_requests" in joined or "quota" in joined or "insufficient" in joined:
        return "额度/限流：请求太频繁或账户余额不足。请稍后重试，或到服务商控制台检查余额与限流。"
    if code is not None and code >= 500:
        return f"服务商故障：对方服务器返回 {code}。请稍后重试；若持续失败，请联系服务商。"
    if code is not None and code >= 400:
        detail = text[:120] if text else err[:120]
        return f"请求被拒绝（HTTP {code}）{('：' + detail) if detail else ''}。请核对 API Key、模型名和网络。"

    if api_type == "runninghub" and ("apikey_user_not_found" in joined or "not_found" in joined):
        return "RunningHub Key 无效：控制台查不到该密钥对应用户。请重新申请/填写正确的 API Key。"

    detail = text[:160] or err[:160] or "未知错误"
    return f"连接失败：{detail}"


def _probe_chat_once(
    *,
    url: str,
    api_key: str,
    model: str,
    timeout_s: int = 20,
) -> tuple[bool, Optional[int], str, Optional[BaseException]]:
    """单次 chat/completions 探测。返回 (ok, status, body, exc)。"""
    import requests

    try:
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 5,
            },
            timeout=timeout_s,
        )
        body = (resp.text or "")[:800]
        if resp.status_code == 200:
            return True, resp.status_code, body, None
        return False, resp.status_code, body, None
    except Exception as e:
        return False, None, "", e


@app.post("/api/config/test")
async def test_config(request: ConfigTestRequest):
    """测试 API Key 连接：失败时自动重连最多 10 次，并返回可读原因。"""
    max_attempts = 10
    retry_delay_s = 1.2
    api_type = (request.api_type or "").strip().lower()
    api_key = (request.api_key or "").strip()
    if not api_key:
        return {"success": False, "message": "请先填写 API Key", "attempts": 0}

    # 与正式业务保持一致的模型名
    qwen_model = "qwen3.8-max"
    glm_model = "zai-org/GLM-5.3"
    doubao_model = "doubao-seed-2-0-code-preview-260215"

    label_map = {
        "qwen": "通义千问",
        "siliconflow": "硅基流动",
        "doubao": "豆包",
        "runninghub": "RunningHub",
    }
    label = label_map.get(api_type, api_type or "未知服务")

    last_status: Optional[int] = None
    last_body = ""
    last_exc: Optional[BaseException] = None

    try:
        if api_type == "runninghub":
            # RunningHub 没有统一 chat 接口：用账户状态接口探测，并做重试
            import requests

            if len(api_key) < 10:
                return {
                    "success": False,
                    "message": "RunningHub API Key 格式不正确（长度过短）",
                    "attempts": 1,
                }
            for attempt in range(1, max_attempts + 1):
                try:
                    resp = await asyncio.to_thread(
                        lambda: requests.post(
                            "https://www.runninghub.cn/uc/openapi/accountStatus",
                            headers={"Content-Type": "application/json"},
                            json={"apiKey": api_key},
                            timeout=20,
                        )
                    )
                    last_status = resp.status_code
                    last_body = (resp.text or "")[:800]
                    try:
                        data = resp.json() if resp.text else {}
                    except Exception:
                        data = {}
                    blob = json.dumps(data, ensure_ascii=False)
                    if "APIKEY_USER_NOT_FOUND" in blob.upper():
                        return {
                            "success": False,
                            "message": _classify_api_test_failure(
                                api_type=api_type, status_code=resp.status_code, body_text=blob
                            ),
                            "attempts": attempt,
                            "fatal": True,
                        }
                    code = data.get("code")
                    if resp.status_code == 200 and code in (0, "0"):
                        return {
                            "success": True,
                            "message": f"{label}连接成功（第 {attempt}/{max_attempts} 次）",
                            "attempts": attempt,
                        }
                    last_exc = None
                except Exception as e:
                    last_exc = e
                    last_status = None
                    last_body = ""
                if attempt < max_attempts:
                    await asyncio.sleep(retry_delay_s)
            reason = _classify_api_test_failure(
                api_type=api_type, status_code=last_status, body_text=last_body, exc=last_exc
            )
            return {
                "success": False,
                "message": f"{label}连续 {max_attempts} 次连接失败。{reason}",
                "attempts": max_attempts,
            }

        if api_type == "qwen":
            base = (request.api_url or "https://dashscope.aliyuncs.com/compatible-mode/v1").rstrip("/")
            url = f"{base}/chat/completions"
            model = qwen_model
        elif api_type == "siliconflow":
            base = (request.api_url or "https://api.siliconflow.cn/v1").rstrip("/")
            url = f"{base}/chat/completions"
            model = glm_model
        elif api_type == "doubao":
            url = request.api_url or "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
            model = doubao_model
        else:
            return {"success": False, "message": f"未知的 API 类型：{request.api_type}", "attempts": 0}

        for attempt in range(1, max_attempts + 1):
            ok, status, body, exc = await asyncio.to_thread(
                _probe_chat_once, url=url, api_key=api_key, model=model, timeout_s=20
            )
            last_status, last_body, last_exc = status, body, exc
            if ok:
                return {
                    "success": True,
                    "message": f"{label}连接成功（模型 {model}，第 {attempt}/{max_attempts} 次）",
                    "attempts": attempt,
                    "model": model,
                }

            # 明确的鉴权/模型错误：继续重试意义不大，但仍按用户要求重试；若是 Key 无效可提前结束
            joined = f"{body} {exc or ''}".lower()
            fatal = (
                status in (401, 403)
                or "model disabled" in joined
                or "model not exist" in joined
                or "model_not_found" in joined
                or ("unauthorized" in joined and "401" in joined)
            )
            if fatal and attempt >= 3:
                # 已重试几次仍是 Key/模型硬错误，避免空等
                reason = _classify_api_test_failure(
                    api_type=api_type, status_code=status, body_text=body, exc=exc
                )
                return {
                    "success": False,
                    "message": f"{label}连接失败（已重试 {attempt} 次）。{reason}",
                    "attempts": attempt,
                    "model": model,
                    "fatal": True,
                }

            if attempt < max_attempts:
                await asyncio.sleep(retry_delay_s)

        reason = _classify_api_test_failure(
            api_type=api_type, status_code=last_status, body_text=last_body, exc=last_exc
        )
        return {
            "success": False,
            "message": f"{label}连续 {max_attempts} 次连接失败。{reason}",
            "attempts": max_attempts,
            "model": model if api_type in ("qwen", "siliconflow", "doubao") else None,
        }
    except Exception as e:
        logger.error(f"[Config] 测试配置失败: {e}")
        reason = _classify_api_test_failure(api_type=api_type, exc=e)
        return {"success": False, "message": f"测试异常。{reason}", "attempts": 0}

# ============================================================================

@app.post("/api/avatar")
async def upload_avatar(file: UploadFile = File(...)):
    """
    上传数字人形象（人物照片）
    
    行为：
        - 接收图片文件
        - 保存到 Pixelle-Video 真实会用到的目录
        - 在 Wrapper 内维护 CURRENT_STATE["avatar_path"]
    """
    print(f"[Wrapper] [API] /api/avatar 被调用，文件名: {file.filename}")
    try:
        # 数据目录存储在 wrapper 目录下（便于打包和独立运行）
        avatar_dir = WRAPPER_BASE_DIR / "data" / "avatars"
        avatar_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成唯一文件名
        original_filename = file.filename or "avatar.png"
        file_ext = Path(original_filename).suffix or ".png"
        avatar_filename = f"avatar_{datetime.now().strftime('%Y%m%d_%H%M%S')}{file_ext}"
        avatar_path = avatar_dir / avatar_filename
        
        # 读取并保存文件
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="文件内容为空")
        
        with open(avatar_path, "wb") as f:
            f.write(content)
        
        # 更新状态
        CURRENT_STATE["avatar_path"] = str(avatar_path)
        
        print(f"[Wrapper] 头像已上传: {avatar_path} (大小: {len(content)} 字节)")
        
        return {
            "success": True,
            "message": "上传成功",
            "path": str(avatar_path),
            "filename": avatar_filename
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Wrapper] 上传失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")

# ============================================================================

class SetTextRequest(BaseModel):
    """设置文案请求"""
    text: str

@app.post("/api/text")
async def set_text(request: SetTextRequest):
    """
    设置口播文案
    
    行为：
        - 存储到 CURRENT_STATE["text"]
    """
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="文案不能为空")
    
    CURRENT_STATE["text"] = text
    
    return {
        "success": True,
        "message": "文案已设置",
        "text_length": len(text)
    }

# ============================================================================

@app.post("/api/product")
async def upload_product(file: UploadFile = File(...)):
    """
    上传产品图片（用于带货模式）
    
    行为：
        - 接收图片文件（PNG, JPG, JPEG, BMP, GIF等）
        - 保存到 Pixelle-Video 的 data/products 目录
        - 存储路径到 CURRENT_STATE["product_path"]
    """
    print(f"[Wrapper] [API] /api/product 被调用，文件名: {file.filename}")
    try:
        # 数据目录存储在 wrapper 目录下（便于打包和独立运行）
        product_dir = WRAPPER_BASE_DIR / "data" / "products"
        product_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成唯一文件名
        file_ext = os.path.splitext(file.filename)[1] or ".jpg"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"product_{timestamp}{file_ext}"
        product_path = product_dir / filename
        
        # 保存文件
        content = await file.read()
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="文件内容为空")
        
        with open(product_path, "wb") as f:
            f.write(content)
        
        # 更新状态
        CURRENT_STATE["product_path"] = str(product_path)
        
        print(f"[Wrapper] 产品图片已上传: {product_path} (大小: {len(content)} 字节)")
        return {
            "success": True,
            "message": "上传成功",
            "path": str(product_path),
            "filename": filename
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Wrapper] 上传产品图片失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"上传产品图片失败: {str(e)}")

# ============================================================================

@app.post("/api/audio")
async def upload_audio(file: UploadFile = File(...)):
    """
    上传音频文件（用于数字人口播）
    
    行为：
        - 接收音频文件（MP3, WAV, M4A等）
        - 保存到 Pixelle-Video 的 data/audios 目录
        - 存储路径到 CURRENT_STATE["audio_path"]
    """
    print(f"[Wrapper] [API] /api/audio 被调用，文件名: {file.filename}")
    try:
        # 数据目录存储在 wrapper 目录下（便于打包和独立运行）
        audio_dir = WRAPPER_BASE_DIR / "data" / "audios"
        audio_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成唯一文件名
        file_ext = os.path.splitext(file.filename)[1] or ".mp3"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"audio_{timestamp}{file_ext}"
        audio_path = audio_dir / filename
        
        # 保存文件
        content = await file.read()
        with open(audio_path, "wb") as f:
            f.write(content)
        
        # 更新状态
        CURRENT_STATE["audio_path"] = str(audio_path)
        
        print(f"[Wrapper] 音频已上传: {audio_path} (大小: {len(content)} 字节)")
        return {
            "success": True,
            "message": "上传成功",
            "path": str(audio_path),
            "filename": filename
        }
    except Exception as e:
        print(f"[Wrapper] 上传音频失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"上传音频失败: {str(e)}")

# ============================================================================

@app.post("/api/background_music")
async def upload_background_music(file: UploadFile = File(...)):
    """
    上传背景音乐文件
    
    行为：
        - 接收音频文件（MP3格式）
        - 保存到 Pixelle-Video 的 data/background_music 目录
        - 存储路径到 CURRENT_STATE["background_music_path"]
    """
    print(f"[Wrapper] [API] /api/background_music 被调用，文件名: {file.filename}")
    print(f"[Wrapper] [API] Content-Type: {file.content_type}")
    try:
        # 数据目录存储在 wrapper 目录下（便于打包和独立运行）
        music_dir = WRAPPER_BASE_DIR / "data" / "background_music"
        music_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成唯一文件名
        file_ext = os.path.splitext(file.filename)[1] or ".mp3"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"bg_music_{timestamp}{file_ext}"
        music_path = music_dir / filename
        
        # 保存文件（分块读取，避免大文件内存溢出）
        print(f"[Wrapper] 开始读取文件内容...")
        content = b""
        chunk_size = 1024 * 1024  # 1MB chunks
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            content += chunk
        
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="文件内容为空")
        
        file_size_mb = len(content) / (1024 * 1024)
        print(f"[Wrapper] 文件大小: {file_size_mb:.2f} MB")
        
        with open(music_path, "wb") as f:
            f.write(content)
        
        # 更新状态
        CURRENT_STATE["background_music_path"] = str(music_path)
        
        print(f"[Wrapper] 背景音乐已上传: {music_path} (大小: {len(content)} 字节)")
        return {
            "success": True,
            "message": "背景音乐上传成功",
            "path": str(music_path),
            "filename": filename
        }
    except Exception as e:
        logger.error(f"[Wrapper] 上传背景音乐失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")


@app.post("/api/showcase_video")
async def upload_showcase_video(
    file: UploadFile = File(...),
    slot: int = Form(0),
):
    """
    上传环境演示视频（用于画中画）。最多 3 槽位 slot=0|1|2，默认 0（兼容旧前端）。
    单段时长须严格小于 40 秒（ffprobe 检测）。
    """
    print(f"[Wrapper] [API] /api/showcase_video 被调用，文件名: {file.filename} slot={slot}")
    print(f"[Wrapper] [API] Content-Type: {file.content_type}")
    try:
        if slot not in (0, 1, 2):
            raise HTTPException(status_code=400, detail="slot 必须为 0、1 或 2")

        showcase_dir = WRAPPER_BASE_DIR / "data" / "showcase_videos"
        showcase_dir.mkdir(parents=True, exist_ok=True)

        file_ext = os.path.splitext(file.filename)[1] or ".mp4"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"showcase_s{slot}_{timestamp}{file_ext}"
        showcase_path = showcase_dir / filename

        print(f"[Wrapper] 开始读取文件内容...")
        content = b""
        chunk_size = 1024 * 1024
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            content += chunk

        if len(content) == 0:
            raise HTTPException(status_code=400, detail="文件内容为空")

        file_size_mb = len(content) / (1024 * 1024)
        print(f"[Wrapper] 文件大小: {file_size_mb:.2f} MB")

        with open(showcase_path, "wb") as f:
            f.write(content)

        dur = _ffprobe_duration_seconds(showcase_path)
        if dur is None:
            try:
                if showcase_path.is_file():
                    showcase_path.unlink()
            except Exception:
                pass
            raise HTTPException(status_code=400, detail="无法读取视频时长，请确认文件为有效视频")
        if dur >= SHOWCASE_MAX_DURATION_SEC:
            try:
                if showcase_path.is_file():
                    showcase_path.unlink()
            except Exception:
                pass
            raise HTTPException(
                status_code=400,
                detail=f"单段环境视频须小于 {SHOWCASE_MAX_DURATION_SEC:.0f} 秒，当前约 {dur:.1f} 秒",
            )

        _migrate_legacy_showcase_if_needed()
        slots = _ensure_showcase_paths_list()
        old = slots[slot]
        if old and str(old) != str(showcase_path):
            _unlink_material_file(str(old))
        slots[slot] = str(showcase_path)
        _sync_showcase_legacy_path()

        print(f"[Wrapper] 环境演示视频已上传槽{slot}: {showcase_path} (时长约 {dur:.1f}s)")
        return {
            "success": True,
            "message": "上传成功",
            "path": str(showcase_path),
            "filename": filename,
            "slot": slot,
            "size": len(content),
            "size_mb": round(file_size_mb, 2),
            "duration_sec": round(dur, 2),
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Wrapper] 上传环境演示视频失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"上传环境演示视频失败: {str(e)}")

# ============================================================================

@app.post("/api/generate")
async def generate_video(request: Request):
    """
    生成视频（最重要）
    
    行为：
        - 后台线程执行
        - 真实调用 Pixelle-Video 生成函数
        - 返回 task_id
        - Wrapper 内部维护任务字典
    - defer_finalize=True：仅出口播底片（+数字人高清），不做画中画/烧字幕/BGM；并返回 subtitle_segments 供成品素材编辑后再 /api/generate/finalize_manual
    
    兼容：无 body、空 body、multipart 的旧客户端不传 JSON 时视为 defer_finalize=False；
    仅当 Content-Type 为 application/json 且 JSON 含 defer_finalize: true 时启用延迟成片。
    """
    defer_finalize = False
    ct = (request.headers.get("content-type") or "").lower()
    if "application/json" in ct:
        try:
            body = await request.json()
            if isinstance(body, dict):
                defer_finalize = bool(body.get("defer_finalize"))
        except Exception:
            pass
    # 检查必要参数
    if not CURRENT_STATE.get("text"):
        raise HTTPException(status_code=400, detail="请先设置文案")

    av = CURRENT_STATE.get("avatar_path")
    au = CURRENT_STATE.get("audio_path")
    if not av or not Path(av).exists():
        raise HTTPException(status_code=400, detail="请先上传人物形象（头像）")
    if not au or not Path(au).exists():
        raise HTTPException(status_code=400, detail="请先上传声音克隆音频")

    # 检查 API Key（可选，但建议设置）
    api_key = CURRENT_STATE.get("api_key") or os.environ.get("PIXELLE_API_KEY")
    if not api_key:
        print("[警告] 未设置 API Key，生成可能会失败")
        # 不强制要求，让 Pixelle-Video 自己处理
    
    # 检查 Pixelle-Video 是否可用
    if not PIXELLE_AVAILABLE:
        raise HTTPException(
            status_code=503, 
            detail="Pixelle-Video 不可用：缺少依赖模块（comfykit）。请检查 Pixelle-Video 环境配置。"
        )
    
    if _pixelle_video is None:
        # 尝试初始化
        try:
            await init_pixelle_video()
        except Exception as e:
            error_detail = f"Pixelle-Video 初始化失败: {str(e)}"
            if not PIXELLE_AVAILABLE:
                error_detail += "\n\n可能的原因："
                error_detail += "\n1. 未找到 Pixelle-Video 项目路径"
                error_detail += "\n2. 请设置环境变量 PIXELLE_VIDEO_ROOT 或在 pixelle_wrapper/config.json 中配置 pixelle_video_path"
                error_detail += f"\n3. 当前检测到的路径: {PIXELLE_VIDEO_PATH}"
                if PIXELLE_VIDEO_PATH and not (PIXELLE_VIDEO_PATH / "pixelle_video").exists():
                    error_detail += f"\n4. 路径存在但未找到 pixelle_video 模块: {PIXELLE_VIDEO_PATH}"
            raise HTTPException(
                status_code=503,
                detail=error_detail
            )
    
    # 生成任务 ID
    task_id = str(uuid.uuid4())
    
    # 初始化任务状态
    TASKS[task_id] = {
        "status": "running",
        "progress": 0,
        "output": None,
        "error": None,
        "created_at": datetime.now().isoformat()
    }
    
    # 在后台线程中执行生成任务
    def run_generation():
        """在后台线程中运行生成任务"""
        try:
            # 使用 asyncio 在新的事件循环中运行
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            async def async_generate():
                try:
                    # 更新进度：开始生成
                    TASKS[task_id]["progress"] = 1
                    TASKS[task_id]["status"] = "running"
                    TASKS[task_id]["step"] = "初始化中..."
                    print(f"[Wrapper] 任务 {task_id} 开始生成，文案: {CURRENT_STATE.get('text', '')[:50]}...")
                    import sys
                    sys.stdout.flush()
                    
                    # 准备生成参数
                    text = CURRENT_STATE["text"]
                    avatar_path = CURRENT_STATE.get("avatar_path")
                    
                    # 在生成前，强制更新 LLM 服务配置和 RunningHub 配置（确保使用最新的 API Key 和模型）
                    api_key = CURRENT_STATE.get("api_key") or os.environ.get("PIXELLE_API_KEY")
                    if api_key:
                        print(f"[Wrapper] ========== 生成前强制更新配置 ==========")
                        print(f"[Wrapper] 检查 _pixelle_video 对象...")
                        if _pixelle_video:
                            print(f"[Wrapper] _pixelle_video 类型: {type(_pixelle_video)}")
                            print(f"[Wrapper] _pixelle_video 属性: {[attr for attr in dir(_pixelle_video) if not attr.startswith('__')]}")
                            if hasattr(_pixelle_video, 'llm'):
                                print(f"[Wrapper] llm 存在: {_pixelle_video.llm is not None}")
                                if _pixelle_video.llm:
                                    print(f"[Wrapper] llm 类型: {type(_pixelle_video.llm)}")
                                    print(f"[Wrapper] llm.model: {getattr(_pixelle_video.llm, 'model', 'N/A')}")
                                    print(f"[Wrapper] llm.base_url: {getattr(_pixelle_video.llm, 'base_url', 'N/A')}")
                        
                        # 更新 LLM 服务配置
                        _update_llm_service_config(api_key)
                        
                        # 更新 RunningHub 配置（确保 workflow 配置生效）
                        try:
                            from pixelle_video.config import config_manager
                            # 直接更新 config_manager 的配置
                            if hasattr(config_manager, 'config') and hasattr(config_manager.config, 'comfyui'):
                                # 更新 image workflow
                                config_manager.config.comfyui.image.default_workflow = "runninghub/image_flux.json"
                                # 更新 video workflow
                                config_manager.config.comfyui.video.default_workflow = "runninghub/video_wan2.1_fusionx.json"
                                
                                # 更新 RunningHub API Key（从 config.yaml 读取，不要使用 Qwen 的 API Key）
                                runninghub_key = getattr(config_manager.config.comfyui, 'runninghub_api_key', None)
                                if not runninghub_key:
                                    # 尝试从 config.yaml 文件直接读取
                                    try:
                                        import yaml
                                        config_yaml_path = find_config_yaml()
                                        if config_yaml_path:
                                            with open(config_yaml_path, 'r', encoding='utf-8') as f:
                                                yaml_config = yaml.safe_load(f)
                                                if yaml_config and 'comfyui' in yaml_config:
                                                    yaml_runninghub_key = yaml_config['comfyui'].get('runninghub_api_key')
                                                    if yaml_runninghub_key:
                                                        config_manager.config.comfyui.runninghub_api_key = yaml_runninghub_key
                                                        print(f"[Wrapper] 已从 config.yaml 读取 RunningHub API Key (长度: {len(yaml_runninghub_key)})")
                                    except Exception as e:
                                        print(f"[Wrapper] 无法从 config.yaml 读取 RunningHub API Key: {e}")
                                
                                # 清除本地 ComfyUI URL
                                config_manager.config.comfyui.comfyui_url = None
                                print(f"[Wrapper] 已更新 config_manager 配置: image workflow, video workflow")
                                if runninghub_key or getattr(config_manager.config.comfyui, 'runninghub_api_key', None):
                                    print(f"[Wrapper] RunningHub API Key 已配置")
                                else:
                                    print(f"[Wrapper] 警告: RunningHub API Key 未配置")
                            
                            # 同时更新 _pixelle_video.config（确保 media 服务能读取到）
                            if hasattr(_pixelle_video, 'config'):
                                pixelle_config = _pixelle_video.config
                                if isinstance(pixelle_config, dict):
                                    if "comfyui" not in pixelle_config:
                                        pixelle_config["comfyui"] = {}
                                    if "image" not in pixelle_config["comfyui"]:
                                        pixelle_config["comfyui"]["image"] = {}
                                    if "video" not in pixelle_config["comfyui"]:
                                        pixelle_config["comfyui"]["video"] = {}
                                    
                                    pixelle_config["comfyui"]["image"]["default_workflow"] = "runninghub/image_flux.json"
                                    pixelle_config["comfyui"]["video"]["default_workflow"] = "runninghub/video_wan2.1_fusionx.json"
                                    # 使用 RunningHub API Key，而不是 Qwen 的 API Key
                                    runninghub_key_for_config = getattr(config_manager.config.comfyui, 'runninghub_api_key', None)
                                    if not runninghub_key_for_config:
                                        # 尝试从 config.yaml 读取
                                        try:
                                            import yaml
                                            config_yaml_path = find_config_yaml()
                                            if config_yaml_path:
                                                with open(config_yaml_path, 'r', encoding='utf-8') as f:
                                                    yaml_config = yaml.safe_load(f)
                                                    if yaml_config and 'comfyui' in yaml_config:
                                                        runninghub_key_for_config = yaml_config['comfyui'].get('runninghub_api_key', '').strip()
                                        except:
                                            pass
                                    if runninghub_key_for_config:
                                        pixelle_config["comfyui"]["runninghub_api_key"] = runninghub_key_for_config
                                    pixelle_config["comfyui"]["comfyui_url"] = None
                                    print(f"[Wrapper] 已更新 _pixelle_video.config: image workflow, video workflow, RunningHub API Key")
                                    print(f"[Wrapper] _pixelle_video.config.comfyui.image.default_workflow: {pixelle_config['comfyui']['image'].get('default_workflow', 'N/A')}")
                        except Exception as e:
                            print(f"[Wrapper] 更新 RunningHub 配置失败: {e}")
                            import traceback
                            print(f"[Wrapper] 错误详情: {traceback.format_exc()}")
                        
                        print(f"[Wrapper] ========== 配置更新完成 ==========")
                    else:
                        print(f"[Wrapper] 警告: 未找到 API Key，无法更新 LLM 服务配置")
                    
                    # 定义进度回调函数（将 Pixelle-Video 的进度转换为 Wrapper 的进度）
                    def progress_callback(event):
                        """进度回调：将 Pixelle-Video 的进度事件转换为 Wrapper 的进度"""
                        try:
                            # event.progress 是 0.0-1.0，转换为 0-100
                            progress_percent = int(event.progress * 100)
                            # 确保进度在 1-99 之间（1% 表示开始，99% 表示即将完成）
                            progress_percent = max(1, min(99, progress_percent))
                            TASKS[task_id]["progress"] = progress_percent
                            print(f"[Wrapper] 任务 {task_id} 进度: {progress_percent}% - {event.event_type}")
                            # 强制刷新输出
                            import sys
                            sys.stdout.flush()
                        except Exception as e:
                            print(f"[Wrapper] 进度回调错误: {e}")
                    
                    # 调用 Pixelle-Video 生成函数
                    # 注意：这里使用 "fixed" 模式，直接使用文案
                    print(f"[Wrapper] 开始调用 _pixelle_video.generate_video...")
                    print(f"[Wrapper] 参数: text={text[:50]}..., mode=fixed, template=1080x1920/default.html")
                    import sys
                    sys.stdout.flush()
                    
                    try:
                        # 确认 _pixelle_video 对象存在
                        if _pixelle_video is None:
                            raise RuntimeError("Pixelle-Video 对象未初始化")
                        
                        print(f"[Wrapper] 调用 generate_video，参数:")
                        print(f"  - text: {text[:50]}...")
                        print(f"  - mode: fixed")
                        print(f"  - frame_template: 1080x1920/default.html")
                        print(f"  - n_scenes: 5")
                        print(f"  - avatar_path: {avatar_path}")
                        sys.stdout.flush()
                        
                        # 调用 Pixelle-Video 生成函数
                        # 数字人口播：如果有头像，使用数字人口播 workflow（该分支内已加字幕+背景音乐，不再在后续重复添加）
                        subtitle_and_bgm_already_done = False
                        if avatar_path and os.path.exists(avatar_path):
                            print(f"[Wrapper] 使用数字人口播模式，头像: {avatar_path}")
                            
                            # 数字人口播流程：
                            # 1. 生成 TTS 音频
                            # 2. 使用数字人口播 workflow 生成视频
                            
                            # 创建任务目录（输出到 wrapper 目录下，而不是 Y 盘）
                            # 使用 wrapper 目录下的 output 目录，便于打包和独立运行
                            from datetime import datetime
                            import uuid
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            task_id_internal = uuid.uuid4().hex[:8]
                            task_dir_name = f"{timestamp}_{task_id_internal}"
                            task_dir = WRAPPER_BASE_DIR / "output" / task_dir_name
                            task_dir.mkdir(parents=True, exist_ok=True)
                            task_dir = str(task_dir.resolve())
                            print(f"[Wrapper] 任务输出目录: {task_dir}")
                            if task_id in TASKS and TASKS[task_id].get("status") == "running":
                                TASKS[task_id]["step"] = "口播语音生成中..."
                            
                            # 步骤1: 生成 TTS 音频（使用ComfyUI模式，支持语音克隆）
                            # 流程：上传音频用于语音克隆 → 用文案生成TTS（使用克隆的声音）→ 结合头像生成视频
                            uploaded_audio_path = CURRENT_STATE.get("audio_path")
                            
                            if uploaded_audio_path and os.path.exists(uploaded_audio_path):
                                # 使用ComfyUI模式进行语音克隆
                                print(f"[Wrapper] ========== 步骤1: 使用ComfyUI模式生成TTS（语音克隆）==========")
                                print(f"[Wrapper] 文案内容: {text[:100]}...")
                                print(f"[Wrapper] 参考音频（用于语音克隆）: {uploaded_audio_path}")
                                if progress_callback:
                                    progress_callback(ProgressEvent(progress=0.1, event_type="generating_tts_with_voice_clone"))
                                
                                # 在调用 TTS 之前，确保 RunningHub API Key 已正确设置
                                # 强制重新加载配置，确保 ComfyKit 能获取到最新的 API Key
                                try:
                                    try:
                                        from runninghub_upload_patch import apply_runninghub_upload_patch
                                        apply_runninghub_upload_patch()
                                    except Exception as _rh_patch_e:
                                        print(f"[Wrapper] [TTS前] 上传补丁: {_rh_patch_e}")
                                    # 重新读取 config.yaml 并更新配置
                                    import yaml
                                    config_yaml_path = find_config_yaml()
                                    if config_yaml_path:
                                        with open(config_yaml_path, 'r', encoding='utf-8') as f:
                                            yaml_config = yaml.safe_load(f)
                                            if yaml_config and 'comfyui' in yaml_config:
                                                yaml_runninghub_key = yaml_config['comfyui'].get('runninghub_api_key')
                                                if yaml_runninghub_key:
                                                    config_manager.config.comfyui.runninghub_api_key = yaml_runninghub_key
                                                    print(f"[Wrapper] [TTS前] 已从 config.yaml 读取 RunningHub API Key (长度: {len(yaml_runninghub_key)})")
                                                    
                                                    # 强制更新 _pixelle_video.config，确保 ComfyKit 能读取到
                                                    if hasattr(_pixelle_video, 'config'):
                                                        pixelle_config = _pixelle_video.config
                                                        if isinstance(pixelle_config, dict):
                                                            if "comfyui" not in pixelle_config:
                                                                pixelle_config["comfyui"] = {}
                                                            pixelle_config["comfyui"]["runninghub_api_key"] = yaml_runninghub_key
                                                            print(f"[Wrapper] [TTS前] 已更新 _pixelle_video.config.comfyui.runninghub_api_key")
                                                    
                                                    # 强制重新创建 ComfyKit（如果已存在，先关闭）
                                                    if _pixelle_video._comfykit is not None:
                                                        try:
                                                            await _pixelle_video._comfykit.close()
                                                        except:
                                                            pass
                                                        _pixelle_video._comfykit = None
                                                        _pixelle_video._comfykit_config_hash = None
                                                        print(f"[Wrapper] [TTS前] 已清除旧 ComfyKit 实例，将重新创建")
                                except Exception as e:
                                    print(f"[Wrapper] [TTS前] 更新 RunningHub API Key 失败: {e}")
                                    import traceback
                                    traceback.print_exc()
                                
                                audio_path = os.path.join(task_dir, "narration.mp3")
                                
                                # 使用ComfyUI模式，传入参考音频用于语音克隆
                                # 直接指定workflow，支持语音克隆
                                await _pixelle_video.tts(
                                    text=text,
                                    output_path=audio_path,
                                    inference_mode="comfyui",  # 使用ComfyUI模式
                                    workflow="runninghub/tts_index2.json",  # 直接指定workflow，支持语音克隆
                                    ref_audio=uploaded_audio_path,  # 传入参考音频用于语音克隆
                                    speed=1.2
                                )
                                print(f"[Wrapper] [TTS] ========== TTS 调用完成 ==========")
                                sys.stdout.flush()
                                
                                # 验证音频文件是否成功生成
                                if not os.path.exists(audio_path):
                                    raise Exception(f"TTS 音频文件未生成: {audio_path}")
                                else:
                                    file_size = os.path.getsize(audio_path)
                                    print(f"[Wrapper] TTS 音频已生成（使用语音克隆）: {audio_path} (大小: {file_size} 字节)")
                            else:
                                # 如果没有上传音频，使用本地TTS
                                print(f"[Wrapper] 步骤1: 使用本地TTS生成音频（未上传参考音频）...")
                                print(f"[Wrapper] 文案内容: {text[:100]}...")
                                if progress_callback:
                                    progress_callback(ProgressEvent(progress=0.1, event_type="generating_tts_local"))
                                
                                audio_path = os.path.join(task_dir, "narration.mp3")
                                await _pixelle_video.tts(
                                    text=text,
                                    output_path=audio_path,
                                    inference_mode="local",
                                    voice="zh-CN-YunjianNeural",
                                    speed=1.2
                                )
                                
                                # 验证音频文件是否成功生成
                                if not os.path.exists(audio_path):
                                    raise Exception(f"TTS 音频文件未生成: {audio_path}")
                                else:
                                    file_size = os.path.getsize(audio_path)
                                    print(f"[Wrapper] TTS 音频已生成（本地模式）: {audio_path} (大小: {file_size} 字节)")
                            
                            if task_id in TASKS and TASKS[task_id].get("status") == "running":
                                TASKS[task_id]["step"] = "生成视频中..."
                            
                            # 步骤2: 使用数字人口播 workflow 生成视频
                            # 检查是否有产品图片，决定使用自定义模式还是带货模式
                            product_path = CURRENT_STATE.get("product_path")
                            has_product = product_path and os.path.exists(product_path)
                            
                            # 在获取 ComfyKit 之前，确保 RunningHub API Key 已正确设置
                            # 强制重新加载配置，确保 ComfyKit 能获取到最新的 API Key
                            try:
                                try:
                                    from runninghub_upload_patch import apply_runninghub_upload_patch
                                    apply_runninghub_upload_patch()
                                except Exception as _rh_patch_e2:
                                    print(f"[Wrapper] [视频前] 上传补丁: {_rh_patch_e2}")
                                # 重新读取 config.yaml 并更新配置
                                import yaml
                                config_yaml_path = find_config_yaml()
                                if config_yaml_path:
                                    with open(config_yaml_path, 'r', encoding='utf-8') as f:
                                        yaml_config = yaml.safe_load(f)
                                        if yaml_config and 'comfyui' in yaml_config:
                                            yaml_runninghub_key = yaml_config['comfyui'].get('runninghub_api_key')
                                            if yaml_runninghub_key:
                                                config_manager.config.comfyui.runninghub_api_key = yaml_runninghub_key
                                                print(f"[Wrapper] [TTS前] 已从 config.yaml 读取 RunningHub API Key (长度: {len(yaml_runninghub_key)})")
                                                
                                                # 强制更新 _pixelle_video.config，确保 ComfyKit 能读取到
                                                if hasattr(_pixelle_video, 'config'):
                                                    pixelle_config = _pixelle_video.config
                                                    if isinstance(pixelle_config, dict):
                                                        if "comfyui" not in pixelle_config:
                                                            pixelle_config["comfyui"] = {}
                                                        pixelle_config["comfyui"]["runninghub_api_key"] = yaml_runninghub_key
                                                        print(f"[Wrapper] [TTS前] 已更新 _pixelle_video.config.comfyui.runninghub_api_key")
                                                
                                                # 强制重新创建 ComfyKit（如果已存在，先关闭）
                                                if _pixelle_video._comfykit is not None:
                                                    try:
                                                        await _pixelle_video._comfykit.close()
                                                    except:
                                                        pass
                                                    _pixelle_video._comfykit = None
                                                    _pixelle_video._comfykit_config_hash = None
                                                    print(f"[Wrapper] [TTS前] 已清除旧 ComfyKit 实例，将重新创建")
                            except Exception as e:
                                print(f"[Wrapper] [TTS前] 更新 RunningHub API Key 失败: {e}")
                            
                            # 获取 ComfyKit 实例（会自动使用最新的配置）
                            kit = await _pixelle_video._get_or_create_comfykit()
                            
                            # 根据是否有产品图片选择不同的模式
                            # 自定义模式：没有产品图片 → 直接生成视频
                            # 带货模式：有产品图片 → 先合成图片，再生成视频
                            if has_product:
                                print(f"[Wrapper] 步骤2: 使用数字人口播带货模式（两步流程）...")
                                print(f"[Wrapper] 产品图片: {product_path}")
                                if progress_callback:
                                    progress_callback(ProgressEvent(progress=0.3, event_type="generating_digital_human_ecommerce"))
                                
                                # 带货模式：第一步 - 合成人物图片和产品图片
                                print(f"[Wrapper] 步骤2.1: 合成人物图片和产品图片...")
                                first_workflow_id = "2010608838151507970"  # digital_customize.json
                                first_workflow_params = {
                                    "firstimage": avatar_path,  # 人物形象
                                    "secondimage": product_path  # 产品图片
                                }
                                
                                print(f"[Wrapper] 调用第一步 workflow (合成图片): {first_workflow_id}")
                                print(f"[Wrapper] 参数: firstimage={avatar_path}, secondimage={product_path}")
                                
                                # 执行第一步：合成图片
                                first_result = await kit.execute(first_workflow_id, first_workflow_params)
                                
                                # 检查第一步结果
                                if first_result.status != "completed":
                                    raise Exception(f"第一步 workflow 执行失败: {first_result.msg}")
                                
                                # 获取合成后的图片 URL
                                combined_image_url = None
                                if hasattr(first_result, 'images') and first_result.images:
                                    combined_image_url = first_result.images[0]
                                elif hasattr(first_result, 'outputs') and first_result.outputs:
                                    for node_id, node_output in first_result.outputs.items():
                                        if isinstance(node_output, dict) and 'images' in node_output:
                                            images = node_output['images']
                                            if images and len(images) > 0:
                                                combined_image_url = images[0]
                                                break
                                
                                if not combined_image_url:
                                    raise Exception("第一步 workflow 未返回合成后的图片，请检查 workflow 配置")
                                
                                print(f"[Wrapper] 图片合成成功，合成图片 URL: {combined_image_url}")
                                
                                # 带货模式：第二步 - 使用合成后的图片生成视频
                                print(f"[Wrapper] 步骤2.2: 使用合成后的图片生成视频...")
                                if progress_callback:
                                    progress_callback(ProgressEvent(progress=0.5, event_type="generating_digital_human_ecommerce"))
                                
                                second_workflow_id = "2003717471859294210"  # digital_combination.json
                                second_workflow_params = {
                                    "videoimage": combined_image_url,  # 合成后的图片（URL）
                                    "audio": audio_path  # TTS 音频
                                }
                                
                                print(f"[Wrapper] 调用第二步 workflow (生成视频): {second_workflow_id}")
                                print(f"[Wrapper] 参数: videoimage={combined_image_url}, audio={audio_path}")
                                
                                # 执行第二步：生成视频
                                workflow_result = await kit.execute(second_workflow_id, second_workflow_params)
                                
                            else:
                                print(f"[Wrapper] 步骤2: 使用数字人口播自定义模式 workflow 生成视频...")
                                if progress_callback:
                                    progress_callback(ProgressEvent(progress=0.3, event_type="generating_digital_human"))
                                
                                # 自定义模式：直接生成视频
                                workflow_id = "2003717471859294210"  # digital_combination.json
                                
                                # 关键修复：ComfyKit 的 execute 方法应该支持本地文件路径，会自动上传
                                # 但为了确保正确，我们需要确保文件路径是绝对路径，并且文件存在
                                
                                # 确保文件路径是绝对路径
                                avatar_path_abs = os.path.abspath(avatar_path) if avatar_path else None
                                audio_path_abs = os.path.abspath(audio_path) if audio_path else None
                                
                                # 验证文件是否存在
                                if avatar_path_abs and not os.path.exists(avatar_path_abs):
                                    raise FileNotFoundError(f"头像文件不存在: {avatar_path_abs}")
                                if audio_path_abs and not os.path.exists(audio_path_abs):
                                    raise FileNotFoundError(f"音频文件不存在: {audio_path_abs}")
                                
                                # 使用绝对路径，ComfyKit 会自动上传到 RunningHub
                                workflow_params = {
                                    "videoimage": avatar_path_abs,  # 人物形象（绝对路径，ComfyKit 会自动上传）
                                    "audio": audio_path_abs  # TTS 音频（绝对路径，ComfyKit 会自动上传）
                                }
                                
                                print(f"[Wrapper] 调用数字人口播自定义模式 workflow: {workflow_id}")
                                print(f"[Wrapper] 参数: videoimage={avatar_path_abs}, audio={audio_path_abs}")
                                print(f"[Wrapper] 注意: ComfyKit 会自动将本地文件上传到 RunningHub")
                                
                                # 执行 workflow
                                workflow_result = await kit.execute(workflow_id, workflow_params)
                            
                            # 调试：打印完整结果结构
                            print(f"[Wrapper] workflow_result 类型: {type(workflow_result)}")
                            print(f"[Wrapper] workflow_result 属性: {dir(workflow_result)}")
                            if hasattr(workflow_result, 'videos'):
                                print(f"[Wrapper] workflow_result.videos: {workflow_result.videos}")
                            if hasattr(workflow_result, 'images'):
                                print(f"[Wrapper] workflow_result.images: {workflow_result.images}")
                            if hasattr(workflow_result, 'outputs'):
                                print(f"[Wrapper] workflow_result.outputs 类型: {type(workflow_result.outputs)}")
                                if workflow_result.outputs:
                                    print(f"[Wrapper] workflow_result.outputs 键: {list(workflow_result.outputs.keys())}")
                                    for node_id, node_output in list(workflow_result.outputs.items())[:3]:  # 只打印前3个
                                        print(f"[Wrapper]   node {node_id}: {type(node_output)}")
                                        if isinstance(node_output, dict):
                                            print(f"[Wrapper]     keys: {list(node_output.keys())}")
                            
                            # 提取视频 URL
                            generated_video_url = None
                            
                            # 方法1: 直接检查 videos 属性
                            if hasattr(workflow_result, 'videos') and workflow_result.videos:
                                generated_video_url = workflow_result.videos[0]
                                print(f"[Wrapper] 从 workflow_result.videos 获取视频 URL")
                            
                            # 方法2: 检查 outputs 中的 videos
                            elif hasattr(workflow_result, 'outputs') and workflow_result.outputs:
                                for node_id, node_output in workflow_result.outputs.items():
                                    if isinstance(node_output, dict):
                                        # 检查 videos 键
                                        if 'videos' in node_output:
                                            videos = node_output['videos']
                                            if videos and len(videos) > 0:
                                                generated_video_url = videos[0]
                                                print(f"[Wrapper] 从 node {node_id} 的 videos 获取视频 URL")
                                                break
                                        # 检查 images 键（某些 workflow 可能返回图片）
                                        elif 'images' in node_output:
                                            images = node_output['images']
                                            if images and len(images) > 0:
                                                # 如果只有图片，可能需要使用其他 workflow
                                                print(f"[Wrapper] 警告: node {node_id} 返回的是图片而不是视频")
                            
                            # 方法3: 检查是否有其他属性包含视频
                            if not generated_video_url:
                                # 尝试检查所有属性
                                for attr in ['video', 'video_url', 'result', 'data']:
                                    if hasattr(workflow_result, attr):
                                        value = getattr(workflow_result, attr)
                                        print(f"[Wrapper] 检查 {attr}: {type(value)}")
                                        if isinstance(value, str) and (value.endswith('.mp4') or 'video' in value.lower()):
                                            generated_video_url = value
                                            print(f"[Wrapper] 从 {attr} 获取视频 URL")
                                            break
                            
                            if not generated_video_url:
                                # 打印完整结果以便调试
                                print(f"[Wrapper] 错误: 无法从 workflow_result 中提取视频 URL")
                                print(f"[Wrapper] workflow_result 完整信息:")
                                print(f"[Wrapper]   {workflow_result}")
                                raise Exception(f"数字人口播 workflow 未返回视频。workflow_result 类型: {type(workflow_result)}, 属性: {[a for a in dir(workflow_result) if not a.startswith('_')]}")
                            
                            print(f"[Wrapper] 数字人口播视频 URL: {generated_video_url}")
                            
                            # 下载视频
                            final_video_path = os.path.join(task_dir, "final.mp4")
                            print(f"[Wrapper] 准备下载视频到: {final_video_path}")
                            print(f"[Wrapper] 视频 URL: {generated_video_url}")
                            
                            # 确保目录存在
                            os.makedirs(os.path.dirname(final_video_path), exist_ok=True)
                            print(f"[Wrapper] 目录已创建: {os.path.dirname(final_video_path)}")
                            
                            import httpx
                            timeout = httpx.Timeout(300.0)
                            async with httpx.AsyncClient(timeout=timeout) as client:
                                print(f"[Wrapper] 开始下载视频...")
                                response = await client.get(generated_video_url)
                                response.raise_for_status()
                                print(f"[Wrapper] 视频下载成功，大小: {len(response.content)} 字节")
                                with open(final_video_path, 'wb') as f:
                                    f.write(response.content)
                            
                            # 验证视频文件是否成功下载
                            if not os.path.exists(final_video_path):
                                raise Exception(f"视频文件未下载: {final_video_path}")
                            
                            file_size = os.path.getsize(final_video_path)
                            print(f"[Wrapper] 视频已下载: {final_video_path} (大小: {file_size / (1024*1024):.2f} MB)")

                            # 口播视频高清增强（RunningHub 工作流）：先高清，再做画中画/字幕/BGM
                            try:
                                # 仅对“数字人口播”分支启用；避免影响其他非口播视频流程
                                if task_id in TASKS and TASKS[task_id].get("status") == "running":
                                    TASKS[task_id]["step"] = "高清增强中..."

                                # 读取主系统 RunningHub Key（优先 config_manager；再回退 config.yaml / 环境变量）
                                runninghub_api_key = getattr(getattr(config_manager, "config", None), "comfyui", None)
                                runninghub_api_key = getattr(runninghub_api_key, "runninghub_api_key", "") if runninghub_api_key else ""
                                runninghub_api_key = (runninghub_api_key or "").strip()
                                require_hd_enhancement = False

                                # workflowId/seed：允许通过 config.yaml 覆盖；否则用默认值（你测试通过的高清工作流）
                                hd_workflow_id = "2037049003786903554"
                                hd_seed = 692322036734462
                                try:
                                    import yaml  # type: ignore
                                    _cfg_path = find_config_yaml()
                                    if _cfg_path:
                                        with open(_cfg_path, "r", encoding="utf-8") as _f:
                                            _y = yaml.safe_load(_f) or {}
                                        _c = (_y.get("comfyui") or {})
                                        _v = ((_y.get("comfyui") or {}).get("video") or {})
                                        hd_workflow_id = str(_v.get("hd_workflow_id") or hd_workflow_id)
                                        if _v.get("hd_seed") is not None:
                                            hd_seed = int(_v.get("hd_seed"))
                                        require_hd_enhancement = bool(_v.get("require_hd_enhancement", False))
                                        if not runninghub_api_key:
                                            runninghub_api_key = str(_c.get("runninghub_api_key") or "").strip()
                                except Exception:
                                    pass
                                if not runninghub_api_key:
                                    runninghub_api_key = os.environ.get("RUNNINGHUB_API_KEY", "").strip()

                                if runninghub_api_key:
                                    from comfykit.comfyui.runninghub_client import RunningHubClient  # type: ignore
                                    import asyncio
                                    import aiohttp
                                    from urllib.parse import urlparse

                                    def _infer_ext(_file_type: str, _file_url: str) -> str:
                                        ft = (_file_type or "").lower()
                                        if "mp4" in ft:
                                            return ".mp4"
                                        if "webm" in ft:
                                            return ".webm"
                                        if "mov" in ft:
                                            return ".mov"
                                        if "avi" in ft:
                                            return ".avi"
                                        p = urlparse(_file_url).path
                                        if "." in p:
                                            return "." + p.split(".")[-1].split("?")[0]
                                        return ".bin"

                                    def _to_ui_video_filename(_uploaded_file_name: str) -> str:
                                        v = (_uploaded_file_name or "").strip()
                                        if v.startswith("api/"):
                                            return v.split("/", 1)[1]
                                        return v

                                    async def _download_to_path(session: aiohttp.ClientSession, url: str, dest_path: str) -> None:
                                        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                                        async with session.get(url) as resp:
                                            resp.raise_for_status()
                                            with open(dest_path, "wb") as f:
                                                async for chunk in resp.content.iter_chunked(1024 * 256):
                                                    if not chunk:
                                                        continue
                                                    f.write(chunk)

                                    base_url = "https://www.runninghub.cn"
                                    rh_client = RunningHubClient(api_key=runninghub_api_key, base_url=base_url, retry_count=3, instance_type=None)
                                    try:
                                        print(f"[Wrapper] [HD] 上传口播视频到 RunningHub: {final_video_path}")
                                        uploaded_file_name = await rh_client.upload_file(str(os.path.abspath(final_video_path)))
                                        ui_video_value = _to_ui_video_filename(uploaded_file_name)

                                        async def _create_task(video_value: str):
                                            node_info_list = [
                                                {"nodeId": "21", "fieldName": "video", "fieldValue": video_value},
                                                {"nodeId": "19", "fieldName": "seed", "fieldValue": hd_seed},
                                            ]
                                            return await rh_client.create_task(hd_workflow_id, node_info_list=node_info_list)

                                        async def _create_with_retry(video_value: str):
                                            backoff_s = 2
                                            while True:
                                                try:
                                                    return await _create_task(video_value)
                                                except Exception as e:
                                                    if "TASK_QUEUE_MAXED" in str(e):
                                                        print(f"[Wrapper] [HD] RunningHub 队列已满，{backoff_s}s 后重试创建任务...")
                                                        await asyncio.sleep(backoff_s)
                                                        backoff_s = min(backoff_s * 2, 30)
                                                        continue
                                                    raise

                                        print(f"[Wrapper] [HD] 创建高清任务 workflowId={hd_workflow_id} ...")
                                        try:
                                            task_data = await _create_with_retry(ui_video_value)
                                        except Exception as e:
                                            msg = str(e)
                                            if "Invalid video file" in msg or "custom_validation_failed" in msg:
                                                print("[Wrapper] [HD] UI-style video value 校验失败，改用 api/<hash>.mp4 重试...")
                                                task_data = await _create_with_retry(uploaded_file_name)
                                            else:
                                                raise

                                        hd_task_id = task_data.get("taskId") or task_data.get("task_id")
                                        if not hd_task_id:
                                            raise RuntimeError(f"[HD] 创建任务失败: {task_data}")
                                        print(f"[Wrapper] [HD] 高清任务已创建: {hd_task_id}")

                                        if task_id in TASKS and TASKS[task_id].get("status") == "running":
                                            TASKS[task_id]["step"] = "高清增强中..."

                                        # 轮询状态
                                        while True:
                                            status_info = await rh_client.query_task_status(hd_task_id)
                                            status = status_info.get("status")
                                            if status == "SUCCESS":
                                                break
                                            if status == "FAILED":
                                                raise RuntimeError(f"[HD] RunningHub 高清任务失败: {status_info.get('msg', '')}")
                                            await asyncio.sleep(3)

                                        if task_id in TASKS and TASKS[task_id].get("status") == "running":
                                            TASKS[task_id]["step"] = "高清下载中..."

                                        # 下载输出视频（优先 mp4）
                                        result_data = await rh_client.query_task_result(hd_task_id)
                                        videos = []
                                        for item in result_data or []:
                                            if not isinstance(item, dict):
                                                continue
                                            file_url = item.get("fileUrl")
                                            file_type = (item.get("fileType") or "").lower()
                                            if not file_url:
                                                continue
                                            ext = _infer_ext(file_type, file_url)
                                            if ext in [".mp4", ".mov", ".avi", ".webm"]:
                                                videos.append((file_url, ext, file_type))

                                        if not videos:
                                            raise RuntimeError("[HD] SUCCESS 但未找到可下载的视频输出")

                                        # 下载第一个视频作为“高清成片”
                                        file_url, ext, _ft = videos[0]
                                        hd_video_path = os.path.join(task_dir, f"final_hd{ext if ext else '.mp4'}")
                                        timeout = aiohttp.ClientTimeout(total=0)
                                        async with aiohttp.ClientSession(timeout=timeout) as download_session:
                                            await _download_to_path(download_session, file_url, hd_video_path)

                                        if os.path.exists(hd_video_path) and os.path.getsize(hd_video_path) > 1024 * 1024:
                                            final_video_path = hd_video_path
                                            print(f"[Wrapper] [HD] 高清视频已下载并启用: {final_video_path}")
                                        else:
                                            print(f"[Wrapper] [HD] 高清视频下载异常，继续使用原视频: {final_video_path}")
                                    finally:
                                        try:
                                            await rh_client.close()
                                        except Exception:
                                            pass
                                else:
                                    if require_hd_enhancement:
                                        raise RuntimeError("[HD] require_hd_enhancement=true，但未配置 runninghub_api_key")
                                    print("[Wrapper] [HD] 未配置 RunningHub API Key，跳过高清增强")
                            except Exception as e:
                                print(f"[Wrapper] [HD] 高清增强流程失败（已降级为原视频继续）: {e}")
                                import traceback
                                traceback.print_exc()
                            
                            # 保存原始文案到任务目录（用于后续字幕生成）
                            script_file = os.path.join(task_dir, "script.txt")
                            try:
                                with open(script_file, 'w', encoding='utf-8') as f:
                                    f.write(text)
                                print(f"[Wrapper] 已保存原始文案到: {script_file}")
                            except Exception as e:
                                print(f"[Wrapper] 保存文案失败: {e}")
                            
                            if defer_finalize:
                                print(f"[Wrapper] defer_finalize=True（数字人）：跳过画中画/字幕/BGM，提取字幕时间轴")
                                try:
                                    from subtitle_burner import extract_subtitle_segments
                                    _segs_dh = extract_subtitle_segments(final_video_path, text)
                                except Exception as _e_dh:
                                    print(f"[Wrapper] 数字人 defer 提取字幕轴失败: {_e_dh}")
                                    _segs_dh = None
                                if task_id in TASKS:
                                    TASKS[task_id]["subtitle_segments"] = _segs_dh or []
                                    TASKS[task_id]["base_video_path"] = final_video_path
                                    TASKS[task_id]["script_text"] = text
                                subtitle_and_bgm_already_done = True

                            if not defer_finalize:
                                # 环境演示（最多 3 段）：0~8 无；8~15 有；15~27 无；27~尾有（见 _apply_showcase_pip_chain）
                                if _collect_existing_showcase_files():
                                    print(f"[Wrapper] 检测到环境演示视频，开始添加画中画效果...")
                                    try:
                                        _pip_host_before = str(final_video_path)

                                        def _run_pip_chain():
                                            return _apply_showcase_pip_chain(_pip_host_before)

                                        pip_video_path = _run_with_step_percent(
                                            task_id,
                                            "画中画匹配中",
                                            _run_pip_chain,
                                            start=5,
                                            cap=92,
                                            tick_sec=1.0,
                                        )
                                        if (
                                            pip_video_path
                                            and os.path.exists(str(pip_video_path))
                                            and str(pip_video_path) != _pip_host_before
                                        ):
                                            final_video_path = str(pip_video_path)
                                            print(f"[Wrapper] 画中画添加成功，视频路径: {final_video_path}")
                                            file_size = os.path.getsize(final_video_path) / (1024 * 1024)
                                            print(f"[Wrapper] 带画中画视频大小: {file_size:.2f} MB")
                                        else:
                                            print(f"[Wrapper] 画中画未改写输出（时长过短或无有效片段），使用原视频")
                                    except Exception as e:
                                        print(f"[Wrapper] 添加画中画时出错: {e}")
                                        import traceback
                                        traceback.print_exc()
                                        print(f"[Wrapper] 继续使用原视频（无画中画）")
                                
                                # 自动为视频添加字幕（使用原始文案）
                                print(f"[Wrapper] 开始为视频添加字幕...")
                                try:
                                    from subtitle_burner import burn_subtitle_to_video
                                    subtitle_video_path = _run_with_step_percent(
                                        task_id,
                                        "字幕匹配中",
                                        lambda: burn_subtitle_to_video(
                                            final_video_path,
                                            text,
                                            None  # 覆盖原视频
                                        ),
                                        start=3,
                                        cap=94,
                                        tick_sec=1.0,
                                    )
                                    if subtitle_video_path and os.path.exists(subtitle_video_path):
                                        final_video_path = subtitle_video_path
                                        print(f"[Wrapper] 字幕添加成功，视频路径: {final_video_path}")
                                        # 更新文件大小
                                        file_size = os.path.getsize(final_video_path) / (1024 * 1024)
                                        print(f"[Wrapper] 带字幕视频大小: {file_size:.2f} MB")
                                    else:
                                        print(f"[Wrapper] 字幕添加失败，使用原视频")
                                except Exception as e:
                                    print(f"[Wrapper] 添加字幕时出错: {e}")
                                    import traceback
                                    traceback.print_exc()
                                    print(f"[Wrapper] 继续使用原视频（无字幕）")
                                
                                # 添加背景音乐（在字幕之后）
                                print(f"[Wrapper] 开始添加背景音乐...")
                                try:
                                    from ai_pipeline.video_editor import add_background_music
                                    import random
                                    
                                    # 检查是否有用户上传的背景音乐
                                    background_music_path = CURRENT_STATE.get("background_music_path")
                                    
                                    # 如果没有用户上传的，从默认音乐中随机选择
                                    if not background_music_path or not os.path.exists(background_music_path):
                                        default_music_dir = WRAPPER_BASE_DIR / "data" / "background_music"
                                        default_music_files = ["轻快.mp3", "野马.mp3", "33.mp3"]
                                        
                                        # 随机选择一个默认音乐
                                        if default_music_dir.exists():
                                            available_music = []
                                            for music_file in default_music_files:
                                                music_path = default_music_dir / music_file
                                                if music_path.exists():
                                                    available_music.append(str(music_path))
                                            
                                            if available_music:
                                                background_music_path = random.choice(available_music)
                                                print(f"[Wrapper] 使用默认背景音乐: {os.path.basename(background_music_path)}")
                                            else:
                                                print(f"[Wrapper] 未找到默认背景音乐文件，跳过背景音乐添加")
                                                background_music_path = None
                                        else:
                                            print(f"[Wrapper] 默认背景音乐目录不存在，跳过背景音乐添加")
                                            background_music_path = None
                                    
                                    if background_music_path and os.path.exists(background_music_path):
                                        music_output_path = os.path.join(os.path.dirname(final_video_path), f"{os.path.splitext(os.path.basename(final_video_path))[0]}_final.mp4")
                                        final_video_with_music = _run_with_step_percent(
                                            task_id,
                                            "BGM匹配中",
                                            lambda: add_background_music(
                                                video_path=str(final_video_path),
                                                music_path=str(background_music_path),
                                                output_path=str(music_output_path),
                                                music_volume=0.08,  # 8%音量
                                                original_volume=1.0,  # 100%原音频音量
                                                fade_in=0.0,
                                                fade_out=0.0,
                                                loop=True
                                            ),
                                            start=2,
                                            cap=93,
                                            tick_sec=1.0,
                                        )
                                        if final_video_with_music and os.path.exists(final_video_with_music):
                                            final_video_path = str(final_video_with_music)
                                            print(f"[Wrapper] 背景音乐添加成功，视频路径: {final_video_path}")
                                            # 更新文件大小
                                            file_size = os.path.getsize(final_video_path) / (1024 * 1024)
                                            print(f"[Wrapper] 带背景音乐视频大小: {file_size:.2f} MB")
                                        else:
                                            print(f"[Wrapper] 背景音乐添加失败，使用原视频")
                                    else:
                                        print(f"[Wrapper] 未找到背景音乐文件，跳过背景音乐添加")
                                except Exception as e:
                                    print(f"[Wrapper] 添加背景音乐时出错: {e}")
                                    import traceback
                                    traceback.print_exc()
                                    print(f"[Wrapper] 继续使用原视频（无背景音乐）")
                                subtitle_and_bgm_already_done = True  # 数字人分支已加字幕+背景音乐，后面不再重复
                            
                            # 获取视频文件大小和时长
                            file_size = os.path.getsize(final_video_path) if os.path.exists(final_video_path) else 0
                            
                            # 尝试从音频获取时长（因为数字人口播视频时长应该等于音频时长）
                            duration = 0.0
                            try:
                                # 先检查音频文件是否存在
                                if audio_path and os.path.exists(audio_path):
                                    print(f"[Wrapper] ========== 准备获取音频时长 ==========")
                                    print(f"[Wrapper] 音频文件路径: {audio_path}")
                                    print(f"[Wrapper] 音频文件绝对路径: {os.path.abspath(audio_path)}")
                                    print(f"[Wrapper] 音频文件存在: {os.path.exists(audio_path)}")
                                    print(f"[Wrapper] 音频文件大小: {os.path.getsize(audio_path) if os.path.exists(audio_path) else 'N/A'} 字节")
                                    
                                    # 检查 FFmpeg 是否可用
                                    import shutil
                                    ffmpeg_path = shutil.which("ffmpeg")
                                    print(f"[Wrapper] FFmpeg 路径: {ffmpeg_path if ffmpeg_path else '未找到（可能使用内部FFmpeg）'}")
                                    
                                    from pixelle_video.utils.tts_util import get_audio_duration
                                    print(f"[Wrapper] 开始调用 get_audio_duration...")
                                    duration = get_audio_duration(audio_path)
                                    print(f"[Wrapper] 从音频获取时长: {duration} 秒")
                                else:
                                    print(f"[Wrapper] 音频文件不存在: {audio_path}，使用默认时长 0.0")
                            except FileNotFoundError as e:
                                print(f"[Wrapper] ========== 文件未找到错误 ==========")
                                print(f"[Wrapper] 错误类型: FileNotFoundError")
                                print(f"[Wrapper] 错误信息: {e}")
                                print(f"[Wrapper] 音频文件路径: {audio_path}")
                                print(f"[Wrapper] 音频文件绝对路径: {os.path.abspath(audio_path) if audio_path else 'N/A'}")
                                print(f"[Wrapper] 音频文件存在: {os.path.exists(audio_path) if audio_path else False}")
                                import traceback
                                print(f"[Wrapper] 完整错误堆栈:\n{traceback.format_exc()}")
                                print(f"[Wrapper] 使用默认值 0.0")
                                duration = 0.0
                            except Exception as e:
                                print(f"[Wrapper] ========== 获取音频时长时出错 ==========")
                                print(f"[Wrapper] 错误类型: {type(e).__name__}")
                                print(f"[Wrapper] 错误信息: {e}")
                                print(f"[Wrapper] 音频文件路径: {audio_path}")
                                print(f"[Wrapper] 音频文件绝对路径: {os.path.abspath(audio_path) if audio_path else 'N/A'}")
                                print(f"[Wrapper] 音频文件存在: {os.path.exists(audio_path) if audio_path else False}")
                                import traceback
                                print(f"[Wrapper] 完整错误堆栈:\n{traceback.format_exc()}")
                                print(f"[Wrapper] 使用默认值 0.0")
                                duration = 0.0
                            
                            # 创建 VideoGenerationResult 对象
                            from pixelle_video.models.storyboard import VideoGenerationResult, Storyboard, StoryboardConfig, StoryboardFrame
                            
                            # 创建最小的 Storyboard 对象
                            config = StoryboardConfig(
                                media_width=1080,
                                media_height=1920,
                                task_id=task_id_internal
                            )
                            
                            # 创建一个空的 storyboard（数字人口播不需要完整的 storyboard）
                            storyboard = Storyboard(
                                title="数字人口播视频",
                                config=config,
                                frames=[],  # 数字人口播不需要 frames
                                final_video_path=final_video_path,
                                total_duration=duration
                            )
                            
                            # 验证视频文件是否存在
                            if not os.path.exists(final_video_path):
                                raise Exception(f"视频文件不存在: {final_video_path}")
                            
                            print(f"[Wrapper] 创建 VideoGenerationResult，视频路径: {final_video_path}")
                            # 验证视频文件是否存在
                            if not os.path.exists(final_video_path):
                                raise Exception(f"视频文件不存在: {final_video_path}")
                            
                            print(f"[Wrapper] 创建 VideoGenerationResult，视频路径: {final_video_path}")
                            result = VideoGenerationResult(
                                video_path=final_video_path,
                                storyboard=storyboard,
                                duration=duration,
                                file_size=file_size
                            )
                            print(f"[Wrapper] VideoGenerationResult 创建成功")
                            print(f"[Wrapper] VideoGenerationResult 创建成功")
                        else:
                            # 没有头像，使用标准 pipeline
                            print(f"[Wrapper] 使用标准 pipeline（无头像）")
                            result = await _pixelle_video.generate_video(
                                text=text,
                                mode="fixed",  # 固定模式，使用文案原样
                                frame_template="1080x1920/default.html",  # 默认模板
                                n_scenes=5,
                                progress_callback=progress_callback,
                            )
                        
                        print(f"[Wrapper] generate_video 调用完成，等待返回结果...")
                        sys.stdout.flush()
                        
                        print(f"[Wrapper] generate_video 调用完成")
                        print(f"[Wrapper] result 类型: {type(result)}")
                        if hasattr(result, 'video_path'):
                            print(f"[Wrapper] result.video_path: {result.video_path}")
                        sys.stdout.flush()
                    except Exception as gen_error:
                        error_msg = str(gen_error)
                        print(f"[Wrapper] generate_video 调用异常: {error_msg}")
                        import traceback
                        error_trace = traceback.format_exc()
                        print(f"[Wrapper] 错误堆栈:\n{error_trace}")
                        sys.stdout.flush()
                        
                        # 如果是文件找不到错误，提供更详细的诊断信息
                        if "WinError 2" in error_msg or "找不到指定的文件" in error_msg or "FileNotFoundError" in error_msg:
                            print(f"[Wrapper] ========== 文件路径诊断 ==========")
                            if 'task_dir' in locals():
                                print(f"[Wrapper] task_dir: {task_dir}")
                                print(f"[Wrapper] task_dir 存在: {os.path.exists(task_dir)}")
                            if 'audio_path' in locals() and audio_path:
                                print(f"[Wrapper] audio_path: {audio_path}")
                                print(f"[Wrapper] audio_path 存在: {os.path.exists(audio_path)}")
                            if 'final_video_path' in locals() and final_video_path:
                                print(f"[Wrapper] final_video_path: {final_video_path}")
                                print(f"[Wrapper] final_video_path 存在: {os.path.exists(final_video_path)}")
                            print(f"[Wrapper] WRAPPER_BASE_DIR: {WRAPPER_BASE_DIR}")
                            print(f"[Wrapper] WRAPPER_BASE_DIR 存在: {WRAPPER_BASE_DIR.exists()}")
                            print(f"[Wrapper] ==================================")
                            sys.stdout.flush()
                        
                        raise
                    
                    # 更新进度：生成完成
                    video_path = result.video_path if hasattr(result, 'video_path') else str(result)
                    print(f"[Wrapper] 提取视频路径: {video_path}")
                    
                    # 验证视频文件是否存在
                    if not video_path or not os.path.exists(video_path):
                        print(f"[Wrapper] 警告: 视频文件不存在: {video_path}")
                        # 尝试在常见位置查找
                        output_dir = find_output_dir()
                        if output_dir and output_dir.exists():
                            # 查找所有子目录中的 final.mp4
                            video_files = list(output_dir.rglob("final.mp4"))
                            if video_files:
                                latest_video = max(video_files, key=os.path.getmtime)
                                video_path = str(latest_video)
                                print(f"[Wrapper] 找到视频文件: {video_path}")
                            else:
                                # 如果没有 final.mp4，查找所有 .mp4 文件
                                video_files = list(output_dir.rglob("*.mp4"))
                                if video_files:
                                    latest_video = max(video_files, key=os.path.getmtime)
                                    video_path = str(latest_video)
                                    print(f"[Wrapper] 找到视频文件: {video_path}")
                    
                    if not video_path or not os.path.exists(video_path):
                        raise Exception(f"无法找到生成的视频文件。result.video_path: {result.video_path if hasattr(result, 'video_path') else 'N/A'}")
                    
                    if defer_finalize:
                        try:
                            from subtitle_burner import extract_subtitle_segments

                            _segs = extract_subtitle_segments(video_path, text)
                        except Exception as _ex:
                            print(f"[Wrapper] defer_finalize 提取字幕轴失败: {_ex}")
                            _segs = None
                        if task_id in TASKS:
                            TASKS[task_id]["subtitle_segments"] = _segs or []
                            TASKS[task_id]["base_video_path"] = video_path
                            TASKS[task_id]["script_text"] = text
                    
                    # 仅当未在数字人分支内加过字幕和背景音乐时，这里再加一次（标准 pipeline 无头像时走这里）
                    if not defer_finalize and not subtitle_and_bgm_already_done:
                        # 自动为视频添加字幕（使用原始文案）
                        print(f"[Wrapper] 开始为视频添加字幕...")
                        try:
                            from subtitle_burner import burn_subtitle_to_video
                            subtitle_video_path = _run_with_step_percent(
                                task_id,
                                "字幕匹配中",
                                lambda: burn_subtitle_to_video(
                                    video_path,
                                    text,  # 使用生成视频时的原始文案
                                    None  # 覆盖原视频
                                ),
                                start=3,
                                cap=94,
                                tick_sec=1.0,
                            )
                            if subtitle_video_path and os.path.exists(subtitle_video_path):
                                video_path = subtitle_video_path
                                print(f"[Wrapper] 字幕添加成功，视频路径: {video_path}")
                            else:
                                print(f"[Wrapper] 字幕添加失败，使用原视频")
                        except Exception as e:
                            print(f"[Wrapper] 添加字幕时出错: {e}")
                            import traceback
                            traceback.print_exc()
                            print(f"[Wrapper] 继续使用原视频（无字幕）")
                        
                        # 添加背景音乐（在字幕之后）
                        print(f"[Wrapper] 开始添加背景音乐...")
                        try:
                            from ai_pipeline.video_editor import add_background_music
                            import random
                            
                            # 检查是否有用户上传的背景音乐
                            background_music_path = CURRENT_STATE.get("background_music_path")
                            
                            # 如果没有用户上传的，从默认音乐中随机选择
                            if not background_music_path or not os.path.exists(background_music_path):
                                default_music_dir = WRAPPER_BASE_DIR / "data" / "background_music"
                                default_music_files = ["轻快.mp3", "野马.mp3", "33.mp3"]
                                
                                # 随机选择一个默认音乐
                                if default_music_dir.exists():
                                    available_music = []
                                    for music_file in default_music_files:
                                        music_path = default_music_dir / music_file
                                        if music_path.exists():
                                            available_music.append(str(music_path))
                                    
                                    if available_music:
                                        background_music_path = random.choice(available_music)
                                        print(f"[Wrapper] 使用默认背景音乐: {os.path.basename(background_music_path)}")
                                    else:
                                        print(f"[Wrapper] 未找到默认背景音乐文件，跳过背景音乐添加")
                                        background_music_path = None
                                else:
                                    print(f"[Wrapper] 默认背景音乐目录不存在，跳过背景音乐添加")
                                    background_music_path = None
                            
                            if background_music_path and os.path.exists(background_music_path):
                                music_output_path = os.path.join(os.path.dirname(video_path), f"{os.path.splitext(os.path.basename(video_path))[0]}_final.mp4")
                                final_video_with_music = _run_with_step_percent(
                                    task_id,
                                    "BGM匹配中",
                                    lambda: add_background_music(
                                        video_path=str(video_path),
                                        music_path=str(background_music_path),
                                        output_path=str(music_output_path),
                                        music_volume=0.08,  # 8%音量
                                        original_volume=1.0,  # 100%原音频音量
                                        fade_in=0.0,
                                        fade_out=0.0,
                                        loop=True
                                    ),
                                    start=2,
                                    cap=93,
                                    tick_sec=1.0,
                                )
                                if final_video_with_music and os.path.exists(final_video_with_music):
                                    video_path = str(final_video_with_music)
                                    print(f"[Wrapper] 背景音乐添加成功，视频路径: {video_path}")
                                else:
                                    print(f"[Wrapper] 背景音乐添加失败，使用原视频")
                            else:
                                print(f"[Wrapper] 未找到背景音乐文件，跳过背景音乐添加")
                        except Exception as e:
                            print(f"[Wrapper] 添加背景音乐时出错: {e}")
                            import traceback
                            traceback.print_exc()
                            print(f"[Wrapper] 继续使用原视频（无背景音乐）")
                    
                    TASKS[task_id]["progress"] = 100
                    TASKS[task_id]["status"] = "done"
                    TASKS[task_id]["output"] = video_path
                    
                    print(f"[Wrapper] [OK] 任务 {task_id} 完成: {video_path}")
                    # 检查文件是否存在
                    if os.path.exists(video_path):
                        file_size = os.path.getsize(video_path) / (1024 * 1024)  # MB
                        print(f"[Wrapper] 视频文件大小: {file_size:.2f} MB")
                    else:
                        print(f"[Wrapper] 警告: 视频文件不存在: {video_path}")
                        # 尝试在常见位置查找
                        output_dir = find_output_dir()
                        if output_dir and output_dir.exists():
                            # 查找所有子目录中的 final.mp4
                            video_files = list(output_dir.rglob("final.mp4"))
                            if video_files:
                                # 按修改时间排序，取最新的
                                latest_video = max(video_files, key=os.path.getmtime)
                                print(f"[Wrapper] 在 {output_dir} 目录找到最新视频文件: {latest_video}")
                                TASKS[task_id]["output"] = str(latest_video)
                            else:
                                # 如果没有 final.mp4，查找所有 .mp4 文件
                                video_files = list(output_dir.rglob("*.mp4"))
                                if video_files:
                                    latest_video = max(video_files, key=os.path.getmtime)
                                    print(f"[Wrapper] 在 {output_dir} 目录找到最新视频文件: {latest_video}")
                                    TASKS[task_id]["output"] = str(latest_video)
                    
                except FileNotFoundError as e:
                    error_msg = f"[WinError 2] 系统找不到指定的文件: {str(e)}"
                    print(f"[Wrapper] ========== 文件未找到错误（任务 {task_id}）==========")
                    print(f"[Wrapper] 错误类型: FileNotFoundError")
                    print(f"[Wrapper] 错误信息: {e}")
                    print(f"[Wrapper] 错误参数: {e.args if hasattr(e, 'args') else 'N/A'}")
                    print(f"[Wrapper] 错误文件名: {e.filename if hasattr(e, 'filename') else 'N/A'}")
                    print(f"[Wrapper] 错误文件编号: {e.filename2 if hasattr(e, 'filename2') else 'N/A'}")
                    import traceback
                    print(f"[Wrapper] 完整错误堆栈:\n{traceback.format_exc()}")
                    print(f"[Wrapper] ==================================")
                    sys.stdout.flush()
                    TASKS[task_id]["status"] = "error"
                    TASKS[task_id]["error"] = error_msg
                    TASKS[task_id]["progress"] = 0
                except Exception as e:
                    error_msg = str(e)
                    print(f"[Wrapper] ========== 任务 {task_id} 失败 ==========")
                    print(f"[Wrapper] 错误类型: {type(e).__name__}")
                    print(f"[Wrapper] 错误信息: {error_msg}")
                    import traceback
                    print(f"[Wrapper] 完整错误堆栈:\n{traceback.format_exc()}")
                    print(f"[Wrapper] ==================================")
                    sys.stdout.flush()
                    TASKS[task_id]["status"] = "error"
                    TASKS[task_id]["error"] = error_msg
                    TASKS[task_id]["progress"] = 0
            
            loop.run_until_complete(async_generate())
            loop.close()
            
        except Exception as e:
            error_msg = str(e)
            print(f"[Wrapper] [X] 任务 {task_id} 执行异常: {error_msg}")
            import traceback
            traceback.print_exc()
            TASKS[task_id]["status"] = "error"
            TASKS[task_id]["error"] = error_msg
    
    # 启动后台线程
    thread = threading.Thread(target=run_generation, daemon=True)
    thread.start()
    
    return {
        "success": True,
        "task_id": task_id,
        "message": "任务已创建"
    }


class FinalizeManualRequest(BaseModel):
    """成品素材「再次生成」：画中画 + 用户确认后的字幕 + BGM。"""

    base_video_path: str
    segments: List[Dict[str, Any]]
    script_text: Optional[str] = ""


def _run_finalize_manual_thread(ftask_id: str, base_video_path: str, segments: List[Dict[str, Any]]):
    """后台线程：与手动数字人成片顺序一致（PIP → 字幕 → BGM）。"""
    try:
        TASKS[ftask_id]["status"] = "running"
        TASKS[ftask_id]["progress"] = 5
        TASKS[ftask_id]["step"] = "准备合成…"
        v = base_video_path.strip()
        if not v or not os.path.exists(v):
            raise FileNotFoundError(f"底片不存在: {v}")

        if _collect_existing_showcase_files():
            TASKS[ftask_id]["step"] = "画中画匹配中…"
            TASKS[ftask_id]["progress"] = 15
            v_before = v
            v = _apply_showcase_pip_chain(v)
            if v != v_before:
                TASKS[ftask_id]["progress"] = 35

        TASKS[ftask_id]["step"] = "字幕烧录中…"
        TASKS[ftask_id]["progress"] = 45
        from subtitle_burner import burn_subtitles_from_segments

        sub_out = os.path.join(os.path.dirname(v), f"{os.path.splitext(os.path.basename(v))[0]}_mf_sub.mp4")
        v_sub = burn_subtitles_from_segments(v, segments, sub_out)
        if v_sub and os.path.exists(v_sub):
            v = v_sub

        TASKS[ftask_id]["step"] = "BGM匹配中…"
        TASKS[ftask_id]["progress"] = 70
        from ai_pipeline.video_editor import add_background_music
        import random

        background_music_path = CURRENT_STATE.get("background_music_path")
        if not background_music_path or not os.path.exists(background_music_path):
            default_music_dir = WRAPPER_BASE_DIR / "data" / "background_music"
            default_music_files = ["轻快.mp3", "野马.mp3", "33.mp3"]
            if default_music_dir.exists():
                available_music = []
                for music_file in default_music_files:
                    music_path = default_music_dir / music_file
                    if music_path.exists():
                        available_music.append(str(music_path))
                if available_music:
                    background_music_path = random.choice(available_music)
        if background_music_path and os.path.exists(background_music_path):
            music_output_path = os.path.join(
                os.path.dirname(v), f"{os.path.splitext(os.path.basename(v))[0]}_mf_final.mp4"
            )
            final_v = add_background_music(
                video_path=str(v),
                music_path=str(background_music_path),
                output_path=str(music_output_path),
                music_volume=0.08,
                original_volume=1.0,
                fade_in=0.0,
                fade_out=0.0,
                loop=True,
            )
            if final_v and os.path.exists(final_v):
                v = str(final_v)

        TASKS[ftask_id]["output"] = v
        TASKS[ftask_id]["status"] = "done"
        TASKS[ftask_id]["progress"] = 100
        TASKS[ftask_id]["step"] = "完成"
        print(f"[Wrapper] finalize_manual 完成: {v}")
    except Exception as e:
        logger.exception("[finalize_manual] 失败: %s", e)
        TASKS[ftask_id]["status"] = "error"
        TASKS[ftask_id]["error"] = str(e)
        TASKS[ftask_id]["progress"] = 0


@app.post("/api/generate/finalize_manual")
async def finalize_manual(req: FinalizeManualRequest):
    """手动成品素材二次合成（不跑 Whisper，仅烧录用户改过的字幕）。"""
    if not req.base_video_path or not req.segments:
        raise HTTPException(status_code=400, detail="base_video_path 与 segments 不能为空")
    ftask_id = str(uuid.uuid4())
    TASKS[ftask_id] = {
        "status": "running",
        "progress": 0,
        "output": None,
        "error": None,
        "created_at": datetime.now().isoformat(),
        "step": "排队中…",
    }
    t = threading.Thread(
        target=_run_finalize_manual_thread,
        args=(ftask_id, req.base_video_path, req.segments),
        daemon=True,
    )
    t.start()
    return {"success": True, "task_id": ftask_id, "message": "二次合成任务已创建"}


class FinishedMaterialRebuildSubtitlesRequest(BaseModel):
    """成品素材页：按当前视频 + 文案重新抽取字幕时间轴（Whisper 管线）。"""

    video_path: str
    script_text: str = ""


@app.post("/api/finished_material/rebuild_subtitles")
async def finished_material_rebuild_subtitles(req: FinishedMaterialRebuildSubtitlesRequest):
    """仅成品素材页使用：路径须在 output/outputs 白名单内。"""
    raw = (req.video_path or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="video_path 不能为空")
    try:
        candidate = Path(raw).expanduser().resolve()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"无效路径: {e}")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    roots = _local_video_allowed_roots()
    if not roots or not _is_path_under_any_root(candidate, roots):
        raise HTTPException(status_code=403, detail="路径不在允许的输出目录内")
    try:
        from subtitle_burner import extract_subtitle_segments

        segs = extract_subtitle_segments(str(candidate), (req.script_text or "").strip()) or []
    except Exception as e:
        logger.exception("[finished_material] rebuild_subtitles: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
    norm = [
        {"start": float(s.get("start", 0.0)), "end": float(s.get("end", 0.0)), "text": str(s.get("text", "") or "")}
        for s in segs
    ]
    return {"success": True, "subtitle_segments": norm}


@app.post("/api/finished_material/upload_video")
async def finished_material_upload_video(
    file: UploadFile = File(...),
    script_text: str = Form(""),
):
    """
    成品素材页：上传替代底片到 output/finished_manual/，供预览与 finalize_manual。
    可选 script_text 用于上传后立即抽字幕轴。
    """
    try:
        out_root = WRAPPER_BASE_DIR / "output" / "finished_manual"
        out_root.mkdir(parents=True, exist_ok=True)
        ext = os.path.splitext(file.filename or "")[1].lower() or ".mp4"
        if ext not in (".mp4", ".webm", ".mov", ".mkv", ".m4v"):
            raise HTTPException(status_code=400, detail="仅支持 mp4/webm/mov/mkv/m4v")
        safe_name = f"fm_{uuid.uuid4().hex}{ext}"
        dest = out_root / safe_name

        max_bytes = 500 * 1024 * 1024
        total = 0
        chunk_size = 1024 * 1024
        with open(dest, "wb") as fp:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    try:
                        dest.unlink(missing_ok=True)
                    except Exception:
                        pass
                    raise HTTPException(status_code=413, detail="文件过大（上限 500MB）")
                fp.write(chunk)
        if total == 0:
            try:
                dest.unlink(missing_ok=True)
            except Exception:
                pass
            raise HTTPException(status_code=400, detail="文件内容为空")

        segs_out: List[Dict[str, Any]] = []
        st = (script_text or "").strip()
        if st:
            try:
                from subtitle_burner import extract_subtitle_segments

                segs_out = extract_subtitle_segments(str(dest.resolve()), st) or []
            except Exception as e:
                logger.warning("[finished_material] upload 后抽字幕失败（可稍后手动生成）: %s", e)
        norm = [
            {"start": float(s.get("start", 0.0)), "end": float(s.get("end", 0.0)), "text": str(s.get("text", "") or "")}
            for s in segs_out
        ]
        return {
            "success": True,
            "path": str(dest.resolve()),
            "filename": safe_name,
            "size": total,
            "subtitle_segments": norm,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[finished_material] upload_video: %s", e)
        raise HTTPException(status_code=500, detail=f"上传失败: {e}")


# ============================================================================

@app.get("/api/task/{task_id}")
async def get_task_status(task_id: str):
    """
    查询任务状态（UI 进度条依赖）
    
    返回：
        {
            "status": "running | done | error",
            "progress": 0-100,
            "output": "video.mp4" 或 null,
            "message": "状态描述信息"
        }
    """
    # 使用 asyncio.sleep(0) 让出控制权，避免阻塞
    await asyncio.sleep(0)
    
    if task_id not in TASKS:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    task = TASKS[task_id]
    
    # 简化：不在这里检查文件，避免阻塞查询接口
    # 文件检查在任务完成时已经完成
    
    # 添加状态描述信息
    message = ""
    if task["status"] == "running":
        # 计算运行时间
        from datetime import datetime
        created_at = datetime.fromisoformat(task.get("created_at", datetime.now().isoformat()))
        elapsed = (datetime.now() - created_at).total_seconds()
        minutes = int(elapsed / 60)
        message = f"视频生成中，已运行 {minutes} 分钟..."
    elif task["status"] == "done":
        output = task.get("output")
        if output and os.path.exists(output):
            message = f"视频生成完成: {output}"
        else:
            message = "视频生成完成（但文件路径可能不正确）"
    elif task["status"] == "cancelled":
        message = "任务已停止（用户取消）"
    elif task["status"] == "error":
        message = f"生成失败: {task.get('error', '未知错误')}"
    
    return {
        "status": task["status"],
        "progress": task["progress"],
        "output": task.get("output"),
        "error": task.get("error"),
        "message": message,
        "step": task.get("step", ""),  # 添加步骤信息
        "script": task.get("script"),  # 添加文案信息
        "video_path": task.get("video_path"),  # 添加视频路径
        "content": task.get("content"),  # 添加内容信息
        "publish_results": task.get("publish_results", []),  # 添加发布结果
        "subtitle_segments": task.get("subtitle_segments"),
        "base_video_path": task.get("base_video_path"),
    }

@app.delete("/api/task/{task_id}")
async def cancel_task(task_id: str):
    """
    Cancel a running or pending auto_generate_full task.
    Only affects the specified task_id.
    """
    if task_id not in TASKS:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 标记取消；执行线程会在关键循环点检查并尽快退出。
    TASKS[task_id]["cancel_requested"] = True
    TASKS[task_id]["status"] = "cancelled"
    TASKS[task_id]["step"] = "已停止"

    # 保留当前 progress/已知信息（不强制归零），便于前端展示
    TASKS[task_id]["completed_at"] = datetime.now().isoformat()

    logger.info(f"[AutoGenerate] 用户取消任务: {task_id}")
    return {
        "success": True,
        "message": "任务已停止",
        "task_id": task_id,
    }

@app.get("/api/tasks")
async def list_tasks():
    """列出所有任务（用于调试）"""
    return {
        "tasks": {
            task_id: {
                "status": task["status"],
                "progress": task["progress"],
                "output": task.get("output"),
                "error": task.get("error"),
                "created_at": task.get("created_at")
            }
            for task_id, task in TASKS.items()
        }
    }

# ============================================================================

def _local_video_allowed_roots():
    """允许通过 /api/local_video_file 读取的视频根目录（output / outputs）。"""
    roots = []
    try:
        w = WRAPPER_BASE_DIR.resolve()
        roots.append(w / "output")
        roots.append(w / "outputs")
    except Exception:
        pass
    if PIXELLE_VIDEO_PATH:
        try:
            pv = Path(PIXELLE_VIDEO_PATH).resolve()
            roots.append(pv / "output")
            roots.append(pv / "outputs")
        except Exception:
            pass
    return roots


def _is_path_under_any_root(file_path: Path, roots: list) -> bool:
    try:
        resolved = file_path.resolve()
    except Exception:
        return False
    for root in roots:
        try:
            root_r = root.resolve()
            resolved.relative_to(root_r)
            return True
        except ValueError:
            continue
        except Exception:
            continue
    return False


@app.get("/api/local_video_file")
async def local_video_file(path: str):
    """
    同源视频预览：从允许的 output 目录读取文件，供浏览器 <video> 播放（避免 file:// 被拦截）。
    """
    from urllib.parse import unquote

    raw = (unquote(path or "") or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="path 为空")
    try:
        candidate = Path(raw).expanduser().resolve()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"无效路径: {e}")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    roots = _local_video_allowed_roots()
    if not roots or not _is_path_under_any_root(candidate, roots):
        raise HTTPException(status_code=403, detail="路径不在允许的输出目录内")

    ext = candidate.suffix.lower()
    if ext not in (".mp4", ".webm", ".mov", ".mkv", ".m4v"):
        raise HTTPException(status_code=400, detail="不支持的文件类型")

    media = "video/mp4"
    if ext == ".webm":
        media = "video/webm"
    elif ext == ".mov":
        media = "video/quicktime"
    elif ext == ".mkv":
        media = "video/x-matroska"

    return FileResponse(
        str(candidate),
        media_type=media,
        filename=candidate.name,
    )


@app.get("/api/download/{task_id}")
async def download_video(task_id: str):
    """
    下载生成视频
    
    返回视频文件（使用 FastAPI FileResponse）
    """
    if task_id not in TASKS:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    task = TASKS[task_id]
    
    if task["status"] != "done":
        raise HTTPException(status_code=400, detail="视频尚未生成完成")
    
    output_path = task.get("output")
    if not output_path or not os.path.exists(output_path):
        raise HTTPException(status_code=404, detail="视频文件不存在")
    
    return FileResponse(
        output_path,
        media_type="video/mp4",
        filename=os.path.basename(output_path)
    )

# ============================================================================
# AI短视频自动生成接口
# ============================================================================

class CopywritingPersonaConfig(BaseModel):
    """文案改写专用人设配置（只包含文案需要的字段）"""
    companyName: str = ""  # 公司/团队名字
    targetMarket: str = ""  # 目标客户群体（全国/区域）
    coreSolution: str = ""  # 核心产品或服务解决的需求
    productYears: str = ""  # 公司产品几年了
    productAdvantages: str = ""  # 产品的优势
    other: str = ""  # 其他（可选）

class AutoGenerateRequest(BaseModel):
    """自动生成请求模型"""
    link: str
    compliance_enabled: bool = False
    platforms: List[str] = []
    persona_config: Optional[CopywritingPersonaConfig] = None  # 文案改写专用人设配置（可选）

@app.post("/api/browser/login")
async def browser_login(payload: Dict[str, Any] = Body(default_factory=dict)):
    """
    打开浏览器登录页面
    
    重要：使用统一的浏览器实例（douyin_publish_mcp.ensure_browser()）
    - 与发布功能使用相同的浏览器实例
    - 浏览器数据保存在项目内：browser_data/chrome_user_data/Profile 3
    - 登录信息会永久保存，下次打开自动登录
    """
    try:
        # 延迟导入，避免模块初始化时阻塞
        # 使用相对导入或添加路径
        import sys
        from pathlib import Path
        wrapper_dir = Path(__file__).parent
        if str(wrapper_dir) not in sys.path:
            sys.path.insert(0, str(wrapper_dir))
        import douyin_publish_mcp
        
        # 明确从 JSON Body 读取，避免某些环境下被解析成 query 导致 422
        platform = (payload or {}).get("platform", "douyin")
        
        logging.info(f"[BrowserLogin] 平台: {platform}")
        
        # 根据平台选择登录URL（使用创作者中心，登录后会自动保存）
        login_urls = {
            'douyin': 'https://creator.douyin.com/creator-micro/content/upload?enter_from=dou_web',
            'kuaishou': (
                'https://cp.kuaishou.com/article/publish/video'
                '?origin=www.kuaishou.com&source=NewReco'
            ),
            'xhs': 'https://creator.xiaohongshu.com/publish/publish',  # 小红书创作者中心
            'sph': 'https://channels.weixin.qq.com'
        }

        platform_domains = {
            'douyin': ('douyin.com',),
            'kuaishou': ('kuaishou.com',),
            'xhs': ('xiaohongshu.com',),
            'sph': ('weixin.qq.com',),
        }
        platform = str(platform or 'douyin').strip().lower()
        if platform not in login_urls:
            raise HTTPException(status_code=400, detail=f"不支持的登录平台: {platform}")

        url = login_urls[platform]
        
        # 使用Selenium方式打开浏览器（与发布功能使用相同的浏览器实例）
        # 直接调用 ensure_browser()，确保使用完全相同的浏览器配置
        # 这与 test_selenium_simple.py 和 _publish_video_impl() 使用完全相同的方式
        logging.info("[BrowserLogin] ========== 开始打开浏览器 ==========")
        
        # 旧实现启动后台线程后立即返回 success，导致 Chrome 只打开新标签页时前端仍误报成功。
        # 现在等待实际导航完成，并以当前域名作为成功判据；慢网络最多等待 150 秒。
        logging.info(f"[BrowserLogin] 启动并确认平台页面: {url}")
        try:
            open_result = await asyncio.wait_for(
                asyncio.to_thread(
                    douyin_publish_mcp.open_login_url,
                    url,
                    platform_domains[platform],
                ),
                timeout=300,
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="打开平台登录页超时，请检查客户机网络后重试")

        if not open_result.get("success"):
            detail = open_result.get("error") or "Chrome 未进入目标平台"
            current_url = open_result.get("current_url") or "未知"
            logging.error(f"[BrowserLogin] 导航失败: {detail}; current_url={current_url}")
            raise HTTPException(
                status_code=502,
                detail=f"打开 {platform} 登录页失败；当前页面: {current_url}；原因: {detail}",
            )

        current_url = open_result.get("current_url") or url
        logging.info(f"[BrowserLogin] ✅ 已确认进入平台页面: {current_url}")
        if platform == "douyin":
            try:
                from ai_pipeline.douyin_cookie_store import load_douyin_cookies
                n = len(load_douyin_cookies(sync_cache=True))
                logging.info(f"[BrowserLogin] 已同步抖音 Cookie ({n} 项) 供下载兜底使用")
            except Exception as sync_exc:
                logging.warning(f"[BrowserLogin] 同步抖音 Cookie 失败: {sync_exc}")

        return {
            "success": True,
            "message": f"浏览器登录页面已打开: {current_url}",
            "url": url,
            "current_url": current_url,
            "platform": platform,
            "note": "已确认浏览器进入目标平台"
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_msg = f"打开浏览器登录页面失败: {str(e)}\n{traceback.format_exc()}"
        logging.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


@app.get("/api/browser/status")
async def browser_status():
    """检查浏览器状态（使用Selenium方式）"""
    try:
        # 使用相对导入或添加路径
        import sys
        from pathlib import Path
        wrapper_dir = Path(__file__).parent
        if str(wrapper_dir) not in sys.path:
            sys.path.insert(0, str(wrapper_dir))
        import douyin_publish_mcp
        
        # 检查Selenium浏览器是否已启动
        is_initialized = False
        platform_status = {}
        
        try:
            if douyin_publish_mcp.driver:
                # 检查浏览器是否仍然有效
                current_url = douyin_publish_mcp.driver.current_url
                is_initialized = True
                
                # 检查每个平台的登录状态
                for platform_id, check_domains in [
                    ('douyin', ['creator.douyin.com', 'douyin.com']),
                    ('kuaishou', ['kuaishou.com', 'cp.kuaishou.com']),
                    ('xhs', ['xiaohongshu.com', 'creator.xiaohongshu.com']),
                    ('sph', ['channels.weixin.qq.com', 'weixin.qq.com']),
                ]:
                    is_logged_in = False
                    try:
                        # 检查当前URL是否匹配平台域名
                        if any(domain in current_url for domain in check_domains):
                            # 如果URL包含登录页面标识，说明未登录
                            login_indicators = ['/login', '/signin', '/passport', '/account/login']
                            if not any(indicator in current_url.lower() for indicator in login_indicators):
                                is_logged_in = True
                    except Exception as e:
                        logger.debug(f"[BrowserStatus] 检查平台 {platform_id} 失败: {e}")
                    
                    platform_status[platform_id] = is_logged_in
        except:
            # 浏览器未启动或已关闭
            is_initialized = False
        
        return {
            "status": "connected" if is_initialized else "disconnected",
            "initialized": is_initialized,
            "message": "浏览器已初始化" if is_initialized else "浏览器未初始化",
            "platforms": platform_status
        }
    except Exception as e:
        return {
            "status": "disconnected",
            "initialized": False,
            "message": f"检查浏览器状态失败: {str(e)}",
            "platforms": {}
        }


class PersonaConfig(BaseModel):
    """人设配置（完整版，用于爆光模块等）"""
    consumptionRange: str = ""  # 产品消费金额区间
    wechatId: str = ""  # 微信号
    companyName: str = ""  # 公司/团队名字
    targetMarket: str = ""  # 目标客户群体（全国/区域）
    coreSolution: str = ""  # 核心产品或服务解决的需求
    companyAddress: str = ""  # 公司地址
    productYears: str = ""  # 公司产品几年了
    productAdvantages: str = ""  # 产品的优势
    other: str = ""  # 其他

class LinkParseRequest(BaseModel):
    """链接解析请求"""
    link: str
    persona_config: Optional[CopywritingPersonaConfig] = None  # 文案改写专用人设配置（可选）
    optimize: bool = False  # 是否继续优化（生成新版本）


@app.post("/api/copywriting/parse_link")
async def parse_link_and_rewrite(request: LinkParseRequest):
    """
    解析链接、下载视频、提取文案、进行二创
    
    流程：
    1. 从链接文本中提取视频URL
    2. 使用 douyin-mcp-server 下载视频并提取文案（使用硅基流动 API，质量更高）
    3. AI改写文案（二创）
    
    返回：
    - original_script: 原文案（从视频中提取，使用硅基流动 API）
    - rewritten_script: 改写后的文案
    """
    try:
        import asyncio
        import sys
        from pathlib import Path
        
        logger.info(f"[API] 开始处理链接解析: {request.link[:100]}...")
        
        # 使用 douyin-mcp-server 提取文案（质量更高，更稳定）
        try:
            # 添加 douyin-mcp-server 路径
            current_file = Path(__file__)
            project_root = current_file.parent.parent
            douyin_mcp_path = project_root / "douyin-mcp-server-main"
            
            if douyin_mcp_path.exists():
                douyin_script_path = douyin_mcp_path / "douyin-video" / "scripts" / "douyin_downloader.py"
                if douyin_script_path.exists():
                    # 导入 douyin-mcp-server 模块
                    import importlib.util
                    spec = importlib.util.spec_from_file_location("douyin_downloader", douyin_script_path)
                    douyin_downloader = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(douyin_downloader)
                    
                    # 获取 API Key（从配置文件或环境变量）
                    api_key = os.getenv('API_KEY', '')
                    if not api_key:
                        config_file = douyin_mcp_path / "config.env"
                        if config_file.exists():
                            with open(config_file, 'r', encoding='utf-8') as f:
                                for line in f:
                                    if line.startswith('API_KEY='):
                                        api_key = line.split('=', 1)[1].strip()
                                        break
                    
                    if not api_key:
                        raise HTTPException(status_code=500, detail="未配置硅基流动 API Key，请在 config.env 中设置")
                    
                    logger.info("[API] 使用 douyin-mcp-server 提取文案（硅基流动 API）...")
                    
                    # 调用 douyin-mcp-server 的 extract_text 函数
                    output_dir = Path(__file__).parent / "materials" / "douyin_output"
                    output_dir.mkdir(parents=True, exist_ok=True)
                    
                    result = await asyncio.to_thread(
                        douyin_downloader.extract_text,
                        request.link,
                        api_key=api_key,
                        output_dir=str(output_dir),
                        save_video=False,
                        show_progress=False
                    )
                    
                    original_text = result['text']
                    video_info = result['video_info']
                    
                    logger.info(f"[API] 文案提取成功（硅基流动 API），长度: {len(original_text)}")
                    logger.info(f"[API] 文案内容: {original_text[:100]}...")
                    
                    # 提取文案结构（hook, problem, solution, cta）
                    from ai_pipeline.script_extractor import extract_script
                    script_dict = extract_script(original_text)
                    script_dict['full_script'] = original_text  # 添加完整文案
                    
                    # AI改写文案（使用人设配置）
                    logger.info("[API] 开始AI改写文案（使用人设配置）...")
                    from ai_pipeline.script_rewriter import rewrite_script
                    persona_dict = None
                    if request.persona_config:
                        persona_dict = request.persona_config.dict()
                        logger.info(f"[API] 使用人设配置: {persona_dict.get('companyName', '')}")
                    # 如果继续优化，在提示词中强调生成不同版本
                    if request.optimize:
                        logger.info("[API] 继续优化模式：生成新版本")
                    
                    rewritten_dict = rewrite_script(
                        script_dict, 
                        persona_config=persona_dict,
                        optimize=request.optimize
                    )
                    
                    logger.info("[API] 文案改写完成")
                    
                    # 计算相似度
                    from ai_pipeline.text_similarity import calculate_similarity
                    similarity_result = calculate_similarity(
                        original_text,
                        rewritten_dict.get('full_script', '')
                    )
                    logger.info(f"[API] 相似度分析: 去重率={similarity_result['deduplication_rate']}%")
                    
                    return {
                        "success": True,
                        "original_script": {
                            "full_script": original_text,
                            "hook": script_dict.get('hook', ''),
                            "problem": script_dict.get('problem', ''),
                            "solution": script_dict.get('solution', ''),
                            "cta": script_dict.get('cta', '')
                        },
                        "rewritten_script": rewritten_dict,
                        "similarity": similarity_result,
                        "video_info": {
                            "video_id": video_info.get('video_id', ''),
                            "title": video_info.get('title', ''),
                            "url": video_info.get('url', '')
                        },
                        "message": "链接解析、视频下载、文案提取与改写成功（使用硅基流动 API）"
                    }
        except Exception as douyin_error:
            logger.warning(f"[API] douyin-mcp-server 提取失败，回退到 Whisper: {douyin_error}")
            # 回退到原来的 Whisper 方案
            pass
        
        # 回退方案：使用原来的 Whisper 流程
        logger.info("[API] 使用 Whisper 提取文案（回退方案）...")
        from ai_pipeline.link_parser import extract_video_url
        from ai_pipeline.video_downloader import download_video
        from ai_pipeline.audio_extractor import extract_audio_from_video
        from ai_pipeline.subtitle_generator import generate_subtitle
        from ai_pipeline.script_extractor import extract_script
        from ai_pipeline.script_rewriter import rewrite_script
        
        # 1. 提取视频URL
        video_url = extract_video_url(request.link)
        if not video_url:
            raise HTTPException(status_code=400, detail="无法从链接中提取视频URL")
        
        logger.info(f"[API] 提取到视频URL: {video_url}")
        
        # 2. 下载视频（在后台线程中执行，避免阻塞）
        materials_dir = Path(__file__).parent / "materials"
        materials_dir.mkdir(exist_ok=True)
        
        logger.info("[API] 开始下载视频...")
        video_path = await asyncio.to_thread(download_video, video_url, materials_dir)
        if not video_path or not Path(video_path).exists():
            raise HTTPException(status_code=500, detail="视频下载失败")
        
        logger.info(f"[API] 视频下载完成: {video_path}")
        
        # 3. 提取音频
        logger.info("[API] 开始提取音频...")
        audio_path = await asyncio.to_thread(extract_audio_from_video, str(video_path), materials_dir)
        if not audio_path or not Path(audio_path).exists():
            raise HTTPException(status_code=500, detail="音频提取失败")
        
        logger.info(f"[API] 音频提取完成: {audio_path}")
        
        # 4. 语音转文字（使用 Whisper）
        logger.info("[API] 开始语音转文字（Whisper）...")
        srt_path = await asyncio.to_thread(generate_subtitle, str(audio_path), materials_dir)
        if not srt_path or not Path(srt_path).exists():
            raise HTTPException(status_code=500, detail="语音转文字失败")
        
        # 从SRT文件中提取完整文案
        with open(srt_path, 'r', encoding='utf-8') as f:
            srt_content = f.read()
        
        # 提取所有文本（去掉时间戳和序号）
        lines = srt_content.split('\n')
        text_lines = []
        for line in lines:
            line = line.strip()
            if line and not line.isdigit() and '-->' not in line:
                text_lines.append(line)
        
        original_text = ' '.join(text_lines)
        logger.info(f"[API] 原文案提取完成: {original_text[:100]}...")
        
        # 5. 提取文案结构（hook, problem, solution, cta）
        script_dict = extract_script(original_text)
        script_dict['full_script'] = original_text  # 添加完整文案
        
        # 6. AI改写文案（使用人设配置）
        logger.info("[API] 开始AI改写文案（使用人设配置）...")
        persona_dict = None
        if request.persona_config:
            persona_dict = request.persona_config.dict()
            logger.info(f"[API] 使用人设配置: {persona_dict.get('companyName', '')}")
        
        # 如果继续优化，在提示词中强调生成不同版本
        if request.optimize:
            logger.info("[API] 继续优化模式：生成新版本")
        
        rewritten_dict = rewrite_script(
            script_dict, 
            persona_config=persona_dict,
            optimize=request.optimize
        )
        
        logger.info("[API] 文案改写完成")
        
        # 计算相似度
        from ai_pipeline.text_similarity import calculate_similarity
        similarity_result = calculate_similarity(
            original_text,
            rewritten_dict.get('full_script', '')
        )
        logger.info(f"[API] 相似度分析: 去重率={similarity_result['deduplication_rate']}%")
        
        return {
            "success": True,
            "original_script": {
                "full_script": original_text,
                "hook": script_dict.get('hook', ''),
                "problem": script_dict.get('problem', ''),
                "solution": script_dict.get('solution', ''),
                "cta": script_dict.get('cta', '')
            },
            "rewritten_script": rewritten_dict,
            "similarity": similarity_result,
            "video_path": str(video_path),
            "audio_path": str(audio_path),
            "srt_path": str(srt_path)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_msg = f"链接解析和改写失败: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


class ComplianceCheckRequest(BaseModel):
    """合规检测请求"""
    script: str  # 需要检测的文案
    extra_rules: Optional[str] = None  # 客户自定义合规补充规则（可选）


@app.post("/api/compliance/check")
async def check_compliance(request: ComplianceCheckRequest):
    """
    合规检测接口
    
    检测文案中的：
    1. 个人私域相关词汇（微信、QQ、电话等）
    2. 三方平台相关词汇（淘宝、京东、抖音等）
    3. 行业限制词（金融、医疗、教育等）
    
    自动处理：在敏感词中间加"某"字或使用谐音字替换
    """
    try:
        from ai_pipeline.compliance_checker import check_compliance
        
        logger.info(f"[API] 开始合规检测，文案长度: {len(request.script)}")
        
        # 调用合规检测（带可选补充规则）
        result = await asyncio.to_thread(check_compliance, request.script, request.extra_rules)
        
        logger.info(f"[API] 合规检测完成，发现问题: {len(result.get('issues', []))}个")
        
        return {
            "success": True,
            "is_compliant": result.get('is_compliant', False),
            "original_script": result.get('original_script', ''),
            "processed_script": result.get('processed_script', ''),
            "issues": result.get('issues', []),
            "replacements": result.get('replacements', []),
            "message": "合规检测完成"
        }
        
    except Exception as e:
        import traceback
        error_msg = f"合规检测失败: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


@app.post("/api/auto_generate")
async def auto_generate(request: AutoGenerateRequest):
    """
    自动生成短视频
    
    流程：
    1. 搜索关键词相关爆款视频
    2. 下载视频素材
    3. 提取并改写文案
    4. 调用Pixelle生成口播视频
    5. 插入素材
    6. 生成字幕
    7. 原创处理
    8. 返回最终视频
    
    参数：
    - keyword: 行业关键词
    - avatar_path: 数字人形象路径（可选）
    - product_path: 产品图片路径（可选）
    """
    try:
        # 导入pipeline模块
        from ai_pipeline.pipeline import generate_video
        import logging
        
        # 配置日志
        logger = logging.getLogger(__name__)
        
        logger.info(f"[AutoGenerate] 收到请求: keyword={request.keyword}")
        
        # 获取API密钥（从全局状态或环境变量）
        api_key = None
        if "CURRENT_STATE" in globals():
            api_key = globals()["CURRENT_STATE"].get("api_key")
        if not api_key:
            api_key = os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY")
        
        # 调用生成流程
        result = generate_video(
            keyword=request.keyword,
            avatar_path=request.avatar_path,
            product_path=request.product_path,
            api_key=api_key
        )
        
        if result.get('success'):
            return {
                "success": True,
                "video_path": result.get('video_path'),
                "subtitle_path": result.get('subtitle_path'),
                "script": result.get('script'),
                "message": result.get('message', '视频生成成功')
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=result.get('message', '视频生成失败')
            )
            
    except ImportError as e:
        logger.error(f"[AutoGenerate] 导入模块失败: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"模块导入失败: {str(e)}"
        )
    except Exception as e:
        logger.error(f"[AutoGenerate] 生成视频时出错: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"生成失败: {str(e)}"
        )


# ============================================================================
# 发布API接口
# ============================================================================

class PublishRequest(BaseModel):
    """发布请求模型"""
    video_path: str
    platform: str = "douyin"  # 平台：douyin, kuaishou, xhs, sph
    title: str = ""
    description: str = ""
    cover_path: Optional[str] = None
    cover_text: Optional[str] = None  # 封面文字内容（4-8个字）
    # 发布期与调度相关（用于让截流/HF 在发布批次期间让路）
    hf_enabled: bool = False
    mining_enabled: bool = False
    publish_batch_id: Optional[str] = None
    # True：本线程结束时若子批次计数归零，不触发 HF/截流恢复（由自动化流水线在全部平台跑完后统一收尾）
    skip_global_publish_teardown: bool = False


class AutoGenerateFullRequest(BaseModel):
    """完整自动化流程请求"""
    link: str
    compliance_enabled: bool = False
    compliance_extra_rules: Optional[str] = None  # 合规检测补充规则（可选）
    hf_enabled: bool = False
    mining_enabled: bool = False
    platforms: List[str] = []
    persona_config: Optional[CopywritingPersonaConfig] = None  # 文案改写专用人设配置（可选）


@app.post("/api/auto_generate_full")
async def auto_generate_full(request: AutoGenerateFullRequest):
    """
    完整自动化流程：链接 → 文案 → 合规检测（可选）→ 视频生成 → 内容生成 → 发布
    
    参数：
    - link: 视频链接
    - compliance_enabled: 是否启用合规检测（默认False）
    - platforms: 发布平台列表，如 ['douyin', 'kuaishou']
    
    返回：
    - task_id: 任务ID（用于查询进度）
    """
    try:
        if not request.link.strip():
            raise HTTPException(status_code=400, detail="链接不能为空")
        
        if not request.platforms:
            raise HTTPException(status_code=400, detail="请至少选择一个发布平台")
        
        # 检查历史记录（优先使用CURRENT_STATE，如果没有则使用文件系统中最新的文件）
        avatar_path = CURRENT_STATE.get("avatar_path")
        audio_path = CURRENT_STATE.get("audio_path")
        
        # 如果CURRENT_STATE中没有，尝试从文件系统获取最新的文件
        if not avatar_path:
            avatar_dir = WRAPPER_BASE_DIR / "data" / "avatars"
            if avatar_dir.exists():
                avatar_files = list(avatar_dir.glob("avatar_*"))
                if avatar_files:
                    # 按修改时间排序，取最新的
                    avatar_path = str(max(avatar_files, key=lambda p: p.stat().st_mtime))
                    logger.info(f"[AutoGenerateFull] 从文件系统获取最新头像: {avatar_path}")
                    CURRENT_STATE["avatar_path"] = avatar_path
        
        if not audio_path:
            audio_dir = WRAPPER_BASE_DIR / "data" / "audios"
            if audio_dir.exists():
                audio_files = list(audio_dir.glob("audio_*"))
                if audio_files:
                    # 按修改时间排序，取最新的
                    audio_path = str(max(audio_files, key=lambda p: p.stat().st_mtime))
                    logger.info(f"[AutoGenerateFull] 从文件系统获取最新音频: {audio_path}")
                    CURRENT_STATE["audio_path"] = audio_path
        
        if not avatar_path or not Path(avatar_path).exists():
            raise HTTPException(status_code=400, detail="未找到历史头像，请先在素材生产中上传头像")
        if not audio_path or not Path(audio_path).exists():
            raise HTTPException(status_code=400, detail="未找到历史音频，请先在素材生产中上传音频")
        
        # 生成任务ID
        task_id = str(uuid.uuid4())
        TASKS[task_id] = {
            "status": "running",
            "progress": 0,
            "step": "初始化中...",
            "script": None,
            "video_path": None,
            "content": None,
            "publish_results": [],
            "cancel_requested": False,
        }
        
        # 在后台线程中执行完整流程
        def execute_full_pipeline():
            def _is_cancelled() -> bool:
                try:
                    return bool(TASKS.get(task_id, {}).get("cancel_requested"))
                except Exception:
                    return False

            try:
                if _is_cancelled():
                    TASKS[task_id]["status"] = "cancelled"
                    TASKS[task_id]["step"] = "已停止"
                    return

                logger.info(f"[AutoGenerateFull] 开始执行完整自动化流程，任务ID: {task_id}")
                
                # 步骤1: 解析链接并生成文案
                logger.info(f"[AutoGenerateFull] 步骤1: 解析链接并生成文案...")
                TASKS[task_id]["progress"] = 10
                TASKS[task_id]["step"] = "生成文案中..."
                
                # 调用链接解析API（传递人设配置）
                import requests
                parse_request_body = {'link': request.link}
                
                # 如果提供了人设配置，添加到请求中
                if request.persona_config:
                    persona_dict = request.persona_config.dict()
                    parse_request_body['persona_config'] = persona_dict
                    logger.info(f"[AutoGenerateFull] 使用人设配置进行文案二创: {persona_dict.get('companyName', '')}")
                
                parse_response = requests.post(
                    f'{SELF_BASE_URL}/api/copywriting/parse_link',
                    json=parse_request_body,
                    timeout=120
                )
                
                logger.info(f"[AutoGenerateFull] 链接解析API响应状态码: {parse_response.status_code}")
                
                if parse_response.status_code != 200:
                    error_text = parse_response.text
                    logger.error(f"[AutoGenerateFull] 链接解析失败: {error_text}")
                    raise Exception(f"链接解析失败: {error_text}")
                
                if _is_cancelled():
                    TASKS[task_id]["status"] = "cancelled"
                    TASKS[task_id]["step"] = "已停止"
                    return

                parse_data = parse_response.json()
                logger.info(f"[AutoGenerateFull] 链接解析API返回数据: {json.dumps(parse_data, ensure_ascii=False, indent=2)[:500]}...")
                
                # 检查返回数据结构
                rewritten_script_dict = parse_data.get('rewritten_script', {})
                if not rewritten_script_dict:
                    logger.error(f"[AutoGenerateFull] 返回数据中没有rewritten_script字段")
                    logger.error(f"[AutoGenerateFull] 完整返回数据: {json.dumps(parse_data, ensure_ascii=False, indent=2)}")
                    raise Exception("链接解析返回数据格式错误：缺少rewritten_script字段")
                
                script = rewritten_script_dict.get('full_script', '')
                
                if not script:
                    logger.error(f"[AutoGenerateFull] 文案生成失败：full_script为空")
                    logger.error(f"[AutoGenerateFull] rewritten_script内容: {json.dumps(rewritten_script_dict, ensure_ascii=False, indent=2)}")
                    raise Exception("文案生成失败：full_script为空")
                
                logger.info(f"[AutoGenerateFull] 文案生成成功，长度: {len(script)}")
                logger.info(f"[AutoGenerateFull] 文案内容预览: {script[:200]}...")
                CURRENT_STATE["text"] = script
                TASKS[task_id]["progress"] = 20
                TASKS[task_id]["step"] = "文案生成完成"
                TASKS[task_id]["script"] = script
                
                # 步骤2: 合规检测（可选）
                if request.compliance_enabled:
                    logger.info(f"[AutoGenerateFull] 步骤2: 执行合规检测...")
                    TASKS[task_id]["progress"] = 30
                    TASKS[task_id]["step"] = "合规检测中..."
                    
                    compliance_response = requests.post(
                        f'{SELF_BASE_URL}/api/compliance/check',
                        json={
                            'script': script,
                            'extra_rules': request.compliance_extra_rules,
                        },
                        timeout=60
                    )
                    
                    if compliance_response.status_code == 200:
                        compliance_data = compliance_response.json()
                        if compliance_data.get('processed_script'):
                            script = compliance_data['processed_script']
                            CURRENT_STATE["text"] = script
                            logger.info(f"[AutoGenerateFull] 合规检测完成，使用安全文案")
                    
                    TASKS[task_id]["progress"] = 40
                    TASKS[task_id]["step"] = "合规检测完成"

                if _is_cancelled():
                    TASKS[task_id]["status"] = "cancelled"
                    TASKS[task_id]["step"] = "已停止"
                    return
                
                # 步骤3: 生成视频（使用历史记录的头像和音频）
                logger.info(f"[AutoGenerateFull] 步骤3: 生成视频...")
                TASKS[task_id]["progress"] = 50
                TASKS[task_id]["step"] = "生成视频中..."
                
                # 先设置文案、头像和音频
                requests.post(f'{SELF_BASE_URL}/api/text', json={'text': script}, timeout=10)
                
                # 调用生成接口（带重试逻辑，处理TASK_QUEUE_MAXED错误）
                import time
                max_retries = 3
                retry_delay = 30  # 重试前等待30秒
                video_task_id = None
                video_path = None
                
                for retry in range(max_retries):
                    try:
                        if _is_cancelled():
                            TASKS[task_id]["status"] = "cancelled"
                            TASKS[task_id]["step"] = "已停止"
                            return

                        if retry > 0:
                            logger.info(f"[AutoGenerateFull] 重试视频生成 (第 {retry} 次)，等待 {retry_delay} 秒...")
                            TASKS[task_id]["step"] = f"等待队列空闲中... (重试 {retry}/{max_retries-1})"
                            time.sleep(retry_delay)
                        
                        generate_response = requests.post(
                            f'{SELF_BASE_URL}/api/generate',
                            json={},
                            timeout=300
                        )
                        
                        if generate_response.status_code != 200:
                            error_text = generate_response.text
                            # 检查是否是队列满的错误
                            if 'TASK_QUEUE_MAXED' in error_text and retry < max_retries - 1:
                                logger.warning(f"[AutoGenerateFull] RunningHub队列已满，将重试...")
                                continue
                            raise Exception(f"视频生成失败: {error_text}")
                        
                        generate_data = generate_response.json()
                        video_task_id = generate_data.get('task_id')
                        
                        if not video_task_id:
                            raise Exception("视频生成任务创建失败")
                        
                        # 等待视频生成完成（增加超时时间到1.5小时）
                        max_wait = 5400  # 最多等待90分钟（1.5小时，视频生成可能需要较长时间）
                        waited = 0
                        
                        while waited < max_wait:
                            time.sleep(5)  # 每5秒检查一次
                            waited += 5

                            if _is_cancelled():
                                # 尽可能取消底层视频任务（如果 Video-main 暴露 DELETE /api/task/{video_task_id}）
                                if video_task_id:
                                    try:
                                        requests.delete(
                                            f'{SELF_BASE_URL}/api/task/{video_task_id}',
                                            timeout=10
                                        )
                                    except Exception:
                                        pass
                                TASKS[task_id]["status"] = "cancelled"
                                TASKS[task_id]["step"] = "已停止"
                                return

                            # 重要：生成过程（尤其是 MoviePy 写文件）可能导致本机 API 短暂无响应。
                            # 这里若仅是 ReadTimeout/连接抖动，不应触发“重新 POST /api/generate”导致重复生成，
                            # 只需要继续轮询即可。
                            try:
                                task_status_response = requests.get(
                                    f'{SELF_BASE_URL}/api/task/{video_task_id}',
                                    timeout=10
                                )
                            except Exception as poll_err:
                                err_text = str(poll_err)
                                if "Read timed out" in err_text or "ConnectTimeout" in err_text or "ConnectionError" in err_text:
                                    logger.warning(f"[AutoGenerateFull] 轮询任务状态超时/连接抖动，继续等待: {err_text}")
                                    continue
                                raise

                            step_updated = False
                            prog_updated = False
                            if task_status_response.status_code == 200:
                                task_status = task_status_response.json()
                                # 将子任务的 step/progress 透传给外层任务（前端一般盯的是 auto_generate_full 的 task_id）
                                try:
                                    inner_step = (task_status.get("step") or "").strip()
                                    inner_progress = task_status.get("progress")
                                    if inner_step:
                                        TASKS[task_id]["step"] = inner_step
                                        step_updated = True
                                    if isinstance(inner_progress, int):
                                        TASKS[task_id]["progress"] = 50 + max(0, min(20, int(inner_progress * 0.2)))
                                        prog_updated = True
                                except Exception:
                                    pass
                                if task_status.get('status') == 'done':
                                    video_path = task_status.get('output')
                                    if video_path:
                                        logger.info(f"[AutoGenerateFull] 视频生成完成，耗时: {waited}秒")
                                        break
                                elif task_status.get('status') == 'error':
                                    error_msg = task_status.get('error', '未知错误')
                                    # 如果是队列满的错误且还有重试次数，继续外层重试
                                    if 'TASK_QUEUE_MAXED' in str(error_msg) and retry < max_retries - 1:
                                        logger.warning(f"[AutoGenerateFull] 视频生成任务失败（队列满），将重试...")
                                        video_task_id = None
                                        break
                                    raise Exception(f"视频生成失败: {error_msg}")

                            # 仅当未能从子任务同步到文案/进度时，再用兜底文案（避免每轮覆盖「画中画/字幕/BGM」等子步骤）
                            if not step_updated:
                                TASKS[task_id]["step"] = "生成视频中..."
                            if not prog_updated:
                                TASKS[task_id]["progress"] = 50 + int((waited / max_wait) * 20)
                        
                        if video_path:
                            break  # 成功生成，跳出重试循环
                        elif not video_task_id:
                            continue  # 需要重试
                        else:
                            # 超时但任务可能还在运行，检查一下任务状态
                            logger.warning(f"[AutoGenerateFull] 视频生成等待超时，检查任务状态...")
                            final_check = requests.get(f'{SELF_BASE_URL}/api/task/{video_task_id}', timeout=10)
                            if final_check.status_code == 200:
                                final_status = final_check.json()
                                if final_status.get('status') == 'done':
                                    video_path = final_status.get('output')
                                    if video_path:
                                        logger.info(f"[AutoGenerateFull] 视频生成完成（超时后检查）")
                                        break
                            raise Exception("视频生成超时（已等待1.5小时）")
                            
                    except Exception as e:
                        error_msg = str(e)
                        if 'TASK_QUEUE_MAXED' in error_msg and retry < max_retries - 1:
                            logger.warning(f"[AutoGenerateFull] 遇到队列满错误，将重试: {error_msg}")
                            continue
                        elif retry == max_retries - 1:
                            # 最后一次重试也失败
                            raise
                        else:
                            # 其他错误，也重试
                            logger.warning(f"[AutoGenerateFull] 视频生成出错，将重试: {error_msg}")
                            continue
                
                if _is_cancelled():
                    TASKS[task_id]["status"] = "cancelled"
                    TASKS[task_id]["step"] = "已停止"
                    return

                if not video_path:
                    raise Exception("视频生成失败：队列繁忙，已重试3次仍失败")
                
                logger.info(f"[AutoGenerateFull] 视频生成完成: {video_path}")
                TASKS[task_id]["progress"] = 70
                TASKS[task_id]["step"] = "视频生成完成"
                TASKS[task_id]["video_path"] = video_path
                
                # 环境演示（最多 3 段）；/api/generate 可能已做过画中画，避免重复叠
                if _collect_existing_showcase_files():
                    base_name = os.path.basename(str(video_path)).lower() if video_path else ""
                    if "_pip" in base_name:
                        logger.info(
                            f"[AutoGenerateFull] 检测到视频已包含画中画标记（{base_name}），跳过第二次画中画。"
                        )
                    else:
                        logger.info(f"[AutoGenerateFull] 检测到环境演示视频，开始添加画中画效果...")
                        TASKS[task_id]["step"] = "画中画匹配中..."
                        try:
                            vp0 = str(video_path)
                            vp1 = _apply_showcase_pip_chain(vp0)
                            if vp1 != vp0 and os.path.exists(vp1):
                                video_path = vp1
                                logger.info(f"[AutoGenerateFull] 画中画添加成功，视频路径: {video_path}")
                                TASKS[task_id]["video_path"] = video_path
                            else:
                                logger.warning(f"[AutoGenerateFull] 画中画未改写输出，使用原视频")
                        except Exception as e:
                            logger.warning(f"[AutoGenerateFull] 添加画中画时出错: {e}")
                            import traceback
                            traceback.print_exc()
                            logger.warning(f"[AutoGenerateFull] 继续使用原视频（无画中画）")
                
                # 步骤4: 生成成品素材内容（封面、标题、描述）
                # 注意：字幕和背景音乐已在 /api/generate 中添加，这里不再重复添加
                logger.info(f"[AutoGenerateFull] 步骤4: 生成成品素材内容...")
                TASKS[task_id]["progress"] = 80
                TASKS[task_id]["step"] = "生成发布素材中..."

                if _is_cancelled():
                    TASKS[task_id]["status"] = "cancelled"
                    TASKS[task_id]["step"] = "已停止"
                    return
                
                content_response = requests.post(
                    f'{SELF_BASE_URL}/api/generate_douyin_content',
                    json={'script_text': script},
                    timeout=300  # 生成抖音发布内容可能较慢，这里放宽到 5 分钟
                )
                
                if content_response.status_code == 200:
                    content = content_response.json()
                    cover_text = content.get('cover_text', '')
                    title = content.get('title', '')
                    description = content.get('description', '')
                else:
                    # 如果生成失败，使用默认值
                    cover_text = script[:8] if len(script) >= 8 else script
                    title = script[:15] if len(script) >= 15 else script
                    description = script[:20] if len(script) >= 20 else script
                    content = {
                        "cover_text": cover_text,
                        "title": title,
                        "description": description
                    }
                
                logger.info(f"[AutoGenerateFull] 内容生成完成: 封面={cover_text}, 标题={title}")
                TASKS[task_id]["progress"] = 85
                TASKS[task_id]["step"] = "内容生成完成"
                TASKS[task_id]["content"] = content
                
                # 步骤5: 发布到各个平台
                logger.info(f"[AutoGenerateFull] 步骤5: 发布到平台 {request.platforms}...")
                TASKS[task_id]["progress"] = 90
                TASKS[task_id]["step"] = "发布中..."

                if _is_cancelled():
                    TASKS[task_id]["status"] = "cancelled"
                    TASKS[task_id]["step"] = "已停止"
                    return

                publish_results = []
                publish_success_count = 0
                ordered_platforms = _ordered_publish_platforms(request.platforms)

                for platform in ordered_platforms:
                    try:
                        if _is_cancelled():
                            TASKS[task_id]["status"] = "cancelled"
                            TASKS[task_id]["step"] = "已停止"
                            return

                        logger.info(f"[AutoGenerateFull] 发布到 {platform}（串行，上一平台结束后再启动）...")
                        TASKS[task_id]["step"] = f"发布到{platform}中..."
                        # 每平台独立子批次 ID，便于等待该次后台线程真正结束，避免多线程同时抢锁
                        sub_batch_id = f"{task_id}:{platform}"
                        publish_response = requests.post(
                            f'{SELF_BASE_URL}/api/publish/douyin' if platform == 'douyin' else f'{SELF_BASE_URL}/api/publish/{platform}',
                            json={
                                'video_path': video_path,
                                'title': title,
                                'description': description,
                                'cover_text': cover_text,
                                'hf_enabled': bool(request.hf_enabled),
                                'mining_enabled': bool(request.mining_enabled),
                                'publish_batch_id': sub_batch_id,
                                'skip_global_publish_teardown': True,
                            },
                            timeout=120,
                        )

                        if publish_response.status_code != 200:
                            raise Exception(publish_response.text)

                        if not _wait_publish_subbatch_done(sub_batch_id, timeout=900.0):
                            raise Exception("发布等待超时（后台未在限定时间内结束）")

                        publish_success_count += 1
                        publish_results.append({
                            "platform": platform,
                            "success": True,
                            "result": publish_response.json(),
                        })
                        logger.info(f"[AutoGenerateFull] {platform} 发布流程已结束（子批次完成）")
                    except Exception as e:
                        logger.error(f"[AutoGenerateFull] {platform} 发布失败: {e}")
                        publish_results.append({
                            "platform": platform,
                            "success": False,
                            "error": str(e),
                        })

                # 多平台子批次均未在各线程内做全局收尾，此处统一恢复 HF / 截流
                _run_global_publish_teardown(
                    bool(request.hf_enabled),
                    bool(request.mining_enabled),
                )

                # 完成
                TASKS[task_id]["status"] = "done"
                TASKS[task_id]["progress"] = 100
                n_ordered = len(ordered_platforms)
                if publish_success_count > 0:
                    if publish_success_count >= n_ordered:
                        TASKS[task_id]["step"] = "发布完成（所选平台均已依次提交）"
                    else:
                        TASKS[task_id]["step"] = (
                            f"发布结束（成功 {publish_success_count}/{n_ordered} 个平台，详见 publish_results）"
                        )
                else:
                    TASKS[task_id]["step"] = "发布失败"
                TASKS[task_id]["publish_results"] = publish_results
                
                logger.info(f"[AutoGenerateFull] 完整自动化流程执行完成，任务ID: {task_id}")
                
            except Exception as e:
                # 如果用户已取消，则避免把 cancelled 误判成 error
                if _is_cancelled():
                    TASKS[task_id]["status"] = "cancelled"
                    TASKS[task_id]["step"] = "已停止"
                    return

                logger.error(f"[AutoGenerateFull] 执行失败: {e}")
                import traceback
                logger.error(traceback.format_exc())
                TASKS[task_id] = {
                    "status": "error",
                    "progress": TASKS.get(task_id, {}).get("progress", 0),
                    "error": str(e),
                    "step": "执行失败"
                }
        
        # 启动后台线程
        thread = threading.Thread(target=execute_full_pipeline, daemon=True)
        thread.start()
        
        logger.info(f"[AutoGenerateFull] 自动化任务已启动，任务ID: {task_id}")
        
        return {
            "success": True,
            "task_id": task_id,
            "message": "自动化流程已启动，正在后台执行..."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[AutoGenerateFull] 启动失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"启动失败: {str(e)}"
        )


@app.post("/api/generate_douyin_content")
async def generate_douyin_content_api(request: Dict[str, Any]):
    """
    根据文案生成抖音发布内容（封面内容、标题、描述）
    
    参数：
    - script_text: 原始文案文本
    
    返回：
    - cover_text: 封面内容（4-8个字）
    - title: 标题（15个字左右，包含3个话题#）
    - description: 描述（20字左右）
    """
    try:
        script_text = request.get('script_text', '')
        if not script_text:
            raise HTTPException(status_code=400, detail="script_text 参数不能为空")
        
        # 导入 generate_douyin_content 函数
        from ai_pipeline.script_rewriter import generate_douyin_content
        
        # 调用生成函数
        result = generate_douyin_content(script_text)
        
        logger.info(f"[GenerateDouyinContent] 生成成功: {result}")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[GenerateDouyinContent] 生成失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"生成失败: {str(e)}"
        )


@app.post("/api/publish/douyin")
async def publish_to_douyin_api(request: PublishRequest):
    """
    发布视频到抖音
    
    重要：使用统一的浏览器实例（douyin_publish_mcp）
    - 与登录功能使用相同的浏览器实例
    - 浏览器数据保存在项目内：browser_data/chrome_user_data/Profile 3
    - 登录信息会永久保存，下次打开自动登录
    
    参数：
    - video_path: 视频文件路径（相对于output目录或绝对路径）
    - title: 视频标题
    - description: 视频描述/介绍
    - cover_path: 封面图片路径（可选，如果不提供则使用视频第一帧）
    
    返回：
    - success: 是否发布成功
    - message: 提示信息
    """
    try:
        # 不再使用 ai_pipeline.publisher，改用 douyin_publish_mcp
        # from ai_pipeline.publisher import publish_to_douyin
        
        # 解析视频路径
        video_path = Path(request.video_path)
        if not video_path.is_absolute():
            # 相对路径，尝试从output目录查找
            output_dir = find_output_dir()
            video_path = output_dir / request.video_path
            # 如果还是找不到，尝试从任务目录查找
            if not video_path.exists():
                # 尝试查找所有任务目录
                for task_dir in output_dir.glob("*"):
                    if task_dir.is_dir():
                        potential_path = task_dir / request.video_path
                        if potential_path.exists():
                            video_path = potential_path
                            break
                        # 也尝试查找 final.mp4
                        final_video = task_dir / "final.mp4"
                        if final_video.exists():
                            video_path = final_video
                            break
        
        if not video_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"视频文件不存在: {video_path}"
            )
        
        logger.info(f"[Publish] 开始发布视频到抖音: {video_path}")
        logger.info(f"[Publish] 标题: {request.title}")
        logger.info(f"[Publish] 描述: {request.description}")
        logger.info(f"[Publish] 封面: {request.cover_path}")
        
        # 处理封面路径（如果没有提供，自动从视频提取）
        cover_path = None
        if request.cover_path:
            cover_path_obj = Path(request.cover_path)
            if not cover_path_obj.is_absolute():
                # 相对路径，尝试从output目录查找
                output_dir = find_output_dir()
                cover_path_obj = output_dir / request.cover_path
            if cover_path_obj.exists():
                cover_path = str(cover_path_obj)
            else:
                logger.warning(f"[Publish] 封面文件不存在: {cover_path_obj}，将从视频提取")
        
        # 使用 douyin_publish_mcp 的发布函数（确保使用统一的浏览器实例）
        # 注意：不再使用 ai_pipeline.publisher，直接使用 douyin_publish_mcp
        import sys
        from pathlib import Path as PathLib
        wrapper_dir = PathLib(__file__).parent
        if str(wrapper_dir) not in sys.path:
            sys.path.insert(0, str(wrapper_dir))
        import douyin_publish_mcp
        import threading
        
        # 发布批次调度信息
        batch_id = request.publish_batch_id or str(uuid.uuid4())
        hf_enabled = bool(request.hf_enabled)
        mining_enabled = bool(request.mining_enabled)
        skip_teardown = bool(request.skip_global_publish_teardown)

        # 标记进入发布期，并增加批次剩余计数
        _publish_active.set()
        with _publish_batch_lock:
            _publish_batch_remaining[batch_id] = _publish_batch_remaining.get(batch_id, 0) + 1
        
        # 在后台线程中执行发布（包括封面提取，避免阻塞API）
        def publish_in_thread():
            try:
                logger.info("[Publish] [后台线程] 开始执行发布流程...")

                # 发布期：如果需要截流，就尽快暂停截流子进程以释放浏览器自动化锁
                if mining_enabled:
                    try:
                        with _intercept_lock:
                            p = _intercept_proc
                        if p is not None and p.poll() is None:
                            logger.info("[Publish] [后台线程] 发布中：已暂停截流子进程，释放浏览器锁...")
                            with _intercept_lock:
                                _intercept_log.append("[系统] 已暂停截流（发布中）")
                            try:
                                p.terminate()
                            except Exception:
                                pass
                            try:
                                p.wait(timeout=15.0)
                            except Exception:
                                pass
                            with _intercept_lock:
                                if _intercept_proc is p:
                                    _intercept_proc = None
                    except Exception:
                        # 暂停截流失败不影响发布，最多导致锁等待变长
                        pass

                # 浏览器自动化资源互斥：发布期间独占 _browser_automation_lock
                _browser_automation_lock.acquire()
                
                try:
                    # 在后台线程中提取封面（如果需要）
                    final_cover_path = cover_path
                    if not final_cover_path:
                        logger.info("[Publish] [后台线程] 未提供封面，尝试从视频自动提取...")
                        try:
                            from ai_pipeline.cover_extractor import extract_cover_from_video
                            cover_path_obj = extract_cover_from_video(str(video_path), video_path.parent)
                            if cover_path_obj and cover_path_obj.exists():
                                final_cover_path = str(cover_path_obj)
                                logger.info(f"[Publish] [后台线程] 封面提取成功: {final_cover_path}")
                            else:
                                logger.warning("[Publish] [后台线程] 封面提取失败，将尝试不使用封面发布")
                        except (ImportError, ModuleNotFoundError) as e:
                            logger.warning(f"[Publish] [后台线程] 封面提取模块不可用: {e}，将不使用封面继续发布")
                            final_cover_path = None  # 明确设置为None
                        except Exception as e:
                            logger.warning(f"[Publish] [后台线程] 封面提取失败: {e}，将不使用封面继续发布")
                            final_cover_path = None  # 明确设置为None
                    
                    # 执行发布
                    result = douyin_publish_mcp._publish_video_impl(
                        video_path=str(video_path),
                        title=request.title,
                        description=request.description,
                        cover_path=final_cover_path,
                        cover_text=request.cover_text
                    )
                    logger.info(f"[Publish] [后台线程] 发布流程完成: {result}")
                    # 检查结果是否包含成功标识
                    if "成功" in str(result) or "success" in str(result).lower():
                        logger.info("[Publish] [后台线程] ✅ 发布成功")
                    else:
                        logger.error(f"[Publish] [后台线程] ❌ 发布失败: {result}")
                finally:
                    _browser_automation_lock.release()
            except Exception as e:
                logger.error(f"[Publish] [后台线程] ❌ 发布异常: {e}")
                import traceback
                logger.error(traceback.format_exc())
            finally:
                # 发布批次收尾：最后一个平台发布完成后再补一次 HF 回复并恢复截流
                remaining_now = 0
                try:
                    with _publish_batch_lock:
                        cur = _publish_batch_remaining.get(batch_id, 0)
                        cur = max(0, cur - 1)
                        if cur == 0:
                            _publish_batch_remaining.pop(batch_id, None)
                        else:
                            _publish_batch_remaining[batch_id] = cur
                        remaining_now = cur
                except Exception:
                    remaining_now = 1  # 避免误触发恢复

                if remaining_now == 0 and not skip_teardown:
                    _run_global_publish_teardown(hf_enabled, mining_enabled)
        
        # 启动后台线程，立即返回
        thread = threading.Thread(target=publish_in_thread, daemon=True)
        thread.start()
        
        logger.info("[Publish] 发布任务已在后台执行，API 立即返回")
        
        return {
            "success": True,
            "message": "发布任务已启动，浏览器将自动执行发布流程",
            "video_path": str(video_path),
            "platform": "douyin",
            "note": "发布流程在后台执行中，请观察浏览器..."
        }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Publish] 发布视频时出错: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"发布失败: {str(e)}"
        )


@app.post("/api/publish/xhs")
async def publish_to_xiaohongshu_api(request: PublishRequest):
    """
    发布视频到小红书创作者中心。

    - 与抖音使用相同的 video_path / title / description（PublishRequest）
    - 与抖音共用 douyin_publish_mcp 浏览器实例（Profile 3）
    - 通过 _browser_automation_lock 与抖音/其它发布串行，避免同时占用浏览器
    """
    try:
        video_path = Path(request.video_path)
        if not video_path.is_absolute():
            output_dir = find_output_dir()
            video_path = output_dir / request.video_path
            if not video_path.exists():
                for task_dir in output_dir.glob("*"):
                    if task_dir.is_dir():
                        potential_path = task_dir / request.video_path
                        if potential_path.exists():
                            video_path = potential_path
                            break
                        final_video = task_dir / "final.mp4"
                        if final_video.exists():
                            video_path = final_video
                            break

        if not video_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"视频文件不存在: {video_path}"
            )

        logger.info(f"[Publish-XHS] 开始发布小红书: {video_path}")
        logger.info(f"[Publish-XHS] 标题: {request.title}")
        logger.info(f"[Publish-XHS] 描述: {request.description}")

        import sys
        from pathlib import Path as PathLib
        wrapper_dir = PathLib(__file__).parent
        if str(wrapper_dir) not in sys.path:
            sys.path.insert(0, str(wrapper_dir))
        import xiaohongshu_publish_selenium as xhs_pub
        import threading

        batch_id = request.publish_batch_id or str(uuid.uuid4())
        hf_enabled = bool(request.hf_enabled)
        mining_enabled = bool(request.mining_enabled)
        skip_teardown = bool(request.skip_global_publish_teardown)

        _publish_active.set()
        with _publish_batch_lock:
            _publish_batch_remaining[batch_id] = _publish_batch_remaining.get(batch_id, 0) + 1

        def publish_xhs_in_thread():
            try:
                logger.info("[Publish-XHS] [后台线程] 开始执行小红书发布…")

                if mining_enabled:
                    try:
                        with _intercept_lock:
                            p = _intercept_proc
                        if p is not None and p.poll() is None:
                            logger.info("[Publish-XHS] [后台线程] 发布中：已暂停截流子进程…")
                            with _intercept_lock:
                                _intercept_log.append("[系统] 已暂停截流（发布中）")
                            try:
                                p.terminate()
                            except Exception:
                                pass
                            try:
                                p.wait(timeout=15.0)
                            except Exception:
                                pass
                            with _intercept_lock:
                                if _intercept_proc is p:
                                    _intercept_proc = None
                    except Exception:
                        pass

                _browser_automation_lock.acquire()
                try:
                    ok = xhs_pub.publish_xiaohongshu_video(
                        str(video_path),
                        request.title or "",
                        request.description or "",
                    )
                    logger.info(f"[Publish-XHS] [后台线程] publish_xiaohongshu_video 返回: {ok}")
                finally:
                    _browser_automation_lock.release()
            except Exception as e:
                logger.error(f"[Publish-XHS] [后台线程] 发布异常: {e}")
                import traceback
                logger.error(traceback.format_exc())
            finally:
                remaining_now = 0
                try:
                    with _publish_batch_lock:
                        cur = _publish_batch_remaining.get(batch_id, 0)
                        cur = max(0, cur - 1)
                        if cur == 0:
                            _publish_batch_remaining.pop(batch_id, None)
                        else:
                            _publish_batch_remaining[batch_id] = cur
                        remaining_now = cur
                except Exception:
                    remaining_now = 1

                if remaining_now == 0 and not skip_teardown:
                    _run_global_publish_teardown(hf_enabled, mining_enabled)

        thread = threading.Thread(target=publish_xhs_in_thread, daemon=True)
        thread.start()

        logger.info("[Publish-XHS] 发布任务已在后台执行，API 立即返回")

        return {
            "success": True,
            "message": "小红书发布任务已启动，浏览器将自动执行（与抖音共用同一浏览器配置）",
            "video_path": str(video_path),
            "platform": "xhs",
            "note": "发布流程在后台执行中，请观察浏览器…",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Publish-XHS] 出错: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"小红书发布失败: {str(e)}"
        )


@app.post("/api/publish/kuaishou")
async def publish_to_kuaishou_api(request: PublishRequest):
    """
    发布视频到快手创作者中心。

    与抖音 / 小红书共用 douyin_publish_mcp 浏览器；通过 _browser_automation_lock 串行。
    """
    try:
        video_path = Path(request.video_path)
        if not video_path.is_absolute():
            output_dir = find_output_dir()
            video_path = output_dir / request.video_path
            if not video_path.exists():
                for task_dir in output_dir.glob("*"):
                    if task_dir.is_dir():
                        potential_path = task_dir / request.video_path
                        if potential_path.exists():
                            video_path = potential_path
                            break
                        final_video = task_dir / "final.mp4"
                        if final_video.exists():
                            video_path = final_video
                            break

        if not video_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"视频文件不存在: {video_path}"
            )

        logger.info(f"[Publish-KS] 开始发布快手: {video_path}")
        logger.info(f"[Publish-KS] 标题: {request.title}")
        logger.info(f"[Publish-KS] 描述: {request.description}")

        import sys
        from pathlib import Path as PathLib
        wrapper_dir = PathLib(__file__).parent
        if str(wrapper_dir) not in sys.path:
            sys.path.insert(0, str(wrapper_dir))
        import kuaishou_publish_selenium as ks_pub
        import threading

        batch_id = request.publish_batch_id or str(uuid.uuid4())
        hf_enabled = bool(request.hf_enabled)
        mining_enabled = bool(request.mining_enabled)
        skip_teardown = bool(request.skip_global_publish_teardown)

        _publish_active.set()
        with _publish_batch_lock:
            _publish_batch_remaining[batch_id] = _publish_batch_remaining.get(batch_id, 0) + 1

        def publish_ks_in_thread():
            try:
                logger.info("[Publish-KS] [后台线程] 开始执行快手发布…")

                if mining_enabled:
                    try:
                        with _intercept_lock:
                            p = _intercept_proc
                        if p is not None and p.poll() is None:
                            logger.info("[Publish-KS] [后台线程] 发布中：已暂停截流子进程…")
                            with _intercept_lock:
                                _intercept_log.append("[系统] 已暂停截流（发布中）")
                            try:
                                p.terminate()
                            except Exception:
                                pass
                            try:
                                p.wait(timeout=15.0)
                            except Exception:
                                pass
                            with _intercept_lock:
                                if _intercept_proc is p:
                                    _intercept_proc = None
                    except Exception:
                        pass

                _browser_automation_lock.acquire()
                try:
                    ok = ks_pub.publish_kuaishou_video(
                        str(video_path),
                        request.title or "",
                        request.description or "",
                    )
                    logger.info(f"[Publish-KS] [后台线程] publish_kuaishou_video 返回: {ok}")
                finally:
                    _browser_automation_lock.release()
            except Exception as e:
                logger.error(f"[Publish-KS] [后台线程] 发布异常: {e}")
                import traceback
                logger.error(traceback.format_exc())
            finally:
                remaining_now = 0
                try:
                    with _publish_batch_lock:
                        cur = _publish_batch_remaining.get(batch_id, 0)
                        cur = max(0, cur - 1)
                        if cur == 0:
                            _publish_batch_remaining.pop(batch_id, None)
                        else:
                            _publish_batch_remaining[batch_id] = cur
                        remaining_now = cur
                except Exception:
                    remaining_now = 1

                if remaining_now == 0 and not skip_teardown:
                    _run_global_publish_teardown(hf_enabled, mining_enabled)

        thread = threading.Thread(target=publish_ks_in_thread, daemon=True)
        thread.start()

        logger.info("[Publish-KS] 发布任务已在后台执行，API 立即返回")

        return {
            "success": True,
            "message": "快手发布任务已启动，浏览器将自动执行（与抖音共用同一浏览器配置）",
            "video_path": str(video_path),
            "platform": "kuaishou",
            "note": "发布流程在后台执行中，请观察浏览器…",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Publish-KS] 出错: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"快手发布失败: {str(e)}"
        )


@app.post("/api/publish/sph")
async def publish_to_wechat_channels(request: PublishRequest):
    """
    发布视频到微信视频号（sph）
    
    - 使用与抖音相同的视频路径和文案
    - 标题需控制在16个字以内，这里会做一次安全截断
    - 依赖 publish/run.py 中已经验证过的微信视频号自动化脚本
    """
    try:
        from pathlib import Path as PathLib
        import sys as _sys

        # 解析视频路径（与抖音保持一致逻辑）
        video_path = Path(request.video_path)
        if not video_path.is_absolute():
            output_dir = find_output_dir()
            video_path = output_dir / request.video_path
            if not video_path.exists():
                for task_dir in output_dir.glob("*"):
                    if task_dir.is_dir():
                        potential_path = task_dir / request.video_path
                        if potential_path.exists():
                            video_path = potential_path
                            break
                        final_video = task_dir / "final.mp4"
                        if final_video.exists():
                            video_path = final_video
                            break

        if not video_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"视频文件不存在: {video_path}"
            )

        # 计算并截断短标题到16个字以内（并移除特殊符号，避免视频号不允许的字符）
        raw_title = (request.title or "").strip()
        # 只保留中英文、数字，去掉其它符号（视频号对符号较严格）
        sanitized_title = re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9]+", "", raw_title)
        if len(sanitized_title) > 16:
            short_title = sanitized_title[:16]
        else:
            short_title = sanitized_title

        logger.info(f"[Publish-SPH] 原始标题: {raw_title}")
        logger.info(f"[Publish-SPH] 已清洗后的短标题（<=16字，无特殊符号）: {short_title}")

        # 导入微信视频号脚本
        project_root = PathLib(__file__).parent.parent
        publish_dir = project_root / "publish"
        if str(publish_dir) not in _sys.path:
            _sys.path.insert(0, str(publish_dir))

        try:
            import run as wx_run  # type: ignore
        except Exception as e:
            logger.error(f"[Publish-SPH] 导入微信视频号脚本失败: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"导入微信视频号脚本失败: {e}"
            )

        # 先检测微信是否已运行，未运行时直接返回提示（前端弹窗）
        try:
            Navigator, Tools, Independent_window = wx_run._import_pyweixin()  # type: ignore[attr-defined]
            if not Tools.is_weixin_running():  # type: ignore[attr-defined]
                logger.warning("[Publish-SPH] 检测到微信未运行")
                raise HTTPException(
                    status_code=400,
                    detail="微信未运行，请先打开并登录PC版微信，再重试视频号发布"
                )
        except HTTPException:
            raise
        except Exception as e:
            # 检测失败不影响后续执行，只做日志记录
            logger.warning(f"[Publish-SPH] 微信运行状态检测失败，继续尝试执行脚本: {e}")

        import threading
        
        # 发布批次调度信息（与抖音发布保持一致）
        batch_id = request.publish_batch_id or str(uuid.uuid4())
        hf_enabled = bool(request.hf_enabled)
        mining_enabled = bool(request.mining_enabled)
        skip_teardown = bool(request.skip_global_publish_teardown)

        _publish_active.set()
        with _publish_batch_lock:
            _publish_batch_remaining[batch_id] = _publish_batch_remaining.get(batch_id, 0) + 1

        def publish_wechat_in_thread():
            try:
                logger.info("[Publish-SPH] [后台线程] 开始执行微信视频号发布脚本...")

                # 发布期：暂停截流子进程以释放浏览器自动化锁
                if mining_enabled:
                    try:
                        with _intercept_lock:
                            p = _intercept_proc
                        if p is not None and p.poll() is None:
                            logger.info("[Publish-SPH] [后台线程] 发布中：已暂停截流子进程...")
                            with _intercept_lock:
                                _intercept_log.append("[系统] 已暂停截流（发布中）")
                            try:
                                p.terminate()
                            except Exception:
                                pass
                            try:
                                p.wait(timeout=15.0)
                            except Exception:
                                pass
                            with _intercept_lock:
                                if _intercept_proc is p:
                                    _intercept_proc = None
                    except Exception:
                        pass

                # 浏览器自动化资源互斥：发布期间独占 _browser_automation_lock
                _browser_automation_lock.acquire()
                try:
                    # 直接调用脚本入口函数，传入视频路径和短标题
                    exit_code = wx_run.main(str(video_path), short_title)  # type: ignore[call-arg]
                    logger.info(f"[Publish-SPH] [后台线程] 微信视频号脚本退出码: {exit_code}")
                finally:
                    _browser_automation_lock.release()
            except Exception as e:
                logger.error(f"[Publish-SPH] [后台线程] 发布异常: {e}")
                import traceback
                logger.error(traceback.format_exc())
            finally:
                remaining_now = 0
                try:
                    with _publish_batch_lock:
                        cur = _publish_batch_remaining.get(batch_id, 0)
                        cur = max(0, cur - 1)
                        if cur == 0:
                            _publish_batch_remaining.pop(batch_id, None)
                        else:
                            _publish_batch_remaining[batch_id] = cur
                        remaining_now = cur
                except Exception:
                    remaining_now = 1

                if remaining_now == 0 and not skip_teardown:
                    _run_global_publish_teardown(hf_enabled, mining_enabled)

        thread = threading.Thread(target=publish_wechat_in_thread, daemon=True)
        thread.start()

        logger.info("[Publish-SPH] 发布任务已在后台执行，API 立即返回")

        return {
            "success": True,
            "message": "微信视频号发布任务已启动，请在微信客户端观察执行过程",
            "video_path": str(video_path),
            "platform": "sph",
            "title": short_title
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Publish-SPH] 发布视频号时出错: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"视频号发布失败: {str(e)}"
        )


# ============================================================================
# 主程序入口
# ============================================================================

# ----------------------------------------------------------------------------
# 口播素材：预览与清除（必须放在「前端静态挂载 /」之前，且尽量靠后，避免根路径
# StaticFiles 在部分环境下优先匹配 /api/* 导致 GET=404、POST=405）
# ----------------------------------------------------------------------------
class ClearMaterialRequest(BaseModel):
    kind: str
    showcase_slot: Optional[int] = None  # 0-2：仅 kind=showcase 时清除单槽；缺省则清空全部环境视频槽


@app.get("/api/material_preview")
async def material_preview(kind: str, slot: Optional[int] = Query(None)):
    """
    从 CURRENT_STATE 读取已上传素材并返回文件流（仅允许 data/ 下路径）。
    kind=showcase 且 slot=0|1|2 时预览对应槽位；不传 slot 时预览首个已上传环境视频（兼容旧前端）。
    """
    await asyncio.sleep(0)
    k0 = (kind or "").strip().lower()
    if k0 == "showcase" and slot is not None:
        if slot not in (0, 1, 2):
            raise HTTPException(status_code=400, detail="showcase 预览 slot 须为 0、1 或 2")
        _migrate_legacy_showcase_if_needed()
        spaths = _ensure_showcase_paths_list()
        path_str = spaths[slot]
        if not path_str:
            raise HTTPException(status_code=404, detail="该槽位未上传环境视频")
        try:
            p = Path(path_str).resolve()
        except Exception:
            raise HTTPException(status_code=404, detail="路径无效")
        if not _path_is_under_data_root(p) or not p.is_file():
            raise HTTPException(status_code=404, detail="文件不存在或不可访问")
        media_type, _ = mimetypes.guess_type(str(p))
        return FileResponse(
            path=str(p),
            filename=p.name,
            media_type=media_type or "application/octet-stream",
        )

    key = _MATERIAL_KIND_TO_STATE_KEY.get(k0)
    if not key:
        raise HTTPException(status_code=400, detail="无效的 kind")
    path_str = CURRENT_STATE.get(key)
    if not path_str:
        raise HTTPException(status_code=404, detail="当前未上传该类型素材")
    try:
        p = Path(path_str).resolve()
    except Exception:
        raise HTTPException(status_code=404, detail="路径无效")
    if not _path_is_under_data_root(p) or not p.is_file():
        raise HTTPException(status_code=404, detail="文件不存在或不可访问")
    media_type, _ = mimetypes.guess_type(str(p))
    return FileResponse(
        path=str(p),
        filename=p.name,
        media_type=media_type or "application/octet-stream",
    )


@app.post("/api/clear_material")
async def clear_material(req: ClearMaterialRequest):
    """
    清除 CURRENT_STATE 中的素材并物理删除对应磁盘文件（须在 data/ 下）。
    kind=showcase 且 showcase_slot 为 0-2 时只清该槽；否则 showcase 清空三槽。
    """
    await asyncio.sleep(0)
    k = (req.kind or "").strip().lower()
    if k == "showcase" and req.showcase_slot is not None:
        idx = req.showcase_slot
        if idx not in (0, 1, 2):
            raise HTTPException(status_code=400, detail="showcase_slot 须为 0、1 或 2")
        _migrate_legacy_showcase_if_needed()
        slots = _ensure_showcase_paths_list()
        path_str = slots[idx]
        _unlink_material_file(path_str)
        slots[idx] = None
        _sync_showcase_legacy_path()
        print(f"[Wrapper] 已清除环境视频槽位 {idx}")
        return {"success": True, "kind": k, "showcase_slot": idx}

    key = _MATERIAL_KIND_TO_STATE_KEY.get(k)
    if not key:
        raise HTTPException(status_code=400, detail="无效的 kind")
    if k == "showcase":
        _migrate_legacy_showcase_if_needed()
        slots = _ensure_showcase_paths_list()
        for i in range(3):
            _unlink_material_file(slots[i])
            slots[i] = None
        CURRENT_STATE["showcase_video_path"] = None
        print(f"[Wrapper] 已清除全部环境视频槽位")
        return {"success": True, "kind": k}

    path_str = CURRENT_STATE.get(key)
    _unlink_material_file(path_str)
    CURRENT_STATE[key] = None
    print(f"[Wrapper] 已清除素材 kind={k} state_key={key}")
    return {"success": True, "kind": k}


# ----------------------------------------------------------------------------
# 前端静态站点挂载（必须放在所有 /api 路由之后，避免拦截 API）
# ----------------------------------------------------------------------------
if FRONTEND_DIR.is_dir():
    try:
        # 直接把 web 目录挂到根路径：/ -> index.html，/assets -> 静态资源，其他路径回退 index.html（SPA）
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
        logger.info(f"[Frontend] 已挂载前端静态站点: {FRONTEND_DIR}")
    except Exception as e:
        logger.warning(f"[Frontend] 挂载前端静态站点失败: {e}")

if __name__ == "__main__":
    # 端口策略：
    # - 开发环境默认 38810
    # - 打包后由启动器通过环境变量 AXON_PORT 注入（例如 33710）
    try:
        # 客户交付版：没显式设置时也默认 33710，避免前后端端口不一致
        server_port = int(os.environ.get("AXON_PORT", "33710"))
    except Exception:
        server_port = 33710

    print("""
╔══════════════════════════════════════════════════════════════╗
║           Pixelle-Video FastAPI Wrapper Server               ║
╚══════════════════════════════════════════════════════════════╝

Starting server at http://127.0.0.1:{port}
API Docs: http://127.0.0.1:{port}/docs

Press Ctrl+C to stop the server
""".format(port=server_port))
    
    # 直接传递 app 对象，避免模块导入问题
    uvicorn.run(
        app,  # 直接传递 app 对象
        host="127.0.0.1",
        port=server_port,
        log_level="info"
    )

