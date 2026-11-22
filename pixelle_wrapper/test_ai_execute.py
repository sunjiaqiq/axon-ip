"""
测试 AI 执行任务 - 确保 AI 能正确调用工具并执行
"""
import asyncio
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

async def test_ai_execute():
    """测试 AI 执行任务"""
    from ai_pipeline.ai_agent import DouyinPublishAgent
    from ai_pipeline.browser_manager import browser_manager
    
    try:
        logger.info("=" * 70)
        logger.info("测试 AI 执行任务")
        logger.info("=" * 70)
        
        # 1. 初始化浏览器
        await browser_manager.ensure_initialized()
        context = await browser_manager.get_page()
        page = await context.new_page()
        
        logger.info("[测试] 浏览器已启动，当前页面: about:blank")
        
        # 2. 创建 AI Agent
        agent = DouyinPublishAgent()
        logger.info(f"[测试] AI Agent 已创建，模型: {agent.model}")
        
        # 3. 给 AI 下任务：导航到百度
        logger.info("\n[测试] 给 AI 下任务：导航到百度...")
        
        task_prompt = """
你是一个浏览器自动化助手。请执行以下任务：
1. 调用 navigate_to_page 工具，导航到 https://www.baidu.com
2. 等待页面加载完成
"""
        
        messages = [
            {
                "role": "system",
                "content": "你是一个专业的浏览器自动化助手，必须通过调用工具来完成任务。不要只回复文字，必须调用工具。"
            },
            {
                "role": "user",
                "content": task_prompt
            }
        ]
        
        # 强制要求 AI 调用工具
        logger.info("[测试] 调用 AI（强制要求调用工具）...")
        response = agent.client.chat.completions.create(
            model=agent.model,
            messages=messages,
            tools=agent.mcp_tools.get_tools(),
            tool_choice="required",  # 强制要求调用工具
            temperature=0.1
        )
        
        assistant_message = response.choices[0].message.content or ""
        tool_calls = []
        
        if response.choices[0].message.tool_calls:
            for tool_call in response.choices[0].message.tool_calls:
                tool_calls.append({
                    "id": tool_call.id,
                    "name": tool_call.function.name,
                    "arguments": tool_call.function.arguments
                })
        
        logger.info(f"[测试] AI 响应: {assistant_message[:100] if assistant_message else '无响应'}...")
        logger.info(f"[测试] AI 返回了 {len(tool_calls)} 个工具调用")
        
        if not tool_calls:
            logger.error("[失败] AI 没有返回工具调用！")
            return
        
        # 4. 执行工具调用
        logger.info("\n[测试] 执行工具调用...")
        for i, tool_call in enumerate(tool_calls):
            logger.info(f"[测试] 工具 {i+1}: {tool_call['name']}")
            logger.info(f"[测试] 参数: {tool_call['arguments']}")
            
            try:
                result = await agent._execute_tool(page, tool_call)
                logger.info(f"[测试] 执行结果: {result}")
                
                if result.get('success'):
                    logger.info(f"[成功] 工具 {tool_call['name']} 执行成功！")
                else:
                    logger.warning(f"[警告] 工具执行失败: {result.get('error')}")
            except Exception as e:
                logger.error(f"[错误] 工具执行异常: {e}")
                import traceback
                traceback.print_exc()
        
        # 5. 检查页面状态
        current_url = page.url
        logger.info(f"\n[测试] 当前页面 URL: {current_url}")
        
        if 'baidu.com' in current_url:
            logger.info("[成功] 页面已成功导航到百度！")
        else:
            logger.warning(f"[警告] 页面未导航到百度，当前: {current_url}")
        
        logger.info("\n[测试] 请检查浏览器窗口，确认页面是否已导航")
        logger.info("[提示] 浏览器将保持打开10秒...")
        await asyncio.sleep(10)
        
    except Exception as e:
        logger.error(f"[测试] 错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_ai_execute())





