import logging

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.types import (
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from a2a.utils import new_agent_text_message, new_task, new_text_artifact
from .agent import YoutubeMCPAgent  # type: ignore[import-untyped]


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AG2AgentExecutor(AgentExecutor):
    """Youtube MCP智能体的执行器。

    该执行器集成AG2框架和YouTube MCP服务器，
    实现YouTube视频字幕下载和处理功能。

    核心功能：
    - 处理YouTube URL的字幕获取请求
    - 通过MCP协议与YouTube服务交互
    - 提供流式任务执行和状态更新
    - 智能解析和格式化YouTube字幕内容
    """

    def __init__(self, llm_provider: str = "ollama", model_name: str = "qwen3:8b"):
        """初始化AG2智能体执行器。

        参数:
            llm_provider: LLM 提供商，支持 "ollama" 或 "lmstudio"
            model_name: 模型名称，默认为 "qwen3:8b"
        """
        self.agent = YoutubeMCPAgent(
            llm_provider=llm_provider, model_name=model_name)
        logger.info(f"AG2智能体执行器初始化完成 - 使用 {llm_provider} 提供商，模型: {model_name}")

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """执行YouTube字幕处理任务

        参数：
            context: 包含用户输入和任务上下文的请求上下文
            event_queue: 用于发布任务状态更新的事件队列
        """
        # 提取用户输入和任务信息
        query = context.get_user_input()
        task = context.current_task

        # 记录任务开始
        logger.info(f"🚀 开始执行AG2 YouTube字幕任务 - 查询: {query[:100]}...")

        if not task:
            if context.message:
                task = new_task(context.message)
                event_queue.enqueue_event(task)
                logger.info(f"📋 创建新任务 - 任务ID: {task.id}")
            else:
                logger.error("无法创建任务：context.message为空")
                return

        # 流式处理智能体响应
        async for item in self.agent.stream(query, task.contextId):
            is_task_complete = item['is_task_complete']
            require_user_input = item['require_user_input']
            content = item['content']

            logger.info(
                f'📦 收到流式项目: 完成={is_task_complete}, 需要输入={require_user_input}, 内容长度={len(content)}'
            )

            if not is_task_complete and not require_user_input:
                # 任务进行中状态
                logger.info("🔄 任务处理中，发送工作状态更新")
                event_queue.enqueue_event(
                    TaskStatusUpdateEvent(
                        status=TaskStatus(
                            state=TaskState.working,
                            message=new_agent_text_message(
                                content,
                                task.contextId,
                                task.id,
                            ),
                        ),
                        final=False,
                        contextId=task.contextId,
                        taskId=task.id,
                    )
                )
            elif require_user_input:
                # 需要用户输入状态
                logger.info("⏸️ 任务需要用户输入，发送输入请求状态")
                event_queue.enqueue_event(
                    TaskStatusUpdateEvent(
                        status=TaskStatus(
                            state=TaskState.input_required,
                            message=new_agent_text_message(
                                content,
                                task.contextId,
                                task.id,
                            ),
                        ),
                        final=True,
                        contextId=task.contextId,
                        taskId=task.id,
                    )
                )
            else:
                # 任务完成状态
                logger.info("✅ 任务完成，发送最终结果")
                event_queue.enqueue_event(
                    TaskArtifactUpdateEvent(
                        append=False,
                        contextId=task.contextId,
                        taskId=task.id,
                        lastChunk=True,
                        artifact=new_text_artifact(
                            name='current_result',
                            description='智能体请求的结果。',
                            text=content,
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
                logger.info(f"🎉 AG2 YouTube字幕任务执行完成 - 任务ID: {task.id}")

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        raise Exception('cancel not supported')
