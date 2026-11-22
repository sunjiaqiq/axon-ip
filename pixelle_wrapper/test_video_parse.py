"""
测试视频下载和文案解析流程
"""
import asyncio
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

async def test_full_process():
    """测试完整流程"""
    test_link = "3.35 06/20 I@V.LW eOX:/ 入住5年才敢说：客厅阳台门千万别拆！# 装修踩坑 # 装修避坑 # 阳台装修 # 家装经验 # 装修干货  https://v.douyin.com/NeDMxbDh5iU/ 复制此链接，打开Dou音搜索，直接观看视频！"
    
    logger.info("=" * 70)
    logger.info("测试视频下载和文案解析流程")
    logger.info("=" * 70)
    logger.info("")
    
    try:
        # 1. 解析链接
        from ai_pipeline.link_parser import extract_video_url
        logger.info("步骤1: 解析链接...")
        video_url = extract_video_url(test_link)
        if not video_url:
            logger.error("✗ 链接解析失败")
            return
        logger.info(f"✓ 链接解析成功: {video_url}")
        logger.info("")
        
        # 2. 下载视频
        from ai_pipeline.video_downloader import download_video
        materials_dir = Path(__file__).parent / "materials"
        materials_dir.mkdir(exist_ok=True)
        
        logger.info("步骤2: 下载视频...")
        logger.info(f"视频URL: {video_url}")
        logger.info(f"输出目录: {materials_dir}")
        logger.info("")
        
        # 在后台线程执行下载
        video_path = await asyncio.to_thread(download_video, video_url, materials_dir)
        if not video_path or not Path(video_path).exists():
            logger.error("✗ 视频下载失败")
            return
        logger.info(f"✓ 视频下载成功: {video_path}")
        logger.info(f"文件大小: {Path(video_path).stat().st_size / (1024*1024):.2f} MB")
        logger.info("")
        
        # 3. 提取音频（如果失败，直接使用视频）
        from ai_pipeline.audio_extractor import extract_audio_from_video
        logger.info("步骤3: 提取音频...")
        audio_path = await asyncio.to_thread(extract_audio_from_video, str(video_path), materials_dir)
        if not audio_path or not Path(audio_path).exists():
            logger.warning("音频提取失败，将直接使用视频文件进行语音识别")
            audio_path = video_path
        else:
            logger.info(f"✓ 音频提取成功: {audio_path}")
            logger.info(f"文件大小: {Path(audio_path).stat().st_size / (1024*1024):.2f} MB")
        logger.info("")
        
        # 4. 语音转文字（Whisper可以直接处理视频）
        from ai_pipeline.subtitle_generator import generate_subtitle
        logger.info("步骤4: 语音转文字（这可能需要几分钟）...")
        logger.info("正在加载Whisper模型...")
        srt_path = await asyncio.to_thread(generate_subtitle, str(audio_path), materials_dir)
        if not srt_path or not Path(srt_path).exists():
            logger.error("✗ 语音转文字失败")
            return
        logger.info(f"✓ 语音转文字成功: {srt_path}")
        logger.info("")
        
        # 5. 读取并显示文案
        logger.info("步骤5: 提取文案内容...")
        with open(srt_path, 'r', encoding='utf-8') as f:
            srt_content = f.read()
        
        # 提取所有文本
        lines = srt_content.split('\n')
        text_lines = []
        for line in lines:
            line = line.strip()
            if line and not line.isdigit() and '-->' not in line:
                text_lines.append(line)
        
        original_text = ' '.join(text_lines)
        
        logger.info("=" * 70)
        logger.info("提取的文案内容:")
        logger.info("=" * 70)
        logger.info(original_text)
        logger.info("=" * 70)
        logger.info("")
        logger.info("✓ 测试完成！")
        
        # 6. 提取文案结构
        from ai_pipeline.script_extractor import extract_script
        logger.info("步骤6: 提取文案结构...")
        script_dict = extract_script(original_text)
        logger.info("")
        logger.info("文案结构:")
        logger.info(f"  钩子: {script_dict.get('hook', '')[:100]}")
        logger.info(f"  问题: {script_dict.get('problem', '')[:100]}")
        logger.info(f"  方案: {script_dict.get('solution', '')[:100]}")
        logger.info(f"  行动: {script_dict.get('cta', '')[:100]}")
        logger.info("")
        logger.info("✓ 所有步骤完成！")
        
    except Exception as e:
        logger.error(f"✗ 测试失败: {e}")
        import traceback
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    asyncio.run(test_full_process())

