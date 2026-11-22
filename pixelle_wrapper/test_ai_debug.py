"""
调试 AI 工具调用 - 查看 AI 到底返回了什么
"""
import asyncio
import logging
import json
from ai_pipeline.ai_agent import DouyinPublishAgent
from ai_pipeline.browser_manager import browser_manager

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

async def test_ai_debug():
    """调试 AI 工具调用"""
    try:
        logger.info("=" * 70)
        logger.info("调试 AI 工具调用")
        logger.info("=" * 70)
        
        # 1. 初始化浏览器
        await browser_manager.ensure_initialized()
        context = await browser_manager.get_page()
        page = await context.new_page()
        
        logger.info("[调试] 浏览器已启动")
        
        # 2. 创建 AI Agent
        agent = DouyinPublishAgent()
        logger.info(f"[调试] AI Agent 已创建")
        
        # 3. 查看工具定义
        tools = agent.mcp_tools.get_tools()
        logger.info(f"[调试] 可用工具数量: {len(tools)}")
        for i, tool in enumerate(tools):
            logger.info(f"[调试] 工具 {i+1}: {tool['function']['name']}")
            logger.info(f"[调试]   描述: {tool['function']['description']}")
        
        # 4. 给 AI 下任务
        logger.info("\n[调试] 给 AI 下任务...")
        task_prompt = """
你是一个浏览器自动化助手。请调用 navigate_to_page 工具，导航到 https://www.baidu.com
你必须调用工具，不能只回复文字。
"""
        
        messages = [
            {
                "role": "system",
                "content": "你是一个专业的浏览器自动化助手，必须通过调用Playwright工具操作浏览器。"
            },
            {
                "role": "user",
                "content": task_prompt
            }
        ]
        
        # 调用 AI
        logger.info("[调试] 正在调用 AI...")
        response = agent.client.chat.completions.create(
            model=agent.model,
            messages=messages,
            tools=tools,
            tool_choice="required",  # 强制要求调用工具
            temperature=0.1
        )
        
        # 详细输出 AI 响应
        logger.info("\n[调试] ========== AI 响应详情 ==========")
        logger.info(f"[调试] 响应 ID: {response.id}")
        logger.info(f"[调试] 模型: {response.model}")
        logger.info(f"[调试] 创建时间: {response.created}")
        
        message = response.choices[0].message
        logger.info(f"[调试] 角色: {message.role}")
        logger.info(f"[调试] 内容: {message.content}")
        logger.info(f"[调试] 工具调用数量: {len(message.tool_calls) if message.tool_calls else 0}")
        
        if message.tool_calls:
            logger.info("\n[调试] ========== 工具调用详情 ==========")
            for i, tool_call in enumerate(message.tool_calls):
                logger.info(f"[调试] 工具调用 {i+1}:")
                logger.info(f"[调试]   ID: {tool_call.id}")
                logger.info(f"[调试]   类型: {tool_call.type}")
                logger.info(f"[调试]   函数名: {tool_call.function.name}")
                logger.info(f"[调试]   参数: {tool_call.function.arguments}")
                
                # 解析参数
                try:
                    args = json.loads(tool_call.function.arguments)
                    logger.info(f"[调试]   解析后的参数: {args}")
                except:
                    logger.warning(f"[调试]   参数解析失败")
        else:
            logger.error("[调试] ❌ AI 没有返回工具调用！")
            logger.error(f"[调试] AI 只返回了文字: {message.content}")
        
        # 5. 执行工具调用
        if message.tool_calls:
            logger.info("\n[调试] ========== 执行工具调用 ==========")
            for i, tool_call in enumerate(message.tool_calls):
                tool_call_dict = {
                    "id": tool_call.id,
                    "name": tool_call.function.name,
                    "arguments": tool_call.function.arguments
                }
                
                logger.info(f"[调试] 执行工具 {i+1}: {tool_call_dict['name']}")
                try:
                    result = await agent._execute_tool(page, tool_call_dict)
                    logger.info(f"[调试] 执行结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
                except Exception as e:
                    logger.error(f"[调试] 执行失败: {e}")
                    import traceback
                    traceback.print_exc()
        else:
            logger.error("[调试] ❌ 没有工具调用可执行！")
        
        # 6. 检查页面状态
        current_url = page.url
        logger.info(f"\n[调试] 当前页面 URL: {current_url}")
        
        logger.info("\n[调试] 请检查浏览器窗口...")
        await asyncio.sleep(5)
        
    except Exception as e:
        logger.error(f"[调试] 错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_ai_debug())





