import logging
import traceback

from typing import Any

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    FilePart,
    InternalError,
    InvalidParamsError,
    Part,
    Task,
    TaskState,
    TextPart,
    UnsupportedOperationError,
)
from a2a.utils import are_modalities_compatible, new_agent_text_message
from a2a.utils.errors import ServerError
from remotes.llama_index_file_chat.agent import (
    ChatResponseEvent,
    InputEvent,
    LogEvent,
    ParseAndChat,
)
from llama_index.core.workflow import Context


logger = logging.getLogger(__name__)


class LlamaIndexAgentExecutor(AgentExecutor):
    """基于LlamaIndex的文档聊天智能体执行器。
    
    支持文档上传和基于文档内容的智能问答。
    提供文档引用功能，将回答与文档的具体位置关联。
    支持多种文件格式：PDF、Word文档、图片等。
    """

    # 技术上支持几乎任何类型，但我们将限制为一些常见类型
    SUPPORTED_INPUT_TYPES = [
        'text/plain',
        'application/pdf',
        'application/msword',
        'image/png',
        'image/jpeg',
    ]
    SUPPORTED_OUTPUT_TYPES = ['text', 'text/plain']

    def __init__(
        self,
        agent: ParseAndChat | None = None,
        llm_provider: str = "lmstudio",
        model_name: str = "qwen3-0.6b",
    ):
        if agent is None:
            agent = ParseAndChat(llm_provider=llm_provider, model_name=model_name, timeout=120.0)
        self.agent = agent
        # 按会话ID存储上下文状态
        # 理想情况下，你应该使用数据库或其他键值存储来保存上下文状态
        self.ctx_states: dict[str, dict[str, Any]] = {}
        logger.info("LlamaIndex文档聊天智能体执行器初始化完成")

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """执行LlamaIndex文档聊天任务的主要方法。
        
        Args:
            context: 请求上下文，包含用户输入、文件附件和任务信息
            event_queue: 事件队列，用于发布任务状态更新
        """
        error = self._validate_request(context)
        if error:
            logger.error("LlamaIndex文档聊天智能体: 请求验证失败")
            raise ServerError(error=InvalidParamsError())

        input_event = self._get_input_event(context)
        context_id = context.context_id
        task_id = context.task_id
        
        logger.info(f"LlamaIndex文档聊天智能体接收请求 - 上下文: {context_id}, 任务: {task_id}")
        if input_event.attachment:
            logger.info(f"检测到文件附件 - 文件名: {input_event.file_name}")
        
        try:
            ctx = None
            handler = None

            # 检查是否有此会话的已保存上下文状态
            print(f'上下文状态数量: {len(self.ctx_states)}', flush=True)
            saved_ctx_state = self.ctx_states.get(context_id, None)

            if saved_ctx_state is not None:
                # 使用现有上下文恢复会话
                logger.info(f'使用已保存上下文恢复会话 {context_id}')
                ctx = Context.from_dict(self.agent, saved_ctx_state)
                handler = self.agent.run(
                    start_event=input_event,
                    ctx=ctx,
                )
            else:
                # 新会话！
                logger.info(f'开始新会话 {context_id}')
                handler = self.agent.run(
                    start_event=input_event,
                )

            # 发出初始任务对象
            updater = TaskUpdater(event_queue, task_id, context_id)
            updater.submit()
            
            logger.info(f"开始流式处理文档聊天 - 任务ID: {task_id}")
            async for event in handler.stream_events():
                if isinstance(event, LogEvent):
                    # 将日志事件作为中间消息发送
                    logger.debug(f"工作流日志 - 任务ID: {task_id}: {event.msg}")
                    updater.update_status(
                        TaskState.working,
                        new_agent_text_message(event.msg, context_id, task_id),
                    )

            # 等待最终响应
            final_response = await handler
            if isinstance(final_response, ChatResponseEvent):
                content = final_response.response
                metadata = (
                    final_response.citations
                    if hasattr(final_response, 'citations')
                    else None
                )
                if metadata is not None:
                    # 确保元数据是字符串键的字典
                    metadata = {str(k): v for k, v in metadata.items()}

                # 保存上下文状态以恢复当前会话
                self.ctx_states[context_id] = handler.ctx.to_dict()
                logger.info(f"文档聊天任务完成 - 任务ID: {task_id}, 响应长度: {len(content)}字符")

                updater.add_artifact(
                    [Part(root=TextPart(text=content))],
                    name='llama_summary',
                    metadata=metadata,
                )
                updater.complete()
            else:
                logger.error(f"意外的完成响应 - 任务ID: {task_id}: {final_response}")
                updater.failed(f'意外的完成响应 {final_response}')

        except Exception as e:
            logger.error(f'LlamaIndex文档聊天智能体流式响应错误 - 任务ID: {task_id}, 错误: {e}')
            logger.error(traceback.format_exc())

            # 出错时清理上下文
            if context_id in self.ctx_states:
                del self.ctx_states[context_id]
            raise ServerError(
                error=InternalError(
                    message=f'流式响应处理错误: {e}'
                )
            )

    async def cancel(
        self, request: RequestContext, event_queue: EventQueue
    ) -> Task | None:
        """取消任务执行。当前LlamaIndex智能体不支持取消操作。"""
        logger.warning("LlamaIndex文档聊天智能体不支持取消操作")
        raise ServerError(error=UnsupportedOperationError())

    def _validate_request(self, context: RequestContext) -> bool:
        """验证请求是否有效。True表示无效，False表示有效。"""
        invalidOutput = self._validate_output_modes(
            context, self.SUPPORTED_OUTPUT_TYPES
        )
        return invalidOutput or self._validate_push_config(context)

    def _get_input_event(self, context: RequestContext) -> InputEvent:
        """如果消息部分中存在文件附件，则提取文件附件。"""
        file_data = None
        file_name = None
        text_parts = []
        for p in context.message.parts:
            part = p.root
            if isinstance(part, FilePart):
                file_data = part.file.bytes
                file_name = part.file.name
                if file_data is None:
                    raise ValueError('文件数据缺失！')
            elif isinstance(part, TextPart):
                text_parts.append(part.text)
            else:
                raise ValueError(f'不支持的部分类型: {type(part)}')

        return InputEvent(
            msg='\n'.join(text_parts),
            attachment=file_data,
            file_name=file_name,
        )

    def _validate_output_modes(
        self,
        context: RequestContext,
        supportedTypes: list[str],
    ) -> bool:
        """验证输出模式是否受支持。"""
        acceptedOutputModes = (
            context.configuration.acceptedOutputModes
            if context.configuration
            else []
        )
        if not are_modalities_compatible(
            acceptedOutputModes,
            supportedTypes,
        ):
            logger.warning(
                '不支持的输出模式。接收到 %s，支持 %s',
                acceptedOutputModes,
                supportedTypes,
            )
            return True
        return False

    def _validate_push_config(
        self,
        context: RequestContext,
    ) -> bool:
        """验证推送通知配置。"""
        pushNotificationConfig = (
            context.configuration.pushNotificationConfig
            if context.configuration
            else None
        )
        if pushNotificationConfig and not pushNotificationConfig.url:
            logger.warning('推送通知URL缺失')
            return True

        return False
