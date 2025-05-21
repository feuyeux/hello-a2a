import os
import sys
import logging
import re
import time
from typing import Optional, Tuple, Dict, Any
from functools import lru_cache

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

# 全局查询缓存
class QueryCache:
    """
    查询缓存类，用于存储和管理之前的查询结果，
    提高重复查询的响应速度和减少对大模型的调用。
    """
    def __init__(self, max_size=100, ttl=3600):
        """
        初始化查询缓存
        
        Args:
            max_size: 缓存的最大条目数
            ttl: 缓存有效期（秒）
        """
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.max_size = max_size
        self.ttl = ttl  # 缓存有效期，单位为秒
        
    def _normalize_query(self, query: str) -> str:
        """
        标准化查询字符串以增加缓存命中率
        
        Args:
            query: 原始查询字符串
            
        Returns:
            标准化后的查询字符串
        """
        # 移除多余空格、转为小写
        normalized = ' '.join(query.lower().split())
        return normalized
    
    def get(self, query: str) -> Optional[Dict[str, Any]]:
        """
        获取缓存的查询结果
        
        Args:
            query: 查询字符串
            
        Returns:
            缓存的结果或None（如果缓存未命中或已过期）
        """
        key = self._normalize_query(query)
        if key in self.cache:
            entry = self.cache[key]
            current_time = time.time()
            
            # 检查是否过期
            if current_time - entry["timestamp"] <= self.ttl:
                logger.debug(f"缓存命中: '{query}'")
                return entry["result"]
            else:
                # 过期移除
                logger.debug(f"缓存过期: '{query}'")
                del self.cache[key]
        
        return None
    
    def set(self, query: str, result: Dict[str, Any]) -> None:
        """
        存储查询结果到缓存
        
        Args:
            query: 查询字符串
            result: 查询结果
        """
        key = self._normalize_query(query)
        
        # 如果缓存已满，移除最旧的条目
        if len(self.cache) >= self.max_size:
            # 简单策略：按时间戳排序，移除最旧的
            oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k]["timestamp"])
            del self.cache[oldest_key]
            logger.debug(f"缓存已满，移除最旧条目: '{oldest_key}'")
        
        # 添加新条目
        self.cache[key] = {
            "result": result,
            "timestamp": time.time()
        }
        logger.debug(f"添加到缓存: '{query}'")
    
    def clear(self) -> None:
        """清空缓存"""
        self.cache.clear()
    
    def info(self) -> Dict[str, Any]:
        """返回缓存统计信息"""
        current_time = time.time()
        active_entries = sum(1 for entry in self.cache.values() 
                           if current_time - entry["timestamp"] <= self.ttl)
        
        return {
            "size": len(self.cache),
            "active_entries": active_entries,
            "max_size": self.max_size,
            "ttl": self.ttl,
        }

# 初始化全局查询缓存实例
query_cache = QueryCache()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


@lru_cache(maxsize=1000)
async def analyze_request(request: str) -> str:
    """
    使用大模型分析用户请求内容，决定使用哪个代理。
    优先使用缓存结果，减少对大模型的调用。
    
    Args:
        request: 用户的请求内容
        
    Returns:
        str: "currency" 或 "element" 表示应该使用的代理类型
    """
    # 先检查缓存
    cache_entry = query_cache.get(request)
    if cache_entry and "llm_result" in cache_entry:
        logger.info(f"从缓存获取分析结果: {cache_entry['llm_result']}")
        return cache_entry["llm_result"]
    
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
            agent_result = "currency"
        else:
            logger.info(f"大模型分析结果: 元素代理 (element)")
            agent_result = "element"
        
        # 存入缓存
        query_cache.set(request, {"llm_result": agent_result})
        
        return agent_result
            
    except Exception as e:
        # 如果大模型分析失败，回退到关键词分析
        logger.error(f"大模型分析失败: {str(e)}，回退到关键词匹配")
        agent_type, confidence = analyze_request_by_keywords(request, logger)
        logger.info(f"关键词分析结果: {agent_type} (置信度: {confidence:.1%})")
        
        # 存入缓存，但标记为关键词分析结果
        query_cache.set(request, {
            "llm_result": agent_type,
            "keyword_result": agent_type,
            "confidence": confidence,
            "method": "keywords_fallback"
        })
        
        return agent_type


def analyze_request_by_keywords(request: str, logger=None) -> tuple:
    """
    通过关键词匹配分析用户请求内容，决定使用哪个代理。
    使用加权系统为关键词分配不同的权重，实现更智能的代理选择。
    优先使用缓存结果，减少计算开销。
    
    Args:
        request: 用户的请求内容
        logger: 可选的日志记录器
        
    Returns:
        tuple: (agent_type, confidence) 
               agent_type是"currency"或"element"表示应该使用的代理类型
               confidence是0到1之间的置信度值
    """
    # 先检查缓存
    cache_entry = query_cache.get(request)
    if cache_entry and "keyword_result" in cache_entry and "confidence" in cache_entry:
        if logger:
            logger.info(f"从缓存获取关键词分析结果: {cache_entry['keyword_result']} (置信度: {cache_entry['confidence']})")
        return cache_entry["keyword_result"], cache_entry["confidence"]
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
            # 确保investment_context变量在所有路径中都被定义
            if 'investment_context' in locals() and investment_context and term.lower() in ['au', 'ag', 'pt', '黄金', '白银', 'gold', 'silver']:
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
            
            # 缓存结果
            query_cache.set(request, {
                "keyword_result": "currency",
                "confidence": confidence,
                "currency_score": currency_score,
                "element_score": element_score,
                "matched_currency_keywords": matched_currency_keywords,
                "matched_element_keywords": matched_element_keywords,
                "special_case_analysis": special_case_analysis
            })
            
            return 'currency', confidence
        else:
            confidence = (element_score / total_score)
            confidence_level = '高' if confidence > 0.7 else '中' if confidence > 0.55 else '低'
            if logger:
                logger.info(f"加权关键词匹配得分 - 货币: {currency_score:.2f}, 元素: {element_score:.2f}, 置信度: {confidence:.1%} ({confidence_level})")
                logger.info(f"基于加权关键词匹配，选择元素代理 (置信度: {confidence:.1%})")
            
            # 缓存结果
            query_cache.set(request, {
                "keyword_result": "element",
                "confidence": confidence,
                "currency_score": currency_score,
                "element_score": element_score,
                "matched_currency_keywords": matched_currency_keywords,
                "matched_element_keywords": matched_element_keywords,
                "special_case_analysis": special_case_analysis
            })
            
            return 'element', confidence
    else:
        # 得分相等时的处理策略
        if logger:
            logger.info("关键词匹配得分相等，默认选择元素代理")
        
        # 缓存结果
        query_cache.set(request, {
            "keyword_result": "element",
            "confidence": 0.5,
            "currency_score": 0,
            "element_score": 0,
            "reason": "得分相等，默认选择元素代理"
        })
        
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
    # 先检查缓存
    cache_key = f"context_analysis_{text}_{term}"
    cache_entry = query_cache.get(cache_key)
    if cache_entry and "result" in cache_entry:
        if logger:
            logger.debug(f"从缓存获取上下文分析结果: '{term}' -> {cache_entry['result']}")
        return cache_entry["result"]
    
    # 术语前后文本窗口长度
    window_size = 100  # 增加窗口大小以捕捉更完整的上下文
    
    # 找到术语的位置 (不区分大小写)
    term_pos = text.lower().find(term.lower())
    if term_pos == -1:
        if logger:
            logger.debug(f"没有在文本中找到术语 '{term}'")
        return 'unknown'
        
    # 提取前后文本窗口
    start = max(0, term_pos - window_size)
    end = min(len(text), term_pos + len(term) + window_size)
    window_text = text[start:end].lower()  # 转为小写以进行不区分大小写的匹配
    
    if logger:
        logger.debug(f"术语 '{term}' 的上下文窗口: '{window_text}'")
    
    # 货币相关的上下文指示词及其权重
    currency_indicators = {
        # 强指示词 (最高权重)
        'currency': 4.0, '货币': 4.0, 'forex': 4.0, 'foreign exchange': 4.0,
        'dollar': 3.5, '美元': 3.5, 'euro': 3.5, '欧元': 3.5, 'yuan': 3.5, '人民币': 3.5,
        'yen': 3.0, '日元': 3.0, 'pound': 3.0, '英镑': 3.0,
        'usd': 3.5, 'eur': 3.5, 'cny': 3.5, 'jpy': 3.5, 'gbp': 3.5,
        
        # 金融和投资术语 (高权重)
        'price': 3.0, '价格': 3.0, 'value': 2.5, '价值': 2.5, 'cost': 2.5, '成本': 2.5, 
        'market': 2.0, '市场': 2.0, 'trade': 2.0, '交易': 2.0, 
        'buy': 2.5, '买': 2.5, 'sell': 2.5, '卖': 2.5, 'bought': 2.5, 'sold': 2.5,
        'money': 2.5, '钱': 2.5, 'exchange': 2.5, '兑换': 2.5,
        'worth': 2.0, '值得': 2.0, 'investment': 3.0, '投资': 3.0, 
        'financial': 2.5, '金融': 2.5, 'portfolio': 2.5, '投资组合': 2.5,
        'fund': 2.2, '基金': 2.2, 'stock': 2.2, '股票': 2.2, 
        'asset': 2.2, '资产': 2.2, 'inflation': 2.5, '通货膨胀': 2.5,
        
        # 贵金属投资术语 (高权重)
        'bullion': 3.5, '金块': 3.5, 'spot price': 3.0, '现货价': 3.0,
        'futures': 2.8, '期货': 2.8, 'troy ounce': 3.0, '金衡盎司': 3.0,
        'karat': 2.8, '纯度': 2.8, 'purity': 2.6, '成色': 2.6,
        'commodity': 2.5, '商品': 2.5, 'premium': 2.2, '溢价': 2.2,
        
        # 金融行业术语 (中等权重)
        'finance': 2.5, '财经': 2.5, 'profit': 2.2, '利润': 2.2,
        'wealth': 2.2, '财富': 2.2, 'capital': 2.2, '资本': 2.2,
        'investor': 2.5, '投资者': 2.5, 'equity': 2.2, '股权': 2.2,
        'bull': 2.2, 'bear': 2.2, '牛市': 2.2, '熊市': 2.2,
        'hedge': 2.2, '对冲': 2.2, 'etf': 2.5, '基金': 2.2,
        'allocation': 2.0, '配置': 2.0, 'liquidity': 2.0, '流动性': 2.0,
        
        # 度量和数量单位 (较低权重，因为化学和金融都会用到)
        'gram': 1.8, '克': 1.8, 'ounce': 2.0, '盎司': 2.0,
        'ton': 1.5, '吨': 1.5, 'kg': 1.5, '公斤': 1.5,
        
        # 新增专门针对贵金属的术语
        'gold market': 3.5, '黄金市场': 3.5, 'gold price': 3.5, '金价': 3.5,
        'silver market': 3.5, '白银市场': 3.5, 'silver price': 3.5, '银价': 3.5,
        'platinum market': 3.5, '铂金市场': 3.5, 'precious metal': 3.0, '贵金属': 3.0,
        'gold reserve': 3.0, '黄金储备': 3.0, 'gold standard': 3.0, '金本位': 3.0,
        'safe haven': 2.8, '避险': 2.8, 'jewelry': 2.5, '珠宝': 2.5,
        'central bank': 2.8, '央行': 2.8, 'treasury': 2.5, '国库': 2.5
    }
    
    # 元素相关的上下文指示词及其权重
    element_indicators = {
        # 化学学科核心术语 (最高权重)
        'element': 4.0, '元素': 4.0, 'periodic table': 4.0, '周期表': 4.0, 
        'chemistry': 4.0, '化学': 4.0, 'chemical': 3.5, '化学的': 3.5,
        'atomic': 3.5, '原子的': 3.5, 'atom': 3.5, '原子': 3.5,
        
        # 化学元素特性 (高权重)
        'proton': 3.0, '质子': 3.0, 'neutron': 3.0, '中子': 3.0, 
        'electron': 3.0, '电子': 3.0, 'isotope': 3.0, '同位素': 3.0, 
        'valence': 2.8, '价': 2.8, 'orbit': 2.8, '轨道': 2.8,
        'shell': 2.8, '电子层': 2.8, 'nucleus': 3.0, '核': 2.8,
        'atomic number': 3.5, '原子序数': 3.5, 'atomic mass': 3.5, '原子质量': 3.5,
        'atomic weight': 3.5, '原子量': 3.5, 'molecular': 3.0, '分子': 3.0, 
        'compound': 3.0, '化合物': 3.0, 'oxidation state': 3.0, '氧化态': 3.0,
        
        # 化学反应和特性 (中等权重)
        'reaction': 2.5, '反应': 2.5, 'synthesis': 2.5, '合成': 2.5, 
        'oxidation': 2.5, '氧化': 2.5, 'reduction': 2.5, '还原': 2.5,
        'property': 2.2, '性质': 2.2, 'catalyst': 2.5, '催化剂': 2.5, 
        'laboratory': 2.5, '实验室': 2.5, 'experiment': 2.5, '实验': 2.5,
        'substance': 2.2, '物质': 2.2, 'material': 1.8, '材料': 1.8,
        
        # 物理状态和特性 (较低权重)
        'melting': 2.2, '熔点': 2.5, 'boiling': 2.2, '沸点': 2.5,
        'conductivity': 2.2, '导电性': 2.5, 'metal': 1.5, '金属': 1.5, 
        'nonmetal': 2.0, '非金属': 2.0, 'metalloid': 2.5, '半金属': 2.5,
        'solid': 1.5, '固体': 1.5, 'liquid': 1.5, '液体': 1.5,
        'gas': 1.5, '气体': 1.5, 'plasma': 2.0, '等离子体': 2.0,
        
        # 化学教育和研究术语
        'mole': 2.5, '摩尔': 2.5, 'scientific': 2.0, '科学': 2.0,
        'solution': 2.0, '溶液': 2.0, 'alloy': 2.2, '合金': 2.2,
        'oxide': 2.5, '氧化物': 2.5, 'reactivity': 2.5, '反应活性': 2.5,
        'group': 2.0, '族': 2.0, 'period': 2.0, '周期': 2.0,
        'noble gas': 2.5, '稀有气体': 2.5, 'halogen': 2.5, '卤素': 2.5,
        'alkali': 2.5, '碱': 2.5, 'alkaline': 2.5, '碱性': 2.5,
        'transition': 2.0, '过渡': 2.0, 'orbital': 2.5, '轨道': 2.5
    }
    
    # 计算匹配的指示词加权总分
    currency_score = 0
    element_score = 0
    
    # 记录匹配到的指示词
    matched_currency_indicators = {}
    matched_element_indicators = {}
    
    # 计算货币指示词的分数
    for indicator, weight in currency_indicators.items():
        if indicator in window_text:
            currency_score += weight
            matched_currency_indicators[indicator] = weight
    
    # 计算元素指示词的分数
    for indicator, weight in element_indicators.items():
        if indicator in window_text:
            element_score += weight
            matched_element_indicators[indicator] = weight
    
    # 货币特有短语及其权重 - 更精确的价格和投资短语匹配
    currency_phrases = {
        # 价格相关短语 (高优先级)
        'price of '+term: 4.0, term+' price': 4.0, 
        'value of '+term: 3.5, term+' value': 3.5,
        term+' cost': 3.5, 'cost of '+term: 3.5, 
        'how much is '+term: 3.5, 'how much does '+term+' cost': 3.8,
        'what is '+term+' worth': 3.8, 'current '+term+' price': 4.0,
        term+' exchange rate': 4.0, term+' rate': 3.0,
        
        # 交易相关短语 (高优先级)
        'buy '+term: 3.8, 'sell '+term: 3.8, 'trade '+term: 3.5,
        'exchange '+term: 3.5, term+' trading': 3.5,
        
        # 投资相关短语 (高优先级)
        term+' investment': 3.8, 'invest in '+term: 3.8, 
        term+' market': 3.2, term+' fund': 3.2, term+' etf': 3.8, 
        term+' stock': 3.2, term+' asset': 3.2, term+' portfolio': 3.2, 
        
        # 金融和储备短语
        term+' reserve': 3.0, term+' account': 3.0, 
        term+' certificate': 3.0, term+' futures': 3.5, 
        term+' commodity': 3.5, term+' bullion': 4.0,
        
        # 度量和纯度短语
        term+' gram': 3.0, term+' ounce': 3.2, term+' kilo': 2.8,
        term+' karat': 3.5, term+' purity': 3.0, term+' fineness': 3.0,
        
        # 金融市场术语
        term+' spot': 3.5, term+' futures': 3.5, term+' options': 3.0,
        term+' hedge': 3.0, term+' allocation': 2.8, term+' position': 2.8,
        
        # 新增的更明确表示货币/投资意图的短语
        term+' as investment': 4.0, term+' as a hedge': 3.5, 
        'investing in '+term: 4.0, term+' investors': 3.5,
        'buy physical '+term: 4.0, term+' holdings': 3.5,
        term+' bars': 3.2, term+' coins': 3.2, term+' bullion': 3.8,
        term+' troy ounce': 4.0, term+' market performance': 3.8,
        term+' price trend': 3.8, term+' price forecast': 3.8
    }
    
    # 元素特有短语及其权重 - 更精确的化学和科学短语匹配
    element_phrases = {
        # 元素特性短语 (高优先级)
        'properties of '+term: 4.0, term+' properties': 4.0, 
        term+' element': 4.5, 'element '+term: 4.5,
        'chemical properties of '+term: 4.5, 'physical properties of '+term: 4.0,
        
        # 原子和分子结构短语 (高优先级)
        term+' atomic': 4.0, 'atomic '+term: 4.0, 
        term+' atom': 4.0, term+' nucleus': 3.8, 
        term+' electron': 3.8, term+' proton': 3.8,
        term+' configuration': 3.8, term+' orbital': 3.8,
        term+' isotope': 4.0, term+' ion': 3.8, 
        
        # 周期表相关短语 (高优先级)
        term+' in periodic': 4.5, term+' in the periodic table': 4.5,
        'periodic table '+term: 4.5, term+' group': 3.5, 
        term+' period': 3.5, term+' in group': 3.8, 
        term+' in period': 3.8, term+' electronic': 3.8,
        
        # 化学反应和化合物短语
        term+' compound': 3.5, term+' molecule': 3.5, 
        term+' reaction': 3.5, term+' oxide': 3.8, 
        term+' in chemistry': 4.0, 'chemical '+term: 3.8,
        term+' oxidation': 3.8, term+' reduction': 3.8,
        term+' bonding': 3.5, term+' catalyst': 3.5,
        
        # 物理特性短语
        term+' melting point': 3.5, term+' boiling point': 3.5,
        term+' density': 3.2, term+' conductivity': 3.5,
        term+' reactivity': 3.5, term+' state': 3.0,
        
        # 更具体的元素科学用语
        'pure '+term: 3.0, term+' sample': 3.2, 
        term+' experiment': 3.5, term+' in lab': 3.8,
        term+' as catalyst': 3.8, term+' ions': 3.5,
        term+' solution': 3.2, term+' alloy': 3.5,
        term+' atomic mass': 4.0, term+' atomic number': 4.0,
        term+' atomic weight': 4.0, term+' valence': 3.8,
        
        # 典型的化学教科书短语
        term+' is a chemical element': 5.0, 
        term+' has atomic number': 4.5,
        term+' is a metal': 3.5, term+' is a nonmetal': 4.0,
        term+' in chemical reactions': 4.0,
        term+' in laboratory': 3.8
    }
    
    # 记录匹配到的特殊短语
    matched_currency_phrases = {}
    matched_element_phrases = {}
    
    # 检查特有短语
    for phrase, weight in currency_phrases.items():
        if phrase in window_text:
            currency_score += weight
            matched_currency_phrases[phrase] = weight
            if logger:
                logger.debug(f"匹配到货币短语: '{phrase}' (权重: {weight})")
    
    for phrase, weight in element_phrases.items():
        if phrase in window_text:
            element_score += weight
            matched_element_phrases[phrase] = weight
            if logger:
                logger.debug(f"匹配到元素短语: '{phrase}' (权重: {weight})")
    
    # 记录匹配情况，便于调试
    if logger:
        if matched_currency_indicators:
            keyword_list = [f"{k}({w})" for k, w in matched_currency_indicators.items()]
            logger.debug(f"'{term}' 匹配到货币指示词: {', '.join(keyword_list)}")
        if matched_element_indicators:
            keyword_list = [f"{k}({w})" for k, w in matched_element_indicators.items()]
            logger.debug(f"'{term}' 匹配到元素指示词: {', '.join(keyword_list)}")
        if matched_currency_phrases:
            phrase_list = [f"{k}({w})" for k, w in matched_currency_phrases.items()]
            logger.debug(f"'{term}' 匹配到货币短语: {', '.join(phrase_list)}")
        if matched_element_phrases:
            phrase_list = [f"{k}({w})" for k, w in matched_element_phrases.items()]
            logger.debug(f"'{term}' 匹配到元素短语: {', '.join(phrase_list)}")
            
    # ========== 特殊情况处理 ==========
    
    # 1. 元素符号特殊处理（Au, Ag, Pt, Pd等）
    if term.lower() in ['au', 'ag', 'pt', 'pd', 'cu', 'fe', 'pb', 'hg', 'sn', 'zn', 'ni']:
        # 检查是否处于明显的元素周期表上下文
        element_context_words = [
            'periodic', 'table', 'element', 'chemistry', 'chemical', 'atomic',
            'molecule', '周期', '周期表', '元素', '化学', '原子', '分子'
        ]
        
        # 检查是否有强烈的元素符号上下文（如周期表讨论）
        strong_element_context = any(w in window_text for w in element_context_words)
        
        # 检查是否有投资或金融相关的上下文
        investment_indicators = [
            '投资', 'invest', '价格', 'price', '价值', 'value', 
            '买', 'buy', '卖', 'sell', '兑换', 'exchange',
            '财务', 'finance', '资产', 'asset', '金融', 'financial',
            '基金', 'etf', 'fund', '股票', 'stock', '市场', 'market',
            '盎司', 'ounce', '克', 'gram', '纯度', 'purity', 'karat',
            '黄金', 'gold', '白银', 'silver', '贵金属', 'precious metal'
        ]
        
        # 投资上下文检测
        investment_context = any(indicator in window_text for indicator in investment_indicators)
        
        # 根据上下文进行不同的处理
        if investment_context and term.lower() in ['au', 'ag', 'pt', 'pd']:
            # 这些符号在投资上下文中可能指贵金属
            # 检查是否有明确的金融短语，如"投资Au"
            premium_finance_phrases = [
                f"{term} 投资", f"投资 {term}", f"{term} investment", 
                f"invest in {term}", f"{term} portfolio", f"{term} etf",
                f"{term} fund", f"{term} price", f"{term} 价格", 
                f"{term} market", f"{term} 市场", f"{term} 盎司", f"{term} ounce"
            ]
            
            explicit_finance = any(phrase.lower() in window_text for phrase in premium_finance_phrases)
            
            if explicit_finance:
                # 明确的金融上下文，强烈增加货币得分
                currency_score += 5.0
                if logger:
                    logger.debug(f"元素符号'{term}'在明确的投资上下文中，极大增加货币匹配权重(+5.0)")
            elif strong_element_context:
                # 虽有投资词但在化学上下文中，可能是在谈论元素的投资/经济价值
                element_score += 3.0
                if logger:
                    logger.debug(f"虽有投资词但元素符号'{term}'在明确的化学上下文中，增加元素匹配权重(+3.0)")
            else:
                # 一般投资上下文但无明确短语，适度增加货币得分
                currency_score += 3.5
                if logger:
                    logger.debug(f"元素符号'{term}'在一般投资上下文中，增加货币匹配权重(+3.5)")
        elif strong_element_context:
            # 明确的化学/元素上下文，强烈增加元素得分
            element_score += 4.5
            if logger:
                logger.debug(f"元素符号'{term}'在明确的化学上下文中，强烈增加元素匹配权重(+4.5)")
        else:
            # 无明确上下文的元素符号，默认偏向元素解释
            element_score += 2.0
            if logger:
                logger.debug(f"元素符号'{term}'无明确上下文，默认增加元素匹配权重(+2.0)")
    
    # 2. 特殊情况：贵金属术语（金、银、铂）
    if term.lower() in ['gold', 'silver', 'platinum', '黄金', '白银', '铂金', '铂']:
        # 检查是否有贵金属投资的明显标志
        investment_signals = [
            'invest', 'price', 'market', 'trade', 'buy', 'sell', 'asset',
            'portfolio', 'fund', 'etf', 'futures', 'ounce', 'karat', 'bullion',
            '投资', '价格', '市场', '交易', '买入', '卖出', '资产',
            '投资组合', '基金', '期货', '盎司', '克拉', '金条'
        ]
        
        # 检查是否有化学元素的明显标志
        chemistry_signals = [
            'element', 'atomic', 'chemistry', 'periodic', 'compound', 'reaction',
            'electron', 'proton', 'neutron', 'isotope', 'oxidation',
            '元素', '原子', '化学', '周期', '化合物', '反应',
            '电子', '质子', '中子', '同位素', '氧化'
        ]
        
        # 计算上下文信号的存在程度
        investment_signal_count = sum(1 for signal in investment_signals if signal in window_text)
        chemistry_signal_count = sum(1 for signal in chemistry_signals if signal in window_text)
        
        # 应用更精确的权重调整
        if investment_signal_count > 0:
            # 贵金属术语与投资信号共现
            investment_boost = min(4.0, 1.5 + 0.5 * investment_signal_count)  # 平滑增益函数
            currency_score += investment_boost
            if logger:
                logger.debug(f"'{term}'与{investment_signal_count}个投资信号共现，增加货币匹配权重(+{investment_boost:.1f})")
            
        if chemistry_signal_count > 0:
            # 贵金属术语与化学信号共现
            chemistry_boost = min(4.0, 1.5 + 0.5 * chemistry_signal_count)  # 平滑增益函数
            element_score += chemistry_boost
            if logger:
                logger.debug(f"'{term}'与{chemistry_signal_count}个化学信号共现，增加元素匹配权重(+{chemistry_boost:.1f})")
            
        # 检测特定的价格查询模式
        price_patterns = [
            f"{term} price", f"price of {term}", f"{term}的价格", 
            f"{term}价格", f"how much is {term}", f"{term}多少钱"
        ]
        
        if any(pattern in window_text for pattern in price_patterns):
            # 明确的价格查询，强烈倾向于货币解释
            currency_score += 4.0
            if logger:
                logger.debug(f"检测到明确的'{term}'价格查询模式，强烈增加货币匹配权重(+4.0)")
    
    # 3. 上下文词频分析 - 考虑周围的词和短语的密度
    currency_density = sum(1 for word in currency_indicators if word in window_text) / len(currency_indicators)
    element_density = sum(1 for word in element_indicators if word in window_text) / len(element_indicators)
    
    # 根据上下文密度进行小幅度调整
    if currency_density > element_density * 1.5:
        # 货币相关词明显更密集
        currency_score += 1.5
        if logger:
            logger.debug(f"货币相关词密度明显更高 ({currency_density:.2f} vs {element_density:.2f})，增加货币匹配权重(+1.5)")
    elif element_density > currency_density * 1.5:
        # 元素相关词明显更密集
        element_score += 1.5
        if logger:
            logger.debug(f"元素相关词密度明显更高 ({element_density:.2f} vs {currency_density:.2f})，增加元素匹配权重(+1.5)")
    
    # 4. 正则表达式检测特定模式 - 如价格查询、元素属性查询
    price_query_pattern = re.compile(r'(price|cost|value|worth|how\s+much|多少钱|价格|价值|值多少)(.*?)('+re.escape(term)+r')', re.IGNORECASE)
    element_query_pattern = re.compile(r'(element|chemical|atomic|周期表|化学元素|原子)(.*?)('+re.escape(term)+r')', re.IGNORECASE)
    
    if price_query_pattern.search(window_text):
        currency_score += 2.0
        if logger:
            logger.debug(f"检测到'{term}'的价格查询模式，增加货币匹配权重(+2.0)")
            
    if element_query_pattern.search(window_text):
        element_score += 2.0
        if logger:
            logger.debug(f"检测到'{term}'的元素查询模式，增加元素匹配权重(+2.0)")
    
    # 保存分析结果
    analysis_result = {
        "currency_score": currency_score,
        "element_score": element_score,
        "matched_currency_indicators": matched_currency_indicators,
        "matched_element_indicators": matched_element_indicators,
        "matched_currency_phrases": matched_currency_phrases,
        "matched_element_phrases": matched_element_phrases
    }
    
    # 做出决策并记录依据
    if currency_score > element_score * 1.1:  # 要求货币得分明显高于元素得分
        result = 'currency'
        if logger:
            logger.debug(f"术语 '{term}' 上下文分析: 货币得分={currency_score:.1f}, 元素得分={element_score:.1f}, 结论=货币相关 (差异明显)")
    elif element_score > currency_score * 1.1:  # 要求元素得分明显高于货币得分
        result = 'element'
        if logger:
            logger.debug(f"术语 '{term}' 上下文分析: 货币得分={currency_score:.1f}, 元素得分={element_score:.1f}, 结论=元素相关 (差异明显)")
    else:
        # 接近平局情况下的决策规则
        if term.lower() in ['au', 'ag', 'pt', 'pd', 'fe', 'cu', 'zn', 'ni', 'pb', 'sn', 'hg']:
            # 接近平局时元素符号更可能是化学元素
            result = 'element'
            reason = "接近平局情况下，元素符号更可能指化学元素"
            if logger:
                logger.debug(f"术语 '{term}' 上下文分析: 货币得分={currency_score:.1f}, 元素得分={element_score:.1f}, {reason}，结论=元素相关")
        elif term.lower() in ['gold', 'silver', 'platinum', '黄金', '白银', '铂金', '铂']:
            # 接近平局时，贵金属名称默认考虑为货币相关（因为更常见）
            result = 'currency'
            reason = "接近平局情况下，贵金属名称默认为货币相关（更常见的用途）"
            if logger:
                logger.debug(f"术语 '{term}' 上下文分析: 货币得分={currency_score:.1f}, 元素得分={element_score:.1f}, {reason}, 结论=货币相关")
        else:
            # 其他情况下的默认行为
            result = 'unknown'
            reason = "接近平局且无明确上下文指示，无法确定"
            if logger:
                logger.debug(f"术语 '{term}' 上下文分析: 货币得分={currency_score:.1f}, 元素得分={element_score:.1f}, {reason}")
    
    # 在判断为unknown的情况下默认回退到更可能的类别
    if result == 'unknown':
        if currency_score >= element_score:
            result = 'currency'
            if logger:
                logger.debug(f"无法明确判断术语'{term}'，回退为货币相关 (货币得分略高或相等)")
        else:
            result = 'element'
            if logger:
                logger.debug(f"无法明确判断术语'{term}'，回退为元素相关 (元素得分略高)")
    
    # 缓存结果
    analysis_result["result"] = result
    query_cache.set(cache_key, analysis_result)
    
    return result


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
