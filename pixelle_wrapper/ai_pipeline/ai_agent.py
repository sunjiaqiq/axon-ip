"""
AI Agent - 使用 GLM 5 驱动浏览器自动化
通过 MCP (Model Context Protocol) 调用 Playwright 工具
"""
import logging
import json
from typing import Dict, Any, Optional, List
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logger.warning("openai 库未安装，请安装: pip install openai")


class PlaywrightMCPTools:
    """Playwright MCP 工具集 - 封装浏览器操作"""
    
    def __init__(self):
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "navigate_to_page",
                    "description": "导航到指定URL",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "要访问的URL"
                            }
                        },
                        "required": ["url"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "click_element",
                    "description": "点击页面元素",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "selector": {
                                "type": "string",
                                "description": "CSS选择器或文本内容"
                            },
                            "text": {
                                "type": "string",
                                "description": "元素文本（如果使用文本定位）"
                            }
                        },
                        "required": ["selector"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "fill_input",
                    "description": "填写输入框",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "selector": {
                                "type": "string",
                                "description": "输入框的CSS选择器"
                            },
                            "text": {
                                "type": "string",
                                "description": "要填写的文本内容"
                            }
                        },
                        "required": ["selector", "text"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "upload_file",
                    "description": "上传文件",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "selector": {
                                "type": "string",
                                "description": "文件输入框的CSS选择器"
                            },
                            "file_path": {
                                "type": "string",
                                "description": "文件路径"
                            }
                        },
                        "required": ["selector", "file_path"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "wait_for_element",
                    "description": "等待元素出现",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "selector": {
                                "type": "string",
                                "description": "要等待的元素选择器"
                            },
                            "timeout": {
                                "type": "number",
                                "description": "超时时间（秒），默认10秒"
                            }
                        },
                        "required": ["selector"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "check_page_state",
                    "description": "检查页面状态（URL变化、元素存在等）",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "check_type": {
                                "type": "string",
                                "enum": ["url", "element", "text"],
                                "description": "检查类型：url变化、元素存在、文本内容"
                            },
                            "value": {
                                "type": "string",
                                "description": "要检查的值（URL、选择器或文本）"
                            }
                        },
                        "required": ["check_type", "value"]
                    }
                }
            }
        ]
    
    def get_tools(self) -> List[Dict]:
        """获取所有工具定义"""
        return self.tools


class DouyinPublishAgent:
    """抖音发布 AI Agent - 使用 GLM 5 驱动"""
    
    def __init__(self, api_key: Optional[str] = None, api_base: Optional[str] = None):
        """
        初始化 AI Agent
        
        Args:
            api_key: 硅基流动 API Key
            api_base: API 基础URL（硅基流动）
        """
        if not OPENAI_AVAILABLE:
            raise ImportError("需要安装 openai 库: pip install openai")
        
        # 从配置文件读取 API Key（优先读取 siliconflow 配置）
        if not api_key:
            try:
                import yaml
                config_path = Path(__file__).parent.parent / "config.yaml"
                if config_path.exists():
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config = yaml.safe_load(f)
                        # 优先读取 siliconflow 配置
                        if config and 'siliconflow' in config:
                            api_key = config['siliconflow'].get('api_key')
                            api_base = config['siliconflow'].get('api_base', api_base)
                            self.model = config['siliconflow'].get('model', 'zai-org/GLM-5.3')
                        # 如果没有 siliconflow 配置，使用 llm 配置
                        elif config and 'llm' in config:
                            api_key = config['llm'].get('api_key')
                            api_base = config['llm'].get('base_url', api_base)
                            self.model = "zai-org/GLM-5.3"
            except Exception as e:
                logger.warning(f"读取配置文件失败: {e}")
        
        if not api_key:
            raise ValueError("需要提供 API Key（通过参数或 config.yaml 中的 siliconflow.api_key）")
        
        # 硅基流动最新 GLM 配置
        self.api_key = api_key
        self.api_base = api_base or "https://api.siliconflow.cn/v1"
        if not hasattr(self, 'model'):
            self.model = "zai-org/GLM-5.3"
        
        # 初始化 OpenAI 客户端（兼容硅基流动）
        self.client = openai.OpenAI(
            api_key=self.api_key,
            base_url=self.api_base
        )
        
        # Playwright 工具集
        self.mcp_tools = PlaywrightMCPTools()
        
        # 定制流程提示词
        self.custom_workflow = """
## 抖音发布定制流程（必须按顺序执行）：

1. **上传视频**
   - 导航到: https://creator.douyin.com/creator-micro/content/upload
   - 等待上传按钮出现
   - 上传视频文件

2. **选择封面**（必须按以下顺序）：
   - 步骤1: 点击"选择封面" (div.title-wA45Xd 或包含"选择封面"文本的元素)
   - 步骤2: 点击"标题" (div.icon-name-Fi8gxR 或包含"标题"文本的元素)
   - 步骤3: 点击canvas中间区域 (canvas.cloudImage-N0ai8Y 或 canvas.lower-canvas)
   - 步骤4: 上传封面文件 (input[type="file"]，选择接受图片的输入框)
   - 步骤5: 点击"确定"按钮 (button.button-dhlUZE.primary-cECiOJ.dialog-b5CBy1 或包含"确定"文本的按钮)
   - 步骤6: 点击"完成"按钮 (span.semi-button-content 或包含"完成"文本的元素)

3. **填写标题**
   - 找到标题输入框 (input[placeholder*="标题"] 或 textarea[placeholder*="标题"])
   - 填写标题文本

4. **填写描述**
   - 找到描述输入框 (textarea 或 contenteditable 元素，排除标题输入框)
   - 填写描述文本

5. **发布视频**
   - 点击发布按钮 (button:has-text("发布") 或 button:has-text("发布视频"))
   - 等待发布成功（检查URL变化或成功提示）

**重要提示：**
- 每个步骤之间需要等待页面加载（建议等待2-3秒）
- 如果元素找不到，尝试多种选择器
- 发布成功后，页面URL通常会变化或出现成功提示
"""
    
    async def execute_publish_task(
        self,
        video_path: str,
        title: str,
        description: str,
        cover_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        执行发布任务 - AI 驱动的流程
        
        Args:
            video_path: 视频文件路径
            title: 视频标题
            description: 视频描述
            cover_path: 封面图片路径（可选）
        
        Returns:
            执行结果
        """
        from ai_pipeline.browser_manager import browser_manager
        
        try:
            # 如果没有提供封面，从视频提取
            if not cover_path:
                logger.info("[AI Agent] 未提供封面，从视频提取...")
                from ai_pipeline.cover_extractor import extract_cover_from_video
                cover_path_obj = extract_cover_from_video(str(video_path), Path(video_path).parent)
                if cover_path_obj and cover_path_obj.exists():
                    cover_path = str(cover_path_obj)
                    logger.info(f"[AI Agent] 封面提取成功: {cover_path}")
                else:
                    logger.warning("[AI Agent] 封面提取失败，继续使用空封面")
            
            # 确保浏览器已初始化
            await browser_manager.ensure_initialized()
            context = await browser_manager.get_page()
            page = await context.new_page()
            
            # 保存 page 实例供工具调用使用
            self._current_page = page
            
            # 构建任务提示词
            task_prompt = f"""
你是一个专业的浏览器自动化助手。你的任务是：**发布视频到抖音**。

## 任务信息：
- 视频路径: {video_path}
- 标题: {title}
- 描述: {description}
- 封面路径: {cover_path or "从视频自动提取"}

{self.custom_workflow}

## 执行要求：
1. 严格按照上述流程顺序执行
2. 每个步骤执行后，等待页面响应（2-3秒）
3. 如果元素找不到，尝试多种选择器策略
4. 发布成功后，确认URL变化或成功提示
5. 如果遇到错误，描述具体问题

现在开始执行发布任务。请逐步调用工具完成整个流程。
"""
            
            # 调用 GLM 5 执行任务
            logger.info("[AI Agent] 开始AI驱动的发布任务...")
            logger.info(f"[AI Agent] 使用模型: {self.model}")
            
            messages = [
                {
                    "role": "system",
                    "content": "你是一个专业的浏览器自动化助手，可以通过调用Playwright工具操作浏览器。严格按照用户提供的流程执行任务。"
                },
                {
                    "role": "user",
                    "content": task_prompt
                }
            ]
            
            # 执行 AI 对话（强制要求调用工具，立即开始工作）
            logger.info("[AI Agent] 正在调用 AI，要求立即开始执行任务...")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=self.mcp_tools.get_tools(),
                tool_choice="required",  # 强制要求调用工具，立即开始工作
                temperature=0.1  # 降低随机性，确保流程稳定
            )
            logger.info("[AI Agent] AI 已响应，开始处理工具调用...")
            
            # 处理响应并提取工具调用
            assistant_message = response.choices[0].message.content or ""
            tool_calls = []
            
            if response.choices[0].message.tool_calls:
                for tool_call in response.choices[0].message.tool_calls:
                    tool_calls.append({
                        "id": tool_call.id,
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments
                    })
            
            logger.info(f"[AI Agent] AI响应: {assistant_message[:100] if assistant_message else '无响应'}...")
            logger.info(f"[AI Agent] 工具调用数量: {len(tool_calls)}")
            
            # 如果没有工具调用，强制让AI调用工具
            if not tool_calls:
                logger.warning("[AI Agent] AI没有返回工具调用，强制要求AI调用工具...")
                # 先导航到上传页面
                await page.goto("https://creator.douyin.com/creator-micro/content/upload", wait_until='domcontentloaded')
                logger.info("[AI Agent] 已导航到上传页面")
                
                # 强制要求AI调用工具
                force_tool_prompt = """
请立即调用 navigate_to_page 工具导航到抖音上传页面，然后开始执行发布任务。
你必须调用工具，不能只回复文字。
"""
                messages.append({
                    "role": "assistant",
                    "content": assistant_message or "收到任务"
                })
                messages.append({
                    "role": "user",
                    "content": force_tool_prompt
                })
                
                # 强制要求AI调用工具
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=self.mcp_tools.get_tools(),
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
                logger.info(f"[AI Agent] 强制调用后，工具调用数量: {len(tool_calls)}")
            
            # 执行工具调用（立即执行，不等待）
            if tool_calls:
                logger.info(f"[AI Agent] ✅ 开始执行 {len(tool_calls)} 个 Playwright MCP 工具调用...")
                tool_results = []
                for i, tool_call in enumerate(tool_calls):
                    logger.info(f"[AI Agent] 🔧 执行工具 {i+1}/{len(tool_calls)}: {tool_call['name']}")
                    logger.info(f"[AI Agent] 📋 工具参数: {tool_call['arguments']}")
                    try:
                        result = await self._execute_tool(page, tool_call)
                        logger.info(f"[AI Agent] ✅ 工具 {tool_call['name']} 执行结果: {result.get('success', False)}")
                        if result.get('success'):
                            logger.info(f"[AI Agent] 🎉 工具执行成功！")
                        else:
                            logger.warning(f"[AI Agent] ⚠️ 工具执行失败: {result.get('error', '未知错误')}")
                        tool_results.append({
                            "tool_call_id": tool_call["id"],
                            "role": "tool",
                            "name": tool_call["name"],
                            "content": json.dumps(result, ensure_ascii=False)
                        })
                    except Exception as e:
                        logger.error(f"[AI Agent] ❌ 工具执行异常: {e}")
                        import traceback
                        logger.error(traceback.format_exc())
                        tool_results.append({
                            "tool_call_id": tool_call["id"],
                            "role": "tool",
                            "name": tool_call["name"],
                            "content": json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
                        })
            else:
                logger.error("[AI Agent] ❌ 没有工具调用！AI 可能没有返回工具调用。")
                tool_results = []
            
            # 继续对话，让AI根据工具结果继续执行（多轮工具调用循环）
            max_iterations = 20  # 最多20轮工具调用
            iteration = 0
            
            while tool_results and iteration < max_iterations:
                iteration += 1
                logger.info(f"[AI Agent] 第 {iteration} 轮工具调用...")
                
                # 添加工具调用结果到消息
                messages.append({
                    "role": "assistant",
                    "content": assistant_message,
                    "tool_calls": tool_calls
                })
                messages.extend(tool_results)
                
                # 继续对话，让AI决定下一步
                next_response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=self.mcp_tools.get_tools(),
                    tool_choice="auto",
                    temperature=0.1
                )
                
                # 处理响应
                assistant_message = next_response.choices[0].message.content or ""
                tool_calls = []
                
                if next_response.choices[0].message.tool_calls:
                    for tool_call in next_response.choices[0].message.tool_calls:
                        tool_calls.append({
                            "id": tool_call.id,
                            "name": tool_call.function.name,
                            "arguments": tool_call.function.arguments
                        })
                
                logger.info(f"[AI Agent] 第 {iteration} 轮AI响应: {assistant_message[:100]}...")
                logger.info(f"[AI Agent] 第 {iteration} 轮工具调用数量: {len(tool_calls)}")
                
                # 如果没有更多工具调用，任务可能完成
                if not tool_calls:
                    logger.info("[AI Agent] 没有更多工具调用，任务可能完成")
                    break
                
                # 执行新的工具调用
                tool_results = []
                for tool_call in tool_calls:
                    try:
                        result = await self._execute_tool(page, tool_call)
                        tool_results.append({
                            "tool_call_id": tool_call["id"],
                            "role": "tool",
                            "name": tool_call["name"],
                            "content": json.dumps(result, ensure_ascii=False)
                        })
                        if result.get("success"):
                            logger.info(f"[AI Agent] 工具 {tool_call['name']} 执行成功")
                        else:
                            logger.warning(f"[AI Agent] 工具 {tool_call['name']} 执行失败: {result.get('error')}")
                    except Exception as e:
                        logger.error(f"[AI Agent] 工具执行异常: {e}")
                        import traceback
                        logger.error(traceback.format_exc())
                        tool_results.append({
                            "tool_call_id": tool_call["id"],
                            "role": "tool",
                            "name": tool_call["name"],
                            "content": json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
                        })
            
            if iteration >= max_iterations:
                logger.warning("[AI Agent] 达到最大迭代次数，任务可能未完成")
            
            # 检查最终状态（URL变化或成功提示）
            final_url = page.url
            logger.info(f"[AI Agent] 最终URL: {final_url}")
            
            # 判断是否发布成功
            publish_success = False
            if 'post' in final_url.lower() or 'success' in final_url.lower() or 'content' in final_url.lower():
                publish_success = True
                logger.info("[AI Agent] 根据URL判断，发布成功！")
            
            return {
                "success": publish_success,
                "message": "AI驱动的发布任务执行完成" if publish_success else "任务执行完成，但无法确认是否发布成功",
                "tool_calls": iteration,
                "final_url": final_url,
                "assistant_message": assistant_message
            }
            
        except Exception as e:
            logger.error(f"[AI Agent] 执行任务失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _execute_tool(self, page, tool_call: Dict) -> Dict[str, Any]:
        """执行单个工具调用"""
        from playwright.async_api import Page
        
        tool_name = tool_call["name"]
        try:
            arguments = json.loads(tool_call["arguments"])
        except:
            arguments = {}
        
        logger.info(f"[AI Agent] 执行工具: {tool_name}")
        logger.info(f"[AI Agent] 工具参数: {arguments}")
        
        if tool_name == "navigate_to_page":
            url = arguments.get("url")
            await page.goto(url, wait_until='domcontentloaded')
            return {"success": True, "url": page.url}
        
        elif tool_name == "click_element":
            selector = arguments.get("selector")
            text = arguments.get("text")
            
            # 尝试多种方式定位元素
            element = None
            
            if text:
                # 方法1: 使用文本定位
                try:
                    element = await page.get_by_text(text).first
                    if element:
                        is_visible = await element.is_visible()
                        if not is_visible:
                            element = None
                except:
                    pass
            
            if not element and selector:
                # 方法2: 使用选择器
                try:
                    element = await page.query_selector(selector)
                    if element:
                        is_visible = await element.is_visible()
                        if not is_visible:
                            element = None
                except:
                    pass
            
            if element:
                await element.scroll_into_view_if_needed()
                await page.wait_for_timeout(500)
                await element.click()
                await page.wait_for_timeout(2000)  # 等待页面响应
                return {"success": True, "clicked": selector or text, "message": "元素点击成功"}
            else:
                return {"success": False, "error": f"元素未找到: {selector or text}", "suggestion": "请检查选择器或文本是否正确"}
        
        elif tool_name == "fill_input":
            selector = arguments.get("selector")
            text = arguments.get("text")
            
            element = await page.query_selector(selector)
            if element:
                await element.fill(text)
                await page.wait_for_timeout(500)
                return {"success": True, "filled": text}
            else:
                return {"success": False, "error": f"输入框未找到: {selector}"}
        
        elif tool_name == "upload_file":
            selector = arguments.get("selector")
            file_path = arguments.get("file_path")
            
            # 检查文件是否存在
            file_path_obj = Path(file_path)
            if not file_path_obj.exists():
                return {"success": False, "error": f"文件不存在: {file_path}"}
            
            # 查找文件输入框（可能多个，需要选择正确的）
            if selector:
                element = await page.query_selector(selector)
            else:
                # 如果没有指定选择器，查找所有文件输入框
                file_inputs = await page.query_selector_all('input[type="file"]')
                if file_inputs:
                    # 根据 accept 属性选择（图片或视频）
                    for file_input in file_inputs:
                        accept = await file_input.get_attribute('accept') or ''
                        if 'image' in accept and file_path_obj.suffix.lower() in ['.jpg', '.jpeg', '.png']:
                            element = file_input
                            break
                        elif 'video' in accept and file_path_obj.suffix.lower() in ['.mp4', '.mov', '.avi']:
                            element = file_input
                            break
                    # 如果没找到匹配的，使用第一个
                    if not element and file_inputs:
                        element = file_inputs[0]
            
            if element:
                await element.set_input_files(str(file_path_obj))
                await page.wait_for_timeout(2000)
                return {"success": True, "uploaded": file_path, "message": "文件上传成功"}
            else:
                return {"success": False, "error": f"文件输入框未找到: {selector}", "suggestion": "请检查页面是否已加载完成"}
        
        elif tool_name == "wait_for_element":
            selector = arguments.get("selector")
            timeout = arguments.get("timeout", 10) * 1000
            
            try:
                await page.wait_for_selector(selector, timeout=timeout)
                return {"success": True, "element_found": selector}
            except:
                return {"success": False, "error": f"元素未出现: {selector}"}
        
        elif tool_name == "check_page_state":
            check_type = arguments.get("check_type")
            value = arguments.get("value")
            
            if check_type == "url":
                current_url = page.url
                return {"success": True, "current_url": current_url, "matches": value in current_url}
            elif check_type == "element":
                element = await page.query_selector(value)
                return {"success": True, "element_exists": element is not None}
            elif check_type == "text":
                content = await page.content()
                return {"success": True, "text_found": value in content}
        
        return {"success": False, "error": f"未知工具: {tool_name}"}


async def publish_with_ai_agent(
    video_path: str,
    title: str,
    description: str,
    cover_path: Optional[str] = None,
    api_key: Optional[str] = None
) -> bool:
    """
    使用 AI Agent 发布视频到抖音
    
    Args:
        video_path: 视频文件路径
        title: 视频标题
        description: 视频描述
        cover_path: 封面图片路径（可选）
        api_key: 硅基流动 API Key（可选，从配置文件读取）
    
    Returns:
        是否发布成功
    """
    try:
        agent = DouyinPublishAgent(api_key=api_key)
        result = await agent.execute_publish_task(video_path, title, description, cover_path)
        return result.get("success", False)
    except Exception as e:
        logger.error(f"[AI Agent] 发布失败: {e}")
        return False

