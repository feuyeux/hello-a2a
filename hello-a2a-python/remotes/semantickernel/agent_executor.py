import logging
import sys
import os

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

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.types import (
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from a2a.utils import (
    new_agent_text_message,
    new_task,
    new_text_artifact,
)
from remotes.semantickernel.agent import SemanticKernelTravelAgent


# 配置日志输出支持 UTF-8 编码
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
# 确保日志处理器使用 UTF-8 编码
for handler in logging.root.handlers:
    if hasattr(handler.stream, 'reconfigure'):
        handler.stream.reconfigure(encoding='utf-8')

logger = logging.getLogger(__name__)


class SemanticKernelTravelAgentExecutor(AgentExecutor):
    """基于Semantic Kernel的旅行智能体执行器。

    负责执行旅行相关任务，包括货币转换、活动规划等。
    使用多个专业智能体协作来提供全面的旅行服务。
    """

    def __init__(self, llm_provider: str = 'lmstudio', model_name: str = 'qwen3-0.6b'):
        self.agent = SemanticKernelTravelAgent(
            llm_provider=llm_provider, model_name=model_name)
        logger.info(
            f"Semantic Kernel旅行智能体执行器初始化完成 - 提供商: {llm_provider}, 模型: {model_name}")

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """执行Semantic Kernel旅行智能体任务的主要方法。

        Args:
            context: 请求上下文，包含用户输入和任务信息
            event_queue: 事件队列，用于发布任务状态更新
        """
        query = context.get_user_input()
        logger.info(f"Semantic Kernel旅行智能体接收查询: {query[:100]}...")

        task = context.current_task
        if not task:
            task = new_task(context.message)
            event_queue.enqueue_event(task)
            logger.info(f"创建新任务 - ID: {task.id}, Context: {task.contextId}")

        logger.info(f"开始流式处理旅行查询 - 任务ID: {task.id}")
        async for partial in self.agent.stream(query, task.contextId):
            require_input = partial['require_user_input']
            is_done = partial['is_task_complete']
            text_content = partial['content']

            if require_input:
                logger.info(f"需要用户输入 - 任务ID: {task.id}, 消息: {text_content}")
                event_queue.enqueue_event(
                    TaskStatusUpdateEvent(
                        status=TaskStatus(
                            state=TaskState.input_required,
                            message=new_agent_text_message(
                                text_content,
                                task.contextId,
                                task.id,
                            ),
                        ),
                        final=True,
                        contextId=task.contextId,
                        taskId=task.id,
                    )
                )
            elif is_done:
                logger.info(
                    f"旅行任务完成 - 任务ID: {task.id}, 结果: {text_content[:100]}...")
                event_queue.enqueue_event(
                    TaskArtifactUpdateEvent(
                        append=False,
                        contextId=task.contextId,
                        taskId=task.id,
                        lastChunk=True,
                        artifact=new_text_artifact(
                            name='current_result',
                            description='智能体请求的处理结果。',
                            text=text_content,
                        ),
                    )
                )
                event_queue.enqueue_event(
                    TaskStatusUpdateEvent(
                        status=TaskStatus(state=TaskState.completed),
                        final=True,
                        contextId=task.contextId,
                        taskId=task.id,
                    )
                )
            else:
                logger.debug(f"任务处理中 - 任务ID: {task.id}, 内容: {text_content}")
                event_queue.enqueue_event(
                    TaskStatusUpdateEvent(
                        status=TaskStatus(
                            state=TaskState.working,
                            message=new_agent_text_message(
                                text_content,
                                task.contextId,
                                task.id,
                            ),
                        ),
                        final=False,
                        contextId=task.contextId,
                        taskId=task.id,
                    )
                )

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        """取消任务执行。当前Semantic Kernel智能体不支持取消操作。"""
        logger.warning("Semantic Kernel旅行智能体不支持取消操作")
        raise Exception('不支持取消操作')
