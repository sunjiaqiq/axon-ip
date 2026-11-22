"""
文本相似度计算模块
"""
import re
from typing import Tuple
from collections import Counter


def calculate_similarity(original: str, rewritten: str) -> dict:
    """
    计算原文案和改写后文案的相似度
    
    Args:
        original: 原文案
        rewritten: 改写后文案
        
    Returns:
        包含重复率、相似度、去重率的字典
    """
    # 清理文本（去除标点符号和空格）
    def clean_text(text: str) -> str:
        # 移除标点符号和空格
        text = re.sub(r'[^\w]', '', text)
        return text.lower()
    
    original_clean = clean_text(original)
    rewritten_clean = clean_text(rewritten)
    
    if not original_clean or not rewritten_clean:
        return {
            "repetition_rate": 0.0,
            "similarity_rate": 0.0,
            "deduplication_rate": 100.0
        }
    
    # 计算字符级别的重复率
    original_chars = Counter(original_clean)
    rewritten_chars = Counter(rewritten_clean)
    
    # 计算重复字符数
    common_chars = sum((original_chars & rewritten_chars).values())
    total_chars = len(original_clean)
    
    if total_chars == 0:
        repetition_rate = 0.0
    else:
        repetition_rate = (common_chars / total_chars) * 100
    
    # 计算词级别的相似度（使用简单的集合交集）
    original_words = set(original_clean)
    rewritten_words = set(rewritten_clean)
    
    if not original_words or not rewritten_words:
        similarity_rate = 0.0
    else:
        common_words = len(original_words & rewritten_words)
        total_unique_words = len(original_words | rewritten_words)
        if total_unique_words == 0:
            similarity_rate = 0.0
        else:
            similarity_rate = (common_words / total_unique_words) * 100
    
    # 去重率 = 100% - 相似度（基于词级别）
    deduplication_rate = 100.0 - similarity_rate
    
    return {
        "repetition_rate": round(repetition_rate, 2),
        "similarity_rate": round(similarity_rate, 2),
        "deduplication_rate": round(deduplication_rate, 2)
    }







