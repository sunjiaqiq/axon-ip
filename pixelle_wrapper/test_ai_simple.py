"""
简单测试：检查浏览器是否还有自动化标识，并测试AI工具调用
"""
import asyncio
import logging
from ai_pipeline.browser_manager import browser_manager
from ai_pipeline.ai_agent import DouyinPublishAgent

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

async def test():
    try:
        logger.info("=" * 70)
        logger.info("测试：检查自动化标识 + AI工具调用")
        logger.info("=" * 70)
        
        # 1. 启动浏览器
        await browser_manager.ensure_initialized()
        context = await browser_manager.get_page()
        page = await context.new_page()
        
        logger.info("[测试] 浏览器已启动")
        
        # 2. 导航到检测页面
        await page.goto("https://bot.sannysoft.com/", wait_until='domcontentloaded')
        await asyncio.sleep(3)
        
        # 3. 检查自动化标识
        detection_result = await page.evaluate("""
            () => {
                return {
                    webdriver: navigator.webdriver,
                    chrome: typeof window.chrome !== 'undefined',
                    automation: document.documentElement.getAttribute('webdriver'),
                    userAgent: navigator.userAgent.includes('HeadlessChrome')
                };
            }
        """)
        
        logger.info(f"[测试] 自动化检测结果: {detection_result}")
        
        if detection_result.get('webdriver'):
            logger.error("[失败] navigator.webdriver 仍然存在！")
        else:
            logger.info("[成功] navigator.webdriver 已隐藏")
        
        # 4. 测试AI工具调用
        logger.info("\n[测试] 测试AI工具调用...")
        agent = DouyinPublishAgent()
        
        test_prompt = "请调用 navigate_to_page 工具，导航到 https://www.baidu.com"
        
        messages = [
            {
                "role": "system",
                "content": "你是一个浏览器自动化助手，必须调用工具完成任务。"
            },
            {
                "role": "user",
                "content": test_prompt
            }
        ]
        
        response = agent.client.chat.completions.create(
            model=agent.model,
            messages=messages,
            tools=agent.mcp_tools.get_tools(),
            tool_choice="required",  # 强制要求调用工具
            temperature=0.1
        )
        
        tool_calls = []
        if response.choices[0].message.tool_calls:
            for tool_call in response.choices[0].message.tool_calls:
                tool_calls.append({
                    "id": tool_call.id,
                    "name": tool_call.function.name,
                    "arguments": tool_call.function.arguments
                })
        
        logger.info(f"[测试] AI返回了 {len(tool_calls)} 个工具调用")
        
        if tool_calls:
            logger.info(f"[测试] 工具名称: {tool_calls[0]['name']}")
            logger.info(f"[测试] 工具参数: {tool_calls[0]['arguments']}")
            
            # 执行工具
            result = await agent._execute_tool(page, tool_calls[0])
            logger.info(f"[测试] 工具执行结果: {result}")
        else:
            logger.error("[失败] AI没有返回工具调用")
        
        logger.info("\n[测试] 请检查浏览器窗口，确认是否还有'正受到自动测试软件控制'的提示")
        logger.info("[提示] 浏览器将保持打开10秒...")
        await asyncio.sleep(10)
        
    except Exception as e:
        logger.error(f"[测试] 错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())





