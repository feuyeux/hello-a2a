from typing import AsyncIterable, Union, List, Optional, cast
from common.types import (
    SendTaskRequest,
    TaskSendParams,
    Message,
    TaskStatus,
    Artifact,
    TextPart,
    Part,
    TaskState,
    TaskArtifactUpdateEvent,
    TaskStatusUpdateEvent,
    Task,
    TaskIdParams,
    PushNotificationConfig,
    InvalidParamsError,
    SendTaskResponse,
    InternalError,
    JSONRPCResponse,
    SendTaskStreamingRequest,
    SendTaskStreamingResponse,
)
from common.server.task_manager import InMemoryTaskManager
from agents.agent import ElementAgent, ElementAPIResponse
from common.utils.logger import setup_logger
from common.utils.push_notification_auth import PushNotificationSenderAuth
import common.server.utils as utils
import asyncio
import logging
import traceback

logger = setup_logger("AgentTaskManager")

class AgentTaskManager(InMemoryTaskManager):
    """智能体任务管理器，处理任务发送、更新和通知管理"""

    def __init__(self, agent: ElementAgent, notification_sender_auth: PushNotificationSenderAuth):
        """初始化任务管理器

        参数:
            agent: 元素周期表智能体实例
            notification_sender_auth: 推送通知认证工具
        """
        super().__init__()
        self.agent = agent
        self.notification_sender_auth = notification_sender_auth

    async def _run_streaming_agent(self, request: SendTaskStreamingRequest):
        """运行流式智能体处理任务

        参数:
            request: 流式任务请求
        """
        task_send_params: TaskSendParams = request.params
        query = self._get_user_query(task_send_params)

        try:
            async for item in self.agent.stream(query, task_send_params.sessionId):
                is_task_complete = item["is_task_complete"]
                artifact = None
                message = None
                # 创建标准化的文本部分
                text_part = TextPart(text=item["content"])
                # 使用类型转换解决类型兼容问题
                parts = cast(List[Part], [text_part])
                end_stream = False

                # 根据智能体返回状态设置任务状态
                if not is_task_complete:
                    task_state = TaskState.WORKING
                    message = Message(role="agent", parts=parts)
                else:
                    task_state = TaskState.COMPLETED
                    artifact = Artifact(parts=parts, index=0, append=False)
                    end_stream = True

                # 更新任务状态并发送通知
                task_status = TaskStatus(state=task_state, message=message)
                latest_task = await self.update_store(
                    task_send_params.id,
                    task_status,
                    [] if artifact is None else [artifact],
                )
                await self.send_task_notification(latest_task)

                # 如果有成品，发送成品更新事件
                if artifact:
                    task_artifact_update_event = TaskArtifactUpdateEvent(
                        id=task_send_params.id, artifact=artifact
                    )
                    await self.enqueue_events_for_sse(
                        task_send_params.id, task_artifact_update_event
                    )

                # 发送任务状态更新事件
                task_update_event = TaskStatusUpdateEvent(
                    id=task_send_params.id, status=task_status, final=end_stream
                )
                await self.enqueue_events_for_sse(
                    task_send_params.id, task_update_event
                )

        except Exception as e:
            # 异常处理
            logger.error(
                f"流式响应处理过程中发生错误: {e}", exc_info=True)
            await self.enqueue_events_for_sse(
                task_send_params.id,
                InternalError(
                    message=f"流式响应处理过程中发生错误: {e}")
            )

    def _validate_request(
        self, request: Union[SendTaskRequest, SendTaskStreamingRequest]
    ) -> JSONRPCResponse | None:
        """验证任务请求

        参数:
            request: 任务请求

        返回:
            错误响应或None（验证通过）
        """
        task_send_params: TaskSendParams = request.params

        # 验证输出模式兼容性
        output_modes = task_send_params.acceptedOutputModes or []
        if not utils.are_modalities_compatible(
            output_modes, ElementAgent.SUPPORTED_CONTENT_TYPES
        ):
            logger.warning(
                f"不支持的输出模式。接收到: {output_modes}, 支持: {ElementAgent.SUPPORTED_CONTENT_TYPES}"
            )
            return utils.new_incompatible_types_error(request.id)

        # 验证推送通知URL
        if task_send_params.pushNotification and not task_send_params.pushNotification.url:
            logger.warning("Push notification URL is missing")
            return JSONRPCResponse(id=request.id, error=InvalidParamsError(message="Push notification URL is missing"))

        return None

    async def on_send_task(self, request: SendTaskRequest) -> SendTaskResponse:
        """处理发送任务请求

        参数:
            request: 发送任务请求

        返回:
            任务响应
        """
        # 验证请求
        validation_error = self._validate_request(request)
        if validation_error:
            return SendTaskResponse(id=request.id, error=validation_error.error)

        # 设置推送通知信息
        if request.params.pushNotification:
            if not await self.set_push_notification_info(request.params.id, request.params.pushNotification):
                return SendTaskResponse(id=request.id, error=InvalidParamsError(message="Push notification URL is invalid"))

        # 创建并更新任务
        await self.upsert_task(request.params)
        task = await self.update_store(
            request.params.id, TaskStatus(state=TaskState.WORKING), []
        )
        await self.send_task_notification(task)

        # 调用智能体处理查询
        task_send_params: TaskSendParams = request.params
        query = self._get_user_query(task_send_params)
        try:
            agent_response = self.agent.invoke(
                query, task_send_params.sessionId)
        except Exception as e:
            logger.error(f"调用智能体时发生错误: {e}")
            raise ValueError(f"调用智能体时发生错误: {e}")

        # 处理智能体响应
        return await self._process_agent_response(
            request, agent_response
        )

    async def on_send_task_subscribe(
        self, request: SendTaskStreamingRequest
    ) -> AsyncIterable[SendTaskStreamingResponse] | JSONRPCResponse:
        """处理流式任务订阅请求

        参数:
            request: 流式任务请求

        返回:
            流式响应或错误
        """
        try:
            # 验证请求
            error = self._validate_request(request)
            if error:
                return error

            # 创建任务
            await self.upsert_task(request.params)

            # 设置推送通知
            if request.params.pushNotification:
                if not await self.set_push_notification_info(request.params.id, request.params.pushNotification):
                    return JSONRPCResponse(id=request.id, error=InvalidParamsError(message="Push notification URL is invalid"))

            # 创建SSE事件队列
            task_send_params: TaskSendParams = request.params
            sse_event_queue = await self.setup_sse_consumer(task_send_params.id, False)

            # 异步启动智能体流式处理
            asyncio.create_task(self._run_streaming_agent(request))

            # 返回SSE事件队列解码器
            async def stream_generator():
                async for event in self.dequeue_events_for_sse(
                    request.id, task_send_params.id, sse_event_queue
                ):
                    yield event
            return stream_generator()
        except Exception as e:
            # 异常处理
            logger.error(f"流式响应处理过程中发生错误: {e}", exc_info=True)
            print(traceback.format_exc())
            return JSONRPCResponse(
                id=request.id,
                error=InternalError(
                    message="流式响应处理过程中发生错误"
                ),
            )

    async def _process_agent_response(
        self, request: SendTaskRequest, agent_response: ElementAPIResponse
    ) -> SendTaskResponse:
        """处理智能体响应并更新任务存储

        参数:
            request: 任务请求
            agent_response: 智能体响应

        返回:
            任务响应
        """
        task_send_params: TaskSendParams = request.params
        task_id = task_send_params.id
        history_length = task_send_params.historyLength
        task_status = None

        # 创建响应部分
        parts = cast(List[Part], [TextPart(text=agent_response["content"])])
        artifact = None
        # 始终设置 message 字段为详细内容
        message = Message(role="agent", parts=parts)

        # 任务完成时设置为COMPLETED状态，否则为FAILED
        if not agent_response.get("require_user_input", False) and agent_response.get("is_task_complete", True):
            artifact = Artifact(parts=parts)
            task_status = TaskStatus(
                state=TaskState.COMPLETED,
                message=message,
            )
        else:
            task_status = TaskStatus(
                state=TaskState.FAILED,
                message=message,
            )

        # 更新存储并生成响应
        task = await self.update_store(
            task_id, task_status, [] if artifact is None else [artifact]
        )
        task_result = self.append_task_history(task, history_length)
        await self.send_task_notification(task)
        return SendTaskResponse(id=request.id, result=task_result)

    def _get_user_query(self, task_send_params: TaskSendParams) -> str:
        """从任务参数中获取用户查询

        参数:
            task_send_params: 任务发送参数

        返回:
            str: 用户查询文本

        异常:
            ValueError: 如果不支持的消息部分类型
        """
        if not task_send_params.message.parts:
            raise ValueError("Message parts cannot be empty")
            
        part = task_send_params.message.parts[0]
        # 兼容 dict 类型，但优先使用强类型
        if isinstance(part, dict):
            if part.get("type") == "text":
                return part.get("text", "")
            else:
                raise ValueError("Only text parts are supported")
        if not isinstance(part, TextPart):
            raise ValueError("Only text parts are supported")
        return part.text

    async def send_task_notification(self, task: Task):
        """发送任务通知

        参数:
            task: 任务对象
        """
        # 检查是否有推送通知信息
        if not await self.has_push_notification_info(task.id):
            logger.info(f"No push notification info found for task {task.id}")
            return
        push_info = await self.get_push_notification_info(task.id)

        # 发送推送通知
        logger.info(f"Notifying for task {task.id} => {task.status.state}")
        await self.notification_sender_auth.send_push_notification(
            push_info.url,
            data=task.model_dump(exclude_none=True)
        )

    async def on_resubscribe_to_task(
        self, request
    ) -> AsyncIterable[SendTaskStreamingResponse] | JSONRPCResponse:
        """处理任务重新订阅请求

        参数:
            request: 重新订阅请求

        返回:
            流式响应或错误
        """
        task_id_params: TaskIdParams = request.params
        try:
            # 创建SSE事件队列
            sse_event_queue = await self.setup_sse_consumer(task_id_params.id, True)
            # 返回包装后的异步生成器
            async def stream_generator():
                async for event in self.dequeue_events_for_sse(request.id, task_id_params.id, sse_event_queue):
                    yield event
            return stream_generator()
        except Exception as e:
            # 异常处理
            logger.error(f"重新连接SSE流时发生错误: {e}")
            return JSONRPCResponse(
                id=request.id,
                error=InternalError(
                    message=f"An error occurred while reconnecting to stream: {e}"
                ),
            )

    async def set_push_notification_info(self, task_id: str, push_notification_config: PushNotificationConfig):
        """设置推送通知信息

        参数:
            task_id: 任务ID
            push_notification_config: 推送通知配置

        返回:
            验证结果（布尔值）
        """
        # 验证通知URL的所有权
        is_verified = await self.notification_sender_auth.verify_push_notification_url(push_notification_config.url)
        if not is_verified:
            return False

        # 设置推送通知信息
        await super().set_push_notification_info(task_id, push_notification_config)
        return True
