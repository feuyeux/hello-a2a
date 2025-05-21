"""
Element Agent tools module
"""
import logging
from langchain_core.tools import tool
from typing import List, Optional
from resources.periodic_table import load_periodic_table, Element

logger = logging.getLogger(__name__)

# 加载元素周期表数据
PERIODIC_TABLE = load_periodic_table()


def element_to_string(elem) -> str:
    """将元素对象转换为格式化的字符串展示
    
    参数:
        elem: Element对象或者包含元素属性的字典
    """
    try:
        # Handle both Element objects and dictionaries
        if isinstance(elem, dict):
            # Create formatted string from dictionary
            name = elem.get('name', 'Unknown')
            chinese_name = elem.get('chinese_name', 'Unknown')
            symbol = elem.get('symbol', 'Unknown')
            atomic_number = elem.get('atomic_number', 'Unknown')
            atomic_weight = elem.get('atomic_weight', 'Unknown')
            period = elem.get('period', 'Unknown')
            group = elem.get('group', 'Unknown')
            # Try to get additional properties if available
            category = elem.get('category', '')
            color = elem.get('color', '')
            discovered_by = elem.get('discovered_by', '')
            phase = elem.get('phase', '')
        else:
            # Create formatted string from Element object
            # Check if it's a proper Element object with the right attributes
            if hasattr(elem, 'name') and hasattr(elem, 'atomic_number'):
                name = elem.name
                chinese_name = elem.chinese_name if hasattr(elem, 'chinese_name') else 'Unknown'
                symbol = elem.symbol
                atomic_number = elem.atomic_number
                atomic_weight = elem.atomic_weight
                period = elem.period
                group = elem.group
                # Get additional properties if available
                category = getattr(elem, 'category', '')
                color = getattr(elem, 'color', '')
                discovered_by = getattr(elem, 'discovered_by', '')
                phase = getattr(elem, 'phase', '')
            else:
                # It might be an Element-like object but without all properties
                logger.warning(f"Element object missing required attributes: {elem}")
                name = getattr(elem, 'name', 'Unknown')
                chinese_name = getattr(elem, 'chinese_name', 'Unknown')
                symbol = getattr(elem, 'symbol', 'Unknown')
                atomic_number = getattr(elem, 'atomic_number', 'Unknown')
                atomic_weight = getattr(elem, 'atomic_weight', 'Unknown')
                period = getattr(elem, 'period', 'Unknown')
                group = getattr(elem, 'group', 'Unknown')
                category = getattr(elem, 'category', '')
                color = getattr(elem, 'color', '')
                discovered_by = getattr(elem, 'discovered_by', '')
                phase = getattr(elem, 'phase', '')
        
        # For debugging purposes
        logger.info(f"Element properties: name={name}, symbol={symbol}, atomic_number={atomic_number}, "
                   f"atomic_weight={atomic_weight}, period={period}, group={group}")
        
        # Construct basic info first
        basic_info = (
            f"元素名称: {name} ({chinese_name})\n"
            f"符号: {symbol}\n"
            f"原子序数: {atomic_number}\n"
            f"原子量: {atomic_weight}\n"
            f"周期: {period}\n"
            f"族: {group}\n"
        )
        
        # Add additional properties if they are available
        additional_info = ""
        if category:
            additional_info += f"类别: {category}\n"
        if color:
            additional_info += f"颜色: {color}\n"
        if discovered_by:
            additional_info += f"发现者: {discovered_by}\n"
        if phase:
            additional_info += f"状态: {phase}\n"
            
        return basic_info + additional_info
        
    except Exception as e:
        logger.error(f"Error formatting element: {e}", exc_info=True)
        return f"元素信息格式化错误: {str(e)}"


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
    
    # 直接处理"氢元素"这样的常见查询
    if not chinese_name and not name and not symbol and not atomic_number:
        # 如果没有提供任何参数，仍尝试返回氢元素作为默认值
        logger.info("没有提供查询参数，尝试返回氢元素作为默认值")
        try:
            element = PERIODIC_TABLE["H"]
            if element:
                logger.info(f"返回默认元素: {element.name}, 符号: {element.symbol}, 原子序数: {element.atomic_number}")
                elements.append(element)
                return elements
        except Exception:
            pass
    
    # 预处理: 清除输入的额外空格和标点
    if name:
        name = name.strip()
        # 处理常见查询，如"hydrogen element"
        if name.lower().endswith(" element"):
            name = name.lower().replace(" element", "")
    
    if symbol:
        symbol = symbol.strip()
    
    if chinese_name:
        chinese_name = chinese_name.strip()
        # 移除"元素"后缀，比如将"氢元素"变为"氢"
        if chinese_name.endswith("元素"):
            chinese_name = chinese_name[:-2]
    
    # 特殊处理常见的元素查询
    # 1. 直接处理"氢"元素
    if (chinese_name and chinese_name == "氢") or (name and name.lower() == "hydrogen") or (symbol and symbol.upper() == "H"):
        try:
            element = PERIODIC_TABLE["H"]
            if element:
                logger.info(f"直接查找氢元素: {element.name}, 符号: {element.symbol}, 原子序数: {element.atomic_number}")
                elements.append(element)
                return elements
        except Exception:
            pass
    
    # 2. 处理其他常见元素的英文名称
    if name and not elements:
        name_lower = name.lower()
        element_map = {
            "hydrogen": "H", "helium": "He", "carbon": "C", 
            "oxygen": "O", "nitrogen": "N", "iron": "Fe",
            "copper": "Cu", "gold": "Au", "silver": "Ag",
            "sodium": "Na", "calcium": "Ca", "potassium": "K"
        }
        
        if name_lower in element_map:
            symbol = element_map[name_lower]
        
    # 按照不同的查询条件查找元素
    if chinese_name:
        element = PERIODIC_TABLE.get_by_chinese_name(chinese_name)
        if element:
            logger.info(
                f"通过中文名称找到元素: {element.chinese_name}, 符号: {element.symbol}, 原子序数: {element.atomic_number}")
            elements.append(element)
            return elements  # 优先返回中文名称匹配结果
    
    if name:
        element = PERIODIC_TABLE.get_by_name(name)
        if element:
            logger.info(
                f"通过名称找到元素: {element.name}, 符号: {element.symbol}, 原子序数: {element.atomic_number}")
            elements.append(element)

    if symbol and not elements:
        try:
            element = PERIODIC_TABLE[symbol]
            if element:
                logger.info(
                    f"通过符号找到元素: {element.name}, 符号: {element.symbol}, 原子序数: {element.atomic_number}")
                elements.append(element)
        except KeyError:
            logger.info(f"未找到符号为 {symbol} 的元素")

    if atomic_number and not elements:
        try:
            element = PERIODIC_TABLE[atomic_number]
            if element:
                logger.info(
                    f"通过原子序数找到元素: {element.name}, 符号: {element.symbol}, 原子序数: {element.atomic_number}")
                elements.append(element)
        except KeyError:
            logger.info(
                f"未找到原子序数为 {atomic_number} 的元素")

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
    
    # 提取可能的元素名称
    # 预处理常见查询模式
    element_hint = ""
    if "氢" in normalized_query or "hydrogen" in normalized_query.lower() or "h元素" in normalized_query.lower():
        element_hint = "用户查询的是氢(Hydrogen, H)元素，应该调用query_element(symbol='H')或query_element(chinese_name='氢')"
    elif "iron" in normalized_query.lower() or "fe" in normalized_query.lower():
        element_hint = "用户查询的是铁(Iron, Fe)元素，应该调用query_element(symbol='Fe')"
    
    # 构建增强查询，强调只处理明确提及的元素
    enhanced_query = (
        f"用户查询：{normalized_query}\n\n"
        f"{element_hint}\n\n" if element_hint else ""
        f"请仔细分析，只识别上述用户查询中明确提及的化学元素（中文名称、英文名称或元素符号）。"
        f"绝对不要添加未被提及的元素，也不要遗漏任何被提及的元素。\n"
        f"查询步骤：\n"
        f"1. 识别用户查询中提到的元素名称（中文或英文）或元素符号\n"
        f"2. 对每个识别到的元素，使用合适的参数调用query_element工具：\n"
        f"   - 对于中文名称（如'氢'），使用query_element(chinese_name='氢')\n"
        f"   - 对于英文名称（如'Hydrogen'），使用query_element(name='Hydrogen')\n"
        f"   - 对于元素符号（如'H'），使用query_element(symbol='H')\n"
        f"3. 只返回查询到的元素，不要添加额外的元素\n\n"
        f"警告：不要返回碳(C)和硅(Si)元素，除非用户明确查询了这些元素。这非常重要！"
    )
    
    return enhanced_query
