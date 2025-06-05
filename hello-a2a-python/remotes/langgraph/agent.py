import os
import logging
import json
import urllib.request
import urllib.parse
import urllib.error

from collections.abc import AsyncIterable
from typing import Any, Literal

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent


logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
memory = MemorySaver()

os.environ['OPENAI_API_KEY'] = 'your_openai_api_key_here'


@tool
def get_exchange_rate(
    currency_from: str = 'USD',
    currency_to: str = 'EUR',
    currency_date: str = 'latest',
    amount: float = 1.0,
):
    """获取当前汇率并执行货币转换的工具函数。

    参数:
        currency_from: 源货币代码 (例如: "USD").
        currency_to: 目标货币代码 (例如: "EUR").
        currency_date: 汇率日期或"latest"表示最新汇率. 默认为"latest".
        amount: 需要转换的金额. 默认为1.0.

    返回:
        包含汇率信息和转换详情的格式化字符串.
    """
    logger.info(f"汇率查询开始: {currency_from} -> {currency_to}, 金额: {amount}")
    try:
        # 构建查询参数 - 使用正确的API格式
        params = {
            'base': currency_from,
            'symbols': currency_to
        }
        query_string = urllib.parse.urlencode(params)
        # 使用正确的API endpoint格式
        if currency_date == 'latest':
            url = f'https://api.frankfurter.dev/v1/latest?{query_string}'
        else:
            url = f'https://api.frankfurter.dev/v1/{currency_date}?{query_string}'
        logger.info(f"请求 API: {url}")

        # 发送请求
        req = urllib.request.Request(url)
        req.add_header(
            'User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
        with urllib.request.urlopen(req, timeout=30) as response:
            response_code = response.getcode()
            logger.info(f"API 响应状态码: {response_code}")

            if response_code != 200:
                error_msg = f'API请求失败，状态码: {response_code}'
                logger.error(error_msg)
                return error_msg

            # 解析响应
            response_data = response.read().decode('utf-8')
            data = json.loads(response_data)
            logger.info(f"API 响应数据: {data}")

            if 'rates' not in data or currency_to not in data['rates']:
                error_msg = f'无法获取 {currency_from} 到 {currency_to} 的汇率'
                logger.error(error_msg)
                return error_msg

            # 计算转换金额
            rate = data['rates'][currency_to]
            converted_amount = amount * rate
            date = data.get('date', currency_date)

            if amount == 1.0:
                result = f'{date} Exchange Rate: 1 {currency_from} = {rate} {currency_to}'
            else:
                result = f'{date}: {amount} {currency_from} = {converted_amount:.2f} {currency_to} (Exchange Rate: 1 {currency_from} = {rate} {currency_to})'

            logger.info(f"汇率查询成功: {result}")
            return result

    except urllib.error.URLError as e:
        if hasattr(e, 'reason'):
            error_msg = f'网络连接失败: {e.reason}。请检查网络连接后重试。'
        else:
            error_msg = '网络连接失败。请检查网络连接后重试。'
        logger.error(error_msg)
        return '当前无法获取实时汇率信息，请检查网络连接后重试。若问题持续，建议稍后再次查询。'
    except json.JSONDecodeError:
        error_msg = '从API获得无效的JSON响应。请稍后重试。'
        logger.error(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f'获取汇率时发生错误: {str(e)}。请检查网络连接后重试。'
        logger.error(error_msg)
        return error_msg


class ResponseFormat(BaseModel):
    """向用户返回响应的标准格式。"""

    status: Literal['input_required', 'completed', 'error'] = 'input_required'
    message: str = Field(
        description="详细的响应消息。对于货币转换，需包含具体的转换金额（例如：'100 EUR = 108.50 USD'）。对于input_required状态，需说明需要什么信息。对于错误状态，需解释出现了什么问题。")


class CurrencyAgent:
    """基于LangGraph的货币转换智能体。

    专门处理货币汇率查询和货币转换计算。使用Frankfurter API获取实时汇率数据。
    支持多种货币之间的转换，并提供详细的汇率信息。
    """

    SYSTEM_INSTRUCTION = (
        '你是一个专门处理货币转换的智能助手。'
        "你的唯一目的是使用 'get_exchange_rate' 工具来回答有关货币汇率的问题。"

        '重要提示：当用户要求转换金额时（例如："将100欧元转换为美元"），你必须： '
        '1. 从用户请求中提取金额、源货币和目标货币 '
        '2. 使用提取的金额、currency_from和currency_to参数调用get_exchange_rate '
        '3. 将工具响应的确切内容作为ResponseFormat中的消息 - 不要修改或总结 '
        '4. 将状态设置为"completed"，并将工具响应直接放在消息字段中 '

        '工具将提供完整的转换详情，包括转换后的金额。 '
        '绝不要自己创建转换计算 - 始终准确使用工具返回的响应。 '

        '如果用户询问货币转换或汇率以外的其他事情，'
        '请礼貌地说明你无法帮助处理该主题，只能协助处理货币相关查询。 '
        '如果用户需要提供更多信息，请将响应状态设置为input_required。 '
        '如果处理请求时出现错误，请将响应状态设置为error。 '
        '当你提供工具响应时，请将响应状态设置为completed。'
    )

    def __init__(self, llm_provider: str = "lmstudio", model_name: str = "qwen3-8b"):
        """初始化货币转换智能体。

        参数:
            llm_provider: LLM 提供商，支持 "lmstudio" 或 "ollama"
            model_name: 模型名称，默认为 "qwen3-8b"
        """
        # 根据提供商设置不同的 base_url
        if llm_provider.lower() == "ollama":
            base_url = "http://localhost:11434/v1"
        elif llm_provider.lower() == "lmstudio":
            base_url = "http://localhost:1234/v1"
        else:
            raise ValueError(
                f"不支持的 LLM 提供商: {llm_provider}。支持的选项: 'lmstudio', 'ollama'")

        self.model = ChatOpenAI(
            model=model_name,
            base_url=base_url,
        )
        self.tools = [get_exchange_rate]

        self.graph = create_react_agent(
            self.model,
            tools=self.tools,
            checkpointer=memory,
            prompt=self.SYSTEM_INSTRUCTION,
            response_format=ResponseFormat,
        )

    def invoke(self, query, sessionId) -> dict[str, Any]:
        logger.info(f"收到查询: {query}, 会话ID: {sessionId}")
        config: RunnableConfig = {'configurable': {'thread_id': sessionId}}
        result = self.graph.invoke({'messages': [('user', query)]}, config)
        logger.info(f"Graph 调用结果: {result}")
        response = self.get_agent_response(config)
        logger.info(f"最终响应: {response}")
        return response

    async def stream(self, query, sessionId) -> AsyncIterable[dict[str, Any]]:
        logger.info(f"开始流式处理查询: {query}, 会话ID: {sessionId}")
        inputs = {'messages': [('user', query)]}
        config: RunnableConfig = {'configurable': {'thread_id': sessionId}}

        for item in self.graph.stream(inputs, config, stream_mode='values'):
            logger.info(f"流式响应项: {item}")
            message = item['messages'][-1]
            if (
                isinstance(message, AIMessage)
                and message.tool_calls
                and len(message.tool_calls) > 0
            ):
                logger.info("AI 消息包含工具调用")
                yield {
                    'is_task_complete': False,
                    'require_user_input': False,
                    'content': '正在查询汇率...',
                }
            elif isinstance(message, ToolMessage):
                logger.info(f"工具消息: {message.content}")
                yield {
                    'is_task_complete': False,
                    'require_user_input': False,
                    'content': '正在处理汇率数据...',
                }

        final_response = self.get_agent_response(config)
        logger.info(f"流式处理完成，最终响应: {final_response}")
        yield final_response

    def get_agent_response(self, config: RunnableConfig):
        current_state = self.graph.get_state(config)
        logger.info(f"当前状态: {current_state}")
        logger.info(f"状态值: {current_state.values}")

        structured_response = current_state.values.get('structured_response')
        logger.info(f"结构化响应: {structured_response}")

        if structured_response and isinstance(
            structured_response, ResponseFormat
        ):
            logger.info(f"找到有效的结构化响应，状态: {structured_response.status}")
            if structured_response.status == 'input_required' or structured_response.status == 'error':
                return {
                    'is_task_complete': False,
                    'require_user_input': True,
                    'content': structured_response.message,
                }
            if structured_response.status == 'completed':
                # 确保返回完整的货币转换结果
                return {
                    'is_task_complete': True,
                    'require_user_input': False,
                    'content': structured_response.message,
                }

        # 如果没有找到结构化响应，尝试从最后一条消息中获取内容
        messages = current_state.values.get('messages', [])
        if messages:
            last_message = messages[-1]
            logger.info(f"最后一条消息: {type(last_message)} - {last_message}")
            if isinstance(last_message, AIMessage):
                return {
                    'is_task_complete': True,
                    'require_user_input': False,
                    'content': last_message.content,
                }

        logger.warning("无法获取有效响应，返回默认错误消息")
        return {
            'is_task_complete': False,
            'require_user_input': True,
            'content': '目前无法处理您的请求，请稍后重试。',
        }

    SUPPORTED_CONTENT_TYPES = ['text', 'text/plain']
