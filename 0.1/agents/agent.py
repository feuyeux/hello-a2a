# filepath: /Users/han/coding/hello-a2a/agents/agent.py
from langchain_ollama import ChatOllama
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables.config import RunnableConfig
from typing import Any, AsyncIterable, Dict, List, Optional, TypedDict, Union, cast
from pydantic import BaseModel, SecretStr
from langchain_openai import ChatOpenAI
from agents.resources.periodic_table import Element
from agents.tools import query_element, find_element, element_to_string, rewrite_query_for_elements
from common.utils.logger import setup_logger

logger = setup_logger("LangGraphAgent")

# 内存保存器，用于保存智能体的状态
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
    elements: List[Element] = []  # 元素列表
    message: str = ""  # 响应消息


class ElementAgent:
    """元素周期表智能体

    这是一个专门用于处理元素周期表查询的智能体。
    它使用Ollama模型来理解用户查询，并通过query_element工具
    从元素周期表中检索元素信息。
    """

    # 支持的内容类型
    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

    # 系统指令，用于指导大模型的行为
    SYSTEM_INSTRUCTION = (
        "你是一个专业的元素周期表智能助手。你的任务是识别用户查询中提到的所有化学元素，并提供它们的详细信息。"
        "\n\n当用户提到任何元素时，不论是常见还是罕见的元素，你必须准确识别它们。"
        "\n例如："
        "\n- 在'给我氢和氧的信息'这个查询中，你必须同时识别'氢'和'氧'这两个元素，并且只识别这两个元素"
        "\n- 在'碳元素和硅元素'这个查询中，你必须同时识别'碳'和'硅'这两个元素，并且只识别这两个元素"
        "\n- 在'Fe和Cu的区别'这个查询中，你必须同时识别'Fe'(铁)和'Cu'(铜)这两个元素符号，并且只识别这两个元素"
        "\n严禁识别用户没有提到的元素，也不要遗漏任何被提及的元素。"
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
        # self.model = ChatOllama(model="qwen3:8b")
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

    def invoke(self, query: str, sessionId: str) -> ElementAPIResponse:
        """
        同步调用智能体处理查询

        参数:
            query: 用户查询文本
            sessionId: 会话ID

        返回:
            ElementAPIResponse: 包含处理结果的字典
        """
        logger.info(f"[SessionID: {sessionId}] 开始处理查询: \"{query}\"")

        # 使用LangGraph模型处理所有查询
        try:
            # 配置字典必须包含 thread_id 以便 MemorySaver 能正确保存状态
            config_dict: Dict[str, Any] = {
                "configurable": {
                    "session_id": sessionId,
                    "thread_id": sessionId  # 使用 sessionId 作为 thread_id
                }
            }

            # 将配置字典转换为 RunnableConfig 类型
            config = cast(RunnableConfig, config_dict)

            # 使用查询改写增强用户查询，让大模型更好地理解用户意图
            enhanced_query = rewrite_query_for_elements(query)
            logger.info(
                f"[SessionID: {sessionId}] 查询改写为: \"{enhanced_query}\"")
            # 使用LangGraph模型进行处理，让模型负责识别和处理元素
            logger.info(f"[SessionID: {sessionId}] 调用LangGraph模型处理查询")
            self.graph.invoke({"input": enhanced_query}, config=config)

            # 使用工具处理响应
            final_response: ElementAPIResponse = self.get_agent_response(
                config_dict)

            # 日志输出
            if final_response.get("content"):
                logger.info(f"[SessionID: {sessionId}] 查询结果:")
                logger.info("=" * 50)
                logger.info(final_response.get("content"))
                logger.info("=" * 50)

            return final_response

        except Exception as e:
            logger.error(
                f"[SessionID: {sessionId}] 处理查询时发生错误: {e}", exc_info=True)
            response: ElementAPIResponse = {"content": "处理请求时出现错误，请重试。"}
            return response

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

            # 配置字典必须包含 thread_id 以便 MemorySaver 能正确保存状态
            config_dict: Dict[str, Any] = {
                "configurable": {
                    "session_id": sessionId,
                    "thread_id": sessionId  # 使用 sessionId 作为 thread_id
                }
            }

            # 将配置字典转换为 RunnableConfig 类型
            # 使用查询改写增强用户查询，让大模型更好地理解用户意图
            config = cast(RunnableConfig, config_dict)
            enhanced_query = rewrite_query_for_elements(query)
            logger.info(
                f"[SessionID: {sessionId}] 原始查询: \"{query}\"")
            logger.info(
                f"[SessionID: {sessionId}] 查询改写为: \"{enhanced_query}\"")
            # 返回初始响应
            response: Dict[str, Any] = {"content": "正在分析您的查询...",
                                        "is_task_complete": False}
            yield response

            # 使用LangGraph模型进行流式处理
            element_count = 0
            for chunk in self.graph.stream({"input": enhanced_query}, config=config):
                if "messages" in chunk:
                    message = chunk["messages"][-1]
                    if hasattr(message, "content"):
                        if isinstance(message, AIMessage):
                            logger.info(
                                f"[SessionID: {sessionId}] 模型思考中: {message.content[:50]}...")
                            response: Dict[str, Any] = {"content": "正在查询元素信息...",
                                                        "is_task_complete": False}
                            yield response
                        elif isinstance(message, ToolMessage):
                            element_count += 1
                            logger.info(
                                f"[SessionID: {sessionId}] 模型收到第 {element_count} 个元素数据，正在处理...")
                            response: Dict[str, Any] = {"content": f"正在处理第 {element_count} 个元素的信息...",
                                                        "is_task_complete": False}
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
            response: Dict[str, Any] = {"content": content,
                                        "is_task_complete": True}
            yield response

        except Exception as e:
            logger.error(
                f"[SessionID: {sessionId}] 流式处理过程中发生错误: {e}", exc_info=True)
            response: Dict[str, Any] = {"content": "处理请求时出现错误，请重试。",
                                        "is_task_complete": True}
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
                elements: List[Element] = structured_response.elements

                # 修正：如果 message 不是字符串，转为字符串
                if not isinstance(message, str):
                    message = str(message)

                # 处理元素列表
                if elements:
                    # 验证返回的元素是否与查询相关
                    relevant_elements: List[Element] = []
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
