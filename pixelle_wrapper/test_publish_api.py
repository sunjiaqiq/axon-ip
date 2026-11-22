"""
测试发布 API：使用素材生产里最新的视频，默认测试内容
"""
import requests
import json
import time
import logging

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def get_latest_video():
    """获取最新生成的视频"""
    import os
    from pathlib import Path
    
    # 方法1: 从任务API获取
    try:
        response = requests.get('http://localhost:38810/api/tasks', timeout=5)
        if response.ok:
            data = response.json()
            tasks = data.get('tasks', {})
            
            # 找到最新的已完成任务
            latest_task = None
            latest_time = 0
            for task_id, task in tasks.items():
                task_data = task
                if task_data.get('status') == 'done' and task_data.get('output'):
                    created_at = task_data.get('created_at', '')
                    if created_at:
                        try:
                            from datetime import datetime
                            created_time = datetime.fromisoformat(created_at.replace('Z', '+00:00')).timestamp()
                            if created_time > latest_time:
                                latest_time = created_time
                                latest_task = task_data
                        except:
                            pass
            
            if latest_task and latest_task.get('output'):
                video_path = latest_task.get('output')
                if os.path.exists(video_path):
                    return video_path
    except Exception as e:
        logger.warning(f"从任务API获取视频失败: {e}")
    
    # 方法2: 从output目录查找最新的final.mp4
    try:
        wrapper_dir = Path(__file__).parent
        output_dir = wrapper_dir / "output"
        if output_dir.exists():
            video_files = list(output_dir.rglob("final.mp4"))
            if video_files:
                latest_video = max(video_files, key=os.path.getmtime)
                return str(latest_video)
    except Exception as e:
        logger.warning(f"从output目录查找视频失败: {e}")
    
    return None

def test_publish():
    """测试发布功能"""
    try:
        logger.info("=" * 70)
        logger.info("测试发布功能")
        logger.info("=" * 70)
        
        # 1. 获取最新视频
        logger.info("\n[1. 获取最新视频]")
        video_path = get_latest_video()
        if not video_path:
            logger.error("未找到已生成的视频")
            return
        
        logger.info(f"最新视频: {video_path}")
        
        # 2. 调用发布 API
        logger.info("\n[2. 调用发布 API]")
        url = "http://localhost:38810/api/publish/douyin"
        payload = {
            "video_path": video_path,
            "title": "测试文字",  # 默认测试标题
            "description": "测试文字",  # 默认测试描述
            "cover_path": None  # 不提供封面，系统会自动从视频提取
        }
        
        logger.info(f"URL: {url}")
        logger.info(f"Payload: {json.dumps(payload, indent=2, ensure_ascii=False)}")
        
        response = requests.post(url, json=payload, timeout=10)
        
        logger.info(f"\n[响应]")
        logger.info(f"状态码: {response.status_code}")
        
        if response.ok:
            result = response.json()
            logger.info(f"结果: {json.dumps(result, indent=2, ensure_ascii=False)}")
            logger.info("\n✅ 发布任务已启动！")
            logger.info("浏览器将自动执行发布流程...")
            logger.info("请观察浏览器，确认发布是否成功")
        else:
            error = response.json()
            logger.error(f"❌ 发布失败: {error.get('detail', '未知错误')}")
            
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_publish()

