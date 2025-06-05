import asyncio
import logging
import os
import json
import sys

# 确保在 Windows 上正确处理 UTF-8 编码
if sys.platform == "win32":
    import locale
    # 设置控制台输出编码为 UTF-8
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
    # 设置环境变量确保 UTF-8 编码
    os.environ['PYTHONIOENCODING'] = 'utf-8'

from collections.abc import AsyncIterable
from typing import TYPE_CHECKING, Annotated, Any, Literal

import httpx

from dotenv import load_dotenv
from pydantic import BaseModel
from semantic_kernel.agents import ChatCompletionAgent, ChatHistoryAgentThread
from semantic_kernel.connectors.ai.open_ai import (
    OpenAIChatCompletion,
    OpenAIChatPromptExecutionSettings,
)
from semantic_kernel.contents import (
    FunctionCallContent,
    FunctionResultContent,
    StreamingChatMessageContent,
    StreamingTextContent,
)
from semantic_kernel.functions import KernelArguments, kernel_function


if TYPE_CHECKING:
    from semantic_kernel.contents import ChatMessageContent

logger = logging.getLogger(__name__)

load_dotenv()

# region Plugin


class CurrencyPlugin:
    """基于Frankfurter API的货币汇率查询插件。

    为 `currency_exchange_agent` 旅行货币智能体提供汇率查询功能。
    支持实时汇率获取和货币之间的汇率计算。
    """

    @kernel_function(
        description='使用Frankfurter API获取currency_from到currency_to之间的汇率'
    )
    def get_exchange_rate(
        self,
        currency_from: Annotated[
            str, '源货币代码，例如 USD'
        ],
        currency_to: Annotated[
            str, '目标货币代码，例如 EUR 或 INR'
        ],
        date: Annotated[str, "日期或 'latest' 表示最新"] = 'latest',
    ) -> str:
        try:
            response = httpx.get(
                f'https://api.frankfurter.app/{date}',
                params={'from': currency_from, 'to': currency_to},
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
            if 'rates' not in data or currency_to not in data['rates']:
                return f'无法获取 {currency_from} 到 {currency_to} 的汇率'
            rate = data['rates'][currency_to]
            return f'1 {currency_from} = {rate} {currency_to}'
        except Exception as e:
            return f'货币API调用失败: {e!s}'


class A2AAgentPlugin:
    """A2A智能体调用插件，用于调用其他A2A智能体服务。"""

    @kernel_function(
        description='调用Currency Agent获取货币汇率信息'
    )
    async def call_currency_agent(
        self,
        query: Annotated[str, '货币查询请求，例如：100 USD to CNY']
    ) -> str:
        """调用Currency Agent获取货币汇率信息。"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "http://localhost:10000",
                    headers={"Content-Type": "application/json"},
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "message/send",
                        "params": {
                            "id": "currency-query",
                            "sessionId": "travel-agent-session",
                            "acceptedOutputModes": ["text"],
                            "message": {
                                "messageId": "msg-currency",
                                "role": "user",
                                "parts": [{
                                    "type": "text",
                                    "text": query
                                }]
                            }
                        }
                    }
                )

                if response.status_code == 200:
                    result = response.json()
                    if 'result' in result and 'artifacts' in result['result']:
                        artifacts = result['result']['artifacts']
                        if artifacts and len(artifacts) > 0:
                            content = artifacts[0].get('parts', [{}])[
                                0].get('text', '')
                            return f"Currency Agent响应: {content}"
                    return "Currency Agent未返回有效响应"
                else:
                    return f"Currency Agent调用失败，状态码: {response.status_code}"

        except Exception as e:
            logger.error(f"调用Currency Agent失败: {e}")
            return f"Currency Agent调用出错: {str(e)}"

    @kernel_function(
        description='调用YouTube Agent获取视频字幕和分析'
    )
    async def call_youtube_agent(
        self,
        query: Annotated[str, 'YouTube视频相关查询']
    ) -> str:
        """调用YouTube Agent获取视频字幕和分析。"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "http://localhost:10010",
                    headers={"Content-Type": "application/json"},
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "message/send",
                        "params": {
                            "id": "youtube-query",
                            "sessionId": "travel-agent-session",
                            "acceptedOutputModes": ["text"],
                            "message": {
                                "messageId": "msg-youtube",
                                "role": "user",
                                "parts": [{
                                    "type": "text",
                                    "text": query
                                }]
                            }
                        }
                    }
                )

                if response.status_code == 200:
                    result = response.json()
                    if 'result' in result and 'artifacts' in result['result']:
                        artifacts = result['result']['artifacts']
                        if artifacts and len(artifacts) > 0:
                            content = artifacts[0].get('parts', [{}])[
                                0].get('text', '')
                            return f"YouTube Agent响应: {content}"
                    return "YouTube Agent未返回有效响应"
                else:
                    return f"YouTube Agent调用失败，状态码: {response.status_code}"

        except Exception as e:
            logger.error(f"调用YouTube Agent失败: {e}")
            return f"YouTube Agent调用出错: {str(e)}"


# endregion

# region Response Format


class ResponseFormat(BaseModel):
    """响应格式模型，用于指导模型如何响应。"""

    status: Literal['input_required', 'completed', 'error'] = 'input_required'
    message: str


# endregion

# region Semantic Kernel Agent


class SemanticKernelTravelAgent:
    """基于Semantic Kernel框架的旅行助手智能体。

    集成多个专业智能体来处理旅行相关任务：
    - CurrencyExchangeAgent: 处理货币汇率和转换
    - ActivityPlannerAgent: 处理活动规划和建议
    - TravelManagerAgent: 主控智能体，负责任务分派
    """

    agent: ChatCompletionAgent
    thread: ChatHistoryAgentThread | None = None
    SUPPORTED_CONTENT_TYPES = ['text', 'text/plain']

    def __init__(self, llm_provider: str = 'lmstudio', model_name: str = 'qwen3-0.6b'):
        # 根据提供商设置配置
        if llm_provider.lower() == 'lmstudio':
            api_key = os.getenv("OPENAI_API_KEY", "lm-studio")
            base_url = os.getenv("OPENAI_BASE_URL", "http://localhost:1234/v1")
        elif llm_provider.lower() == 'ollama':
            api_key = os.getenv("OPENAI_API_KEY", "ollama")
            base_url = os.getenv(
                "OPENAI_BASE_URL", "http://localhost:11434/v1")
        else:
            raise ValueError(
                f"不支持的 LLM 提供商: {llm_provider}。支持的选项: 'lmstudio', 'ollama'")

        logger.info(
            f"初始化Semantic Kernel旅行智能体 - 提供商: {llm_provider}, 模型: {model_name}, 基础URL: {base_url}")

        # 创建共享的OpenAI客户端，使用自定义base_url
        import openai
        openai_client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url=base_url  # 使用base_url连接到本地服务
        )

        # 定义货币汇率智能体来处理货币相关任务
        currency_exchange_agent = ChatCompletionAgent(
            service=OpenAIChatCompletion(
                ai_model_id=model_name,
                api_key=api_key,
                async_client=openai_client  # 使用预配置的客户端
            ),
            name='CurrencyExchangeAgent',
            instructions=(
                '你专门处理旅行者的货币相关请求。'
                '包括提供当前汇率、不同货币之间的金额转换、'
                '解释与货币兑换相关的费用或收费，以及提供货币兑换的最佳实践建议。'
                '你的目标是及时准确地协助旅行者解决所有货币相关问题。'
            ),
            plugins=[CurrencyPlugin()],
        )

        # 定义活动规划智能体来处理活动相关任务
        activity_planner_agent = ChatCompletionAgent(
            service=OpenAIChatCompletion(
                ai_model_id=model_name,
                api_key=api_key,
                async_client=openai_client  # 使用预配置的客户端
            ),
            name='ActivityPlannerAgent',
            instructions=(
                '你专门为旅行者规划和推荐活动。'
                '包括建议观光选择、当地活动、餐饮推荐、'
                '景点门票预订、旅行行程建议，确保活动'
                '符合旅行者的偏好和时间安排。'
                '你的目标是为旅行者创造愉快和个性化的体验。'
            ),
        )

        # 定义主要的旅行管理智能体，能够调用其他A2A智能体
        self.agent = ChatCompletionAgent(
            service=OpenAIChatCompletion(
                ai_model_id=model_name,
                api_key=api_key,
                async_client=openai_client  # 使用预配置的客户端
            ),
            name='TravelManagerAgent',
            instructions=(
                "你是一位专业的旅行规划师，擅长制定详细具体的旅行计划。"
                "你拥有以下工具函数：\n"
                "1. call_currency_agent(query): 调用Currency Agent获取货币汇率\n"
                "2. get_exchange_rate(currency_from, currency_to): 直接查询汇率\n"
                "3. call_youtube_agent(query): 获取旅行相关视频信息\n\n"

                "工作流程：\n"
                "1. 当用户提到货币或预算时，立即使用get_exchange_rate函数查询汇率\n"
                "2. 获得汇率信息后，制定详细的旅行计划\n"
                "3. 计划必须包括：交通、住宿、景点、餐饮、预算（使用实时汇率）\n\n"

                "示例：如果用户说'3000美元去日本'，你应该：\n"
                "- 先调用get_exchange_rate('USD', 'JPY')获取汇率\n"
                "- 然后制定具体的日本旅行计划\n\n"

                "请始终用中文回复，提供具体实用的建议。"
                "最终响应必须是JSON格式：{\"status\": \"completed\", \"message\": \"详细旅行计划内容\"}"
            ),
            plugins=[CurrencyPlugin(), A2AAgentPlugin()],
            # 移除response_format限制，让模型自由调用函数
        )

        logger.info("Semantic Kernel旅行智能体初始化完成")

    async def invoke(self, user_input: str, session_id: str) -> dict[str, Any]:
        """处理同步任务（如tasks/send）。

        参数:
            user_input (str): 用户输入消息。
            session_id (str): 会话的唯一标识符。

        返回:
            dict: 包含内容、任务完成状态和用户输入要求的字典。
        """
        await self._ensure_thread_exists(session_id)

        logger.info(
            f"Semantic Kernel旅行智能体同步调用 - 会话: {session_id}, 输入: {user_input[:100]}...")

        # 使用SK的get_response进行单次调用
        response = await self.agent.get_response(
            messages=user_input,
            thread=self.thread,
        )

        result = self._get_agent_response(response.content)
        logger.info(
            f"Semantic Kernel旅行智能体响应完成 - 会话: {session_id}, 状态: {result.get('is_task_complete')}")
        return result

    async def stream(
        self,
        user_input: str,
        session_id: str,
    ) -> AsyncIterable[dict[str, Any]]:
        """流式任务处理，逐步输出SK智能体的invoke_stream进度。

        参数:
            user_input (str): 用户输入消息。
            session_id (str): 会话的唯一标识符。

        生成:
            dict: 包含内容、任务完成状态和用户输入要求的字典。
        """
        await self._ensure_thread_exists(session_id)

        logger.info(
            f"Semantic Kernel旅行智能体流式调用开始 - 会话: {session_id}, 输入: {user_input[:100]}...")

        plugin_notice_seen = False
        plugin_event = asyncio.Event()

        text_notice_seen = False
        chunks: list[StreamingChatMessageContent] = []

        async def _handle_intermediate_message(
            message: 'ChatMessageContent',
        ) -> None:
            """处理智能体的中间消息。"""
            nonlocal plugin_notice_seen
            if not plugin_notice_seen:
                plugin_notice_seen = True
                plugin_event.set()
            # 处理函数调用期间的中间消息示例
            for item in message.items or []:
                if isinstance(item, FunctionResultContent):
                    logger.debug(f'SK函数结果: {item.result} 函数名: {item.name}')
                elif isinstance(item, FunctionCallContent):
                    logger.debug(f'SK函数调用: {item.name} 参数: {item.arguments}')
                else:
                    logger.debug(f'SK消息: {item}')

        async for chunk in self.agent.invoke_stream(
            messages=user_input,
            thread=self.thread,
            on_intermediate_message=_handle_intermediate_message,
        ):
            if plugin_event.is_set():
                yield {
                    'is_task_complete': False,
                    'require_user_input': False,
                    'content': '正在处理函数调用...',
                }
                plugin_event.clear()

            if any(isinstance(i, StreamingTextContent) for i in chunk.items):
                if not text_notice_seen:
                    yield {
                        'is_task_complete': False,
                        'require_user_input': False,
                        'content': '正在构建输出...',
                    }
                    text_notice_seen = True
                chunks.append(chunk.message)

        if chunks:
            result = self._get_agent_response(sum(chunks[1:], chunks[0]))
            logger.info(
                f"Semantic Kernel旅行智能体流式响应完成 - 会话: {session_id}, 状态: {result.get('is_task_complete')}")
            yield result

    def _get_agent_response(
        self, message: 'ChatMessageContent'
    ) -> dict[str, Any]:
        """从智能体的消息内容中提取结构化响应。

        参数:
            message (ChatMessageContent): 来自智能体的消息内容。

        返回:
            dict: 包含内容、任务完成状态和用户输入要求的字典。
        """
        content = message.content

        # 尝试解析JSON响应
        try:
            # 如果内容是JSON格式
            if content.strip().startswith('{') and content.strip().endswith('}'):
                structured_response = ResponseFormat.model_validate_json(
                    content)

                response_map = {
                    'input_required': {
                        'is_task_complete': False,
                        'require_user_input': True,
                    },
                    'error': {
                        'is_task_complete': False,
                        'require_user_input': True,
                    },
                    'completed': {
                        'is_task_complete': True,
                        'require_user_input': False,
                    },
                }

                response = response_map.get(structured_response.status)
                if response:
                    return {**response, 'content': structured_response.message}
            else:
                # 如果不是JSON格式，检查是否包含完整的旅行计划
                if len(content) > 200 and any(keyword in content for keyword in ['交通', '住宿', '景点', '预算', '汇率']):
                    # 这看起来像一个完整的旅行计划
                    return {
                        'is_task_complete': True,
                        'require_user_input': False,
                        'content': content,
                    }
                else:
                    # 简短回复，可能需要更多信息
                    return {
                        'is_task_complete': False,
                        'require_user_input': True,
                        'content': content,
                    }

        except Exception as e:
            logger.warning(f"无法解析响应为JSON: {e}")
            # 如果JSON解析失败，直接返回文本内容
            if len(content) > 100:
                return {
                    'is_task_complete': True,
                    'require_user_input': False,
                    'content': content,
                }
            else:
                return {
                    'is_task_complete': False,
                    'require_user_input': True,
                    'content': content,
                }

    async def _ensure_thread_exists(self, session_id: str) -> None:
        """确保给定会话ID的线程存在。

        参数:
            session_id (str): 会话的唯一标识符。
        """
        if self.thread is None or self.thread.id != session_id:
            await self.thread.delete() if self.thread else None
            self.thread = ChatHistoryAgentThread(thread_id=session_id)
            logger.debug(f"为会话 {session_id} 创建新的聊天线程")


# endregion
