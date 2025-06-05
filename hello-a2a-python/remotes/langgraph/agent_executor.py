import logging

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    InternalError,
    InvalidParamsError,
    Part,
    Task,
    TaskState,
    TextPart,
    UnsupportedOperationError,
)
from a2a.utils import (
    new_agent_text_message,
    new_task,
)
from a2a.utils.errors import ServerError
from remotes.langgraph.agent import CurrencyAgent


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CurrencyAgentExecutor(AgentExecutor):
    """基于LangGraph的货币转换智能体执行器。

    负责执行货币汇率查询和转换任务。
    使用LangGraph框架和流式处理来提供实时的汇率转换服务。
    """

    def __init__(self, llm_provider: str = "lmstudio", model_name: str = "qwen3-8b"):
        """初始化货币转换智能体执行器。

        参数:
            llm_provider: LLM 提供商，支持 "lmstudio" 或 "ollama"
            model_name: 模型名称，默认为 "qwen3-8b"
        """
        self.agent = CurrencyAgent(
            llm_provider=llm_provider, model_name=model_name)
        logger.info(
            f"货币转换智能体执行器初始化完成 - 使用 {llm_provider} 提供商，模型: {model_name}")

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """执行货币转换任务的主要方法。

        Args:
            context: 请求上下文，包含用户输入和任务信息
            event_queue: 事件队列，用于发布任务状态更新
        """
        error = self._validate_request(context)
        if error:
            logger.error("LangGraph货币智能体: 请求验证失败")
            raise ServerError(error=InvalidParamsError())

        query = context.get_user_input()
        logger.info(f"LangGraph货币智能体接收查询: {query[:100]}...")

        task = context.current_task
        if not task:
            if not context.message:
                logger.error("LangGraph货币智能体: 缺少消息上下文")
                raise ServerError(error=InvalidParamsError())
            task = new_task(context.message)
            event_queue.enqueue_event(task)
            logger.info(f"创建新任务 - ID: {task.id}, Context: {task.contextId}")

        updater = TaskUpdater(event_queue, task.id, task.contextId)
        try:
            logger.info(f"开始流式处理货币转换查询 - 任务ID: {task.id}")
            async for item in self.agent.stream(query, task.contextId):
                is_task_complete = item['is_task_complete']
                require_user_input = item['require_user_input']

                if not is_task_complete and not require_user_input:
                    logger.debug(
                        f"任务处理中 - 任务ID: {task.id}, 内容: {item['content']}")
                    updater.update_status(
                        TaskState.working,
                        new_agent_text_message(
                            item['content'],
                            task.contextId,
                            task.id,
                        ),
                    )
                elif require_user_input:
                    logger.info(
                        f"需要用户输入 - 任务ID: {task.id}, 消息: {item['content']}")
                    updater.update_status(
                        TaskState.input_required,
                        new_agent_text_message(
                            item['content'],
                            task.contextId,
                            task.id,
                        ),
                        final=True,
                    )
                    break
                else:
                    logger.info(
                        f"货币转换完成 - 任务ID: {task.id}, 结果: {item['content'][:100]}...")
                    # 添加最终的agent响应消息到历史记录
                    final_message = new_agent_text_message(
                        item['content'],
                        task.contextId,
                        task.id,
                    )
                    # 添加 artifact 包含转换结果
                    updater.add_artifact(
                        [Part(root=TextPart(text=item['content']))],
                        name='conversion_result',
                    )
                    # 完成任务并包含最终消息
                    updater.complete()
                    break

        except Exception as e:
            logger.error(
                f'LangGraph货币智能体流式响应错误 - 任务ID: {task.id if task else "未知"}, 错误: {e}')
            raise ServerError(error=InternalError()) from e

    def _validate_request(self, context: RequestContext) -> bool:
        return False

    async def cancel(
        self, request: RequestContext, event_queue: EventQueue
    ) -> Task | None:
        raise ServerError(error=UnsupportedOperationError())
