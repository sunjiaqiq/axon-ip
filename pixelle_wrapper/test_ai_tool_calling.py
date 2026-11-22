"""
测试 AI 工具调用功能
"""
import asyncio
import logging
from ai_pipeline.ai_agent import DouyinPublishAgent

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

async def test_tool_calling():
    """测试 AI 工具调用"""
    try:
        # 创建 AI Agent
        agent = DouyinPublishAgent()
        logger.info(f"[测试] 使用模型: {agent.model}")
        logger.info(f"[测试] API Base: {agent.api_base}")
        
        # 测试简单的工具调用任务
        test_prompt = """
你是一个浏览器自动化助手。请调用 navigate_to_page 工具，导航到 https://www.baidu.com
"""
        
        messages = [
            {
                "role": "system",
                "content": "你是一个专业的浏览器自动化助手，可以通过调用Playwright工具操作浏览器。"
            },
            {
                "role": "user",
                "content": test_prompt
            }
        ]
        
        logger.info("[测试] 开始调用 AI...")
        response = agent.client.chat.completions.create(
            model=agent.model,
            messages=messages,
            tools=agent.mcp_tools.get_tools(),
            tool_choice="auto",
            temperature=0.1
        )
        
        logger.info(f"[测试] AI 响应: {response.choices[0].message.content}")
        
        if response.choices[0].message.tool_calls:
            logger.info(f"[测试] AI 返回了 {len(response.choices[0].message.tool_calls)} 个工具调用")
            for i, tool_call in enumerate(response.choices[0].message.tool_calls):
                logger.info(f"[测试] 工具 {i+1}: {tool_call.function.name}")
                logger.info(f"[测试] 参数: {tool_call.function.arguments}")
        else:
            logger.warning("[测试] AI 没有返回工具调用")
            
    except Exception as e:
        logger.error(f"[测试] 错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_tool_calling())





