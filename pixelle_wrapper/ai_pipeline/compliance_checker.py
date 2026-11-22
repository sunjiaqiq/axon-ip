"""
合规检测模块 - 使用豆包模型检测文案合规性，自动处理敏感词
"""
import logging
import os
import json
import re
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    import requests
except ImportError:
    logger.warning("requests 未安装，将使用模拟检测")
    requests = None

# 敏感词库（可扩展）
SENSITIVE_WORDS = {
    # 个人私域相关
    'wechat': ['微信', 'wechat', 'wx', 'vx'],
    'qq': ['QQ', 'qq', '企鹅'],
    'phone': ['电话', '手机号', '联系方式'],
    'email': ['邮箱', 'email', '邮件'],
    
    # 三方平台相关
    'taobao': ['淘宝', 'taobao', 'tb'],
    'jd': ['京东', 'jd', 'jingdong'],
    'pdd': ['拼多多', 'pdd', '拼夕夕'],
    'douyin': ['抖音', 'douyin'],
    'kuaishou': ['快手', 'kuaishou'],
    'xiaohongshu': ['小红书', 'xiaohongshu', '红书'],
    
    # 行业限制词
    'finance': ['金融', '贷款', '理财', '投资', '股票', '基金', '保险', '银行', '信用卡'],
    'medical': ['医疗', '药品', '治疗', '疾病', '医院', '医生'],
    'education': ['教育', '培训', '学校', '课程'],
}


def check_compliance(
    script: str,
    extra_rules: Optional[str] = None,
    api_key: Optional[str] = None,
    api_url: Optional[str] = None
) -> Dict[str, any]:
    """
    检测文案合规性，并自动处理敏感词
    
    Args:
        script: 需要检测的文案
        api_key: API密钥，如果为None则使用默认密钥
        api_url: API地址，如果为None则使用默认地址
        
    Returns:
        包含检测结果和处理后文案的字典
    """
    logger.info("[ComplianceChecker] 开始合规检测")
    
    if not script or not script.strip():
        return {
            "is_compliant": True,
            "original_script": script,
            "processed_script": script,
            "issues": [],
            "replacements": []
        }
    
    try:
        # 使用默认API配置（豆包模型）
        if api_url is None:
            api_url = os.getenv('AI_API_URL', 'https://ark.cn-beijing.volces.com/api/v3/chat/completions')
        if api_key is None:
            api_key = os.getenv('AI_API_KEY', '5d24f49e-bec4-4af0-b527-015fef194fdb')
        
        if not api_key or requests is None:
            logger.warning("[ComplianceChecker] API密钥未设置或requests未安装，使用本地检测")
            return _local_compliance_check(script)
        
        # 构建提示词
        extra_rules_block = ""
        if extra_rules and str(extra_rules).strip():
            extra_rules_block = f"""

【客户自定义合规补充规则（最高优先级）】
{str(extra_rules).strip()}

要求：在不改变原意的前提下，严格按以上规则进行替换与改写；如果补充规则与通用规则冲突，以补充规则为准。
"""

        prompt = f"""你是一位专业的法务合规检测专家，负责检测短视频文案的合规性问题。

检测要求：
1. 检测个人私域相关词汇（如：微信、QQ、电话、邮箱等联系方式）
2. 检测三方平台相关词汇（如：淘宝、京东、拼多多、抖音、快手、小红书等）
3. 检测行业限制词（如：金融、贷款、理财、投资、股票、基金、保险、银行、医疗、药品等）

处理规则：
- 个人私域词汇：在中间加"某"字，如"微信"→"微某信"或"某信"
- 三方平台词汇：在中间加"某"字，如"淘宝"→"淘某宝"或"某宝"
- 行业限制词：在中间加"某"字，如"金融"→"金某融"或"某金融"
- 也可以使用谐音字或音译词替代
{extra_rules_block}

需要检测的文案：
{script}

请以JSON格式返回检测结果：
{{
    "is_compliant": true/false,
    "issues": [
        {{
            "type": "个人私域/三方平台/行业限制",
            "word": "敏感词",
            "position": "在文案中的位置描述",
            "suggestion": "建议替换为"
        }}
    ],
    "processed_script": "处理后的安全文案（已替换所有敏感词）"
}}

重要：
- 必须返回处理后的完整文案，确保所有敏感词都已替换
- 替换后的文案要保持原意和流畅性
- 使用正常标点符号，不要使用特殊符号"""
        
        # 调用AI API
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}'
        }
        
        data = {
            'model': 'doubao-seed-2-0-code-preview-260215',
            'messages': [
                {'role': 'system', 'content': '你是一位专业的法务合规检测专家，负责检测短视频文案的合规性问题。'},
                {'role': 'user', 'content': prompt}
            ],
            'temperature': 0.3,  # 降低温度，确保准确性
            'max_tokens': 2000
        }
        
        logger.info(f"[ComplianceChecker] 调用AI API进行合规检测: {api_url}")
        response = requests.post(api_url, headers=headers, json=data, timeout=60)
        
        if response.status_code != 200:
            logger.error(f"[ComplianceChecker] API调用失败: {response.status_code} - {response.text}")
            return _local_compliance_check(script)
        
        # 解析响应
        result_data = response.json()
        content = result_data['choices'][0]['message']['content']
        logger.info(f"[ComplianceChecker] AI响应: {content[:200]}...")
        
        # 尝试解析JSON
        try:
            # 提取JSON部分
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
            else:
                result = json.loads(content)
            
            # 确保返回格式正确
            if 'processed_script' not in result:
                result['processed_script'] = script
            
            if 'issues' not in result:
                result['issues'] = []
            
            if 'is_compliant' not in result:
                result['is_compliant'] = len(result.get('issues', [])) == 0
            
            result['original_script'] = script
            result['replacements'] = []
            
            # 提取替换信息
            for issue in result.get('issues', []):
                if 'word' in issue and 'suggestion' in issue:
                    result['replacements'].append({
                        'original': issue['word'],
                        'replacement': issue['suggestion'],
                        'type': issue.get('type', '未知')
                    })
            
            logger.info(f"[ComplianceChecker] 合规检测完成，发现问题: {len(result.get('issues', []))}个")
            return result
            
        except json.JSONDecodeError:
            logger.warning("[ComplianceChecker] JSON解析失败，使用本地检测")
            return _local_compliance_check(script)
            
    except Exception as e:
        logger.error(f"[ComplianceChecker] 合规检测时出错: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return _local_compliance_check(script)


def _local_compliance_check(script: str) -> Dict[str, any]:
    """本地合规检测（当API不可用时使用）"""
    logger.info("[ComplianceChecker] 使用本地合规检测")
    
    issues = []
    replacements = []
    processed_script = script
    
    # 检测敏感词
    for category, words in SENSITIVE_WORDS.items():
        for word in words:
            if word in processed_script:
                # 生成替换词（中间加"某"）
                if len(word) == 2:
                    replacement = word[0] + '某' + word[1]
                elif len(word) > 2:
                    replacement = word[0] + '某' + word[-1]
                else:
                    replacement = '某' + word
                
                issues.append({
                    'type': category,
                    'word': word,
                    'position': f'文案中包含"{word}"',
                    'suggestion': replacement
                })
                
                replacements.append({
                    'original': word,
                    'replacement': replacement,
                    'type': category
                })
                
                # 替换
                processed_script = processed_script.replace(word, replacement)
    
    return {
        "is_compliant": len(issues) == 0,
        "original_script": script,
        "processed_script": processed_script,
        "issues": issues,
        "replacements": replacements
    }







