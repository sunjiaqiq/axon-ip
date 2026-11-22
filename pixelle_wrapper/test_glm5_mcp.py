"""
测试 GLM 5 调用抖音发布 MCP Server
"""
import asyncio
import logging
import json
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

async def test_glm5_mcp():
    """测试 GLM 5 调用 MCP 工具"""
    try:
        import openai
        
        # 从配置文件读取 API Key
        import yaml
        config_path = Path(__file__).parent / "config.yaml"
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            api_key = config['siliconflow']['api_key']
            api_base = config['siliconflow']['api_base']
            model = config['siliconflow']['model']
        
        logger.info("=" * 70)
        logger.info("测试 GLM 5 调用抖音发布 MCP Server")
        logger.info("=" * 70)
        logger.info(f"模型: {model}")
        logger.info(f"API Base: {api_base}")
        
        # 初始化 OpenAI 客户端（兼容硅基流动）
        client = openai.OpenAI(
            api_key=api_key,
            base_url=api_base
        )
        
        # 查找测试视频
        output_dir = Path(__file__).parent / "output"
        if not output_dir.exists():
            logger.error("output目录不存在")
            return
        
        video_path = None
        task_dirs = sorted([d for d in output_dir.iterdir() if d.is_dir()], 
                          key=lambda x: x.stat().st_mtime, reverse=True)
        for task_dir in task_dirs:
            final_video = task_dir / "final.mp4"
            if final_video.exists():
                video_path = final_video
                logger.info(f"[测试] 找到视频: {video_path}")
                break
        
        if not video_path:
            logger.error("未找到测试视频")
            return
        
        # 定义 MCP 工具（模拟 MCP Server 的工具定义）
        mcp_tools = [
            {
                "type": "function",
                "function": {
                    "name": "publish_video",
                    "description": "发布视频到抖音。需要提供视频路径、标题和描述。如果不提供封面路径，会自动从视频提取封面。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "video_path": {
                                "type": "string",
                                "description": "视频文件的完整路径"
                            },
                            "title": {
                                "type": "string",
                                "description": "视频标题"
                            },
                            "description": {
                                "type": "string",
                                "description": "视频描述/作品介绍"
                            },
                            "cover_path": {
                                "type": "string",
                                "description": "封面图片路径（可选，如果不提供则从视频自动提取）"
                            }
                        },
                        "required": ["video_path", "title", "description"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "check_browser_status",
                    "description": "检查浏览器状态，查看浏览器是否正常运行",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            }
        ]
        
        # 给 GLM 5 下任务
        task_prompt = f"""
你是一个专业的视频发布助手。请帮我发布视频到抖音。

视频信息：
- 视频路径: {video_path}
- 标题: 测试视频 - GLM 5 驱动发布
- 描述: 这是使用 GLM 5 模型通过 MCP 工具自动发布的测试视频

请调用 publish_video 工具来完成发布任务。必须调用工具，不能只回复文字。
"""
        
        messages = [
            {
                "role": "system",
                "content": "你是一个专业的视频发布助手，可以通过调用 MCP 工具发布视频到抖音。你必须调用工具来完成任务，不能只回复文字。"
            },
            {
                "role": "user",
                "content": task_prompt
            }
        ]
        
        logger.info("\n[测试] 调用 GLM 5...")
        logger.info(f"[测试] 任务: 发布视频 {video_path.name}")
        
        # 调用 GLM 5（先不使用 tool_choice="required"，看看 GLM 5 是否支持）
        logger.info("[测试] 第一次调用 GLM 5（tool_choice=auto）...")
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=mcp_tools,
            tool_choice="auto",  # 让 GLM 5 自主决定
            temperature=0.1
        )
        
        # 如果第一次没有返回工具调用，强制要求
        if not hasattr(response, 'choices') or len(response.choices) == 0 or not hasattr(response.choices[0].message, 'tool_calls') or not response.choices[0].message.tool_calls:
            logger.warning("[测试] 第一次调用没有返回工具调用，尝试强制要求...")
            messages.append({
                "role": "assistant",
                "content": response.choices[0].message.content if hasattr(response, 'choices') and len(response.choices) > 0 else ""
            })
            messages.append({
                "role": "user",
                "content": "你必须调用 publish_video 工具来发布视频，不能只回复文字。请立即调用工具。"
            })
            
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=mcp_tools,
                tool_choice="auto",
                temperature=0.1
            )
        
        # 处理响应
        logger.info(f"\n[测试] 响应对象: {type(response)}")
        logger.info(f"[测试] 响应 ID: {response.id}")
        logger.info(f"[测试] 响应模型: {response.model}")
        
        if not hasattr(response, 'choices') or len(response.choices) == 0:
            logger.error(f"[测试] ❌ 响应中没有 choices，完整响应: {response}")
            return
        
        message = response.choices[0].message
        assistant_message = message.content or ""
        tool_calls = []
        
        if hasattr(message, 'tool_calls') and message.tool_calls:
            for tool_call in message.tool_calls:
                tool_calls.append({
                    "id": tool_call.id,
                    "name": tool_call.function.name,
                    "arguments": tool_call.function.arguments
                })
        
        logger.info(f"\n[测试] GLM 5 响应: {assistant_message[:100] if assistant_message else '无文字响应'}...")
        logger.info(f"[测试] GLM 5 返回了 {len(tool_calls)} 个工具调用")
        
        if not tool_calls:
            logger.error("[测试] ❌ GLM 5 没有返回工具调用！")
            logger.error("[测试] 尝试强制要求 GLM 5 调用工具...")
            
            # 再次强制要求
            messages.append({
                "role": "assistant",
                "content": assistant_message or "收到任务"
            })
            messages.append({
                "role": "user",
                "content": "你必须立即调用 publish_video 工具来发布视频，不能只回复文字。这是必须的。"
            })
            
            response2 = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=mcp_tools,
                tool_choice="auto",
                temperature=0.1
            )
            
            if hasattr(response2, 'choices') and len(response2.choices) > 0:
                message2 = response2.choices[0].message
                if hasattr(message2, 'tool_calls') and message2.tool_calls:
                    for tool_call in message2.tool_calls:
                        tool_calls.append({
                            "id": tool_call.id,
                            "name": tool_call.function.name,
                            "arguments": tool_call.function.arguments
                        })
                    logger.info(f"[测试] 第二次调用后，工具调用数量: {len(tool_calls)}")
            
            if not tool_calls:
                logger.error("[测试] ❌ GLM 5 仍然没有返回工具调用！")
                logger.error("[测试] 可能需要检查工具定义或 API 配置")
                return
        
        # 执行工具调用
        logger.info("\n[测试] ========== 执行 MCP 工具调用 ==========")
        for i, tool_call in enumerate(tool_calls):
            logger.info(f"[测试] 工具 {i+1}: {tool_call['name']}")
            logger.info(f"[测试] 参数: {tool_call['arguments']}")
            
            # 解析参数
            try:
                args = json.loads(tool_call['arguments'])
            except:
                logger.error("[测试] 参数解析失败")
                continue
            
            # 调用实际的 MCP 工具
            if tool_call['name'] == 'publish_video':
                logger.info("[测试] 正在调用 publish_video 工具...")
                
                # 导入 MCP 模块并调用原始实现函数
                import douyin_publish_mcp
                
                try:
                    # 调用原始实现函数（不通过 MCP 装饰器）
                    result = await douyin_publish_mcp._publish_video_impl(
                        video_path=args.get('video_path'),
                        title=args.get('title'),
                        description=args.get('description'),
                        cover_path=args.get('cover_path')
                    )
                    logger.info(f"[测试] ✅ 工具执行结果: {result}")
                except Exception as e:
                    logger.error(f"[测试] ❌ 工具执行失败: {e}")
                    import traceback
                    traceback.print_exc()
            
            elif tool_call['name'] == 'check_browser_status':
                logger.info("[测试] 正在调用 check_browser_status 工具...")
                import douyin_publish_mcp
                try:
                    result = await douyin_publish_mcp._check_browser_status_impl()
                    logger.info(f"[测试] ✅ 浏览器状态: {result}")
                except Exception as e:
                    logger.error(f"[测试] ❌ 检查状态失败: {e}")
        
        logger.info("\n[测试] ========== 测试完成 ==========")
        logger.info("[测试] 请检查浏览器窗口，确认是否已发布成功")
        logger.info("[提示] 浏览器将保持打开10秒...")
        await asyncio.sleep(10)
        
    except Exception as e:
        logger.error(f"[测试] 错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_glm5_mcp())

