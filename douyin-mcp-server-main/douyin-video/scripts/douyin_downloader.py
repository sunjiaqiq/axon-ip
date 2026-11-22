#!/usr/bin/env python3
"""
抖音无水印视频下载和文案提取工具

功能:
1. 从抖音分享链接获取无水印视频下载链接
2. 下载视频并提取音频
3. 使用硅基流动 API 从音频中提取文本
4. 自动保存文案到文件 (一个视频一个文件夹)

环境变量:
- API_KEY: 硅基流动 API 密钥 (用于文案提取功能)

使用示例:
  # 获取下载链接 (无需 API 密钥)
  python douyin_downloader.py --link "抖音分享链接" --action info

  # 下载视频
  python douyin_downloader.py --link "抖音分享链接" --action download --output ./videos

  # 提取文案并保存到文件 (需要 API_KEY 环境变量)
  python douyin_downloader.py --link "抖音分享链接" --action extract --output ./output
"""

import os
import re
import sys
import json
import argparse
import tempfile
import shutil
from pathlib import Path
from typing import Optional
from datetime import datetime


def check_dependencies():
    """检查必要的依赖是否已安装"""
    missing = []
    try:
        import requests
    except ImportError:
        missing.append("requests")
    try:
        import ffmpeg
    except ImportError:
        missing.append("ffmpeg-python")

    if missing:
        print(f"缺少依赖: {', '.join(missing)}")
        print(f"请运行: pip install {' '.join(missing)}")
        sys.exit(1)


check_dependencies()

import requests
import ffmpeg

# 请求头，模拟移动端访问
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) EdgiOS/121.0.2277.107 Version/17.0 Mobile/15E148 Safari/604.1'
}

# 硅基流动 API 配置（默认）
# 也可以使用其他兼容的语音识别 API
DEFAULT_API_BASE_URL = "https://api.siliconflow.cn/v1/audio/transcriptions"
DEFAULT_MODEL = "FunAudioLLM/SenseVoiceSmall"

# 如果设置了自定义 API URL，使用自定义的
CUSTOM_API_BASE_URL = os.getenv('CUSTOM_API_BASE_URL', '')
CUSTOM_API_KEY = os.getenv('CUSTOM_API_KEY', '')


class DouyinProcessor:
    """抖音视频处理器"""

    def __init__(self, api_key: str = "", api_base_url: Optional[str] = None, model: Optional[str] = None):
        # 优先使用环境变量中的配置
        if CUSTOM_API_KEY and CUSTOM_API_BASE_URL:
            self.api_key = CUSTOM_API_KEY
            self.api_base_url = CUSTOM_API_BASE_URL
            self.model = model or DEFAULT_MODEL
        else:
            self.api_key = api_key or os.getenv('API_KEY', '')
            self.api_base_url = api_base_url or DEFAULT_API_BASE_URL
            self.model = model or DEFAULT_MODEL
        self.temp_dir = Path(tempfile.mkdtemp())

    def __del__(self):
        """清理临时目录"""
        if hasattr(self, 'temp_dir') and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def parse_share_url(self, share_text: str) -> dict:
        """从分享文本中提取无水印视频链接"""
        # 提取分享链接
        urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', share_text)
        if not urls:
            raise ValueError("未找到有效的分享链接")

        share_url = urls[0]
        share_response = requests.get(share_url, headers=HEADERS)
        video_id = share_response.url.split("?")[0].strip("/").split("/")[-1]
        share_url = f'https://www.iesdouyin.com/share/video/{video_id}'

        # 获取视频页面内容
        response = requests.get(share_url, headers=HEADERS)
        response.raise_for_status()

        pattern = re.compile(
            pattern=r"window\._ROUTER_DATA\s*=\s*(.*?)</script>",
            flags=re.DOTALL,
        )
        find_res = pattern.search(response.text)

        if not find_res or not find_res.group(1):
            raise ValueError("从HTML中解析视频信息失败")

        # 解析JSON数据
        json_data = json.loads(find_res.group(1).strip())
        VIDEO_ID_PAGE_KEY = "video_(id)/page"
        NOTE_ID_PAGE_KEY = "note_(id)/page"

        if VIDEO_ID_PAGE_KEY in json_data["loaderData"]:
            original_video_info = json_data["loaderData"][VIDEO_ID_PAGE_KEY]["videoInfoRes"]
        elif NOTE_ID_PAGE_KEY in json_data["loaderData"]:
            original_video_info = json_data["loaderData"][NOTE_ID_PAGE_KEY]["videoInfoRes"]
        else:
            raise Exception("无法从JSON中解析视频或图集信息")

        data = original_video_info["item_list"][0]

        # 获取视频信息
        video_url = data["video"]["play_addr"]["url_list"][0].replace("playwm", "play")
        desc = data.get("desc", "").strip() or f"douyin_{video_id}"

        # 替换文件名中的非法字符
        desc = re.sub(r'[\\/:*?"<>|]', '_', desc)

        return {
            "url": video_url,
            "title": desc,
            "video_id": video_id
        }

    def _download_via_cookie_api(self, video_info: dict, output_dir: Path, show_progress: bool = True) -> Path:
        """CDN 失败时，使用 TikTokDownloader Detail API + 本地 Cookie 下载。"""
        try:
            wrapper_root = Path(__file__).resolve().parents[3] / "pixelle_wrapper"
            if not wrapper_root.exists():
                wrapper_root = Path(__file__).resolve().parents[4] / "pixelle_wrapper"
            install_dir = os.environ.get("AXON_INSTALL_DIR")
            if install_dir:
                candidate = Path(install_dir) / "pixelle_wrapper"
                if candidate.is_dir():
                    wrapper_root = candidate
            if str(wrapper_root) not in sys.path:
                sys.path.insert(0, str(wrapper_root))
            from ai_pipeline.douyin_api_downloader import download_douyin_video_api

            if show_progress:
                print("CDN 下载失败，尝试 Cookie API 下载...")
            return download_douyin_video_api(
                f"https://www.douyin.com/video/{video_info['video_id']}",
                output_dir,
                aweme_id=video_info["video_id"],
            )
        except Exception as exc:
            raise RuntimeError(f"Cookie API 下载失败: {exc}") from exc

    def _download_via_cookie_api_from_link(
        self, share_link: str, output_dir: Path, show_progress: bool = True
    ) -> Path:
        """按分享链接 + Cookie API 直接下载（主路径）。"""
        try:
            wrapper_root = _resolve_wrapper_root()
            if str(wrapper_root) not in sys.path:
                sys.path.insert(0, str(wrapper_root))
            from ai_pipeline.douyin_api_downloader import download_douyin_video_api

            if show_progress:
                print("使用链接 + Cookie API 下载...")
            return download_douyin_video_api(share_link, output_dir)
        except Exception as exc:
            raise RuntimeError(f"Cookie API 下载失败: {exc}") from exc

    def download_video(self, video_info: dict, output_dir: Optional[Path] = None, show_progress: bool = True) -> Path:
        """下载视频"""
        if output_dir is None:
            output_dir = self.temp_dir
        else:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{video_info['video_id']}.mp4"
        filepath = output_dir / filename

        if show_progress:
            print(f"正在下载视频: {video_info['title']}")

        try:
            response = requests.get(video_info['url'], headers=HEADERS, stream=True, timeout=60)
            response.raise_for_status()

            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=81936):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if show_progress and total_size > 0:
                            progress = downloaded / total_size * 100
                            print(f"\r下载进度: {progress:.1f}%", end="", flush=True)

            if downloaded < 100_000:
                filepath.unlink(missing_ok=True)
                raise requests.HTTPError(f"downloaded file too small ({downloaded} bytes)")

            if show_progress:
                print(f"\n视频下载完成: {filepath}")
            return filepath
        except (requests.HTTPError, requests.RequestException, RuntimeError):
            if filepath.exists():
                filepath.unlink(missing_ok=True)
            return self._download_via_cookie_api(video_info, output_dir, show_progress=show_progress)

    def extract_audio(self, video_path: Path, show_progress: bool = True) -> Path:
        """从视频文件中提取音频"""
        audio_path = video_path.with_suffix('.mp3')

        if show_progress:
            print("正在提取音频...")
        try:
            # 尝试使用我们自己的音频提取模块（如果可用）
            try:
                import sys
                from pathlib import Path as PathLib
                # 添加 pixelle_wrapper 路径
                current_file = PathLib(__file__)
                pixelle_path = current_file.parent.parent.parent.parent / "pixelle_wrapper"
                if pixelle_path.exists():
                    sys.path.insert(0, str(pixelle_path))
                    from ai_pipeline.audio_extractor import extract_audio_from_video
                    result_path = extract_audio_from_video(str(video_path), output_dir=audio_path.parent)
                    if result_path and PathLib(result_path).exists():
                        if show_progress:
                            print(f"音频提取完成: {result_path}")
                        return PathLib(result_path)
            except Exception as e:
                if show_progress:
                    print(f"[WARNING] 使用自定义模块失败，回退到 ffmpeg: {e}")
            
            # 回退到使用 ffmpeg
            (
                ffmpeg
                .input(str(video_path))
                .output(str(audio_path), acodec='libmp3lame', q=0)
                .run(capture_stdout=True, capture_stderr=True, overwrite_output=True)
            )
            if show_progress:
                print(f"音频提取完成: {audio_path}")
            return audio_path
        except Exception as e:
            raise Exception(f"提取音频时出错: {str(e)}")

    def get_audio_info(self, audio_path: Path) -> dict:
        """获取音频文件信息（时长和大小）"""
        try:
            probe = ffmpeg.probe(str(audio_path))
            duration = float(probe['format'].get('duration', 0))
            size = audio_path.stat().st_size
            return {'duration': duration, 'size': size}
        except Exception:
            return {'duration': 0, 'size': audio_path.stat().st_size}

    def split_audio(self, audio_path: Path, segment_duration: int = 600, show_progress: bool = True) -> list:
        """
        将音频分割成多个片段

        参数:
            audio_path: 音频文件路径
            segment_duration: 每段时长（秒），默认 10 分钟
            show_progress: 是否显示进度

        返回:
            分割后的音频文件路径列表
        """
        audio_info = self.get_audio_info(audio_path)
        duration = audio_info['duration']

        if duration <= segment_duration:
            return [audio_path]

        segments = []
        segment_index = 0
        current_time = 0

        if show_progress:
            total_segments = int(duration / segment_duration) + 1
            print(f"音频时长 {duration:.0f} 秒，将分割为 {total_segments} 段...")

        while current_time < duration:
            segment_path = self.temp_dir / f"segment_{segment_index}.mp3"

            try:
                (
                    ffmpeg
                    .input(str(audio_path), ss=current_time, t=segment_duration)
                    .output(str(segment_path), acodec='libmp3lame', q=0)
                    .run(capture_stdout=True, capture_stderr=True, overwrite_output=True)
                )
                segments.append(segment_path)

                if show_progress:
                    print(f"  分割片段 {segment_index + 1}: {current_time:.0f}s - {min(current_time + segment_duration, duration):.0f}s")

            except Exception as e:
                raise Exception(f"分割音频片段 {segment_index} 时出错: {str(e)}")

            current_time += segment_duration
            segment_index += 1

        return segments

    def transcribe_single_audio(self, audio_path: Path) -> str:
        """转录单个音频文件"""
        # 如果没有 API Key，直接使用 Whisper
        if not self.api_key:
            return self._transcribe_with_whisper(audio_path)
        
        files = {
            'file': (audio_path.name, open(audio_path, 'rb'), 'audio/mpeg'),
            'model': (None, self.model)
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }

        try:
            response = requests.post(self.api_base_url, files=files, headers=headers)
            response.raise_for_status()

            result = response.json()
            if 'text' in result:
                return result['text']
            else:
                return response.text

        except Exception as e:
            # API 调用失败，回退到 Whisper
            print(f"[WARNING] API 调用失败: {e}")
            print("[INFO] 回退到使用 Whisper 本地模型...")
            files['file'][1].close()
            return self._transcribe_with_whisper(audio_path)
    
    def _transcribe_with_whisper(self, audio_path: Path) -> str:
        """使用 Whisper 本地模型转录音频"""
        try:
            import sys
            from pathlib import Path as PathLib
            # 添加 whisper 和 pixelle_wrapper 路径
            current_file = PathLib(__file__)
            # 从 douyin-video/scripts/douyin_downloader.py 向上找到项目根目录
            project_root = current_file.parent.parent.parent.parent
            whisper_path = project_root / "whisper-main"
            pixelle_path = project_root / "pixelle_wrapper"
            
            if whisper_path.exists():
                if str(whisper_path) not in sys.path:
                    sys.path.insert(0, str(whisper_path))
            if pixelle_path.exists():
                if str(pixelle_path) not in sys.path:
                    sys.path.insert(0, str(pixelle_path))
            else:
                raise Exception(f"pixelle_path 不存在: {pixelle_path}")
            
            try:
                from ai_pipeline.subtitle_generator import generate_subtitle
                # 使用 Whisper 提取文案
                print(f"[DEBUG] 调用 generate_subtitle: {audio_path}")
                srt_path = generate_subtitle(str(audio_path), output_dir=audio_path.parent)
                print(f"[DEBUG] generate_subtitle 返回: {srt_path}")
                if srt_path and PathLib(srt_path).exists():
                    # 读取文案文本
                    text_path = PathLib(audio_path).parent / f"{PathLib(audio_path).stem}.txt"
                    if text_path.exists():
                        with open(text_path, 'r', encoding='utf-8') as f:
                            text = f.read()
                            print(f"[DEBUG] 从txt文件读取文案，长度: {len(text)}")
                            return text
                    # 如果没有txt文件，从SRT文件提取
                    with open(srt_path, 'r', encoding='utf-8') as f:
                        srt_content = f.read()
                    lines = srt_content.split('\n')
                    text_lines = [line for line in lines if line and line.strip() and not line.strip().isdigit() and '-->' not in line]
                    text = '\n'.join(text_lines)
                    print(f"[DEBUG] 从SRT文件提取文案，长度: {len(text)}")
                    return text
                else:
                    raise Exception(f"Whisper 生成字幕失败，srt_path={srt_path}")
            except ImportError as ie:
                raise Exception(f"无法导入 subtitle_generator: {ie}, sys.path={sys.path[:5]}")
            except Exception as e:
                raise Exception(f"Whisper 处理失败: {e}")
        except Exception as e:
            raise Exception(f"使用 Whisper 提取文字时出错: {str(e)}")

    def extract_text_from_audio(self, audio_path: Path, show_progress: bool = True) -> str:
        """从音频文件中提取文字（支持大文件自动分段）"""
        if not self.api_key:
            raise ValueError("未设置 API 密钥，请设置环境变量 DOUYIN_API_KEY")

        # 检查文件大小和时长
        audio_info = self.get_audio_info(audio_path)
        max_duration = 3600  # 1 小时
        max_size = 50 * 1024 * 1024  # 50MB

        # 判断是否需要分段
        need_split = audio_info['duration'] > max_duration or audio_info['size'] > max_size

        if not need_split:
            # 文件在限制范围内，直接处理
            if show_progress:
                print("正在识别语音...")
            return self.transcribe_single_audio(audio_path)

        # 需要分段处理
        if show_progress:
            print(f"音频文件较大（时长: {audio_info['duration']:.0f}秒, 大小: {audio_info['size'] / 1024 / 1024:.1f}MB）")
            print("将自动分段处理...")

        # 分割音频
        segments = self.split_audio(audio_path, segment_duration=540, show_progress=show_progress)  # 9分钟一段，留余量

        # 逐段转录
        all_texts = []
        for i, segment_path in enumerate(segments):
            if show_progress:
                print(f"正在识别第 {i + 1}/{len(segments)} 段...")

            text = self.transcribe_single_audio(segment_path)
            all_texts.append(text)

            # 清理分段文件
            if segment_path != audio_path:
                self.cleanup_files(segment_path)

        # 合并文本
        merged_text = ''.join(all_texts)

        if show_progress:
            print(f"语音识别完成，共处理 {len(segments)} 个片段")

        return merged_text

    def cleanup_files(self, *file_paths: Path):
        """清理指定的文件"""
        for file_path in file_paths:
            if file_path.exists():
                file_path.unlink()


def _link_api_available() -> bool:
    try:
        wrapper_root = _resolve_wrapper_root()
        if str(wrapper_root) not in sys.path:
            sys.path.insert(0, str(wrapper_root))
        from ai_pipeline.douyin_api_downloader import is_api_downloader_available

        return bool(is_api_downloader_available())
    except Exception:
        return False


def _resolve_wrapper_root() -> Path:
    install_dir = os.environ.get("AXON_INSTALL_DIR")
    if install_dir:
        candidate = Path(install_dir) / "pixelle_wrapper"
        if candidate.is_dir():
            return candidate
    wrapper_root = Path(__file__).resolve().parents[3] / "pixelle_wrapper"
    if wrapper_root.exists():
        return wrapper_root
    return Path(__file__).resolve().parents[4] / "pixelle_wrapper"


def _parse_video_info_via_link_api(share_link: str) -> dict:
    wrapper_root = _resolve_wrapper_root()
    if str(wrapper_root) not in sys.path:
        sys.path.insert(0, str(wrapper_root))
    from ai_pipeline.douyin_api_downloader import fetch_aweme_from_link

    meta = fetch_aweme_from_link(share_link)
    return {"url": share_link, "title": meta["title"], "video_id": meta["video_id"]}


def get_video_info(share_link: str) -> dict:
    """获取视频信息和下载链接"""
    if _link_api_available():
        try:
            return _parse_video_info_via_link_api(share_link)
        except Exception:
            pass
    processor = DouyinProcessor()
    return processor.parse_share_url(share_link)


def download_video(share_link: str, output_dir: str = ".") -> Path:
    """下载视频到指定目录"""
    processor = DouyinProcessor()
    out = Path(output_dir)
    if _link_api_available():
        try:
            return processor._download_via_cookie_api_from_link(share_link, out, show_progress=True)
        except Exception:
            pass
    try:
        video_info = processor.parse_share_url(share_link)
        return processor.download_video(video_info, out)
    except Exception:
        return processor._download_via_cookie_api_from_link(share_link, out, show_progress=True)


def extract_text(share_link: str, api_key: Optional[str] = None, output_dir: Optional[str] = None,
                 save_video: bool = False, show_progress: bool = True) -> dict:
    """
    从视频中提取文案并保存到文件

    返回:
        dict: 包含 video_info, text, output_path 的字典
    """
    api_key = api_key or os.getenv('API_KEY')
    if not api_key:
        raise ValueError("未设置环境变量 API_KEY，请先获取硅基流动 API 密钥")

    processor = DouyinProcessor(api_key)

    if show_progress:
        print("正在解析抖音分享链接...")
    video_info = None
    if _link_api_available():
        try:
            video_info = _parse_video_info_via_link_api(share_link)
        except Exception:
            video_info = None
    if not video_info:
        try:
            video_info = processor.parse_share_url(share_link)
        except Exception:
            video_info = {"video_id": "", "title": "douyin_video", "url": share_link}

    if show_progress:
        print("正在下载视频...")
    try:
        if _link_api_available():
            video_path = processor._download_via_cookie_api_from_link(
                share_link, processor.temp_dir, show_progress=show_progress
            )
        elif video_info.get("video_id"):
            video_path = processor.download_video(video_info, show_progress=show_progress)
        else:
            raise ValueError("parse empty")
    except Exception:
        video_path = processor._download_via_cookie_api_from_link(
            share_link, processor.temp_dir, show_progress=show_progress
        )
        if not video_info.get("video_id"):
            video_info["video_id"] = video_path.stem

    if show_progress:
        print("正在提取音频...")
    audio_path = processor.extract_audio(video_path, show_progress=show_progress)

    if show_progress:
        print("正在从音频中提取文本...")
    text_content = processor.extract_text_from_audio(audio_path, show_progress=show_progress)

    result = {
        "video_info": video_info,
        "text": text_content,
        "output_path": None
    }

    # 保存到文件
    if output_dir:
        output_base = Path(output_dir)
        video_folder = output_base / video_info['video_id']
        video_folder.mkdir(parents=True, exist_ok=True)

        # 保存文案为 Markdown 格式
        transcript_path = video_folder / "transcript.md"
        with open(transcript_path, 'w', encoding='utf-8') as f:
            f.write(f"# {video_info['title']}\n\n")
            f.write(f"| 属性 | 值 |\n")
            f.write(f"|------|----|\n")
            f.write(f"| 视频ID | `{video_info['video_id']}` |\n")
            f.write(f"| 提取时间 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} |\n")
            f.write(f"| 下载链接 | [点击下载]({video_info['url']}) |\n\n")
            f.write(f"---\n\n")
            f.write(f"## 文案内容\n\n")
            f.write(text_content)

        result["output_path"] = str(video_folder)

        if show_progress:
            print(f"文案已保存到: {transcript_path}")

        # 保存视频 (可选)
        if save_video:
            saved_video_path = video_folder / f"{video_info['video_id']}.mp4"
            shutil.copy2(video_path, saved_video_path)
            if show_progress:
                print(f"视频已保存到: {saved_video_path}")

    # 清理临时文件
    if show_progress:
        print("正在清理临时文件...")
    processor.cleanup_files(video_path, audio_path)

    return result


def main():
    parser = argparse.ArgumentParser(
        description="抖音无水印视频下载和文案提取工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 获取视频信息和下载链接
  python douyin_downloader.py --link "抖音分享链接" --action info

  # 下载视频
  python douyin_downloader.py --link "抖音分享链接" --action download --output ./videos

  # 提取文案并保存到文件 (需要设置 DOUYIN_API_KEY 环境变量)
  python douyin_downloader.py --link "抖音分享链接" --action extract --output ./output

  # 提取文案并同时保存视频
  python douyin_downloader.py --link "抖音分享链接" --action extract --output ./output --save-video
        """
    )

    parser.add_argument("--link", "-l", required=True, help="抖音分享链接或包含链接的文本")
    parser.add_argument("--action", "-a", choices=["info", "download", "extract"],
                        default="info", help="操作类型: info(获取信息), download(下载视频), extract(提取文案)")
    parser.add_argument("--output", "-o", default="./output", help="输出目录 (默认 ./output)")
    parser.add_argument("--api-key", "-k", help="硅基流动 API 密钥 (也可通过 DOUYIN_API_KEY 环境变量设置)")
    parser.add_argument("--save-video", "-v", action="store_true", help="提取文案时同时保存视频")
    parser.add_argument("--quiet", "-q", action="store_true", help="安静模式，减少输出")

    args = parser.parse_args()

    try:
        if args.action == "info":
            info = get_video_info(args.link)
            print("\n" + "=" * 50)
            print("视频信息:")
            print("=" * 50)
            print(f"视频ID: {info['video_id']}")
            print(f"标题: {info['title']}")
            print(f"下载链接: {info['url']}")
            print("=" * 50)

        elif args.action == "download":
            video_path = download_video(args.link, args.output)
            print(f"\n视频已保存到: {video_path}")

        elif args.action == "extract":
            result = extract_text(
                args.link,
                args.api_key,
                output_dir=args.output,
                save_video=args.save_video,
                show_progress=not args.quiet
            )

            if not args.quiet:
                print("\n" + "=" * 50)
                print("提取完成!")
                print("=" * 50)
                print(f"视频ID: {result['video_info']['video_id']}")
                print(f"标题: {result['video_info']['title']}")
                if result['output_path']:
                    print(f"保存位置: {result['output_path']}")
                print("=" * 50)
                print("\n文案内容:\n")
                print(result['text'][:500] + "..." if len(result['text']) > 500 else result['text'])
                print("\n" + "=" * 50)

    except Exception as e:
        print(f"\n错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
