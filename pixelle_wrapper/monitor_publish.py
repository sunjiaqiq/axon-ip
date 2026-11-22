"""
发布流程监控脚本 - 实时监控发布日志和错误
"""
import requests
import time
import json
from datetime import datetime

def log(message):
    """打印带时间戳的日志"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

def monitor_publish():
    """监控发布流程"""
    log("=" * 70)
    log("开始监控发布流程...")
    log("=" * 70)
    
    # 使用最新的视频文件
    video_path = r"F:\shuziren\pixelle_wrapper\output\20260316_095606_5cb49fcc\final.mp4"
    title = "AI生产力测试 - 带字幕视频"
    description = "这是自动化生成的带字幕视频，测试发布功能"
    cover_text = "AI测试"
    
    log(f"视频路径: {video_path}")
    log(f"标题: {title}")
    log(f"描述: {description}")
    log("=" * 70)
    
    try:
        # 调用发布接口
        log("正在调用发布接口...")
        response = requests.post(
            'http://127.0.0.1:38810/api/publish/douyin',
            json={
                'video_path': video_path,
                'title': title,
                'description': description,
                'cover_text': cover_text
            },
            timeout=30
        )
        
        log(f"发布接口响应状态: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            log(f"发布接口返回: {json.dumps(result, ensure_ascii=False, indent=2)}")
            
            if result.get('success'):
                log("✅ 发布任务已启动，正在后台执行...")
                log("=" * 70)
                log("开始监控浏览器状态和发布进度...")
                log("=" * 70)
                
                # 监控浏览器状态
                max_wait = 600  # 最多等待10分钟
                waited = 0
                check_interval = 5  # 每5秒检查一次
                
                while waited < max_wait:
                    time.sleep(check_interval)
                    waited += check_interval
                    
                    # 检查浏览器状态
                    try:
                        status_response = requests.get('http://127.0.0.1:38810/api/browser/status', timeout=5)
                        if status_response.status_code == 200:
                            status_data = status_response.json()
                            log(f"[浏览器状态] {status_data.get('status', 'unknown')} - {status_data.get('message', '')}")
                            
                            if status_data.get('platforms'):
                                douyin_status = status_data['platforms'].get('douyin', False)
                                log(f"[平台状态] 抖音登录: {'已登录' if douyin_status else '未登录'}")
                    except Exception as e:
                        log(f"[警告] 检查浏览器状态失败: {e}")
                    
                    # 每30秒打印一次进度
                    if waited % 30 == 0:
                        minutes = waited // 60
                        seconds = waited % 60
                        log(f"[监控] 已等待 {minutes}分{seconds}秒，继续监控...")
                
                log("=" * 70)
                log("监控完成（10分钟）")
                log("=" * 70)
            else:
                log(f"❌ 发布任务启动失败: {result.get('message', '未知错误')}")
        else:
            log(f"❌ 发布接口调用失败: {response.status_code}")
            log(f"错误信息: {response.text}")
            
    except Exception as e:
        log(f"❌ 发布流程出错: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    monitor_publish()




