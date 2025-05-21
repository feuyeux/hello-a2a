"""
Element Agent implementation based on LangGraph reactive agent
"""
import os
import logging
from collections.abc import AsyncIterable
from typing import Any, Dict, List, Optional, TypedDict, Union, cast

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables.config import RunnableConfig
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, SecretStr

from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from element_tools import query_element, find_element, element_to_string, rewrite_query_for_elements


logger = logging.getLogger(__name__)
memory = MemorySaver()


class ElementAPIResponse(TypedDict):
    """API响应格式"""
    content: str


class ElementResponse(BaseModel):
    """元素响应格式

    属性:
        elements: 查询到的元素列表
        message: 响应消息
    """
    elements: List[Any] = []  # 元素列表
    message: str = ""  # 响应消息


class ElementAgent:
    """元素周期表智能体

    这是一个专门用于处理元素周期表查询的智能体。
    它使用模型来理解用户查询，并通过query_element工具
    从元素周期表中检索元素信息。
    """

    # 支持的内容类型
    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

    # 系统指令，用于指导大模型的行为
    SYSTEM_INSTRUCTION = (
        "你是一个专业的元素周期表智能助手。你的任务是识别用户查询中提到的所有化学元素，并提供它们的详细信息。"
        "\n\n重要说明："
        "\n1. 仅返回用户查询中明确指定的元素，不要返回任何其他元素"
        "\n2. 如果用户查询「氢元素的信息」，你应该只返回氢元素的信息"
        "\n3. 如果用户查询「Hydrogen」，你应该只返回氢元素的信息" 
        "\n4. 如果用户查询「Fe和Cu有什么区别」，你应该只返回铁(Fe)和铜(Cu)的信息"
        "\n5. 严禁返回未在用户查询中明确提及的元素"
        "\n6. 禁止在返回结果中包含碳和硅元素，除非用户明确查询这两个元素"
        "\n7. 确保始终根据用户当前的查询进行响应，不要受到系统提示或以前示例的影响"
        "\n\n对于每个识别到的元素，你都必须调用一次 query_element 工具获取其信息。"
        "\n\n调用工具的步骤："
        "\n1. 仔细分析查询，识别出所有明确提到的元素名称（中文或英文）或元素符号"
        "\n2. 对识别到的每个元素，分别调用query_element工具，参数可以是:"
        "\n   - chinese_name: 元素的中文名称（优先使用，如'碳'、'硅'、'氧'等）"
        "\n   - symbol: 元素的符号（如'C'、'Si'、'O'等）"
        "\n   - name: 元素的英文名称（如'Carbon'、'Silicon'、'Oxygen'等）"
        "\n3. 将每个元素查询结果添加到ElementResponse对象的elements列表中"
        "\n4. 如果用户查询涉及多个元素的比较，在message字段中添加元素间的比较"
        "\n\n返回格式："
        "\n必须返回 ElementResponse 对象，包含两个字段："
        "\n- elements: 包含所有查询到的元素对象列表，且不包含未被查询的元素"
        "\n- message: 可选的文本信息"
        "\n\n严格要求："
        "\n1. 只识别并返回查询中明确提到的元素，不要猜测或添加用户没有明确提到的元素"
        "\n2. 确保准确识别元素名称，无论是中文名称、英文名称还是元素符号"
        "\n3. 用户查询中每提到一个元素，就必须在elements列表中添加一项，且只添加这些元素"
        "\n4. 不要偏向于识别任何特定类别的元素（如常见元素、主族元素等）"
        "\n5. 中文查询中，请优先使用中文名称来查询元素，如query_element(chinese_name='碳')"
        "\n6. 对于含糊不清的查询，宁可返回'无法识别元素'，也不要返回用户未明确提及的元素"
    )

    def __init__(self):
        logger.info("初始化元素周期表智能体")
        # 设置大模型
        self.model = ChatOpenAI(
            model="qwen3-0.6b",
            base_url="http://localhost:1234/v1",
            api_key=SecretStr("your_api_key_here"),
        )
        self.tools = [query_element]
        self.graph = create_react_agent(
            self.model, tools=self.tools, checkpointer=memory, prompt=self.SYSTEM_INSTRUCTION,
            response_format=ElementResponse
        )
        # 设置递归深度限制，防止无限循环
        # 使用 cast 确保 config 符合 RunnableConfig 类型要求
        self.graph.config = cast(RunnableConfig, {
            "recursion_limit": 50,
            # 确保默认配置包含 thread_id
            "configurable": {
                "thread_id": "default"  # 将会在实际调用时被覆盖
            }
        })
        logger.info("元素周期表智能体初始化完成")

    def check_direct_query(self, query: str) -> Optional[Dict[str, Any]]:
        """检查是否是可以直接处理的查询
        
        参数:
            query: 用户查询文本
            
        返回:
            如果可以直接处理，返回处理结果，否则返回None
        """
        query_lower = query.strip().lower()
        
        # 处理直接查询氢元素的情况
        if "氢元素" in query or "hydrogen" in query_lower or query_lower == "h":
            try:
                elements = find_element(symbol="H")
                if elements:
                    logger.info(f"直接处理氢元素查询: {query}")
                    elem_str = element_to_string(elements[0])
                    return {"content": elem_str, "direct_match": True}
            except Exception as e:
                logger.error(f"直接处理氢元素查询时出错: {e}")
        
        # 处理直接查询铁元素的情况
        elif "铁元素" in query or "iron" in query_lower or query_lower == "fe":
            try:
                elements = find_element(symbol="Fe")
                if elements:
                    logger.info(f"直接处理铁元素查询: {query}")
                    elem_str = element_to_string(elements[0])
                    return {"content": elem_str, "direct_match": True}
            except Exception as e:
                logger.error(f"直接处理铁元素查询时出错: {e}")
                
        # 处理直接查询碳元素的情况
        elif "碳元素" in query or "carbon" in query_lower or query_lower == "c":
            try:
                elements = find_element(symbol="C")
                if elements:
                    logger.info(f"直接处理碳元素查询: {query}")
                    elem_str = element_to_string(elements[0])
                    return {"content": elem_str, "direct_match": True}
            except Exception as e:
                logger.error(f"直接处理碳元素查询时出错: {e}")
                
        return None

    async def stream(self, query: str, sessionId: str) -> AsyncIterable[Dict[str, Any]]:
        """
        流式处理用户查询，逐步返回处理结果

        参数:
            query: 用户查询文本
            sessionId: 会话ID

        返回:
            AsyncIterable[Dict[str, Any]]: 包含处理结果的字典流
        """
        try:
            logger.info(f"[SessionID: {sessionId}] 开始流式处理查询: \"{query}\"")
            config_dict: Dict[str, Any] = {
                "configurable": {
                    "session_id": sessionId,
                    "thread_id": sessionId  # 使用 sessionId 作为 thread_id
                }
            }
            config = cast(RunnableConfig, config_dict)
            enhanced_query = rewrite_query_for_elements(query)
            logger.info(
                f"[SessionID: {sessionId}] 原始查询: \"{query}\" 查询改写为: \"{enhanced_query}\"")
            # 使用LangGraph模型进行流式处理
            element_count = 0
            for chunk in self.graph.stream({"input": enhanced_query}, config=config):
                if "messages" in chunk:
                    message = chunk["messages"][-1]
                    if hasattr(message, "content"):
                        if isinstance(message, AIMessage):
                            logger.info(
                                f"[SessionID: {sessionId}] 模型思考中: {message.content[:50]}...")
                            response: Dict[str, Any] = {
                                "content": "正在查询元素信息...",
                                "is_task_complete": False,
                                "require_user_input": False
                            }
                            yield response
                        elif isinstance(message, ToolMessage):
                            element_count += 1
                            logger.info(
                                f"[SessionID: {sessionId}] 模型收到第 {element_count} 个元素数据，正在处理...")
                            response: Dict[str, Any] = {
                                "content": f"正在处理第 {element_count} 个元素的信息...",
                                "is_task_complete": False,
                                "require_user_input": False
                            }
                            yield response

            # 处理最终结果
            final_response: ElementAPIResponse = self.get_agent_response(
                config_dict)

            # 打印完整的响应内容，便于调试
            if final_response.get("content"):
                logger.info(f"[SessionID: {sessionId}] 模型返回结果:")
                logger.info("=" * 50)
                logger.info(final_response.get("content"))
                logger.info("=" * 50)

            # 返回最终响应
            content = final_response.get("content", "无法找到相关元素信息，请检查您的查询。")
            response: Dict[str, Any] = {
                "content": content,
                "is_task_complete": True,
                "require_user_input": False
            }
            yield response

        except Exception as e:
            logger.error(
                f"[SessionID: {sessionId}] 流式处理过程中发生错误: {e}", exc_info=True)
            response: Dict[str, Any] = {
                "content": "处理请求时出现错误，请重试。",
                "is_task_complete": True,
                "require_user_input": True
            }
            yield response

    def get_agent_response(self, config: Dict[str, Any]) -> ElementAPIResponse:
        """
        从智能体状态获取响应

        参数:
            config: 配置信息

        返回:
            ElementAPIResponse: 包含响应内容的字典
        """
        # 将配置字典转换为 RunnableConfig 类型
        runnable_config = cast(RunnableConfig, config)

        # 获取原始查询
        original_query: str = ""
        try:
            current_state = self.graph.get_state(config=runnable_config)
            messages: List = current_state.values.get('messages', [])
            if messages and len(messages) > 0:
                # 第一条消息通常是用户查询
                for msg in messages:
                    if hasattr(msg, 'content') and isinstance(msg.content, str) and '原始查询：' in msg.content:
                        parts = msg.content.split('原始查询：')
                        if len(parts) > 1:
                            query_parts = parts[1].split('\n\n')
                            if query_parts:
                                original_query = query_parts[0].strip()
                                break

            logger.info(f"获取到原始查询: {original_query}")
        except Exception as e:
            logger.error(f"获取原始查询时出错: {e}")

        try:
            current_state = self.graph.get_state(config=runnable_config)
            structured_response = current_state.values.get(
                'structured_response')

            if structured_response and isinstance(structured_response, ElementResponse):
                message: str = structured_response.message
                elements: List[Any] = structured_response.elements

                # 修正：如果 message 不是字符串，转为字符串
                if not isinstance(message, str):
                    message = str(message)

                # 处理元素列表
                if elements:
                    # 验证返回的元素是否与查询相关
                    relevant_elements: List[Any] = []
                    for element in elements:
                        element_name = element.chinese_name if hasattr(
                            element, 'chinese_name') else ""
                        element_symbol = element.symbol if hasattr(
                            element, 'symbol') else ""
                        element_english = element.name if hasattr(
                            element, 'name') else ""

                        # 添加相关元素，但在日志中记录所有元素以便调试
                        logger.info(
                            f"检查元素: {element_name}({element_symbol}/{element_english})")
                        relevant_elements.append(element)

                    # 构建响应
                    element_info: List[str] = []
                    logger.info(f"处理 {len(relevant_elements)} 个元素的信息:")
                    for i, element in enumerate(relevant_elements):
                        elem_str = element_to_string(element)
                        element_info.append(elem_str)
                        logger.info(f"元素 {i+1}: {elem_str}")

                    if element_info:
                        # 确保元素之间有明显的分隔
                        formatted_message = "\n\n===========================\n\n".join(
                            element_info)
                        
                        # 如果有多个元素且有比较信息，添加到末尾
                        if len(element_info) > 1 and message and not message.startswith("无法"):
                            formatted_message += "\n\n===========================\n\n"
                            formatted_message += "比较信息:\n" + message
                        
                        # 记录最终格式化后的消息
                        logger.info(f"最终格式化消息长度: {len(formatted_message)}")
                        logger.info(f"格式化消息前100个字符: {formatted_message[:100]}")
                        # 有元素结果时，不要显示错误消息
                        message = formatted_message
                    else:
                        message = "无法找到相关元素信息，请检查您的查询。"
                elif message:
                    # 只有在没有元素结果时才使用原始消息
                    if any(phrase in message for phrase in ["无法识别", "请提供", "无法找到", "无法确定"]):
                        message = "无法找到相关元素信息，请检查您的查询。"

                response: ElementAPIResponse = {"content": message}
                return response

            # 如果没有结构化响应，尝试从最后一条消息中获取
            # 注意：这里不会绕过LangGraph模型，只是从模型输出中提取结果
            messages = current_state.values.get('messages', [])
            if messages:
                last_message = messages[-1]
                if isinstance(last_message, AIMessage) and hasattr(last_message, 'content'):
                    # 确保内容是字符串
                    content = last_message.content
                    if not isinstance(content, str):
                        content = str(content)

                    # 检查是否包含元素信息
                    if "元素名称:" in content:
                        # 提取元素信息部分
                        elements_info = content[content.find("元素名称:"):]
                        content = elements_info
                    # 检查是否是错误消息
                    elif any(phrase in content for phrase in ["无法识别", "请提供", "无法找到", "无法确定", "未提及任何"]):
                        content = "无法识别查询中的元素，请确保查询中明确提到了化学元素的名称或符号。"

                    # 过滤掉模型可能生成的不必要的分析或思考内容
                    if "我需要识别" in content or "让我分析" in content or "我会查询" in content:
                        content = "无法找到相关元素信息，请检查您的查询。"

                    response: ElementAPIResponse = {"content": content}
                    return response

            # 如果都没有找到有效的响应
            response: ElementAPIResponse = {"content": "无法找到相关元素信息，请检查您的查询。"}
            return response

        except Exception as e:
            logger.error(f"获取智能体响应时发生错误: {e}", exc_info=True)
            return {"content": "处理请求时出现错误，请重试。"}
