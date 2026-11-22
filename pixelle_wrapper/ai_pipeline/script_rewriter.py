"""
文案改写模块 - 使用 GPT API 改写文案，避免重复，更加口语化
"""
import logging
import os
import json
import re
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def generate_douyin_content(script_text: str) -> Dict[str, str]:
    """
    根据文案生成抖音发布内容（封面内容、标题、描述）
    
    Args:
        script_text: 原始文案文本
        
    Returns:
        包含 cover_text, title, description 的字典
    """
    logger.info("[ScriptRewriter] 开始生成抖音发布内容")
    
    try:
        # 使用豆包API配置（和rewrite_script保持一致）
        api_url = os.getenv('AI_API_URL', 'https://ark.cn-beijing.volces.com/api/v3/chat/completions')
        api_key = os.getenv('AI_API_KEY', '5d24f49e-bec4-4af0-b527-015fef194fdb')
        
        if not api_key or requests is None:
            logger.warning("[ScriptRewriter] API密钥未设置或requests未安装，使用简单规则生成")
            return _generate_simple_douyin_content(script_text)
        
        # 构建提示词
        prompt = f"""根据以下口播文案，生成抖音发布所需的三个内容：

1. 封面内容（cover_text）：
   你是封面设计的专家，根据这个文案总结出5-8个字的简短内容放到封面上。
   要求：必须是5-8个字（不是词），要简短有力，吸引眼球，适合放在视频封面上。

2. 标题（title）：
   你是一个标题档的专家，根据这个内容生成一个标题，并且根据行业等信息，给出三个相应的话题（格式：#话题）。
   要求：字数不大于16个字，必须包含3个话题标签（格式：#话题），要吸引点击。

3. 描述（description）：
   总结这段文案，写出相应的描述文字。
   要求：字数不大于30字，要简洁有力。

口播文案：
{script_text}

请返回JSON格式：
{{
    "cover_text": "5-8个字的封面内容（例如：动嘴电脑就能干活）",
    "title": "标题内容（不大于16字，包含3个#话题，例如：动嘴提效 #科技 #电脑 #效率）",
    "description": "描述文字（不大于30字）"
}}

重要提醒：
- cover_text必须是5-8个字（不是词），例如"动嘴电脑就能干活"是7个字
- title必须包含3个话题标签（格式：#话题），总字数不超过16字
- description字数不超过30字
"""
        
        # 使用豆包模型配置（和rewrite_script保持一致）
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}'
        }
        
        data = {
            'model': 'doubao-seed-2-0-code-preview-260215',  # 使用豆包模型
            'messages': [
                {'role': 'system', 'content': '你是一个专业的抖音内容创作专家。'},
                {'role': 'user', 'content': prompt}
            ],
            'temperature': 0.7,
            'max_tokens': 500
        }
        
        logger.info(f"[ScriptRewriter] 调用AI API生成抖音内容: {api_url}")
        response = requests.post(api_url, headers=headers, json=data, timeout=60)
        
        if response.status_code != 200:
            logger.error(f"[ScriptRewriter] API调用失败: {response.status_code} - {response.text}")
            return _generate_simple_douyin_content(script_text)
        
        # 解析响应
        result_data = response.json()
        content = result_data.get('choices', [{}])[0].get('message', {}).get('content', '')
        logger.info(f"[ScriptRewriter] AI响应: {content[:200]}...")
        
        # 尝试解析JSON
        try:
            # 提取JSON部分（支持多行JSON）
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                content_dict = json.loads(json_match.group())
                result = {
                    'cover_text': content_dict.get('cover_text', '').strip(),
                    'title': content_dict.get('title', '').strip(),
                    'description': content_dict.get('description', '').strip()
                }
                logger.info(f"[ScriptRewriter] 解析成功: {result}")
                return result
        except json.JSONDecodeError as e:
            logger.warning(f"[ScriptRewriter] JSON解析失败: {e}")
        
        # 如果解析失败，使用简单规则
        logger.warning("[ScriptRewriter] AI响应解析失败，使用简单规则生成")
        return _generate_simple_douyin_content(script_text)
        
    except Exception as e:
        logger.error(f"[ScriptRewriter] 生成抖音内容失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return _generate_simple_douyin_content(script_text)


def _generate_simple_douyin_content(script_text: str) -> Dict[str, str]:
    """简单规则生成抖音内容（备用方案）"""
    # 封面内容：取前4-8个字
    cover_text = script_text[:8].strip() if len(script_text) >= 8 else script_text.strip()
    
    # 标题：取前15个字 + 话题
    title_base = script_text[:15].strip() if len(script_text) >= 15 else script_text.strip()
    topics = ["#热门话题", "#生活分享", "#知识科普"]
    title = f"{title_base} {''.join(topics)}"
    
    # 描述：取前20个字
    description = script_text[:20].strip() if len(script_text) >= 20 else script_text.strip()
    
    return {
        'cover_text': cover_text,
        'title': title,
        'description': description
    }

try:
    import requests
except ImportError:
    logger.warning("requests 未安装，将使用模拟改写")
    requests = None


def rewrite_script(script: Dict[str, str], api_key: Optional[str] = None, api_url: Optional[str] = None, persona_config: Optional[Dict[str, str]] = None, optimize: bool = False) -> Dict[str, str]:
    """
    改写文案，避免重复，更加口语化，根据人设配置个性化改写
    
    Args:
        script: 原始文案字典（包含 hook, problem, solution, cta）
        api_key: API密钥，如果为None则使用默认密钥
        api_url: API地址，如果为None则使用默认地址
        persona_config: 人设配置字典（可选）
        
    Returns:
        改写后的文案字典
    """
    logger.info("[ScriptRewriter] 开始改写文案")
    
    try:
        # 使用默认API配置（豆包模型）
        if api_url is None:
            # 豆包API地址（火山引擎）
            api_url = os.getenv('AI_API_URL', 'https://ark.cn-beijing.volces.com/api/v3/chat/completions')
        if api_key is None:
            api_key = os.getenv('AI_API_KEY', '5d24f49e-bec4-4af0-b527-015fef194fdb')
        
        if not api_key or requests is None:
            logger.warning("[ScriptRewriter] API密钥未设置或requests未安装，使用模拟改写")
            return _mock_rewrite(script)
        
        # 构建提示词
        persona_info = ""
        if persona_config:
            persona_info = f"""
人设配置信息（请根据以下信息个性化改写文案）：
- 公司/团队名字：{persona_config.get('companyName', '')}
- 目标客户群体：{persona_config.get('targetMarket', '')}
- 核心产品或服务解决的需求：{persona_config.get('coreSolution', '')}
- 公司产品年限：{persona_config.get('productYears', '')}
- 产品优势：{persona_config.get('productAdvantages', '')}
- 其他信息：{persona_config.get('other', '')}

请根据以上人设信息，将文案改写成符合该客户/公司特点的内容。
"""
        
        optimize_hint = ""
        if optimize:
            optimize_hint = "\n重要：这是继续优化请求，请生成一个与之前版本不同的新版本，使用不同的表达方式和结构，但保持核心内容不变。"
        
        # 计算原文案长度，用于字数控制
        original_script_text = script.get('full_script', '')
        original_length = len(original_script_text) if original_script_text else 0
        
        # 根据原文案长度确定目标字数范围
        # 如果原文案较长（>800字），改写后控制在300-500字（约1分钟左右口播，上限500字）
        # 如果原文案较短（<800字），改写后控制在原文案的70%-100%之间
        if original_length > 800:
            target_min = 300
            target_max = 500
            length_hint = f"原文案长度为{original_length}字，改写后的文案字数应控制在300-500字之间（约1分钟左右口播，最多500字）"
        elif original_length > 0:
            target_min = int(original_length * 0.7)
            target_max = original_length
            length_hint = f"原文案长度为{original_length}字，改写后的文案字数应控制在{target_min}-{target_max}字之间"
        else:
            target_min = 300
            target_max = 500
            length_hint = "改写后的文案字数应控制在300-500字之间"
        
        prompt = f"""你是一位资深的短视频文案创作专家，擅长将原始文案进行二创改写，生成符合短视频平台特点的爆款文案。

任务：根据原始文案的结构和框架，结合人设配置信息，进行二创改写。

核心要求：
1. 严格遵循原始文案的结构框架（钩子→问题→解决方案→行动号召），保持逻辑完整性，改写后的结构要与原文案结构基本一致
2. 字数控制：{length_hint}。必须保留原文案的核心内容和关键信息，不能过度简化。
3. 根据人设配置信息，将文案改写成符合该客户/公司特点的内容
4. 语言风格：口语化、自然流畅，像朋友聊天一样亲切
5. 避免重复用词，使用多样化的表达方式
6. 开头钩子必须在3秒内抓住注意力
7. 禁止使用特殊符号，包括但不限于：星号*、井号#、下划线_、方括号[]、花括号{{}}等
8. 必须使用正常的标点符号：逗号、句号、问号、感叹号、引号、冒号、分号等，确保口播时能正确断句
9. 自动纠正明显的错别字、常见语病与标点错误（不改变原意，不改专有名词/品牌名）
10. 禁止用空格代替标点来分句或制造停顿；句内停顿必须用中文标点（如「，」「、」），句末用「。」「！」「？」等；禁止写成「字 字 字」这种用空格断开的中文（英文词、品牌名等可保留必要空格）
{optimize_hint}

{persona_info}

原始文案结构：
开头钩子：{script.get('hook', '')}
问题：{script.get('problem', '')}
解决方案：{script.get('solution', '')}
行动号召：{script.get('cta', '')}
完整文案：{script.get('full_script', '')}

请严格按照原始文案的结构框架，结合人设配置，进行二创改写。返回JSON格式：
{{
    "hook": "改写后的开头钩子（三秒吸引，使用正常标点符号）",
    "problem": "改写后的问题描述（痛点，使用正常标点符号）",
    "solution": "改写后的解决方案（价值，融入人设信息，使用正常标点符号）",
    "cta": "改写后的行动号召（转化，使用正常标点符号）",
    "full_script": "完整的口播文案（字数控制在{target_min}-{target_max}字之间，必须保留原文案的核心内容和关键信息，按照爆款框架，融入人设信息，使用正常标点符号：逗号、句号、问号、感叹号等）"
}}

重要提醒：
- 结构要求：改写后的文案结构要与原始文案基本一致，保持钩子→问题→解决方案→行动号召的框架
- 字数要求：改写后的文案字数必须控制在{target_min}-{target_max}字之间，必须保留原文案的核心内容和关键信息
- 内容要求：必须基于原文案的完整内容进行改写，不能遗漏重要信息，不能过度简化
- 禁止使用特殊符号（星号*、井号#、下划线_、方括号[]、花括号{{}}等）
- 必须使用正常标点符号（逗号、句号、问号、感叹号、引号、冒号、分号等），确保口播时能正确断句
- 禁止用空格分句：不要用空格代替逗号/顿号；避免出现大量无意义空格断词
- 保持原始文案的核心逻辑和结构框架
- 根据人设配置个性化改写，让文案更符合客户特点"""
        
        # 调用AI API（豆包模型）
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}'
        }
        # 豆包API可能需要不同的认证方式，如果Bearer不行，可以尝试：
        # headers = {
        #     'Content-Type': 'application/json',
        #     'Authorization': f'Bearer {api_key}',
        #     'X-API-Key': api_key  # 某些豆包API可能需要这个
        # }
        
        # 根据目标字数调整max_tokens（确保足够生成长文案）
        # 1000字大约需要1500-2000 tokens（中文1字≈1.5-2 tokens）
        max_tokens_value = max(1500, int(target_max * 2))
        
        data = {
            'model': 'doubao-seed-2-0-code-preview-260215',
            'messages': [
                {'role': 'system', 'content': '你是一个专业的短视频文案改写专家。'},
                {'role': 'user', 'content': prompt}
            ],
            'temperature': 0.7,
            'max_tokens': max_tokens_value
        }
        
        logger.info(f"[ScriptRewriter] 原文案长度: {original_length}字, 目标字数: {target_min}-{target_max}字, max_tokens: {max_tokens_value}")
        
        logger.info(f"[ScriptRewriter] 调用AI API: {api_url}")
        response = requests.post(api_url, headers=headers, json=data, timeout=60)
        
        if response.status_code != 200:
            logger.error(f"[ScriptRewriter] API调用失败: {response.status_code} - {response.text}")
            return _mock_rewrite(script)
        
        # 解析响应
        result_data = response.json()
        content = result_data['choices'][0]['message']['content']
        logger.info(f"[ScriptRewriter] AI响应: {content[:100]}...")
        
        # 尝试解析JSON
        try:
            # 提取JSON部分
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
            else:
                result = json.loads(content)
            
            # 清理特殊符号（星号、井号等）
            result = _clean_special_symbols(result)
            
            logger.info("[ScriptRewriter] 改写完成")
            return result
            
        except json.JSONDecodeError:
            logger.warning("[ScriptRewriter] JSON解析失败，使用文本提取")
            return _extract_from_text(content, script)
            
    except Exception as e:
        logger.error(f"[ScriptRewriter] 改写文案时出错: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return _mock_rewrite(script)


def _clean_special_symbols(result: Dict[str, str]) -> Dict[str, str]:
    """清理文案中的特殊符号（星号、井号等），但保留正常标点符号"""
    # 需要清理的特殊符号（不包括正常标点符号）
    special_symbols = ['*', '#', '_', '[', ']', '{', '}', '【', '】']
    # 保留的正常标点符号：逗号、句号、问号、感叹号、引号、冒号、分号、顿号、省略号等
    # 这些标点符号不需要清理
    
    cleaned_result = {}
    for key, value in result.items():
        if isinstance(value, str):
            # 只移除特殊符号，保留正常标点符号
            cleaned_text = value
            for symbol in special_symbols:
                cleaned_text = cleaned_text.replace(symbol, '')
            # 清理多余的空格（但保留标点符号后的正常空格）
            # 只清理连续多个空格的情况
            import re
            cleaned_text = re.sub(r' +', ' ', cleaned_text)  # 多个空格替换为单个空格
            cleaned_result[key] = cleaned_text
        else:
            cleaned_result[key] = value
    
    return cleaned_result


def _extract_from_text(text: str, original: Dict[str, str]) -> Dict[str, str]:
    """从文本中提取改写后的内容"""
    # 简单提取逻辑
    lines = text.split('\n')
    result = {
        'hook': original.get('hook', ''),
        'problem': original.get('problem', ''),
        'solution': original.get('solution', ''),
        'cta': original.get('cta', ''),
        'full_script': text[:500]  # 取前500字作为完整文案
    }
    
    # 尝试从文本中提取各部分
    for i, line in enumerate(lines):
        if 'hook' in line.lower() or '开头' in line:
            if i + 1 < len(lines):
                result['hook'] = lines[i + 1].strip()
        elif 'problem' in line.lower() or '问题' in line:
            if i + 1 < len(lines):
                result['problem'] = lines[i + 1].strip()
        elif 'solution' in line.lower() or '解决' in line:
            if i + 1 < len(lines):
                result['solution'] = lines[i + 1].strip()
    
    return result


def _mock_rewrite(script: Dict[str, str]) -> Dict[str, str]:
    """模拟改写（当API不可用时）"""
    logger.info("[ScriptRewriter] 使用模拟改写")
    
    hook = script.get('hook', '')
    problem = script.get('problem', '')
    solution = script.get('solution', '')
    cta = script.get('cta', '')
    
    # 简单的改写逻辑：添加口语化词汇
    rewritten_hook = f"你知道吗？{hook}" if not hook.startswith('你') else hook
    rewritten_problem = f"很多人都在问：{problem}" if problem else ""
    rewritten_solution = f"其实很简单，{solution}" if solution else ""
    rewritten_cta = cta if cta else "觉得有用的话，记得点赞关注哦！"
    
    full_script = f"{rewritten_hook}。{rewritten_problem}。{rewritten_solution}。{rewritten_cta}"
    
    return {
        'hook': rewritten_hook,
        'problem': rewritten_problem,
        'solution': rewritten_solution,
        'cta': rewritten_cta,
        'full_script': full_script
    }

