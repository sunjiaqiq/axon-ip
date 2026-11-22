"""
测试完整的 AI 驱动发布流程
确保使用指定的浏览器 Profile 3
"""
import asyncio
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

async def test_ai_full_flow():
    """测试完整的 AI 驱动流程"""
    from ai_pipeline.ai_agent import DouyinPublishAgent
    from ai_pipeline.browser_manager import browser_manager
    
    try:
        # 1. 确保浏览器使用指定的 Profile 3
        logger.info("=" * 70)
        logger.info("测试 AI 驱动发布流程")
        logger.info("=" * 70)
        logger.info("确保使用指定的浏览器 Profile 3")
        
        # 2. 创建 AI Agent
        agent = DouyinPublishAgent()
        logger.info(f"[AI Agent] 使用模型: {agent.model}")
        logger.info(f"[AI Agent] API Base: {agent.api_base}")
        
        # 3. 初始化浏览器（使用 Profile 3）
        await browser_manager.ensure_initialized()
        context = await browser_manager.get_page()
        page = await context.new_page()
        
        logger.info("[测试] 浏览器已启动，检查自动化标识...")
        
        # 4. 导航到测试页面，检查是否还有自动化标识
        await page.goto("https://bot.sannysoft.com/", wait_until='domcontentloaded')
        await asyncio.sleep(2)
        
        # 检查 webdriver 属性
        webdriver_detected = await page.evaluate("""
            () => {
                return {
                    navigator_webdriver: navigator.webdriver,
                    window_chrome: typeof window.chrome !== 'undefined',
                    document_webdriver: document.documentElement.getAttribute('webdriver')
                };
            }
        """)
        
        logger.info(f"[测试] 自动化检测结果: {webdriver_detected}")
        
        if webdriver_detected.get('navigator_webdriver'):
            logger.warning("[警告] navigator.webdriver 仍然存在！")
        else:
            logger.info("[成功] navigator.webdriver 已隐藏")
        
        # 5. 测试 AI 工具调用
        logger.info("\n[测试] 测试 AI 工具调用...")
        
        test_prompt = """
你是一个浏览器自动化助手。请执行以下任务：
1. 调用 navigate_to_page 工具，导航到 https://www.baidu.com
2. 等待页面加载完成
3. 检查页面状态
"""
        
        messages = [
            {
                "role": "system",
                "content": "你是一个专业的浏览器自动化助手，可以通过调用Playwright工具操作浏览器。严格按照用户提供的流程执行任务。"
            },
            {
                "role": "user",
                "content": test_prompt
            }
        ]
        
        logger.info("[测试] 调用 AI...")
        response = agent.client.chat.completions.create(
            model=agent.model,
            messages=messages,
            tools=agent.mcp_tools.get_tools(),
            tool_choice="auto",
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
        
        # 6. 执行工具调用
        for i, tool_call in enumerate(tool_calls):
            logger.info(f"[测试] 执行工具 {i+1}: {tool_call['name']}")
            logger.info(f"[测试] 参数: {tool_call['arguments']}")
            
            result = await agent._execute_tool(page, tool_call)
            logger.info(f"[测试] 工具执行结果: {result}")
        
        logger.info("\n[测试] 测试完成！")
        logger.info("请检查浏览器窗口，确认是否还有'正受到自动测试软件控制'的提示")
        
        # 保持浏览器打开，让用户检查
        logger.info("\n[提示] 浏览器将保持打开状态，请检查...")
        await asyncio.sleep(10)
        
    except Exception as e:
        logger.error(f"[测试] 错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_ai_full_flow())





