import os
import sys
import logging
import re
from typing import Optional, Tuple

import click
import httpx

from agent import CurrencyAgent  # type: ignore[import-untyped]
# type: ignore[import-untyped]
from agent_executor import CurrencyAgentExecutor
from element_agent import ElementAgent
from element_agent_executor import ElementAgentExecutor
from dotenv import load_dotenv

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler, RequestHandler
from a2a.server.tasks import InMemoryPushNotifier, InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


async def analyze_request(request: str) -> str:
    """
    使用大模型分析用户请求内容，决定使用哪个代理。
    
    Args:
        request: 用户的请求内容
        
    Returns:
        str: "currency" 或 "element" 表示应该使用的代理类型
    """
    try:
        # 使用大模型进行分析
        from langchain_openai import ChatOpenAI
        
        # 初始化模型 (使用与元素和货币代理相同的模型配置)
        model = ChatOpenAI(
            model="qwen3-0.6b",
            base_url="http://localhost:1234/v1",
        )
        
        # 构建系统提示和用户查询
        system_message = """
        你是一个高级路由决策系统，负责将用户查询分配给最合适的专业代理。
        你需要分析用户输入，并决定将请求路由到以下哪个代理：
        
        1. 货币代理 (currency): 专门处理所有与货币、汇率、金融兑换相关的查询
           - 处理货币转换
           - 获取货币汇率信息
           - 解答关于货币、汇率波动的问题
        
        2. 元素代理 (element): 专门处理所有与化学元素、周期表相关的查询
           - 提供关于化学元素的信息
           - 回答关于元素性质、原子量、原子结构的问题
           - 处理与周期表相关的所有查询
        
        仅返回单个词: "currency" 或 "element"，表示最合适处理该查询的代理。
        """
        
        # 调用模型进行代理选择
        result = await model.ainvoke([
            {"role": "system", "content": system_message},
            {"role": "user", "content": f"用户查询: {request}\n请决定应该路由到哪个代理 (只回答 currency 或 element):"}
        ])
        
        # 解析结果
        agent_choice = str(result.content).lower().strip()
        if "currency" in agent_choice:
            logger.info(f"大模型分析结果: 货币代理 (currency)")
            return "currency"
        else:
            logger.info(f"大模型分析结果: 元素代理 (element)")
            return "element"
            
    except Exception as e:
        # 如果大模型分析失败，回退到关键词分析
        logger.error(f"大模型分析失败: {str(e)}，回退到关键词匹配")
        agent_type, confidence = analyze_request_by_keywords(request, logger)
        logger.info(f"关键词分析结果: {agent_type} (置信度: {confidence:.1%})")
        return agent_type


def analyze_request_by_keywords(request: str, logger=None) -> tuple:
    """
    通过关键词匹配分析用户请求内容，决定使用哪个代理。
    使用加权系统为关键词分配不同的权重，实现更智能的代理选择。
    
    Args:
        request: 用户的请求内容
        logger: 可选的日志记录器
        
    Returns:
        tuple: (agent_type, confidence) 
               agent_type是"currency"或"element"表示应该使用的代理类型
               confidence是0到1之间的置信度值
    """
    # 货币相关关键词及其权重 (权重越高，越有可能使用该代理)
    currency_keywords = {
        # 高权重词 - 明确表示货币查询的关键词
        'currency': 3, '货币': 3, 'exchange rate': 3, '汇率': 3, 'exchange': 2.5, '兑换': 2.5,
        # 中权重词 - 具体货币名称
        'dollar': 2, '美元': 2, 'euro': 2, '欧元': 2, 'yuan': 2, '人民币': 2, 
        'yen': 2, '日元': 2, 'pound': 2, '英镑': 2,
        # 低权重词 - 货币简写或通用词
        'money': 1, '钱': 1, 'usd': 1.5, 'eur': 1.5, 'cny': 1.5, 'jpy': 1.5, 'gbp': 1.5,
        'rate': 1, '汇价': 1, 'conversion': 1.5, 'convert': 1.5, 'price': 0.8, 'market': 0.8, '市场': 0.8
    }
    
    # 元素相关关键词及其权重
    element_keywords = {
        # 高权重词 - 明确表示元素查询的关键词
        'element': 3, '元素': 3, 'periodic table': 3, '周期表': 3, 'chemistry': 2.5, '化学': 2.5,
        # 中权重词 - 基础元素名称和化学相关词
        'atom': 2, '原子': 2, 'hydrogen': 2, '氢': 2, 'oxygen': 2, '氧': 2, 'carbon': 2, '碳': 2,
        'molecular': 2, '分子': 2, 'compound': 2, '化合物': 2, 'atomic': 2, '原子的': 2,
        # 低权重词 - 元素符号或化合物
        'h2o': 1.5, 'co2': 1.5, 'fe': 1.5, 'cu': 1.5, 'nonmetal': 1.5, '非金属': 1.5,
        'metal': 0.8, '金属': 0.8  # 较低权重因为"金属"也可能指货币
    }
    
    request_lower = request.lower()
    
    # 计算加权匹配得分
    currency_score = 0
    element_score = 0
    
    # 记录匹配的关键词和其权重
    matched_currency_keywords = {}
    matched_element_keywords = {}
    
    # 计算货币关键词匹配得分
    for keyword, weight in currency_keywords.items():
        if keyword.lower() in request_lower:
            currency_score += weight
            matched_currency_keywords[keyword] = weight
    
    # 计算元素关键词匹配得分
    for keyword, weight in element_keywords.items():
        if keyword.lower() in request_lower:
            element_score += weight
            matched_element_keywords[keyword] = weight
    
    # 上下文分析：检查是否有明确的意图指示词
    intent_indicators = {
        # 货币转换意图
        'convert': 1, '转换': 1, 'rate': 1, '比率': 1, 'worth': 1, '值多少': 1, '值': 1,
        # 元素查询意图
        'properties': 1, '性质': 1, 'atomic': 1, '原子': 1, 'information': 0.5, '信息': 0.5
    }
    
    # 应用意图加权
    for intent, weight in intent_indicators.items():
        if intent.lower() in request_lower:
            # 根据意图关键词的上下文判断应当强化哪种代理
            context_before = request_lower.split(intent.lower())[0] if len(request_lower.split(intent.lower())) > 1 else ""
            context_after = request_lower.split(intent.lower())[1] if len(request_lower.split(intent.lower())) > 1 else ""
            
            # 金融相关意图通常与货币相关
            if any(fin_term in context_before or fin_term in context_after for fin_term in ['money', 'currency', '货币', '钱']):
                currency_score += weight
                if logger:
                    logger.debug(f"上下文分析：增加货币得分 {weight} (基于意图词 '{intent}')")
            
            # 科学相关意图通常与元素相关
            if any(sci_term in context_before or sci_term in context_after for sci_term in ['chemistry', 'element', '元素', '化学']):
                element_score += weight
                if logger:
                    logger.debug(f"上下文分析：增加元素得分 {weight} (基于意图词 '{intent}')")
    
    # 处理混合查询的特殊情况 (例如："gold的价格是多少美元")
    # 元素符号也是贵金属货币名称的特殊情况
    special_cases = {
        'gold': {'element': 1, 'currency': 1.5},  # 黄金既是元素又是货币，但更常见作为货币
        'silver': {'element': 1, 'currency': 1.5},  # 白银既是元素又是货币，但更常见作为货币
        '黄金': {'element': 1, 'currency': 1.5},
        '白银': {'element': 1, 'currency': 1.5},
        'au': {'element': 2, 'currency': 0.5},  # 作为元素符号更明显
        'ag': {'element': 2, 'currency': 0.5},  # 作为元素符号更明显
        'platinum': {'element': 1.5, 'currency': 1}, # 铂金
        '铂': {'element': 1.5, 'currency': 1}
    }
    
    # 记录特殊案例分析结果
    special_case_analysis = {}
    
    # 处理特殊情况
    for term, weights in special_cases.items():
        if term in request_lower:
            # 直接检查是否有强烈的投资/财务相关表述结合元素符号
            investment_indicators = ['投资', '价格', '价值', '买', '卖', '兑换', '汇率', '行情', '资产', '财务', 
                                    '金融', '价', 'invest', 'price', 'value', 'buy', 'sell', 'exchange', 'market']
            
            if term.lower() in ['au', 'ag', 'pt', '黄金', '白银', 'gold', 'silver']:
                # 检查紧密的投资上下文来处理特殊情况
                investment_context = False
                
                # 可能的投资短语组合
                investment_phrases = [f"投资{term}", f"{term}投资", f"{term}价格", f"买{term}", f"卖{term}",
                                    f"invest in {term}", f"buy {term}", f"sell {term}", f"{term} price"]
                
                # 检查这些紧密组合
                for phrase in investment_phrases:
                    if phrase in request_lower:
                        investment_context = True
                        if logger:
                            logger.debug(f"检测到明确的投资短语: '{phrase}'，元素符号/贵金属更可能指货币")
                        break
                
                # 如果有明确的投资短语，强制设置为货币上下文
                if investment_context:
                    context_suggestion = 'currency'
                    # 给予更高权重
                    currency_weight = 3.0  # 高权重货币相关
                    element_weight = 0.5   # 低权重元素相关 
                    if logger:
                        logger.debug(f"因投资上下文，强制将'{term}'视为货币相关并增加权重")
                else:
                    # 如果没有明确投资短语，再进行常规的上下文分析
                    context_suggestion = analyze_ambiguous_term_context(request_lower, term, logger)
                    currency_weight = weights['currency'] * (1.5 if context_suggestion == 'currency' else 0.5)
                    element_weight = weights['element'] * (1.5 if context_suggestion == 'element' else 0.5)
            else:
                # 对于非贵金属/元素符号的常规处理
                context_suggestion = analyze_ambiguous_term_context(request_lower, term, logger)
                currency_weight = weights['currency'] * (1.5 if context_suggestion == 'currency' else 0.5)
                element_weight = weights['element'] * (1.5 if context_suggestion == 'element' else 0.5)
            
            # 准备记录分析结果
            reason = '未知原因'
            
            # 如果是投资上下文中的元素符号，给予特殊处理
            if investment_context and term.lower() in ['au', 'ag', 'pt', '黄金', '白银', 'gold', 'silver']:
                reason = '投资上下文中的元素符号/贵金属'
                # currency_weight和element_weight已经在前面设置了
            elif context_suggestion == 'currency':
                # 如果没有明确设置过weights，再设置
                if 'currency_weight' not in locals():
                    currency_weight = weights['currency'] * 1.5  # 增强货币权重
                    element_weight = weights['element'] * 0.5   # 降低元素权重
                reason = '上下文更符合货币相关'
            elif context_suggestion == 'element':
                # 如果没有明确设置过weights，再设置
                if 'currency_weight' not in locals():
                    element_weight = weights['element'] * 1.5   # 增强元素权重
                    currency_weight = weights['currency'] * 0.5  # 降低货币得分权重
                reason = '上下文更符合元素相关'
            else:
                # 如果没有明确设置过weights，再设置
                if 'currency_weight' not in locals():
                    currency_weight = weights['currency']
                    element_weight = weights['element']
                reason = '无明确上下文提示，使用默认权重'
                
            # 记录完整的分析结果
            special_case_analysis[term] = {
                'context_suggests': context_suggestion,
                'currency_weight': currency_weight, 
                'element_weight': element_weight,
                'reason': reason
            }
                
            currency_score += currency_weight
            element_score += element_weight
            
            if logger:
                logger.debug(f"特殊词分析: '{term}' - {special_case_analysis[term]['reason']}")
    
    # 记录匹配结果
    if matched_currency_keywords:
        keyword_list = [f"{k}({w})" for k, w in matched_currency_keywords.items()]
        if logger:
            logger.debug(f"匹配到货币关键词: {', '.join(keyword_list)}")
    if matched_element_keywords:
        keyword_list = [f"{k}({w})" for k, w in matched_element_keywords.items()]
        if logger:
            logger.debug(f"匹配到元素关键词: {', '.join(keyword_list)}")
    
    # 记录特殊情况分析结果
    for term, analysis in special_case_analysis.items():
        if logger:
            logger.debug(f"歧义词 '{term}' 分析: 元素得分={analysis['element_weight']:.1f}, 货币得分={analysis['currency_weight']:.1f}, 上下文建议={analysis['context_suggests']}")
    
    # 计算置信度
    total_score = currency_score + element_score
    if total_score > 0:
        if currency_score > element_score:
            confidence = (currency_score / total_score) 
            confidence_level = '高' if confidence > 0.7 else '中' if confidence > 0.55 else '低'
            if logger:
                logger.info(f"加权关键词匹配得分 - 货币: {currency_score:.2f}, 元素: {element_score:.2f}, 置信度: {confidence:.1%} ({confidence_level})")
                logger.info(f"基于加权关键词匹配，选择货币代理 (置信度: {confidence:.1%})")
            return 'currency', confidence
        else:
            confidence = (element_score / total_score)
            confidence_level = '高' if confidence > 0.7 else '中' if confidence > 0.55 else '低'
            if logger:
                logger.info(f"加权关键词匹配得分 - 货币: {currency_score:.2f}, 元素: {element_score:.2f}, 置信度: {confidence:.1%} ({confidence_level})")
                logger.info(f"基于加权关键词匹配，选择元素代理 (置信度: {confidence:.1%})")
            return 'element', confidence
    else:
        # 得分相等时的处理策略
        if logger:
            logger.info("关键词匹配得分相等，默认选择元素代理")
        return 'element', 0.5


def analyze_ambiguous_term_context(text: str, term: str, logger=None) -> str:
    """
    分析歧义术语的上下文，判断它更可能是货币相关还是元素相关
    
    Args:
        text: 用户的完整请求文本
        term: 歧义术语（如'gold'或'silver'）
        logger: 日志记录器（可选）
        
    Returns:
        str: 'currency'或'element'表示更可能的类别，'unknown'表示无法确定
    """
    # 术语前后文本窗口长度
    window_size = 50
    
    # 找到术语的位置
    term_pos = text.find(term)
    if term_pos == -1:
        if logger:
            logger.debug(f"没有在文本中找到术语 '{term}'")
        return 'unknown'
        
    # 提取前后文本窗口
    start = max(0, term_pos - window_size)
    end = min(len(text), term_pos + len(term) + window_size)
    window_text = text[start:end]
    
    if logger:
        logger.debug(f"术语 '{term}' 的上下文窗口: '{window_text}'")
    
    # 货币相关的上下文指示词
    currency_indicators = [
        'price', '价格', 'value', '价值', 'cost', '成本', 
        'market', '市场', 'trade', '交易', 'buy', '买', 'sell', '卖',
        'currency', '货币', 'money', '钱', 'dollar', '美元', 'exchange', '兑换',
        'worth', '值得', 'investment', '投资', 'financial', '金融', 'portfolio', '投资组合',
        'fund', '基金', 'stock', '股票', 'asset', '资产', 'inflation', '通货膨胀'
    ]
    
    # 元素相关的上下文指示词
    element_indicators = [
        'atom', '原子', 'element', '元素', 'chemistry', '化学',
        'periodic', '周期', 'property', '性质', 'metal', '金属',
        'reaction', '反应', 'molecular', '分子', 'compound', '化合物',
        'substance', '物质', 'material', '材料', 'atomic', '原子的',
        'proton', '质子', 'neutron', '中子', 'electron', '电子',
        'isotope', '同位素', 'valence', '价', 'bond', '键', 'nucleus', '核'
    ]
    
    # 计算匹配的指示词数量
    currency_matches = sum(1 for indicator in currency_indicators if indicator in window_text)
    element_matches = sum(1 for indicator in element_indicators if indicator in window_text)
    
    # 货币特有短语
    currency_phrases = [
        'price of '+term, term+' price', 'value of '+term, term+' value',
        term+' cost', 'cost of '+term, term+' market', 'buy '+term, 'sell '+term,
        term+' investment', 'invest in '+term, term+' fund', term+' stock',
        term+' asset', term+' portfolio', term+' trader', term+' trading'
    ]
    
    # 元素特有短语
    element_phrases = [
        'properties of '+term, term+' properties', term+' element', 'element '+term,
        term+' atomic', 'atomic '+term, term+' in periodic', 'chemical '+term,
        term+' atom', term+' compound', term+' molecule', term+' reaction',
        term+' oxide', term+' ion', term+' isotope', term+' electron'
    ]
    
    # 检查特有短语
    currency_phrase_matches = sum(1 for phrase in currency_phrases if phrase in window_text)
    element_phrase_matches = sum(1 for phrase in element_phrases if phrase in window_text)
    
    # 给短语匹配额外加分
    currency_matches += currency_phrase_matches * 2
    element_matches += element_phrase_matches * 2
    
    # 记录匹配情况，便于调试
    if logger:
        if currency_phrase_matches > 0:
            matched_phrases = [phrase for phrase in currency_phrases if phrase in window_text]
            logger.debug(f"'{term}' 匹配到货币短语: {', '.join(matched_phrases)}")
        if element_phrase_matches > 0:
            matched_phrases = [phrase for phrase in element_phrases if phrase in window_text]
            logger.debug(f"'{term}' 匹配到元素短语: {', '.join(matched_phrases)}")
    
    # 特殊情况判断 - 元素符号
    if term.lower() in ['au', 'ag', 'pt']:
        # 检查是否有投资或金融相关的上下文
        investment_indicators = ['投资', 'invest', '价格', 'price', '价值', 'value', 
                                '买', 'buy', '卖', 'sell', '兑换', 'exchange',
                                '财务', 'finance', '资产', 'asset', '金融', 'financial']
        
        if any(indicator in window_text for indicator in investment_indicators):
            # 投资/金融上下文中的元素符号更可能指贵金属
            currency_matches += 4  # 给更高的权重，因为这是非常强的指标
            if logger:
                logger.debug(f"'{term}' 在投资/金融上下文中，强烈增加货币匹配权重")
        elif not any(indicator in window_text for indicator in currency_indicators):
            # 如果是元素符号且没有明显的货币或投资上下文，更可能是元素解释
            element_matches += 3
            if logger:
                logger.debug(f"'{term}' 作为元素符号且无金融上下文，增加元素匹配权重")
    
    # 特殊情况判断 - 与价格明确关联
    if any(price_term in window_text for price_term in ['price', 'cost', '价格', '价值', 'dollar', 'usd', '$', '美元', '钱']):
        # 价格上下文强烈暗示是货币相关
        currency_matches += 2
        if logger:
            logger.debug(f"'{term}' 与价格术语相关，增加货币匹配权重")
            
    # 特殊情况判断 - 与化学性质明确关联
    if any(chem_term in window_text for chem_term in ['atomic', 'element', 'chemical', 'periodic table', '原子', '元素', '化学', '周期表']):
        # 化学性质上下文强烈暗示是元素相关
        element_matches += 2
        if logger:
            logger.debug(f"'{term}' 与化学术语相关，增加元素匹配权重")
    
    # 做出决策并记录依据
    if currency_matches > element_matches:
        if logger:
            logger.debug(f"术语 '{term}' 上下文分析: 货币匹配={currency_matches}, 元素匹配={element_matches}, 结论=货币相关")
        return 'currency'
    elif element_matches > currency_matches:
        if logger:
            logger.debug(f"术语 '{term}' 上下文分析: 货币匹配={currency_matches}, 元素匹配={element_matches}, 结论=元素相关")
        return 'element'
    else:
        # 平局情况下，根据元素符号优先
        if term.lower() in ['au', 'ag', 'pt', 'fe', 'cu']:
            if logger:
                logger.debug(f"术语 '{term}' 上下文分析: 货币匹配={currency_matches}, 元素匹配={element_matches}, 平局情况下因为是常见元素符号，结论=元素相关")
            return 'element'
        else:
            if logger:
                logger.debug(f"术语 '{term}' 上下文分析: 货币匹配={currency_matches}, 元素匹配={element_matches}, 平局情况下默认为货币相关")
            return 'currency'  # 默认考虑为货币


class SmartRequestHandler(DefaultRequestHandler):
    """智能请求处理器，根据请求内容选择适当的代理执行器"""
    
    def __init__(
        self,
        currency_executor: CurrencyAgentExecutor,
        element_executor: ElementAgentExecutor,
        agent_executor=None,  # This will be set by the parent class
        **kwargs
    ):
        self.currency_executor = currency_executor
        self.element_executor = element_executor
        self.current_executor = self.element_executor  # 默认使用元素代理
        
        # 确保 agent_executor 参数不会导致冲突
        kwargs['agent_executor'] = self.current_executor
        super().__init__(**kwargs)
    
    async def execute(self, context, event_queue):
        """代理执行方法，根据请求内容选择合适的执行器"""
        if context and context.message:
            user_input = context.get_user_input()
            logger.info(f"收到用户查询: '{user_input}'")
            
            # 1. 首先使用关键词加权匹配进行分析(快速且不依赖外部服务)
            logger.info("执行关键词加权匹配分析...")
            keyword_result, keyword_confidence = analyze_request_by_keywords(user_input, logger)
            logger.info(f"关键词分析结果: {keyword_result} (置信度: {keyword_confidence:.1%})")
            
            try:
                # 2. 使用大模型进行更深入的分析(更精确但需要调用外部服务)
                logger.info("执行大模型智能分析...")
                llm_result = await analyze_request(user_input)
                logger.info(f"大模型分析结果: {llm_result}")
                
                # 3. 整合两种分析结果
                if keyword_result != llm_result:
                    # 低置信度的关键词分析应该被大模型覆盖
                    if keyword_confidence < 0.65:
                        logger.info(f"分析结果不一致 - 关键词: {keyword_result} (低置信度: {keyword_confidence:.1%}), 大模型: {llm_result}")
                        logger.info("由于关键词分析置信度低，采用大模型分析结果作为最终决策")
                        agent_type = llm_result
                        confidence = 0.8  # 假设大模型有较高置信度
                        decision_method = "LLM (置信度优先)"
                    # 高置信度的关键词分析可能更可靠
                    else:
                        logger.info(f"分析结果不一致 - 关键词: {keyword_result} (高置信度: {keyword_confidence:.1%}), 大模型: {llm_result}")
                        logger.info("由于关键词分析置信度高，保留关键词分析结果作为最终决策")
                        agent_type = keyword_result
                        confidence = keyword_confidence
                        decision_method = "关键词 (高置信)"
                else:
                    logger.info(f"分析结果一致 - 关键词和大模型均建议: {keyword_result}")
                    agent_type = keyword_result
                    confidence = max(keyword_confidence, 0.85)  # 两种方法一致，提高置信度
                    decision_method = "一致结果"
            except Exception as e:
                # 大模型分析失败时，回退到关键词分析结果
                logger.warning(f"大模型分析失败: {str(e)}")
                logger.info("回退使用关键词分析结果")
                agent_type = keyword_result
                confidence = keyword_confidence
                decision_method = "关键词 (LLM失败)"
            
            # 4. 设置当前执行器
            if agent_type == 'currency':
                self.current_executor = self.currency_executor
                logger.info(f"最终决策: 使用货币代理处理请求 (置信度: {confidence:.1%}, 决策方法: {decision_method})")
            else:
                self.current_executor = self.element_executor
                logger.info(f"最终决策: 使用元素代理处理请求 (置信度: {confidence:.1%}, 决策方法: {decision_method})")
                
            # 添加分析结果到上下文，让代理知道是如何被选中的
            if not context.memory:
                context.memory = {}
            context.memory['agent_selection'] = {
                'keyword_result': keyword_result,
                'keyword_confidence': f"{keyword_confidence:.1%}",
                'llm_result': llm_result if 'llm_result' in locals() else None,
                'final_decision': agent_type,
                'confidence': f"{confidence:.1%}",
                'decision_method': decision_method
            }
        else:
            logger.warning("请求中没有包含有效的消息内容")
        
        # 将请求委托给当前选定的执行器
        return await self.current_executor.execute(context, event_queue)


@click.command()
@click.option('--host', 'host', default='localhost', help='Host address to bind the server to')
@click.option('--port', 'port', default=10000, type=int, help='Port to run the server on')
@click.option('--agent-type', 'agent_type', default='auto', 
              type=click.Choice(['currency', 'element', 'auto']),
              help='Agent type to use: "currency", "element", or "auto" (智能使用大模型选择)')
def main(host: str, port: int, agent_type: str):
    """Start the A2A Agent server with the specified agent type."""
    client = httpx.AsyncClient()
    
    # 初始化两种代理执行器
    currency_executor = CurrencyAgentExecutor()
    element_executor = ElementAgentExecutor()
    
    if agent_type == 'auto':
        logger.info("初始化智能代理选择模式...")
        # 创建智能请求处理器
        request_handler = SmartRequestHandler(
            currency_executor=currency_executor,
            element_executor=element_executor,
            task_store=InMemoryTaskStore(),
            push_notifier=InMemoryPushNotifier(client),
        )
        # 创建智能代理卡片
        agent_card = get_smart_agent_card(host, port)
        logger.info(f"启动智能A2A代理服务器 http://{host}:{port}/...")
    else:
        logger.info(f"初始化 {agent_type.capitalize()} 代理...")
        # 固定使用指定的代理
        if agent_type.lower() == 'currency':
            agent_executor = currency_executor
            agent_card = get_currency_agent_card(host, port)
            logger.info(f"启动货币代理服务器 http://{host}:{port}/...")
        else:
            agent_executor = element_executor
            agent_card = get_element_agent_card(host, port)
            logger.info(f"启动元素代理服务器 http://{host}:{port}/...")

        request_handler = DefaultRequestHandler(
            agent_executor=agent_executor,
            task_store=InMemoryTaskStore(),
            push_notifier=InMemoryPushNotifier(client),
        )

    server = A2AStarletteApplication(
        agent_card=agent_card, http_handler=request_handler
    )
    import uvicorn

    uvicorn.run(server.build(), host=host, port=port)


def get_currency_agent_card(host: str, port: int):
    """Returns the Agent Card for the Currency Agent."""
    capabilities = AgentCapabilities(streaming=True, pushNotifications=True)
    skill = AgentSkill(
        id='convert_currency',
        name='Currency Exchange Rates Tool',
        description='Helps with exchange values between various currencies',
        tags=['currency conversion', 'currency exchange'],
        examples=['What is exchange rate between USD and GBP?'],
    )
    return AgentCard(
        name='Currency Agent',
        description='Helps with exchange rates for currencies',
        url=f'http://{host}:{port}/',
        version='1.0.0',
        defaultInputModes=CurrencyAgent.SUPPORTED_CONTENT_TYPES,
        defaultOutputModes=CurrencyAgent.SUPPORTED_CONTENT_TYPES,
        capabilities=capabilities,
        skills=[skill],
    )


def get_element_agent_card(host: str, port: int):
    """Returns the Agent Card for the Element Agent."""
    capabilities = AgentCapabilities(streaming=True, pushNotifications=True)
    skill = AgentSkill(
        id='query_element',
        name='元素周期表工具',
        description='Helps with queries about chemical elements and the periodic table',
        tags=['element', 'periodic table', 'chemistry'],
        examples=['氢元素的信息'],
    )
    return AgentCard(
        name='Element Agent',
        description='Helps with queries about the periodic table of elements',
        url=f'http://{host}:{port}/',
        version='1.0.0',
        defaultInputModes=ElementAgent.SUPPORTED_CONTENT_TYPES,
        defaultOutputModes=ElementAgent.SUPPORTED_CONTENT_TYPES,
        capabilities=capabilities,
        skills=[skill],
    )


def get_smart_agent_card(host: str, port: int):
    """Returns the Agent Card for the Smart Agent that can handle both currency and element queries."""
    capabilities = AgentCapabilities(streaming=True, pushNotifications=True)
    
    # 添加货币代理技能
    currency_skill = AgentSkill(
        id='convert_currency',
        name='Currency Exchange Rates Tool',
        description='Helps with exchange values between various currencies',
        tags=['currency conversion', 'currency exchange'],
        examples=['What is exchange rate between USD and GBP?'],
    )
    
    # 添加元素代理技能
    element_skill = AgentSkill(
        id='query_element',
        name='元素周期表工具',
        description='Helps with queries about chemical elements and the periodic table',
        tags=['element', 'periodic table', 'chemistry'],
        examples=['氢元素的信息'],
    )
    
    # 创建包含两种技能的智能代理卡片
    return AgentCard(
        name='Smart A2A Agent',
        description='智能代理，能够处理货币兑换和化学元素查询',
        url=f'http://{host}:{port}/',
        version='1.0.0',
        # 使用两种代理支持的内容类型
        defaultInputModes=CurrencyAgent.SUPPORTED_CONTENT_TYPES,
        defaultOutputModes=CurrencyAgent.SUPPORTED_CONTENT_TYPES,
        capabilities=capabilities,
        skills=[currency_skill, element_skill],
    )


if __name__ == '__main__':
    main()
