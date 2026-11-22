"""
测试发布流程 - 使用最新视频，监控所有步骤和错误
"""
import requests
import time
import json
from datetime import datetime
from pathlib import Path

def log(message):
    """打印带时间戳的日志"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

def test_publish_flow():
    """测试发布流程"""
    log("=" * 70)
    log("开始测试发布流程（带日志监控）")
    log("=" * 70)
    
    # 使用最新的视频文件（带字幕的）
    video_path = r"F:\shuziren\pixelle_wrapper\output\20260316_095606_5cb49fcc\final.mp4"
    
    # 检查视频是否存在
    if not Path(video_path).exists():
        log(f"视频文件不存在: {video_path}")
        return
    
    log(f"视频文件存在: {video_path}")
    log(f"   文件大小: {Path(video_path).stat().st_size / (1024*1024):.2f} MB")
    
    # 准备发布内容
    title = "AI生产力测试 - 带字幕视频"
    description = "这是自动化生成的带字幕视频，测试发布功能"
    cover_text = "AI测试"
    
    log(f"标题: {title}")
    log(f"描述: {description}")
    log(f"封面文字: {cover_text}")
    log("=" * 70)
    
    # 检查后端状态
    try:
        status_response = requests.get('http://127.0.0.1:38810/api/browser/status', timeout=5)
        if status_response.status_code == 200:
            status_data = status_response.json()
            log(f"浏览器状态: {status_data.get('status', 'unknown')}")
            log(f"抖音登录: {'已登录' if status_data.get('platforms', {}).get('douyin') else '未登录'}")
        else:
            log(f"无法获取浏览器状态: {status_response.status_code}")
    except Exception as e:
        log(f"检查浏览器状态失败: {e}")
    
    log("=" * 70)
    log("正在调用发布接口...")
    log("=" * 70)
    
    try:
        # 调用发布接口
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
            log(f"发布接口返回:")
            log(json.dumps(result, ensure_ascii=False, indent=2))
            
            if result.get('success'):
                log("=" * 70)
                log("发布任务已启动，正在后台执行...")
                log("=" * 70)
                log("监控说明:")
                log("   1. 发布流程在后台线程执行")
                log("   2. 所有日志会输出到后端控制台")
                log("   3. 请观察浏览器窗口，查看发布进度")
                log("   4. 如果卡住，请查看后端日志中的错误信息")
                log("=" * 70)
                log("等待发布完成（最多10分钟）...")
                log("=" * 70)
                
                # 持续监控（最多10分钟）
                max_wait = 600
                waited = 0
                check_interval = 10  # 每10秒检查一次
                
                while waited < max_wait:
                    time.sleep(check_interval)
                    waited += check_interval
                    
                    # 每30秒打印一次进度
                    if waited % 30 == 0:
                        minutes = waited // 60
                        seconds = waited % 60
                        log(f"[监控] 已等待 {minutes}分{seconds}秒...")
                        
                        # 检查浏览器状态
                        try:
                            status_response = requests.get('http://127.0.0.1:38810/api/browser/status', timeout=5)
                            if status_response.status_code == 200:
                                status_data = status_response.json()
                                current_url = status_data.get('current_url', '')
                                if current_url:
                                    log(f"[浏览器] 当前URL: {current_url[:80]}...")
                        except:
                            pass
                
                log("=" * 70)
                log("监控完成（10分钟）")
                log("=" * 70)
                log("提示:")
                log("   - 请查看后端控制台的日志输出")
                log("   - 请观察浏览器窗口，确认是否发布成功")
                log("   - 如果发布失败，请查看后端日志中的错误信息")
            else:
                log(f"❌ 发布任务启动失败: {result.get('message', '未知错误')}")
        else:
            log(f"发布接口调用失败: {response.status_code}")
            log(f"错误信息: {response.text}")
            
    except requests.exceptions.Timeout:
        log("发布接口调用超时")
    except requests.exceptions.ConnectionError:
        log("无法连接到后端服务，请确保后端正在运行")
    except Exception as e:
        log(f"发布流程出错: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_publish_flow()

