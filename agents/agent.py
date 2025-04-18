from langchain_ollama import ChatOllama
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import AIMessage, ToolMessage
from typing import Any, Dict, AsyncIterable, Literal
from pydantic import BaseModel
import logging
from agents.periodic_table import PERIODIC_TABLE

logger = logging.getLogger(__name__)

# 内存保存器，用于保存智能体的状态
memory = MemorySaver()

# 响应格式定义，所有回复需遵循该结构


class ResponseFormat(BaseModel):
    """以该格式回复用户。"""
    status: Literal["input_required", "completed",
                    "error"] = "input_required"  # 回复状态
    message: str  # 回复内容


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
    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

    SYSTEM_INSTRUCTION = (
        "你是一个元素周期表智能助手。你的唯一任务是使用 query_element 工具，回答关于化学元素及其性质的问题。"
        "严格按照用户输入内容调用 query_element 工具，不要对元素名称、符号等参数做任何翻译、编码或变换。"
        "如果用户问题涉及多个元素，必须依次分别调用 query_element 工具，并将每个元素的结果用换行拼接成一个字符串，作为最终 message 返回。"
        "最终 message 必须包含每个元素的详细信息文本，不允许只回复确认或泛泛内容。输出格式示例：\\n元素名称: 碳 (C)...\\n元素名称: 硅 (Si)..."
        "如果用户的问题不是关于化学元素或元素周期表，请礼貌地说明你只能回答元素周期表相关问题。"
        "如果需要用户补充信息，设置 response status 为 input_required，并在 message 里说明需要哪些信息。"
        "如果遇到错误，设置 response status 为 error，并在 message 里返回错误原因。"
        "如果请求已完成，设置 response status 为 completed。"
    )

    def __init__(self):
        logger.info("Initializing ElementAgent")
        self.model = ChatOllama(model="llama3.2")
        self.tools = [query_element]
        self.graph = create_react_agent(
            self.model, tools=self.tools, checkpointer=memory, prompt=self.SYSTEM_INSTRUCTION, response_format=ResponseFormat
        )
        # 设置递归深度限制，防止无限循环
        if getattr(self.graph, "config", None) is None:
            self.graph.config = {}
        self.graph.config["recursion_limit"] = 50
        logger.info("ElementAgent initialized successfully")

    def invoke(self, query, sessionId) -> str:
        import re
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
        for word in re.findall(r"[\u4e00-\u9fa5]+|[A-Za-z]+", query):
            w = word.strip()
            if w in chinese_names or w.lower() in names or w.lower() in symbols:
                element_names.add(w)
        if not element_names:
            return {"is_task_complete": False, "require_user_input": True, "content": "未检测到有效元素名，请输入元素的中文名、英文名或符号。"}
        results = []
        for name in element_names:
            # 优先判断是否为中文
            if not name.isascii():
                elem_info = query_element(
                    chinese_name=name, name=None, symbol=None, atomic_number=None)
            elif name.lower() in names:
                elem_info = query_element(
                    name=name, chinese_name=None, symbol=None, atomic_number=None)
            elif name.lower() in symbols:
                elem_info = query_element(
                    symbol=name, name=None, chinese_name=None, atomic_number=None)
            else:
                elem_info = {
                    "error": "Element not found. Please check your input."}
            if isinstance(elem_info, dict) and "error" in elem_info:
                results.append(f"未找到元素: {name}")
            else:
                results.append(elem_info)
        message = "\n".join(results)
        return {"is_task_complete": True, "require_user_input": False, "content": message}

    async def stream(self, query, sessionId) -> AsyncIterable[Dict[str, Any]]:
        logger.info(
            f"[SessionID: {sessionId}] Starting streaming invocation with query: {query}")
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
                    yield {"is_task_complete": False, "require_user_input": False, "content": "Looking up the element..."}
                elif isinstance(message, ToolMessage):
                    yield {"is_task_complete": False, "require_user_input": False, "content": "Processing the element information..."}
            final_response = self.get_agent_response(config)
            yield final_response
        except Exception as e:
            logger.error(
                f"[SessionID: {sessionId}] Error during streaming: {e}", exc_info=True)
            raise

    def get_agent_response(self, config):
        thread_id = config.get("configurable", {}).get("thread_id", "unknown")
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
        return {"is_task_complete": False, "require_user_input": True, "content": "We are unable to process your request at the moment. Please try again."}