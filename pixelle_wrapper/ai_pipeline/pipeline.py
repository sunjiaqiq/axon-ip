"""
完整流程管道 - 实现从关键词到最终视频的完整流程
"""
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

from .crawler import search_videos
from .video_downloader import download_video
from .script_extractor import extract_script
from .script_rewriter import rewrite_script
from .subtitle_generator import generate_subtitle
from .video_editor import insert_material
from .original_filter import apply_filter

logger = logging.getLogger(__name__)


def generate_video(
    keyword: str,
    avatar_path: Optional[str] = None,
    product_path: Optional[str] = None,
    output_dir: Optional[Path] = None,
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    完整视频生成流程
    
    流程：
    1. 搜索爆款视频
    2. 下载视频素材
    3. 提取文案
    4. 改写文案
    5. 调用 Pixelle API 生成口播视频
    6. 插入素材
    7. 生成字幕
    8. 原创处理
    9. 输出最终视频
    
    Args:
        keyword: 行业关键词
        avatar_path: 数字人形象路径（可选，如果已有）
        product_path: 产品图片路径（可选）
        output_dir: 输出目录
        api_key: API密钥
        
    Returns:
        包含生成结果的字典：
        {
            'success': bool,
            'video_path': str,
            'subtitle_path': str,
            'message': str
        }
    """
    logger.info(f"[Pipeline] 开始生成视频，关键词: {keyword}")
    
    try:
        # 设置输出目录
        if output_dir is None:
            output_dir = Path(__file__).parent.parent / "output" / f"auto_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        else:
            output_dir = Path(output_dir)
        
        output_dir.mkdir(parents=True, exist_ok=True)
        materials_dir = output_dir / "materials"
        materials_dir.mkdir(exist_ok=True)
        
        # 步骤1: 搜索爆款视频
        logger.info("[Pipeline] 步骤1: 搜索爆款视频...")
        videos = search_videos(keyword)
        
        if not videos:
            return {
                'success': False,
                'message': '未找到符合条件的视频'
            }
        
        logger.info(f"[Pipeline] 找到 {len(videos)} 条视频")
        
        # 步骤2: 下载视频素材
        logger.info("[Pipeline] 步骤2: 下载视频素材...")
        material_paths = []
        for i, video in enumerate(videos[:3]):  # 只下载前3个
            try:
                video_url = video.get('video_url', '')
                if video_url:
                    downloaded = download_video(video_url, materials_dir)
                    if downloaded:
                        material_paths.append(str(downloaded))
                        logger.info(f"[Pipeline] 下载素材 {i+1}/{len(videos[:3])}: {downloaded.name}")
            except Exception as e:
                logger.warning(f"[Pipeline] 下载素材失败: {e}")
                continue
        
        if not material_paths:
            logger.warning("[Pipeline] 没有成功下载的素材")
        
        # 步骤3: 提取文案
        logger.info("[Pipeline] 步骤3: 提取文案...")
        first_video = videos[0]
        script = extract_script(first_video.get('desc', ''))
        
        # 步骤4: 改写文案
        logger.info("[Pipeline] 步骤4: 改写文案...")
        # 使用默认AI接口配置
        api_url = os.getenv('AI_API_URL', 'https://new.12ai.org/v1/chat/completions')
        if not api_key:
            api_key = os.getenv('AI_API_KEY', '')
        rewritten_script = rewrite_script(script, api_key, api_url)
        full_script = rewritten_script.get('full_script', rewritten_script.get('hook', '') + rewritten_script.get('solution', ''))
        
        logger.info(f"[Pipeline] 改写后的文案: {full_script[:100]}...")
        
        # 步骤5: 调用 Pixelle API 生成口播视频
        logger.info("[Pipeline] 步骤5: 生成口播视频...")
        # 这里需要调用现有的 Pixelle API
        # 由于不能修改现有逻辑，我们需要通过HTTP调用
        host_video_path = _generate_host_video(
            full_script,
            avatar_path,
            product_path,
            output_dir,
            api_key
        )
        
        if not host_video_path or not Path(host_video_path).exists():
            return {
                'success': False,
                'message': '口播视频生成失败'
            }
        
        logger.info(f"[Pipeline] 口播视频生成完成: {host_video_path}")
        
        # 步骤6: 插入素材
        edited_video_path = None
        if material_paths:
            logger.info("[Pipeline] 步骤6: 插入素材...")
            edited_video_path = insert_material(host_video_path, material_paths, output_dir / "edited_video.mp4")
            if edited_video_path:
                logger.info(f"[Pipeline] 素材插入完成: {edited_video_path}")
        
        # 使用编辑后的视频或原始视频
        video_to_process = str(edited_video_path) if edited_video_path else host_video_path
        
        # 步骤7: 生成字幕（从音频生成）
        logger.info("[Pipeline] 步骤7: 生成字幕...")
        # 需要先提取音频
        audio_path = _extract_audio(video_to_process, output_dir)
        subtitle_path = None
        if audio_path:
            subtitle_path = generate_subtitle(audio_path, output_dir)
            if subtitle_path:
                logger.info(f"[Pipeline] 字幕生成完成: {subtitle_path}")
        
        # 步骤8: 原创处理
        logger.info("[Pipeline] 步骤8: 原创处理...")
        final_video_path = apply_filter(video_to_process, output_dir / "final_video.mp4")
        
        if not final_video_path or not Path(final_video_path).exists():
            # 如果原创处理失败，使用原视频
            final_video_path = video_to_process
            logger.warning("[Pipeline] 原创处理失败，使用原视频")
        
        logger.info(f"[Pipeline] 最终视频: {final_video_path}")
        
        return {
            'success': True,
            'video_path': str(final_video_path),
            'subtitle_path': str(subtitle_path) if subtitle_path else None,
            'script': full_script,
            'message': '视频生成成功'
        }
        
    except Exception as e:
        logger.error(f"[Pipeline] 生成视频时出错: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            'success': False,
            'message': f'生成失败: {str(e)}'
        }


def _generate_host_video(
    script: str,
    avatar_path: Optional[str],
    product_path: Optional[str],
    output_dir: Path,
    api_key: Optional[str]
) -> Optional[str]:
    """
    调用 Pixelle API 生成口播视频
    这里通过HTTP调用现有的 /api/generate 接口
    """
    try:
        import requests
        import os
        
        # 获取API基础URL（从环境变量或使用默认值）
        base_url = os.getenv('PIXELLE_API_URL', 'http://localhost:8000')
        
        # 准备请求数据
        data = {
            'text': script,
            'mode': 'fixed',
            'frame_template': '1080x1920/default.html',
            'n_scenes': 5
        }
        
        # 如果有avatar和product，需要先上传
        files = {}
        if avatar_path and Path(avatar_path).exists():
            files['avatar'] = open(avatar_path, 'rb')
        
        if product_path and Path(product_path).exists():
            files['product'] = open(product_path, 'rb')
        
        # 调用生成接口
        response = requests.post(
            f"{base_url}/api/generate",
            data=data,
            files=files if files else None,
            timeout=300
        )
        
        if files:
            for f in files.values():
                f.close()
        
        if response.status_code == 200:
            result = response.json()
            task_id = result.get('task_id')
            
            # 轮询任务状态
            import time
            max_wait = 600  # 最多等待10分钟
            waited = 0
            while waited < max_wait:
                time.sleep(5)
                status_response = requests.get(f"{base_url}/api/task/{task_id}")
                if status_response.status_code == 200:
                    status_data = status_response.json()
                    if status_data.get('status') == 'completed':
                        video_path = status_data.get('result', {}).get('video_path')
                        if video_path:
                            return video_path
                    elif status_data.get('status') == 'failed':
                        logger.error(f"[Pipeline] 视频生成失败: {status_data.get('message')}")
                        return None
                waited += 5
            
            logger.error("[Pipeline] 视频生成超时")
            return None
        else:
            logger.error(f"[Pipeline] API调用失败: {response.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"[Pipeline] 调用Pixelle API时出错: {e}")
        return None


def _extract_audio(video_path: str, output_dir: Path) -> Optional[str]:
    """从视频中提取音频"""
    try:
        from moviepy.editor import VideoFileClip
        
        video = VideoFileClip(video_path)
        audio_path = output_dir / "audio.wav"
        video.audio.write_audiofile(str(audio_path))
        video.close()
        return str(audio_path)
    except Exception as e:
        logger.error(f"[Pipeline] 提取音频失败: {e}")
        return None

