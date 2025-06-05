"""
Ollama 响应修复器
用于处理 Ollama 返回的格式问题，避免 JSON 解析错误
"""

import re
import json
import logging

logger = logging.getLogger(__name__)

class OllamaResponseFixer:
    """修复 Ollama 响应中的格式问题"""
    
    @staticmethod
    def clean_response(response_text: str) -> str:
        """清理和修复 Ollama 响应文本"""
        if not response_text:
            return "I'm ready to help you."
            
        try:
            # 1. 处理未闭合的 <think> 标记
            if '<think>' in response_text and '</think>' not in response_text:
                # 如果有开始但没有结束标记，提供简洁的默认响应
                logger.info("🔧 检测到截断的 <think> 标记，提供默认响应")
                return "Hello! How can I help you today?"
            
            # 2. 移除完整的 <think> 内容
            think_pattern = r'<think>.*?</think>'
            if re.search(think_pattern, response_text, re.DOTALL):
                # 提取 think 标记外的内容
                cleaned = re.sub(think_pattern, '', response_text, flags=re.DOTALL)
                cleaned = cleaned.strip()
                if cleaned:
                    response_text = cleaned
                    logger.info("🧹 已移除 <think> 标记内容")
                else:
                    # 如果移除 think 后没有内容，提供默认响应
                    logger.info("🔄 移除<think>后无内容，提供默认响应")
                    return "I understand. How can I assist you?"
            
            # 3. 检查是否整个响应都是 <think> 内容（即以<think>开始且无结束标记）
            if response_text.strip().startswith('<think>'):
                logger.info("🔄 响应完全是<think>内容，提供清洁响应")
                return "Hello! I'm here to help. What would you like to know?"
            
            # 4. 清理多余的空白字符
            response_text = re.sub(r'\n\s*\n', '\n\n', response_text)
            response_text = response_text.strip()
            
            # 5. 确保响应不为空且有意义
            if not response_text or len(response_text) < 3:
                logger.info("🔄 响应太短或为空，提供默认响应")
                return "I'm ready to help you."
                
            return response_text
            
        except Exception as e:
            logger.error(f"❌ 清理响应时出错: {e}")
            return "I apologize, but I encountered an error processing the response."
    
    @staticmethod
    def fix_json_response(json_str: str) -> str:
        """修复 JSON 响应中的格式问题"""
        try:
            # 尝试解析原始 JSON
            json.loads(json_str)
            return json_str  # 如果成功，直接返回
        except json.JSONDecodeError as e:
            logger.warning(f"⚠️ JSON 解析错误，尝试修复: {e}")
            
            try:
                # 1. 修复未闭合的字符串
                if 'Unterminated string' in str(e):
                    # 在错误位置添加闭合引号
                    char_pos = getattr(e, 'pos', len(json_str))
                    fixed_json = json_str[:char_pos] + '"}'
                    json.loads(fixed_json)  # 验证修复结果
                    logger.info("🔧 修复了未闭合的字符串")
                    return fixed_json
                
                # 2. 其他修复策略
                # 移除控制字符
                cleaned = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', json_str)
                json.loads(cleaned)
                logger.info("🧹 移除了控制字符")
                return cleaned
                
            except json.JSONDecodeError:
                # 如果修复失败，返回简单的有效 JSON
                logger.error("❌ JSON 修复失败，返回默认响应")
                return '{"response": "I encountered a formatting error. Please try again."}'
    
    @staticmethod  
    def should_retry_request(error_message: str) -> bool:
        """判断是否应该重试请求"""
        retry_indicators = [
            'unterminated string',
            'json decode error',
            'invalid json',
            'unexpected end of json'
        ]
        
        error_lower = error_message.lower()
        return any(indicator in error_lower for indicator in retry_indicators)


def test_response_fixer():
    """测试响应修复器"""
    test_cases = [
        '<think>\nThis is incomplete',
        '<think>Complete thought</think>\nHello!',
        '{"incomplete": "string',
        '{"response": "normal response"}',
        '',
    ]
    
    fixer = OllamaResponseFixer()
    
    for i, test_case in enumerate(test_cases):
        print(f"\n测试用例 {i+1}:")
        print(f"输入: {repr(test_case)}")
        
        if test_case.startswith('{'):
            result = fixer.fix_json_response(test_case)
            print(f"JSON修复: {repr(result)}")
        else:
            result = fixer.clean_response(test_case)
            print(f"文本清理: {repr(result)}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_response_fixer()
