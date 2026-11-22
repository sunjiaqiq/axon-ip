#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
发布打包脚本：将项目打成可交付目录（含 Video-main），供 ISS 或手动安装使用。

- 打包后生成一个 EXE 启动器，用户双击即可启动后端并打开浏览器网关。
- 所有 .py 会编译为 .pyc 并删除 .py，隐藏源码。

打包前必做（避免发给客户后 UI/截流/回复不一致）：
1) 项目根执行 `npm run build`，生成最新 `web/`（含：挖掘客户面板、人设扩展字段、启动账号门禁 StartupLoginGate）。
2) 若账号校验地址非默认，构建前设置环境变量 `VITE_ACCOUNT_API_BASE`（见 components/StartupLoginGate.tsx）。
3) 确认 `pixelle_wrapper/requirements_runtime.txt` 含 selenium、webdriver-manager、psutil、fastmcp、pyyaml 等（HF 私信 + 抖音截流子进程共用运行时）。
4) 后端已含：/api/intercept/*（挖掘客户）、HF 私信、截流与自动回复互斥（同 Chrome user-data 目录不并行）；交付包内会校验截流脚本与 prompts 是否存在。

源码保护说明：
- `pixelle_wrapper/`、`publish/` 在发布目录中会 compileall 并删除 .py，运行时以 .pyc 为主（见 bootstrap 调 main.pyc）。
- 前端运行以 `web/` 构建产物为主；随包的 `views/`、`components/`、`*.tsx` 若存在则为明文源码，如需对客户隐藏需另行混淆或从发布清单移除。
"""

import compileall
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

# 项目根目录（本脚本所在目录）
PROJECT_ROOT = Path(__file__).resolve().parent
# 发布输出根目录（可与 ISS 输出目录一致）
RELEASE_ROOT = PROJECT_ROOT / "dist" / "Axon_Program"

# ---------- 必须随包项（缺一不可） ----------
# 名称: (源路径相对项目根, 说明)
REQUIRED_ITEMS = [
    ("Video-main", "Video-main", "【必选】数字人生成核心，缺则后端连不上数字人"),
    ("pixelle_wrapper", "pixelle_wrapper", "后端服务与口播逻辑"),
    ("web", "web", "前端静态网站（打包后的 React UI）"),
    ("env", "env", "FFmpeg、ChromeDriver 150（Chrome 由客户自行安装）、requirements.txt"),
    ("whisper-main", "whisper-main", "Whisper 字幕"),
    ("yt-dlp-master", "yt-dlp-master", "视频下载"),
    ("douyin-mcp-server-main", "douyin-mcp-server-main", "抖音解析/文案提取"),
    ("TikTokDownloader-master", "downnn/TikTokDownloader-master", "【必选】抖音 Cookie API 兜底下载"),
    ("views", "views", "前端页面"),
    ("components", "components", "前端组件"),
    ("utils", "utils", "前端工具（如本地视频预览 URL）"),
    ("publish", "publish", "微信视频号发布独立包（pyweixin-main + run.py）"),
]

# 可选单文件（若存在则复制到发布根）
OPTIONAL_FILES = [
    "scripts/account_set_user.py",
    "config.yaml",
    "package.json",
    "vite.config.ts",
    "types.ts",
    "index.html",
    "index.tsx",
    "App.tsx",
]


def ensure_release_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


BUNDLE_CHROME_MILESTONE = os.environ.get("BUNDLE_CHROME_MILESTONE", "155").strip()
CFT_VERSIONS_URL = (
    "https://googlechromelabs.github.io/chrome-for-testing/"
    "latest-versions-per-milestone-with-downloads.json"
)


def _exe_version_text(exe: Path) -> str:
    if not exe.is_file():
        return ""
    try:
        r = subprocess.run(
            [str(exe), "--version"],
            capture_output=True,
            timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0,
        )
        parts: list[str] = []
        for blob in (r.stdout, r.stderr):
            if not blob:
                continue
            parts.append(blob.decode("utf-8", errors="replace"))
        return " ".join(parts).strip()
    except Exception:
        return ""


def _chromedriver_major(version_text: str) -> str:
    """只解析 `ChromeDriver 150.x` 的主版本，避免提交哈希里的数字造成误判。"""
    match = re.search(r"\bChromeDriver\s+(\d+)\.", version_text, flags=re.IGNORECASE)
    return match.group(1) if match else ""


def _download_zip(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"[Browser] 下载: {url}")
    urllib.request.urlretrieve(url, dest)


def _extract_zip_prefix(zip_path: Path, prefix: str, dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.namelist():
            if not member.startswith(prefix) or member.endswith("/"):
                continue
            rel = member[len(prefix) :]
            if not rel:
                continue
            target = dest_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)


def ensure_chromedriver_bundle(project_root: Path) -> bool:
    """确保 env/chromedriver 为 Chrome for Testing 里程碑（默认 150）。Chrome 浏览器由客户自行安装。"""
    driver_exe = project_root / "env" / "chromedriver" / "chromedriver.exe"
    milestone = BUNDLE_CHROME_MILESTONE
    driver_v = _exe_version_text(driver_exe)
    if driver_exe.is_file() and _chromedriver_major(driver_v) == milestone:
        print(f"[Browser] 已就绪 ChromeDriver 里程碑 {milestone}: {driver_v}")
        return True

    print(f"[Browser] 需要同步 ChromeDriver 里程碑 {milestone}（当前 driver={driver_v or '缺失'}）")
    try:
        with urllib.request.urlopen(CFT_VERSIONS_URL, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[致命] 无法获取 Chrome for Testing 版本清单: {e}", file=sys.stderr)
        if not driver_exe.is_file():
            return False
        print(f"[警告] 将继续使用现有 env/chromedriver（版本可能不是 {milestone}）", file=sys.stderr)
        return True

    milestone_data = (data.get("milestones") or {}).get(milestone)
    if not milestone_data:
        print(f"[致命] 版本清单中无里程碑 {milestone}", file=sys.stderr)
        return False

    version = milestone_data.get("version") or ""
    downloads = milestone_data.get("downloads") or {}
    driver_url = next(
        (d["url"] for d in downloads.get("chromedriver", []) if d.get("platform") == "win64"),
        "",
    )
    if not driver_url:
        print("[致命] 未找到 win64 的 chromedriver 下载地址", file=sys.stderr)
        return False

    tmp = Path(tempfile.mkdtemp(prefix="axon_cft_drv_"))
    try:
        driver_zip = tmp / "chromedriver-win64.zip"
        _download_zip(driver_url, driver_zip)

        driver_dir = project_root / "env" / "chromedriver"
        driver_dir.mkdir(parents=True, exist_ok=True)

        if driver_exe.is_file():
            bak = driver_dir / f"chromedriver.exe.bak_{time.strftime('%Y%m%d_%H%M%S')}"
            try:
                shutil.copy2(driver_exe, bak)
            except Exception:
                pass
        for old_bak in driver_dir.glob("chromedriver.exe.bak*"):
            try:
                old_bak.unlink()
            except Exception:
                pass

        _extract_zip_prefix(driver_zip, "chromedriver-win64/", driver_dir)

        driver_v2 = _exe_version_text(driver_exe)
        if _chromedriver_major(driver_v2) != milestone:
            print(
                f"[致命] 同步后 ChromeDriver 版本仍不对: {driver_v2}（期望含 {milestone}）",
                file=sys.stderr,
            )
            return False
        print(f"[OK] 已同步 ChromeDriver {version}: {driver_v2}")
        return True
    except Exception as e:
        print(f"[致命] 同步 ChromeDriver 失败: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def verify_browser_runtime(project_root: Path) -> list[str]:
    """校验内置 ChromeDriver 存在且为约定主版本（Chrome 由客户自行安装）。"""
    issues: list[str] = []
    driver_exe = project_root / "env" / "chromedriver" / "chromedriver.exe"
    if not driver_exe.is_file():
        issues.append(f"缺少内置 ChromeDriver: {driver_exe.relative_to(project_root)}")
        return issues
    milestone = BUNDLE_CHROME_MILESTONE
    driver_v = _exe_version_text(driver_exe)
    if _chromedriver_major(driver_v) != milestone:
        issues.append(f"内置 ChromeDriver 版本不含 {milestone}: {driver_v}")
    return issues


def _rmtree_onerror(func, path, exc_info):
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass


def robust_rmtree(path: Path) -> None:
    """Windows 下 WinError 145/拒绝访问时多次尝试删除整目录。"""
    if not path.exists():
        return
    for _ in range(10):
        try:
            shutil.rmtree(path, onerror=_rmtree_onerror)
            if not path.exists():
                return
        except OSError:
            pass
        time.sleep(0.4)
    if path.exists():
        shutil.rmtree(path, onerror=_rmtree_onerror)


def pick_runtime_python_src(release_root: Path) -> tuple[Path | None, str]:
    """
    内置 CPython 来源（须含 python.exe）。
    顺序：项目根 runtime_env -> Axon34 参考目录 -> 当前 dist 内已有（用于在参考目录不可用时保留上一版完整环境）。
    """
    candidates: list[tuple[Path, str]] = [
        (PROJECT_ROOT / "runtime_env" / "python", "项目根 runtime_env/python"),
        (Path("F:/Axon34/dist/Axon_Program/runtime_env/python"), "F:/Axon34/dist/Axon_Program/runtime_env/python"),
        (Path("F:\\Axon34\\dist\\Axon_Program\\runtime_env\\python"), "Axon34 runtime_env/python"),
    ]
    for p, tag in candidates:
        if p.is_dir() and (p / "python.exe").is_file():
            return p.resolve(), tag
    embedded = release_root / "runtime_env" / "python"
    if embedded.is_dir() and (embedded / "python.exe").is_file():
        return embedded.resolve(), "当前 dist/Axon_Program/runtime_env/python（沿用上一版）"
    return None, ""


def install_embedded_runtime(release_root: Path) -> bool:
    """清空发布目录内 runtime_env 后完整复制内置 Python。失败则必须中止打包（客户机无开发环境）。"""
    src, tag = pick_runtime_python_src(release_root)
    if not src:
        print("[致命] 未找到任何可用的内置 Python（目录内须有 python.exe）。", file=sys.stderr)
        print(f"       请将嵌入式 Python 放到: {PROJECT_ROOT / 'runtime_env' / 'python'}", file=sys.stderr)
        print("       或保留可用的 F:/Axon34/dist/Axon_Program/runtime_env/python。", file=sys.stderr)
        return False

    dst = release_root / "runtime_env" / "python"
    tmp_staging: Path | None = None
    real_src = src

    try:
        if src.resolve() == dst.resolve():
            tmp_staging = Path(tempfile.mkdtemp(prefix="axon_runtime_stage_"))
            staging_py = tmp_staging / "python"
            print(f"[Runtime] 源与目标相同，先暂存到 {staging_py} …")
            shutil.copytree(src, staging_py, dirs_exist_ok=True)
            real_src = staging_py

        print(f"[Runtime] 内置 Python 源 ({tag}): {real_src}")
        robust_rmtree(release_root / "runtime_env")
        ensure_release_dir(dst.parent)
        shutil.copytree(real_src, dst, dirs_exist_ok=False)
    except Exception as e:
        print(f"[致命] 复制内置 Python 失败: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return False
    finally:
        if tmp_staging is not None:
            shutil.rmtree(tmp_staging, ignore_errors=True)

    if not (dst / "python.exe").is_file():
        print(f"[致命] 复制后仍缺少: {dst / 'python.exe'}", file=sys.stderr)
        return False
    print(f"[OK] 已写入内置 Python: {dst}")
    return True


def copy_item(src: Path, dst: Path, name: str, description: str) -> bool:
    """复制目录或文件。若源不存在则根据是否必选报错或跳过。"""
    if not src.exists():
        return False
    try:
        if src.is_dir():
            if dst.exists():
                # 目录可能被系统/杀软/上一次打包占用，使用更稳健的删除策略避免 WinError 32
                robust_rmtree(dst)
            # 默认完整复制；对超大且与运行无关的目录做排除，避免安装包膨胀/夹带用户数据
            ignore = None
            if name == "Video-main":
                # Video-main 以源码方式被 runtime_env 的 Python import；其 .venv 不应随包发布（重复且超大）
                ignore = shutil.ignore_patterns(".venv", "__pycache__")
            elif name == "TikTokDownloader-master":
                ignore = shutil.ignore_patterns("__pycache__", ".git", ".github", "docs", "locale")
            elif name == "env":
                # Chrome 浏览器由客户自行安装；安装包只带 ChromeDriver
                ignore = shutil.ignore_patterns(
                    "chrome",
                    "__pycache__",
                    "chromedriver.exe.bak_*",
                    "chromedriver.exe.bak*",
                )
            elif name == "pixelle_wrapper":
                # 用户数据/调试产物/历史输出都不应随包带给客户机（运行时自动创建 output、browser_data、data 等）
                # 须保留：test_intercept_selenium.py、prompts/、hf_auto_reply.py、douyin_publish_mcp*、ai_pipeline/ 等业务文件
                ignore = shutil.ignore_patterns(
                    "browser_data",
                    "output",
                    "data",
                    "debug_artifacts",
                    "debug_artifacts_intercept",
                    "debug_artifacts_intercept_selenium",
                    "debug_artifacts_selenium",
                    "debug_artifacts_pw",
                    "logs",
                    "temp_subtitle*",
                    "ffmpeg",
                    # PyInstaller/调试构建残留（会导致安装包变大且可能在客户机触发“源文件损坏/拦截”）
                    "dist",
                    "build",
                    "__pycache__",
                )
            try:
                shutil.copytree(src, dst, dirs_exist_ok=False, ignore=ignore)
            except FileExistsError:
                # Windows 下若目录仍被占用导致删除不彻底，会出现 WinError 183 / FileExistsError。
                # 兜底：允许覆盖复制，保证打包可继续（避免因一处目录锁直接失败）。
                shutil.copytree(src, dst, dirs_exist_ok=True, ignore=ignore)
        else:
            ensure_release_dir(dst.parent)
            shutil.copy2(src, dst)
        return True
    except Exception as e:
        print(f"  [错误] 复制失败 {name}: {e}", file=sys.stderr)
        return False


def compile_py_to_pyc(release_root: Path) -> None:
    """将发布目录下的 Python 源码编译为 .pyc 并删除 .py，隐藏源码。
    优先用 runtime_env 里的 Python 编译，保证 .pyc 与运行时版本一致。"""
    runtime_py = release_root / "runtime_env" / "python" / "python.exe"
    if not runtime_py.is_file():
        runtime_py = release_root / "runtime_env" / "python" / "python"
    python_exe = str(runtime_py) if runtime_py.is_file() else sys.executable
    if python_exe != sys.executable:
        print(f"[编译] 使用运行时 Python: {python_exe}")
    dirs_to_compile = ["pixelle_wrapper", "publish"]
    for dir_name in dirs_to_compile:
        d = release_root / dir_name
        if not d.is_dir():
            continue
        print(f"[编译] {dir_name} ...")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(release_root)
        # pixelle_wrapper 需要“无源码可运行”，用 legacy(-b) 生成 module.pyc（非 __pycache__），便于 sourceless 启动
        # publish/（视频号 sph）同理：后端需要 `import run`，若只生成 __pycache__ 下的时间戳 pyc 并删除 .py，
        # 某些环境下会导致 import 失败，因此也对 publish 用 legacy(-b) 生成 run.pyc 等。
        compile_args = [python_exe, "-m", "compileall", "-q", str(d)]
        if dir_name in ("pixelle_wrapper", "publish"):
            compile_args = [python_exe, "-m", "compileall", "-b", "-q", str(d)]
        r = subprocess.run(
            compile_args,
            cwd=str(release_root),
            env=env,
            timeout=120,
        )
        if r.returncode != 0:
            print(f"  [警告] compileall 返回 %s，改用当前 Python 编译" % r.returncode, file=sys.stderr)
            compileall.compile_dir(str(d), quiet=1)
        removed = 0
        for py_file in d.rglob("*.py"):
            try:
                py_file.unlink()
                removed += 1
            except Exception as e:
                print(f"  [警告] 删除失败 {py_file}: {e}", file=sys.stderr)
        print(f"[OK] {dir_name}: 已编译为 .pyc 并移除 .py（legacy(-b) 可能生成非 __pycache__ 的 pyc）")


def build_launcher_exe(project_root: Path, release_root: Path) -> bool:
    """用 PyInstaller 打包 launcher.py 为单文件 EXE，并复制到发布目录。"""
    launcher_py = project_root / "launcher.py"
    if not launcher_py.is_file():
        print("[警告] 未找到 launcher.py，跳过 EXE 生成。", file=sys.stderr)
        return False
    icon_ico = project_root / "assets" / "ip_auto.ico"
    try:
        r = subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--version"],
            capture_output=True,
            text=True,
            cwd=str(project_root),
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        r = None
    if r is None or r.returncode != 0:
        print("[警告] 未安装 PyInstaller，无法生成启动器 EXE。请执行: pip install pyinstaller", file=sys.stderr)
        return False
    exe_name = "Axon_Launcher"
    out_dir = project_root / "dist"
    work_dir = project_root / "build"
    spec_dir = project_root
    args = [
        str(launcher_py),
        "--onefile",
        "--console",  # 保留控制台，便于从命令行运行看到报错；不需要黑框可改为 --noconsole
        "--name", exe_name,
        "--distpath", str(out_dir),
        "--workpath", str(work_dir),
        "--specpath", str(spec_dir),
        "--clean",
    ]
    if icon_ico.is_file():
        args += ["--icon", str(icon_ico)]
    print("[EXE] 正在用 PyInstaller 打包启动器 ...")
    r = subprocess.run([sys.executable, "-m", "PyInstaller"] + args, cwd=str(project_root))
    if r.returncode != 0:
        print("[警告] PyInstaller 执行失败。", file=sys.stderr)
        return False
    built_exe = out_dir / (exe_name + ".exe")
    if built_exe.is_file():
        dest = release_root / (exe_name + ".exe")
        shutil.copy2(built_exe, dest)
        print(f"[OK] 启动器已生成: {dest}")
        return True
    print("[警告] PyInstaller 未产出 EXE 文件。", file=sys.stderr)
    return False


def build_pixelle_wrapper_exe(project_root: Path, release_root: Path) -> bool:
    """
    生成 pixelle_wrapper/PixelleWrapper.exe 并放入发布目录。
    目标：交付包里 EXE 图标统一为 IP auto。
    """
    wrapper_main = project_root / "pixelle_wrapper" / "main.py"
    if not wrapper_main.is_file():
        print("[警告] 未找到 pixelle_wrapper/main.py，跳过 PixelleWrapper.exe 生成。", file=sys.stderr)
        return False
    icon_ico = project_root / "assets" / "ip_auto.ico"
    if not icon_ico.is_file():
        print("[警告] 未找到 assets/ip_auto.ico，PixelleWrapper.exe 将不带自定义图标。", file=sys.stderr)

    try:
        r = subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--version"],
            capture_output=True,
            text=True,
            cwd=str(project_root),
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        r = None
    if r is None or r.returncode != 0:
        print("[警告] 未安装 PyInstaller，无法生成 PixelleWrapper.exe。", file=sys.stderr)
        return False

    exe_name = "PixelleWrapper"
    out_dir = project_root / "dist"
    work_dir = project_root / "build"
    args = [
        str(wrapper_main),
        "--onefile",
        "--noconsole",
        "--name", exe_name,
        "--distpath", str(out_dir),
        "--workpath", str(work_dir),
        "--specpath", str(project_root),
        "--clean",
    ]
    if icon_ico.is_file():
        args += ["--icon", str(icon_ico)]
    print("[EXE] 正在用 PyInstaller 打包 PixelleWrapper ...")
    r = subprocess.run([sys.executable, "-m", "PyInstaller"] + args, cwd=str(project_root))
    if r.returncode != 0:
        print("[警告] PixelleWrapper PyInstaller 执行失败。", file=sys.stderr)
        return False
    built_exe = out_dir / (exe_name + ".exe")
    if not built_exe.is_file():
        print("[警告] 未产出 PixelleWrapper.exe。", file=sys.stderr)
        return False
    dest = release_root / "pixelle_wrapper" / (exe_name + ".exe")
    ensure_release_dir(dest.parent)
    shutil.copy2(built_exe, dest)
    print(f"[OK] PixelleWrapper.exe 已生成: {dest}")
    return True


def ensure_runtime_deps(release_root: Path) -> bool:
    """确保 runtime_env 的 Python 具备后端运行所需依赖（FastAPI/Uvicorn 等）。失败返回 False 并中止打包。"""
    python_exe = release_root / "runtime_env" / "python" / "python.exe"
    if not python_exe.is_file():
        python_exe = release_root / "runtime_env" / "python" / "python"
    if not python_exe.is_file():
        print("[致命] 未找到 runtime_env/python/python.exe，无法安装依赖。", file=sys.stderr)
        return False

    req = release_root / "pixelle_wrapper" / "requirements_runtime.txt"
    if not req.is_file():
        print("[致命] 未找到 pixelle_wrapper/requirements_runtime.txt。", file=sys.stderr)
        return False

    print(f"[RuntimeDeps] 安装后端运行依赖到 runtime_env ...")
    try:
        subprocess.run([str(python_exe), "-m", "ensurepip", "--upgrade"], cwd=str(release_root), timeout=180)
    except Exception:
        pass

    r = subprocess.run(
        [str(python_exe), "-m", "pip", "install", "-r", str(req), "--upgrade", "--ignore-installed", "--no-warn-script-location"],
        cwd=str(release_root),
        # 完整运行环境依赖较多；客户发布机网络较慢时，Selenium 等单包下载
        # 可能接近 20 分钟。放宽到 60 分钟，仍保留明确的失败上限。
        timeout=3600,
    )
    if r.returncode != 0:
        print("[致命] runtime_env pip install 失败，客户机将无法启动后端。请关闭占用该目录的进程后重试。", file=sys.stderr)
        return False
    print("[OK] runtime_env 后端依赖已安装。")

    # 二次强校验：客户机最常见“能启动但功能缺失”来源就是依赖没装全（尤其 jieba）。
    # 这里直接在 runtime_env 里 import，一旦失败立刻中止打包，避免交付半成品。
    try:
        r2 = subprocess.run(
            [
                str(python_exe),
                "-c",
                "import fastapi, uvicorn, pydantic, yaml, requests, httpx, loguru, selenium, psutil, fastmcp, jieba, gmssl, rich, cryptography; print('runtime_deps_ok')",
            ],
            cwd=str(release_root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if r2.returncode != 0 or "runtime_deps_ok" not in (r2.stdout or ""):
            print("[致命] runtime_env 依赖自检失败（import 失败），请先修复再打包：", file=sys.stderr)
            out = (r2.stderr or r2.stdout or "").strip()
            if out:
                print(out[:2000], file=sys.stderr)
            return False
        print("[OK] runtime_env 依赖自检通过（含 jieba）。")
    except Exception as e:
        print(f"[致命] runtime_env 依赖自检异常：{e}", file=sys.stderr)
        return False

    try:
        print("[RuntimeDeps] 清理 torch/openai-whisper（避免客户机误导性依赖）...")
        subprocess.run(
            [str(python_exe), "-m", "pip", "uninstall", "-y", "openai-whisper", "torch", "torchvision", "torchaudio"],
            cwd=str(release_root),
            timeout=600,
        )
    except Exception as e:
        print(f"[提示] 清理 torch/openai-whisper 跳过/失败: {e}", file=sys.stderr)

    try:
        print("[RuntimeDeps] 修复/重装 pywin32 ...")
        subprocess.run(
            [str(python_exe), "-m", "pip", "install", "--upgrade", "--force-reinstall", "pywin32"],
            cwd=str(release_root),
            timeout=600,
        )
        subprocess.run([str(python_exe), "-c", "import pywin32_postinstall; pywin32_postinstall.main()"], cwd=str(release_root), timeout=180)
        print("[OK] pywin32 修复步骤已执行。")
    except Exception as e:
        print(f"[提示] pywin32 修复步骤跳过/失败: {e}", file=sys.stderr)

    # RunningHub：新 API Key 对旧 /task/openapi/upload 会 401，打包后给 comfykit 打上传补丁
    try:
        _patch_runninghub_upload_in_runtime(release_root)
    except Exception as e:
        print(f"[提示] RunningHub 上传补丁跳过/失败: {e}", file=sys.stderr)

    return True


def _patch_runninghub_upload_in_runtime(release_root: Path) -> None:
    """把 comfykit RunningHubClient.upload_file 换成 v2 优先，避免新 Key 上传 401。"""
    client_py = (
        release_root
        / "runtime_env"
        / "python"
        / "Lib"
        / "site-packages"
        / "comfykit"
        / "comfyui"
        / "runninghub_client.py"
    )
    if not client_py.is_file():
        print("[提示] 未找到 comfykit runninghub_client.py，跳过 RH 上传补丁", file=sys.stderr)
        return
    text = client_py.read_text(encoding="utf-8")
    if "openapi/v2/media/upload/binary" in text:
        print("[OK] RunningHub 上传补丁已存在（跳过）")
        return
    src_patch = PROJECT_ROOT / "pixelle_wrapper" / "runninghub_upload_patch.py"
    # 直接用仓库里已维护的 patched 副本覆盖（若本机 dist 已有则优先）
    patched_ref = (
        PROJECT_ROOT
        / "dist"
        / "Axon_Program"
        / "runtime_env"
        / "python"
        / "Lib"
        / "site-packages"
        / "comfykit"
        / "comfyui"
        / "runninghub_client.py"
    )
    # 若当前就是正在写入的同一文件，用内嵌替换逻辑
    needle = 'result = await self._make_request("POST", "/task/openapi/upload", data=data, files=files)'
    if needle not in text:
        print("[提示] runninghub_client.py 结构变化，无法自动打补丁", file=sys.stderr)
        return
    # Prefer copying from Video-main/.venv if it already has v2 marker after local fix
    venv_ref = (
        PROJECT_ROOT
        / "Video-main"
        / ".venv"
        / "Lib"
        / "site-packages"
        / "comfykit"
        / "comfyui"
        / "runninghub_client.py"
    )
    for ref in (venv_ref, patched_ref):
        if ref.is_file() and ref.resolve() != client_py.resolve():
            ref_text = ref.read_text(encoding="utf-8")
            if "openapi/v2/media/upload/binary" in ref_text:
                client_py.write_text(ref_text, encoding="utf-8")
                print(f"[OK] 已写入 RunningHub 上传补丁: {client_py}")
                return
    print("[提示] 无可用的 RH 上传补丁源文件，依赖 pixelle_wrapper 运行时 monkeypatch", file=sys.stderr)
    _ = src_patch  # keep referenced for future packagers


def _download(url: str, dest: Path, timeout: int = 300) -> None:
    ensure_release_dir(dest.parent)
    if dest.exists() and dest.stat().st_size > 0:
        return
    print(f"[Download] {url} -> {dest}")
    with urllib.request.urlopen(url, timeout=timeout) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)


def ensure_whispercpp(release_root: Path) -> None:
    """
    确保 whisper.cpp (whisper-cli.exe) + base 模型已随包存在。
    目标结构：
      tools/whispercpp/whisper-cli.exe
      tools/whispercpp/models/ggml-base.bin
    """
    tools_dir = release_root / "tools" / "whispercpp"
    # 目标：Release\whisper-cli.exe（与 dll 同目录）+ 根目录放一个可直跑的 whisper-cli.exe（保证 doctor/脚本不踩坑）
    exe_release = tools_dir / "Release" / "whisper-cli.exe"
    exe_root = tools_dir / "whisper-cli.exe"
    model = tools_dir / "models" / "ggml-base.bin"
    already_present = exe_release.exists() and model.exists()
    if already_present:
        print("[OK] whisper.cpp 已存在，跳过下载（继续做根治修复：exe/dll 放置）。")

    ensure_release_dir(tools_dir)
    if not already_present:
        # Windows x64 二进制（镜像，速度更稳定；必要时可替换为 GitHub release 直链）
        zip_url = "https://sourceforge.net/projects/whisper-cpp.mirror/files/v1.7.6/whisper-bin-x64.zip/download"
        zip_path = tools_dir / "whisper-bin-x64.zip"
        try:
            _download(zip_url, zip_path, timeout=600)
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(tools_dir)
        except Exception as e:
            print(f"[警告] whisper.cpp 二进制下载/解压失败: {e}", file=sys.stderr)

    # 兼容 zip 内部结构：确保 Release\whisper-cli.exe 存在
    if not exe_release.exists():
        for p in tools_dir.rglob("whisper-cli.exe"):
            if p.name.lower() == "whisper-cli.exe" and p.parent.name.lower() == "release":
                ensure_release_dir(exe_release.parent)
                shutil.copy2(p, exe_release)
                break
        if not exe_release.exists():
            for p in tools_dir.rglob("whisper-cli.exe"):
                ensure_release_dir(exe_release.parent)
                shutil.copy2(p, exe_release)
                break

    # 根治：把 Release 里的 DLL 复制到 tools_dir 根目录（即使已经存在也要补齐）
    try:
        release_dir = tools_dir / "Release"
        if release_dir.exists():
            copied = 0
            for dll in release_dir.glob("*.dll"):
                dst = tools_dir / dll.name
                if not dst.exists() or dst.stat().st_size != dll.stat().st_size:
                    shutil.copy2(dll, dst)
                    copied += 1
            if copied:
                print(f"[OK] whisper.cpp DLL 已复制到根目录: {copied} 个")
    except Exception as e:
        print(f"[提示] 复制 whisper.cpp DLL 到根目录失败（不阻断）：{e}", file=sys.stderr)

    # 根治：根目录放一个 whisper-cli.exe（doctor/兼容旧路径）
    if exe_release.exists():
        try:
            shutil.copy2(exe_release, exe_root)
        except Exception:
            pass
        print(f"[OK] whisper-cli.exe 准备完成: {exe_release} (+ root copy)")
    else:
        print("[警告] 未找到 Release\\whisper-cli.exe（请检查下载包结构）。", file=sys.stderr)

    # base 模型（ggml）
    model_urls = [
        # 国内常见可用 HuggingFace 镜像
        "https://hf-mirror.com/ggerganov/whisper.cpp/resolve/main/ggml-base.bin",
        # 备用：原站（部分环境可能被阻断）
        "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin",
    ]
    downloaded = False
    for model_url in model_urls:
        try:
            _download(model_url, model, timeout=1200)
            # 粗校验：base 模型应为百 MB 级；若明显过小，通常是 HTML 错页/跳转页
            if model.exists() and model.stat().st_size > 50 * 1024 * 1024:
                print(f"[OK] whisper.cpp 模型已下载: {model} ({model.stat().st_size} bytes)")
                downloaded = True
                break
            if model.exists():
                try:
                    model.unlink()
                except Exception:
                    pass
                print(f"[警告] 下载到的模型文件异常（疑似 HTML/错误页），已删除并尝试下一个来源: {model_url}", file=sys.stderr)
        except Exception as e:
            print(f"[提示] whisper.cpp 模型来源不可用: {model_url} ({e})", file=sys.stderr)
    if not downloaded:
        print("[警告] whisper.cpp 模型下载失败（客户机字幕时间戳将不可用）。", file=sys.stderr)


def patch_tiktok_downloader_for_py311(release_root: Path) -> None:
    """TikTokDownloader 部分源码使用 3.12 多行 f-string，runtime 为 3.11 时需补丁。"""
    fixes = [
        (
            release_root / "TikTokDownloader-master" / "src" / "custom" / "internal.py",
            (
                'PROJECT_NAME = f"DouK-Downloader V{VERSION_MAJOR}.{VERSION_MINOR} {\n'
                "    'Beta' if VERSION_BETA else 'Stable'\n"
                '}"',
                'PROJECT_NAME = f"DouK-Downloader V{VERSION_MAJOR}.{VERSION_MINOR} {\'Beta\' if VERSION_BETA else \'Stable\'}"',
            ),
        ),
    ]
    for path, (old, new) in fixes:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if old in text:
            path.write_text(text.replace(old, new), encoding="utf-8")
            print(f"[OK] TikTokDownloader Py3.11 补丁: {path.relative_to(release_root)}")


def sanitize_release_tree(release_root: Path) -> list[str]:
    """复制后二次清理：去掉不应交付的调试/用户数据/驱动备份。"""
    removed: list[str] = []
    pw = release_root / "pixelle_wrapper"
    for name in (
        "browser_data",
        "output",
        "data",
        "logs",
        "ffmpeg",
        "debug_artifacts",
        "debug_artifacts_intercept",
        "debug_artifacts_intercept_selenium",
        "debug_artifacts_selenium",
        "debug_artifacts_pw",
    ):
        p = pw / name
        if p.exists():
            robust_rmtree(p)
            removed.append(str(p.relative_to(release_root)))

    chrome_dir = release_root / "env" / "chrome"
    if chrome_dir.exists():
        robust_rmtree(chrome_dir)
        removed.append(str(chrome_dir.relative_to(release_root)))

    drv_dir = release_root / "env" / "chromedriver"
    if drv_dir.is_dir():
        for bak in drv_dir.glob("chromedriver.exe.bak*"):
            try:
                bak.unlink()
                removed.append(str(bak.relative_to(release_root)))
            except Exception:
                pass

    if removed:
        print(f"[OK] 已清理不应随包的目录/文件 {len(removed)} 项")
        for item in removed[:12]:
            print(f"     - {item}")
        if len(removed) > 12:
            print(f"     ... 另有 {len(removed) - 12} 项")
    return removed


def write_pack_manifest(release_root: Path) -> None:
    """写入打包体积清单，便于对比是否漏项/混入垃圾。"""
    lines = ["IP auto 打包体积清单（sanitize 后）", "=" * 48]
    total = 0
    for name in (
        "Video-main",
        "pixelle_wrapper",
        "runtime_env",
        "env",
        "TikTokDownloader-master",
        "douyin-mcp-server-main",
        "whisper-main",
        "yt-dlp-master",
        "tools",
        "web",
        "publish",
    ):
        p = release_root / name
        if not p.exists():
            lines.append(f"{name:28} MISSING")
            continue
        size = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
        total += size
        lines.append(f"{name:28} {size / (1024 * 1024):8.1f} MB")
    lines.append("-" * 48)
    lines.append(f"{'合计（主要目录）':28} {total / (1024 * 1024):8.1f} MB")
    lines.append("")
    lines.append("说明：")
    lines.append(f"- env 不含 chrome/（Chrome 由客户安装），含 chromedriver {BUNDLE_CHROME_MILESTONE} + ffmpeg")
    lines.append("- pixelle_wrapper 不含 browser_data/data/debug_artifacts* 等运行时目录")
    lines.append("- TikTokDownloader-master 为 Cookie 链接下载兜底")
    (release_root / "PACK_MANIFEST.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[OK] 已写入 PACK_MANIFEST.txt")


def verify_release_sanity(release_root: Path) -> list[str]:
    """打包后禁止出现的垃圾/缺项检查。"""
    issues: list[str] = []
    forbidden = [
        release_root / "pixelle_wrapper" / "debug_artifacts_intercept",
        release_root / "pixelle_wrapper" / "debug_artifacts_selenium",
        release_root / "env" / "chrome",
    ]
    for p in forbidden:
        if p.exists():
            issues.append(f"不应随包存在: {p.relative_to(release_root)}")
    drv = release_root / "env" / "chromedriver" / "chromedriver.exe"
    if not drv.is_file():
        issues.append("缺少 env/chromedriver/chromedriver.exe")
    elif _chromedriver_major(_exe_version_text(drv)) != BUNDLE_CHROME_MILESTONE:
        issues.append(f"ChromeDriver 非 {BUNDLE_CHROME_MILESTONE}: {_exe_version_text(drv)}")
    tiktok = release_root / "TikTokDownloader-master" / "src" / "interface" / "detail.py"
    if not tiktok.is_file():
        issues.append("缺少 TikTokDownloader Detail API")
    api_pyc = release_root / "pixelle_wrapper" / "ai_pipeline" / "douyin_api_downloader.pyc"
    api_py = release_root / "pixelle_wrapper" / "ai_pipeline" / "douyin_api_downloader.py"
    if not api_pyc.is_file() and not api_py.is_file():
        issues.append("缺少 pixelle_wrapper/ai_pipeline/douyin_api_downloader")
    return issues


def verify_delivery_artifacts(release_root: Path) -> list[str]:
    """打包后、编译前校验客户机必备路径，避免漏拷截流/私信/门禁前端。"""
    missing: list[str] = []
    checks: list[tuple[Path, str]] = [
        (release_root / "pixelle_wrapper" / "test_intercept_selenium.py", "抖音截流子进程脚本"),
        (release_root / "pixelle_wrapper" / "hf_auto_reply.py", "HF 自动回复"),
        (release_root / "pixelle_wrapper" / "douyin_publish_mcp.py", "抖音浏览器单例 MCP"),
        (release_root / "pixelle_wrapper" / "prompts" / "私信回复_豆包prompt.txt", "豆包私信提示词"),
        (release_root / "pixelle_wrapper" / "prompts" / "素材评论一句话_豆包prompt.txt", "豆包评论提示词"),
        (release_root / "pixelle_wrapper" / "prompts" / "意向客户判定_豆包prompt.txt", "豆包二次意向判定"),
        (release_root / "douyin-mcp-server-main" / "douyin-video" / "scripts" / "douyin_downloader.py", "抖音 MCP 下载脚本"),
        (release_root / "TikTokDownloader-master" / "src" / "interface" / "detail.py", "TikTokDownloader Detail API"),
        (release_root / "web" / "index.html", "前端构建入口"),
        (release_root / "env" / "chromedriver" / "chromedriver.exe", f"内置 ChromeDriver {BUNDLE_CHROME_MILESTONE}（Chrome 由客户安装）"),
        (release_root / "components" / "StartupLoginGate.tsx", "启动账号门禁组件源码（随包；运行时用 web 构建产物）"),
    ]
    for path, label in checks:
        if not path.exists():
            missing.append(f"{label}: {path.relative_to(release_root)}")
    return missing


def write_customer_deliver_notes(release_root: Path) -> None:
    """安装目录根下简短说明，方便客户开箱；ISS 随包复制（ASCII 文件名避免工具链编码问题）。"""
    path = release_root / "DELIVER_NOTES.txt"
    text = f"""================================================================================
  IP auto / 数字人系统 — 交付说明（请随安装目录保留）
================================================================================

【系统要求】
  须为 64 位 Windows（可运行 x64 程序）。32 位系统无法运行本包内的 Axon_Launcher.exe 与内置 Python；
  若安装包已限制架构，在 32 位系统上会无法完成安装（属预期）。

【启动】
  双击 Axon_Launcher.exe（或开始菜单「IP auto」）。后端默认端口 33710。

【账号门禁】
  首次进入需账号密码；校验走外网接口。若贵司自有账号服务器，请在「重新打包前端」时设置环境变量：
  VITE_ACCOUNT_API_BASE=https://你的域名
  再执行 npm run build，然后重新执行发布打包脚本。

【抖音 / 快手 / 小红书 / 视频号】
  ·「设置」与「分发中心」均可打开共用 Chrome 登录页：抖音、快手、小红书、视频号（网页端）分平台切换后点登录。
  ·「分发中心」发布与「自动化」成片发布共用同一套 video_path、标题、描述（成品素材）；快手仅有「作品描述」输入框，无单独标题栏。
  · 自动化多选平台时按 抖音→快手→小红书→视频号 依次发布（串行，不并行抢浏览器）。

【抖音 / 浏览器登录】
  须先在本机安装 Google Chrome（建议主版本 {BUNDLE_CHROME_MILESTONE}，与安装包内 ChromeDriver 一致）。
  在系统内「设置」完成浏览器登录；与 Chrome 用户数据目录有关，勿多开同一 Profile 的手动 Chrome。

【文案创作 → 配置人设】
  微信号、行业搜索词轮换、意向词补充、评论风格示例等在此填写；会参与截流与私信豆包文案。
  仓库内 config.yaml 的 wechat_id 建议保持空，真实信息只放在本机人设里。

【自动化】
  · 挖掘客户：开关启动抖音截流（子进程）；面板统计与日志与 data 下 jsonl 一致。
  · 自动回复：HF 私信；可与「挖掘客户」同时勾选开关，但二者在软件内互斥排队，不会同时占用浏览器配置目录。
  · 截流默认开启「豆包二次意向判定」（关键词命中后再 AI 确认）。

【自检与运行库】
  · 安装目录下 doctor.bat：一键检查 Python、FFmpeg、whisper 等。
  · 时间轴字幕依赖 whisper-cli 与 VC++ 2015-2022 x64；安装包会尝试静默安装运行库。

【环境变量】
  安装程序会设置用户级 PIXELLE_VIDEO_ROOT 指向「安装目录\\Video-main」。

================================================================================
"""
    path.write_text(text, encoding="utf-8")
    print(f"[OK] 已写入 {path.name}（中文说明，根目录可查）")


def write_doctor(release_root: Path) -> None:
    """生成一键自检脚本：把“缺啥/哪里坏”在客户机一次性打出来。"""
    doctor = release_root / "doctor.bat"
    tools = release_root / "tools" / "whispercpp"
    with open(doctor, "w", encoding="utf-8") as f:
        f.write("@echo off\n")
        f.write("chcp 65001 >nul\n")
        f.write("setlocal enabledelayedexpansion\n")
        f.write("title AI Creator OS Doctor\n")
        f.write("set \"ROOT=%~dp0\"\n")
        f.write("set \"LOG=%ROOT%doctor.log\"\n")
        f.write("echo ===== AI Creator OS Doctor =====\n")
        f.write("echo Root: %ROOT%\n")
        f.write("echo Log : %LOG%\n")
        f.write("echo. \n")
        f.write("echo ===== AI Creator OS Doctor ===== > \"%LOG%\"\n")
        f.write("echo Root: %ROOT% >> \"%LOG%\"\n")
        f.write("echo Start: %DATE% %TIME% >> \"%LOG%\"\n")
        f.write("echo. >> \"%LOG%\"\n")
        f.write("echo.\n")
        f.write("echo [1/5] Python runtime\n")
        f.write("echo [1/5] Python runtime >> \"%LOG%\"\n")
        f.write("if exist \"%~dp0runtime_env\\python\\python.exe\" (\n")
        f.write("  \"%~dp0runtime_env\\python\\python.exe\" -V 1>>\"%LOG%\" 2>>&1\n")
        f.write("  echo python_ok\n")
        f.write(") else (\n")
        f.write("  echo MISSING: runtime_env\\python\\python.exe\n")
        f.write("  echo MISSING: runtime_env\\python\\python.exe >> \"%LOG%\"\n")
        f.write(")\n")
        f.write("echo.\n")
        f.write("echo [2/5] FFmpeg\n")
        f.write("echo [2/5] FFmpeg >> \"%LOG%\"\n")
        f.write("if exist \"%~dp0env\\ffmpeg\\ffmpeg.exe\" (\n")
        f.write("  \"%~dp0env\\ffmpeg\\ffmpeg.exe\" -version 1>>\"%LOG%\" 2>>&1\n")
        f.write("  echo ffmpeg_ok\n")
        f.write(") else (\n")
        f.write("  where ffmpeg 1>>\"%LOG%\" 2>>&1\n")
        f.write(")\n")
        f.write("echo.\n")
        f.write("echo [3/5] moviepy/imageio/numpy/PIL import\n")
        f.write("echo [3/5] imports >> \"%LOG%\"\n")
        f.write("if exist \"%~dp0runtime_env\\python\\python.exe\" (\n")
        f.write("  \"%~dp0runtime_env\\python\\python.exe\" -c \"import numpy,imageio,imageio_ffmpeg,moviepy,PIL; print('imports_ok')\" 1>>\"%LOG%\" 2>>&1\n")
        f.write("  echo imports_ran (see doctor.log)\n")
        f.write(")\n")
        f.write("echo.\n")
        f.write("echo [4/5] whisper.cpp\n")
        f.write("echo [4/5] whisper.cpp >> \"%LOG%\"\n")
        f.write(f"if exist \"%~dp0{tools.relative_to(release_root)}\\Release\\whisper-cli.exe\" (\n")
        f.write(f"  echo whisper-cli: \"%~dp0{tools.relative_to(release_root)}\\Release\\whisper-cli.exe\" >> \"%LOG%\"\n")
        f.write(f"  call \"%~dp0{tools.relative_to(release_root)}\\Release\\whisper-cli.exe\" -h 1>>\"%LOG%\" 2>>&1\n")
        f.write("  echo whisper_cli_exitcode=!errorlevel! >> \"%LOG%\"\n")
        f.write("  echo whisper_cli_exitcode=!errorlevel!\n")
        f.write(") else (\n")
        f.write("  echo MISSING: tools\\whispercpp\\Release\\whisper-cli.exe\n")
        f.write("  echo MISSING: tools\\whispercpp\\Release\\whisper-cli.exe >> \"%LOG%\"\n")
        f.write(")\n")
        f.write(f"if exist \"%~dp0{tools.relative_to(release_root)}\\models\\ggml-base.bin\" (\n")
        f.write("  echo Model OK: ggml-base.bin\n")
        f.write("  echo Model OK: ggml-base.bin >> \"%LOG%\"\n")
        f.write(") else (\n")
        f.write("  echo MISSING: tools\\whispercpp\\models\\ggml-base.bin\n")
        f.write("  echo MISSING: tools\\whispercpp\\models\\ggml-base.bin >> \"%LOG%\"\n")
        f.write(")\n")
        f.write("echo.\n")
        f.write("echo [5/5] Done.\n")
        f.write("echo [5/5] Done. >> \"%LOG%\"\n")
        f.write("echo End  : %DATE% %TIME% >> \"%LOG%\"\n")
        f.write("pause\n")
    print("[OK] 已生成 doctor.bat")


def main() -> int:
    print("=" * 60)
    print("发布打包脚本（含 Video-main 校验）")
    print("=" * 60)
    print(f"项目根: {PROJECT_ROOT}")
    print(f"输出目录: {RELEASE_ROOT}")
    print()

    # 1. 强制校验 Video-main：缺则直接退出
    video_main_src = PROJECT_ROOT / "Video-main"
    if not video_main_src.is_dir():
        print("[致命] 未找到 Video-main 目录。", file=sys.stderr)
        print("       数字人后端依赖此项目，缺则口播生成无法连接。", file=sys.stderr)
        print(f"       请将 Pixelle-Video 项目放在: {video_main_src}", file=sys.stderr)
        return 1
    print("[必选] Video-main 已存在，继续打包。")

    if not ensure_chromedriver_bundle(PROJECT_ROOT):
        return 1
    browser_issues = verify_browser_runtime(PROJECT_ROOT)
    if browser_issues:
        print("[致命] ChromeDriver 校验失败：", file=sys.stderr)
        for item in browser_issues:
            print(f"       - {item}", file=sys.stderr)
        return 1

    ensure_release_dir(RELEASE_ROOT)

    failed = []
    for name, rel_path, desc in REQUIRED_ITEMS:
        src = PROJECT_ROOT / rel_path
        dst = RELEASE_ROOT / name
        if not src.exists():
            if "必选" in desc or name == "Video-main":
                print(f"[失败] {name}: 缺失（{desc}）")
                failed.append(name)
            else:
                print(f"[跳过] {name}: 不存在")
            continue
        ok = copy_item(src, dst, name, desc)
        if ok:
            print(f"[OK] {name}: {desc}")
            if name == "env":
                bundled_chrome = dst / "chrome"
                if bundled_chrome.exists():
                    robust_rmtree(bundled_chrome)
                    print("[OK] 已排除 env/chrome（Chrome 由客户自行安装）")
        else:
            failed.append(name)

    patch_tiktok_downloader_for_py311(RELEASE_ROOT)
    sanitize_release_tree(RELEASE_ROOT)

    # 内置 Python：整目录删除后完整复制，避免 WinError 145 导致半成品；失败则中止打包
    if not install_embedded_runtime(RELEASE_ROOT):
        return 1

    if not ensure_runtime_deps(RELEASE_ROOT):
        return 1

    # 确保 whisper.cpp 与模型随包存在（字幕时间戳）
    ensure_whispercpp(RELEASE_ROOT)

    for f in OPTIONAL_FILES:
        src = PROJECT_ROOT / f
        if src.is_file():
            dst = RELEASE_ROOT / f
            try:
                ensure_release_dir(dst.parent)
                shutil.copy2(src, dst)
                print(f"[OK] {f} (可选)")
            except Exception as e:
                print(f"[跳过] {f}: {e}")

            # 兼容：pixelle_video.config 默认在 Video-main 目录找 config.yaml
            # 我们发布包根目录已经有一份，但客户机最容易出现“Video-main 找不到 config.yaml”的情况，
            # 这里再额外复制一份到 Video-main/config.yaml，确保“系统设置里配好的 key”能被读取到。
            if f == "config.yaml":
                try:
                    vm_cfg = RELEASE_ROOT / "Video-main" / "config.yaml"
                    ensure_release_dir(vm_cfg.parent)
                    shutil.copy2(src, vm_cfg)
                    print("[OK] 已同步 config.yaml 到 Video-main/config.yaml（避免找不到配置）")
                except Exception as e:
                    print(f"[跳过] 同步到 Video-main/config.yaml 失败: {e}")

    # 确保 pixelle_wrapper 内有 config.json 且含 pixelle_video_path
    config_json = RELEASE_ROOT / "pixelle_wrapper" / "config.json"
    if config_json.exists():
        try:
            import json
            with open(config_json, "r", encoding="utf-8") as fp:
                cfg = json.load(fp)
            if cfg.get("pixelle_video_path") != "Video-main":
                cfg["pixelle_video_path"] = "Video-main"
                with open(config_json, "w", encoding="utf-8") as fp:
                    json.dump(cfg, fp, ensure_ascii=False, indent=2)
                print("[OK] 已确认 pixelle_wrapper/config.json 中 pixelle_video_path = Video-main")
        except Exception as e:
            print(f"[提示] config.json 未修改: {e}")
    else:
        ensure_release_dir(config_json.parent)
        with open(config_json, "w", encoding="utf-8") as f:
            f.write('{\n  "pixelle_video_path": "Video-main"\n}\n')
        print("[OK] 已创建 pixelle_wrapper/config.json (pixelle_video_path=Video-main)")

    miss = verify_delivery_artifacts(RELEASE_ROOT)
    if miss:
        print("[致命] 交付物校验失败（以下缺失将导致客户机截流/回复/前端异常）：", file=sys.stderr)
        for m in miss:
            print(f"       - {m}", file=sys.stderr)
        print("       请确认已 npm run build 且 pixelle_wrapper 源码完整。", file=sys.stderr)
        return 1

    write_customer_deliver_notes(RELEASE_ROOT)

    # 写入 bootstrap.py：启动器调用。必须做到“无源码也能跑”，所以直接执行 main.pyc
    bootstrap_py = RELEASE_ROOT / "bootstrap.py"
    with open(bootstrap_py, "w", encoding="utf-8") as f:
        f.write('#!/usr/bin/env python3\n')
        f.write('# 由启动器调用，显式把安装目录加入 sys.path（runtime_env 的 Python 不读 PYTHONPATH）\n')
        f.write('# 重要：不要依赖 pixelle_wrapper/main.py 源码，直接运行 main.pyc\n')
        f.write('import sys\n')
        f.write('import os\n')
        f.write('from pathlib import Path\n')
        f.write('_d = Path(__file__).resolve().parent\n')
        f.write('os.environ.setdefault("AXON_INSTALL_DIR", str(_d))\n')
        f.write('if str(_d) not in sys.path:\n')
        f.write('    sys.path.insert(0, str(_d))\n')
        f.write('import runpy\n')
        f.write('_entry = _d / "pixelle_wrapper" / "main.pyc"\n')
        f.write('if _entry.is_file():\n')
        f.write('    runpy.run_path(str(_entry), run_name="__main__")\n')
        f.write('else:\n')
        f.write('    raise FileNotFoundError(f"missing entry bytecode: {_entry}")\n')
    print("[OK] 已写入 bootstrap.py")

    # 生成自检脚本（放在发布根，客户机双击即可）
    write_doctor(RELEASE_ROOT)

    # 将所有 .py 编译为 .pyc 并删除 .py，隐藏源码
    # 客户侧打包前：清空截流统计用的 demo jsonl，避免出现“累计私信/累计评论固定为演示数据”的情况
    try:
        demo_files = [
            RELEASE_ROOT / "pixelle_wrapper" / "data" / "dm_sent.jsonl",
            RELEASE_ROOT / "pixelle_wrapper" / "data" / "intercept_comments.jsonl",
        ]
        for df in demo_files:
            if df.exists():
                df.write_text("", encoding="utf-8")
                print(f"[OK] 已清空截流 demo 统计文件: {df.relative_to(RELEASE_ROOT)}")
    except Exception as e:
        print(f"[提示] 清空截流 demo 统计失败（不阻断）: {e}", file=sys.stderr)

    compile_py_to_pyc(RELEASE_ROOT)

    sanity = verify_release_sanity(RELEASE_ROOT)
    if sanity:
        print("[致命] 发布包自检失败：", file=sys.stderr)
        for item in sanity:
            print(f"       - {item}", file=sys.stderr)
        return 1

    write_pack_manifest(RELEASE_ROOT)

    intercept_pyc = RELEASE_ROOT / "pixelle_wrapper" / "test_intercept_selenium.pyc"
    if not intercept_pyc.is_file():
        print(
            "[致命] 编译后缺失 pixelle_wrapper/test_intercept_selenium.pyc（截流子进程无法启动）",
            file=sys.stderr,
        )
        return 1

    # 生成启动器 EXE（用户双击即启动后端并打开浏览器）
    build_launcher_exe(PROJECT_ROOT, RELEASE_ROOT)

    # PixelleWrapper.exe 为调试入口（可选）。
    # 注意：在某些开发环境中，PyInstaller 可能会因深度依赖（diffusers/torch 等）导致打包极慢或失败。
    # 为保证交付稳定，这里不强制重建 PixelleWrapper.exe；若需要，可单独在可控环境中构建后再复制入包。

    print()
    if failed:
        print("以下项打包失败或缺失:", failed, file=sys.stderr)
        return 1
    print("打包完成。发布目录含 Video-main、.pyc 字节码及 Axon_Launcher.exe，可直接用于 ISS 或交付。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
