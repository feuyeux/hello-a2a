from langchain_core.tools import tool
from typing import List, Optional
from agents.resources.periodic_table import load_periodic_table, Element
import re
from common.utils.logger import setup_logger

logger = setup_logger("ElementTools")

# 加载元素周期表数据
PERIODIC_TABLE = load_periodic_table()


def element_to_string(elem: Element) -> str:
    """将元素对象转换为格式化的字符串展示"""
    return (
        f"元素名称: {elem.name} ({elem.chinese_name})\n"
        f"符号: {elem.symbol}\n"
        f"原子序数: {elem.atomic_number}\n"
        f"原子量: {elem.atomic_weight}\n"
        f"周期: {elem.period}\n"
        f"族: {elem.group}"
    )


# 定义一个直接用于元素查询的函数，不作为工具使用
def find_element(
    name: Optional[str] = None,
    symbol: Optional[str] = None,
    atomic_number: Optional[int] = None,
    chinese_name: Optional[str] = None
) -> List[Element]:
    """查询元素周期表。可根据元素名称、符号、原子序数或中文名称查询。返回Element对象列表，未找到则返回空列表。"""
    logger.info(
        f"查询元素: 名称={name}, 符号={symbol}, 原子序数={atomic_number}, 中文名称={chinese_name}")
    elements = []
    # 按照不同的查询条件查找元素
    if name:
        element = PERIODIC_TABLE.get_by_name(name)
        if element:
            logger.info(
                f"通过名称找到元素: {element.name}, 符号: {element.symbol}, 原子序数: {element.atomic_number}")
            elements.append(element)

    elif symbol:
        try:
            element = PERIODIC_TABLE[symbol]
            if element:
                logger.info(
                    f"通过符号找到元素: {element.name}, 符号: {element.symbol}, 原子序数: {element.atomic_number}")
                elements.append(element)
        except KeyError:
            logger.info(f"未找到符号为 {symbol} 的元素")

    elif atomic_number:
        try:
            element = PERIODIC_TABLE[atomic_number]
            if element:
                logger.info(
                    f"通过原子序数找到元素: {element.name}, 符号: {element.symbol}, 原子序数: {element.atomic_number}")
                elements.append(element)
        except KeyError:
            logger.info(
                f"未找到原子序数为 {atomic_number} 的元素")

    elif chinese_name:
        element = PERIODIC_TABLE.get_by_chinese_name(chinese_name)
        if element:
            logger.info(
                f"通过中文名称找到元素: {element.chinese_name}, 符号: {element.symbol}, 原子序数: {element.atomic_number}")
            elements.append(element)

    if not elements:
        logger.warning("未找到匹配条件的元素")

    return elements


# 作为工具供LangChain使用的函数版本
@tool
def query_element(
    name: Optional[str] = None,
    symbol: Optional[str] = None,
    atomic_number: Optional[int] = None,
    chinese_name: Optional[str] = None
) -> List[Element]:
    """查询元素周期表。可根据元素名称、符号、原子序数或中文名称查询。返回Element对象列表，未找到则返回空列表。"""
    return find_element(name=name, symbol=symbol, atomic_number=atomic_number, chinese_name=chinese_name)


def rewrite_query_for_elements(query: str) -> str:
    """对用户查询进行改写，以便更好地让大模型理解用户意图，精确识别用户提到的元素

    参数:
        query: 用户查询文本

    返回:
        改写后的查询字符串，更明确地表达用户意图
    """
    # 先进行简单的标准化处理
    normalized_query = query.strip()

    # 构建增强查询，强调只处理明确提及的元素
    enhanced_query = (
        f"原始查询：{normalized_query}\n\n"
        f"请仔细分析，只识别上述查询中明确提及的化学元素（中文名称、英文名称或元素符号）。"
        f"例如，'碳元素和硅元素'中明确提及了'碳'和'硅'两个元素。"
        f"不要添加未被提及的元素，也不要遗漏任何被提及的元素。\n"
        f"对每个识别到的元素，都需要单独调用query_element工具获取其详细信息。"
        f"查询时优先使用中文名称作为参数，例如查询'碳'应使用：query_element(chinese_name='碳')。\n"
        f"确保返回的elements列表中只包含用户实际提及的元素，不要添加猜测的元素。"
    )

    return enhanced_query
