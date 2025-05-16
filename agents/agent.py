from langchain_ollama import ChatOllama
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import AIMessage, ToolMessage
from typing import Any, Dict, AsyncIterable, Literal
from pydantic import BaseModel
from agents.periodic_table import PERIODIC_TABLE
from langchain_openai import ChatOpenAI
import re
from common.utils.logger import setup_logger

logger = setup_logger("LangGraphAgent")

# 内存保存器，用于保存智能体的状态
memory = MemorySaver()

class ResponseFormat(BaseModel):
    """以该格式回复用户。

    属性:
        status: 回复状态，可选值有input_required（需要用户输入）、completed（任务已完成）和error（发生错误）
        message: 回复内容，包含实际的文本消息
    """
    status: Literal["input_required", "completed",
                    "error"] = "input_required"  # 回复状态，默认为需要用户输入
    message: str

@tool
def query_element(
    name: str = None,
    symbol: str = None,
    atomic_number: int = None,
    chinese_name: str = None
) -> dict:
    """查询元素周期表。可根据元素名称、符号、原子序数或中文名称查询。"""
    logger.info(
        f"Querying element: name={name}, symbol={symbol}, atomic_number={atomic_number}, chinese_name={chinese_name}")
    for elem in PERIODIC_TABLE:
        if name and elem["name"].lower() == name.lower():
            logger.info(
                f"Element found by name: {elem['name']}, symbol: {elem['symbol']}, atomic_number: {elem['atomic_number']}")
            return elem
        if symbol and elem["symbol"].lower() == symbol.lower():
            logger.info(
                f"Element found by symbol: {elem['name']}, symbol: {elem['symbol']}, atomic_number: {elem['atomic_number']}")
            return elem
        if atomic_number and elem["atomic_number"] == atomic_number:
            logger.info(
                f"Element found by atomic number: {elem['name']}, symbol: {elem['symbol']}, atomic_number: {elem['atomic_number']}")
            return elem
        if chinese_name and elem["chinese_name"].strip() == chinese_name.strip():
            logger.info(
                f"Element found by chinese_name: {elem['chinese_name']}, symbol: {elem['symbol']}, atomic_number: {elem['atomic_number']}")
            return elem
    return {"error": "Element not found. Please check your input."}


def format_element_info(elem: dict) -> str:
    """格式化输出元素的详细信息"""
    return (
        f"元素名称: {elem['name']} ({elem['chinese_name']})\n"
        f"符号: {elem['symbol']}\n"
        f"原子序数: {elem['atomic_number']}\n"
        f"原子量: {elem['atomic_weight']}\n"
        f"周期: {elem['period']}\n"
        f"族: {elem['group']}"
    )

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
        "你是一个元素周期表智能助手。你的唯一任务是使用 query_element 工具，回答关于化学元素及其性质的问题。"
        "严格按照用户输入内容调用 query_element 工具，不要对元素名称、符号等参数做任何翻译、编码或变换。"
        "如果用户问题涉及多个元素，必须依次分别调用 query_element 工具，并将每个元素的结果用换行拼接成一个字符串，作为最终 message 返回。"
        "最终 message 必须明确包含每个元素的详细信息文本，包括元素的名称、符号、原子序数等信息。"
        "输出格式示例：\\n元素名称: Carbon (碳)\\n符号: C\\n原子序数: 6\\n...\\n\\n元素名称: Silicon (硅)\\n符号: Si\\n原子序数: 14\\n..."
        "不允许只回复确认或泛泛内容，必须包含完整的元素查询结果。"
        "如果用户的问题不是关于化学元素或元素周期表，请礼貌地说明你只能回答元素周期表相关问题。"
        "如果需要用户补充信息，设置 response status 为 input_required，并在 message 里说明需要哪些信息。"
        "如果遇到错误，设置 response status 为 error，并在 message 里返回错误原因。"
        "如果请求已完成，设置 response status 为 completed。"
    )

    def __init__(self):
        logger.info("Initializing ElementAgent")
        # self.model = ChatOllama(model="qwen3:8b")
        self.model = ChatOpenAI(
            model="qwen3-0.6b",
            base_url="http://localhost:1234/v1",
            api_key="your_api_key_here",
        )
        self.tools = [query_element]
        self.graph = create_react_agent(
            self.model, tools=self.tools, checkpointer=memory, prompt=self.SYSTEM_INSTRUCTION,
            response_format=ResponseFormat
        )
        # 设置递归深度限制，防止无限循环
        if getattr(self.graph, "config", None) is None:
            self.graph.config = {}
        self.graph.config["recursion_limit"] = 50
        logger.info("ElementAgent initialized successfully")

    def invoke(self, query, sessionId) -> str:
        """
        同步调用智能体处理查询

        参数:
            query: 用户查询文本
            sessionId: 会话ID

        返回:
            字典，包含处理结果
        """
        logger.info(f"[SessionID: {sessionId}] 开始处理查询: \"{query}\"")

        # 优先尝试直接解析元素名称
        # 构建所有元素的中英文名和符号集合
        names = set()
        symbols = set()
        chinese_names = set()
        for elem in PERIODIC_TABLE:
            names.add(elem["name"].lower())
            symbols.add(elem["symbol"].lower())
            chinese_names.add(elem["chinese_name"].strip())

        # 提取所有可能的元素名
        element_names = set()
        # 更全面的元素提取正则表达式，能够处理中文元素名
        # 对于常见的中文元素名特别处理
        common_elements = ["氢", "氦", "锂", "铍", "硼", "碳", "氮", "氧", "氟", "氖",
                           "钠", "镁", "铝", "硅", "磷", "硫", "氯", "氩", "钾", "钙"]

        # 从查询中直接寻找中文元素名
        for element in common_elements:
            if element in query:
                element_names.add(element)

        # 使用原有的正则表达式作为备选
        if not element_names:
            # 尝试清理输入文本，移除常见的干扰词
            cleaned_query = query
            for noise in ["元素", "和", "的", "信息", "详情", "属性", "特性"]:
                cleaned_query = cleaned_query.replace(noise, " ")
            
            # 在清理后的文本中查找元素
            for word in re.findall(r"[\u4e00-\u9fa5]{1,2}|[A-Za-z]+", cleaned_query):
                w = word.strip()
                if w in chinese_names or w.lower() in names or w.lower() in symbols:
                    element_names.add(w)

        # 日志输出已识别的元素
        if element_names:
            logger.info(
                f"[SessionID: {sessionId}] 从查询中提取到元素: {', '.join(element_names)}")
        else:
            logger.warning(f"[SessionID: {sessionId}] 未从查询中提取到有效元素")
            return {"is_task_complete": False, "require_user_input": True,
                    "content": "未检测到有效元素名，请输入元素的中文名、英文名或符号。"}

        results = []
        for name in element_names:
            # 优先判断是否为中文
            try:
                # 准备输入参数字典
                tool_input = {}
                if not name.isascii():
                    tool_input = {"chinese_name": name}
                elif name.lower() in names:
                    tool_input = {"name": name}
                elif name.lower() in symbols:
                    tool_input = {"symbol": name}

                # 直接调用函数而不是工具对象
                elem_info = query_element.func(**tool_input)
            except Exception as e:
                logger.error(
                    f"[SessionID: {sessionId}] 调用query_element工具失败: {e}", exc_info=True)
                elem_info = {
                    "error": "Failed to query element. Please try again."}

            if isinstance(elem_info, dict) and "error" in elem_info:
                results.append(f"未找到元素: {name}")
            else:
                # 对元素信息进行格式化后再添加到结果
                results.append(format_element_info(elem_info))

        message = "\n\n".join(results)
        # 输出最终结果日志
        logger.info(f"[SessionID: {sessionId}] ✨ 返回元素查询结果:")
        logger.info("=" * 50)
        logger.info(message)
        logger.info("=" * 50)

        return {"is_task_complete": True, "require_user_input": False, "content": message}

    async def stream(self, query, sessionId) -> AsyncIterable[Dict[str, Any]]:
        """
        流式处理用户查询

        参数:
            query: 用户查询文本
            sessionId: 会话ID

        返回:
            AsyncIterable[Dict[str, Any]]: 异步迭代器，返回处理结果流
        """
        logger.info(f"[SessionID: {sessionId}] 开始流式处理查询: \"{query}\"")

        # 尝试直接处理常见查询模式
        try:
            # 构建所有元素的中英文名和符号集合
            names = set()
            symbols = set()
            chinese_names = set()
            for elem in PERIODIC_TABLE:
                names.add(elem["name"].lower())
                symbols.add(elem["symbol"].lower())
                chinese_names.add(elem["chinese_name"].strip())

            # 提取所有可能的元素名
            element_names = set()
            # 更全面的元素提取正则表达式，能够处理中文元素名
            # 对于常见的中文元素名特别处理
            common_elements = ["氢", "氦", "锂", "铍", "硼", "碳", "氮", "氧", "氟", "氖",
                               "钠", "镁", "铝", "硅", "磷", "硫", "氯", "氩", "钾", "钙"]

            # 从查询中直接寻找中文元素名
            for element in common_elements:
                if element in query:
                    element_names.add(element)

            # 使用原有的正则表达式作为备选
            if not element_names:
                # 尝试清理输入文本，移除常见的干扰词
                cleaned_query = query
                for noise in ["元素", "和", "的", "信息", "详情", "属性", "特性"]:
                    cleaned_query = cleaned_query.replace(noise, " ")
                
                # 在清理后的文本中查找元素
                for word in re.findall(r"[\u4e00-\u9fa5]{1,2}|[A-Za-z]+", cleaned_query):
                    w = word.strip()
                    if w in chinese_names or w.lower() in names or w.lower() in symbols:
                        element_names.add(w)

            if element_names:
                # 日志清楚地标记出找到了哪些元素
                logger.info(
                    f"[SessionID: {sessionId}] 从查询中提取到元素: {', '.join(element_names)}")

                results = []
                for name in element_names:
                    # 先发送处理中的状态
                    yield {"is_task_complete": False, "require_user_input": False,
                            "content": f"正在查询元素 {name}..."}

                    try:
                        # 准备输入参数字典
                        tool_input = {}
                        if not name.isascii():
                            tool_input = {"chinese_name": name}
                        elif name.lower() in names:
                            tool_input = {"name": name}
                        elif name.lower() in symbols:
                            tool_input = {"symbol": name}

                        # 直接调用函数而不是工具对象
                        elem_info = query_element.func(**tool_input)
                    except Exception as e:
                        logger.error(
                            f"[SessionID: {sessionId}] 调用query_element工具失败: {e}", exc_info=True)
                        elem_info = {
                            "error": "Failed to query element. Please try again."}

                    if isinstance(elem_info, dict) and "error" in elem_info:
                        results.append(f"未找到元素: {name}")
                    else:
                        # 对元素信息进行格式化后再添加到结果
                        results.append(format_element_info(elem_info))

                message = "\n\n".join(results)
                logger.info(f"[SessionID: {sessionId}] ✨ 直接返回元素查询结果:")
                logger.info("=" * 50)
                logger.info(message)
                logger.info("=" * 50)

                # 再发送处理完成的状态
                yield {"is_task_complete": True, "require_user_input": False, "content": message}
                return
            else:
                logger.warning(
                    f"[SessionID: {sessionId}] 未从查询中提取到有效元素，尝试使用大模型处理")
        except Exception as e:
            logger.error(
                f"[SessionID: {sessionId}] ❌ 直接处理元素查询失败: {e}", exc_info=True)
            # 如果直接处理失败，继续使用大模型处理

        # 如果不是直接的元素查询或直接处理失败，使用大模型处理
        inputs = {"messages": [("user", query)]}
        config = {"configurable": {"thread_id": sessionId}}
        try:
            for item in self.graph.stream(inputs, config, stream_mode="values"):
                message = item["messages"][-1]
                if (
                        isinstance(message, AIMessage)
                        and message.tool_calls
                        and len(message.tool_calls) > 0
                ):
                    logger.info(f"[SessionID: {sessionId}] 🔍 大模型正在查询元素...")
                    yield {"is_task_complete": False, "require_user_input": False, "content": "正在查询元素..."}
                elif isinstance(message, ToolMessage):
                    logger.info(
                        f"[SessionID: {sessionId}] 📊 大模型收到元素数据，正在处理...")
                    yield {"is_task_complete": False, "require_user_input": False, "content": "正在处理元素信息..."}
            final_response = self.get_agent_response(config)
            # 打印完整的响应内容，便于调试
            if final_response.get("content"):
                logger.info(f"[SessionID: {sessionId}] ✨ 大模型返回结果:")
                # 用分隔线使输出更加醒目
                logger.info("=" * 50)
                logger.info(final_response.get("content"))
                logger.info("=" * 50)

                # 检查输出是否缺乏元素信息 - 多种格式判断
                if (("元素名称:" not in final_response.get("content") and
                     "未找到元素" not in final_response.get("content")) or
                        "查询完成" in final_response.get("content") or
                        "成功获取" in final_response.get("content") or
                        "完成" in final_response.get("content")):
                    # 尝试检查LLM是否执行了元素查询但没有返回格式化数据
                    try:
                        current_state = self.graph.get_state(config)
                        # 找出已经执行过的工具调用结果
                        tool_messages = [msg for msg in current_state.values.get('messages', [])
                                         if isinstance(msg, ToolMessage)]

                        if tool_messages:
                            # 如果有工具调用结果，说明LLM已经查询过元素，但可能没有格式化输出
                            element_data = []
                            for message in tool_messages:
                                content = message.content
                                logger.info(
                                    f"[SessionID: {sessionId}] 🔎 检查工具消息内容: {content}")
                                # 支持字典和字符串两种格式
                                if isinstance(content, dict) and "error" not in content:
                                    # 对元素信息进行格式化
                                    element_data.append(
                                        format_element_info(content))
                                # 可能某些工具执行后返回的是字符串而不是字典
                                elif isinstance(content, str) and content.startswith("{"):
                                    try:
                                        import json
                                        content_dict = json.loads(content)
                                        if "error" not in content_dict:
                                            element_data.append(
                                                format_element_info(content_dict))
                                    except Exception as json_err:
                                        logger.error(f"[SessionID: {sessionId}] 解析JSON工具调用结果失败: {json_err}",
                                                     exc_info=True)

                            if element_data:
                                # 替换原始响应内容
                                formatted_response = "\n\n".join(element_data)
                                logger.info(
                                    f"[SessionID: {sessionId}] 🔧 补充元素详细信息:")
                                logger.info("=" * 50)
                                logger.info(formatted_response)
                                logger.info("=" * 50)
                                final_response["content"] = formatted_response
                                final_response["is_task_complete"] = True
                                final_response["require_user_input"] = False
                            else:
                                logger.warning(
                                    f"[SessionID: {sessionId}] ⚠️ 无法从工具调用结果中提取有效元素信息")
                    except Exception as e:
                        logger.error(
                            f"[SessionID: {sessionId}] ❌ 处理工具调用结果时出错: {e}", exc_info=True)
                        # 错误处理失败不影响主流程

            yield final_response
        except Exception as e:
            logger.error(
                f"[SessionID: {sessionId}] ❌ 流式处理过程中发生错误: {e}", exc_info=True)
            raise

    def get_agent_response(self, config):
        """
        从智能体状态获取响应

        参数:
            config: 配置信息

        返回:
            dict: 包含响应状态和内容的字典
        """
        current_state = self.graph.get_state(config)
        structured_response = current_state.values.get('structured_response')
        if structured_response and isinstance(structured_response, ResponseFormat):
            status = structured_response.status
            message = structured_response.message
            # 修正：如果 message 不是字符串，转为字符串
            if not isinstance(message, str):
                message = str(message)
            if status == "input_required":
                return {"is_task_complete": False, "require_user_input": True, "content": message}
            elif status == "error":
                return {"is_task_complete": False, "require_user_input": True, "content": message}
            elif status == "completed":
                return {"is_task_complete": True, "require_user_input": False, "content": message}
        return {"is_task_complete": False, "require_user_input": True,
                "content": "We are unable to process your request at the moment. Please try again."}
