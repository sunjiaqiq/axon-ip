"""
自动化测试脚本 - 每10分钟检测一次，启动一次全流程自动化
只发抖音，检测打开
"""
import requests
import time
import json
from datetime import datetime
import sys

# 配置
DOUYIN_LINK = "https://v.douyin.com/-XVB9noP1bw/"
API_BASE_URL = "http://localhost:38810"
CHECK_INTERVAL = 600  # 10分钟 = 600秒
PLATFORM = "douyin"  # 只发抖音

def log(message):
    """打印带时间戳的日志"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

def check_backend():
    """检查后端是否可用"""
    try:
        # 使用 /api/state 接口检查后端
        response = requests.get(f"{API_BASE_URL}/api/state", timeout=5)
        return response.status_code == 200
    except:
        return False

def start_automation():
    """启动自动化流程"""
    log("=" * 60)
    log("开始启动自动化流程...")
    log(f"链接: {DOUYIN_LINK}")
    log(f"平台: {PLATFORM}")
    
    try:
        # 调用自动化接口
        response = requests.post(
            f"{API_BASE_URL}/api/auto_generate_full",
            json={
                "link": DOUYIN_LINK,
                "compliance_enabled": True,  # 启用合规检测
                "platforms": [PLATFORM]  # 只发抖音
            },
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            task_id = result.get("task_id")
            log(f"✅ 自动化流程已启动！")
            log(f"任务ID: {task_id}")
            log(f"响应: {json.dumps(result, ensure_ascii=False, indent=2)}")
            return task_id
        else:
            log(f"❌ 启动失败: {response.status_code}")
            log(f"错误信息: {response.text}")
            return None
            
    except Exception as e:
        log(f"❌ 启动自动化流程时出错: {e}")
        import traceback
        traceback.print_exc()
        return None

def check_task_status(task_id):
    """检查任务状态"""
    try:
        response = requests.get(
            f"{API_BASE_URL}/api/auto_task/{task_id}",
            timeout=5
        )
        if response.status_code == 200:
            return response.json()
        return None
    except:
        return None

def main():
    """主循环"""
    log("=" * 60)
    log("自动化测试脚本启动")
    log(f"检测间隔: {CHECK_INTERVAL}秒 (10分钟)")
    log(f"目标链接: {DOUYIN_LINK}")
    log(f"发布平台: {PLATFORM}")
    log("=" * 60)
    
    # 检查后端
    if not check_backend():
        log("❌ 后端服务不可用，请先启动后端！")
        sys.exit(1)
    
    log("✅ 后端服务正常")
    
    # 立即启动一次
    log("\n[第1次] 立即启动自动化流程...")
    task_id = start_automation()
    
    if task_id:
        log(f"\n[监控] 开始监控任务 {task_id}...")
        # 监控任务状态（最多30分钟）
        max_wait = 1800  # 30分钟
        waited = 0
        while waited < max_wait:
            time.sleep(10)  # 每10秒检查一次
            waited += 10
            status = check_task_status(task_id)
            if status:
                status_text = status.get("status", "unknown")
                progress = status.get("progress", 0)
                log(f"[监控] 任务状态: {status_text}, 进度: {progress}%")
                
                if status_text == "done":
                    log("✅ 任务完成！")
                    log(f"结果: {json.dumps(status, ensure_ascii=False, indent=2)}")
                    break
                elif status_text == "error":
                    log(f"❌ 任务失败: {status.get('error', '未知错误')}")
                    break
    
    # 开始定时循环
    run_count = 1
    while True:
        try:
            log(f"\n[等待] 等待 {CHECK_INTERVAL} 秒后进行下一次检测...")
            time.sleep(CHECK_INTERVAL)
            
            run_count += 1
            log(f"\n[第{run_count}次] 开始启动自动化流程...")
            
            # 检查后端
            if not check_backend():
                log("❌ 后端服务不可用，跳过本次执行")
                continue
            
            # 启动自动化
            task_id = start_automation()
            
            if task_id:
                log(f"\n[监控] 开始监控任务 {task_id}...")
                # 监控任务状态（最多30分钟）
                max_wait = 1800
                waited = 0
                while waited < max_wait:
                    time.sleep(10)
                    waited += 10
                    status = check_task_status(task_id)
                    if status:
                        status_text = status.get("status", "unknown")
                        progress = status.get("progress", 0)
                        if waited % 60 == 0:  # 每分钟打印一次
                            log(f"[监控] 任务状态: {status_text}, 进度: {progress}%")
                        
                        if status_text == "done":
                            log("✅ 任务完成！")
                            log(f"结果: {json.dumps(status, ensure_ascii=False, indent=2)}")
                            break
                        elif status_text == "error":
                            log(f"❌ 任务失败: {status.get('error', '未知错误')}")
                            break
                            
        except KeyboardInterrupt:
            log("\n收到中断信号，退出...")
            break
        except Exception as e:
            log(f"❌ 执行出错: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(60)  # 出错后等待1分钟再继续

if __name__ == "__main__":
    main()

