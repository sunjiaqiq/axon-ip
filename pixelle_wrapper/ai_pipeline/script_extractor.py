"""
文案提取模块 - 从视频描述中提取结构化内容
"""
import logging
import re
from typing import Dict, Any

logger = logging.getLogger(__name__)


def extract_script(desc: str) -> Dict[str, str]:
    """
    从视频描述中提取结构化内容
    
    Args:
        desc: 视频描述文本
        
    Returns:
        包含以下字段的字典：
        - hook: 开头钩子（前3秒吸引人的内容）
        - problem: 问题/痛点
        - solution: 解决方案
        - cta: 行动号召（Call To Action）
    """
    logger.info(f"[ScriptExtractor] 开始提取文案: {desc[:50]}...")
    
    try:
        # 清理描述文本
        desc = desc.strip()
        
        # 提取钩子（通常在前30-50字）
        hook = desc[:50] if len(desc) > 50 else desc
        hook = _clean_text(hook)
        
        # 提取问题（包含"为什么"、"怎么"、"如何"等关键词）
        problem = _extract_problem(desc)
        
        # 提取解决方案（包含"方法"、"技巧"、"步骤"等）
        solution = _extract_solution(desc)
        
        # 提取行动号召（包含"关注"、"点赞"、"收藏"等）
        cta = _extract_cta(desc)
        
        result = {
            'hook': hook,
            'problem': problem,
            'solution': solution,
            'cta': cta,
            'original': desc
        }
        
        logger.info(f"[ScriptExtractor] 提取完成 - Hook: {hook[:30]}...")
        return result
        
    except Exception as e:
        logger.error(f"[ScriptExtractor] 提取文案时出错: {e}")
        return {
            'hook': desc[:50] if desc else '',
            'problem': '',
            'solution': desc if desc else '',
            'cta': '',
            'original': desc
        }


def _clean_text(text: str) -> str:
    """清理文本"""
    # 移除多余空格
    text = re.sub(r'\s+', ' ', text)
    # 移除特殊字符
    text = re.sub(r'[^\w\s\u4e00-\u9fff]', '', text)
    return text.strip()


def _extract_problem(text: str) -> str:
    """提取问题/痛点"""
    # 查找包含问题的句子
    problem_keywords = ['为什么', '怎么', '如何', '问题', '痛点', '困扰', '难题']
    sentences = re.split(r'[。！？\n]', text)
    
    for sentence in sentences:
        for keyword in problem_keywords:
            if keyword in sentence:
                return _clean_text(sentence)
    
    # 如果没有找到，返回前100字
    return _clean_text(text[:100])


def _extract_solution(text: str) -> str:
    """提取解决方案"""
    solution_keywords = ['方法', '技巧', '步骤', '解决', '办法', '方案', '教你']
    sentences = re.split(r'[。！？\n]', text)
    
    solutions = []
    for sentence in sentences:
        for keyword in solution_keywords:
            if keyword in sentence:
                solutions.append(_clean_text(sentence))
    
    if solutions:
        return ' '.join(solutions[:2])  # 返回前2个解决方案
    
    # 如果没有找到，返回中间部分
    mid_start = len(text) // 3
    return _clean_text(text[mid_start:mid_start+100])


def _extract_cta(text: str) -> str:
    """提取行动号召"""
    cta_keywords = ['关注', '点赞', '收藏', '转发', '评论', '私信', '了解更多']
    sentences = re.split(r'[。！？\n]', text)
    
    for sentence in sentences:
        for keyword in cta_keywords:
            if keyword in sentence:
                return _clean_text(sentence)
    
    return '关注我，了解更多实用技巧'







