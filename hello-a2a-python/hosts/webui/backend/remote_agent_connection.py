import json
import logging
import time
import uuid
from datetime import datetime
from typing import Callable

import httpx
from a2a.client import A2AClient
from a2a.types import (
    AgentCard,
    JSONRPCErrorResponse,
    Message,
    MessageSendParams,
    SendMessageRequest,
    SendStreamingMessageRequest,
    Task,
    TaskArtifactUpdateEvent,
    TaskStatusUpdateEvent,
)

# Setup logging
logger = logging.getLogger(__name__)

# Simple logging helper class for Remote Agent Connection


class RemoteAgentLogger:
    """简洁的远程智能体连接日志记录器"""

    @staticmethod
    def generate_correlation_id() -> str:
        return str(uuid.uuid4())

    @staticmethod
    def log_a2a_request(correlation_id: str, agent_name: str, message_id: str, streaming: bool = False):
        """记录A2A请求"""
        logger.info(
            f"📡 A2A请求: {agent_name} | ID:{correlation_id[:8]} | 流式:{streaming}")

    @staticmethod
    def log_a2a_response(correlation_id: str, agent_name: str, duration_ms: float, success: bool = True):
        """记录A2A响应"""
        status = "✅" if success else "❌"
        logger.info(
            f"{status} A2A响应: {agent_name} | ID:{correlation_id[:8]} | 耗时:{round(duration_ms, 2)}ms")

    @staticmethod
    def log_flow_event(correlation_id: str, event: str, agent_name: str, details: str = ""):
        """记录A2A流程事件"""
        logger.info(
            f"🌐 A2A流程: {event} | {agent_name} | ID:{correlation_id[:8]} | {details}")


TaskCallbackArg = Task | TaskStatusUpdateEvent | TaskArtifactUpdateEvent
TaskUpdateCallback = Callable[[TaskCallbackArg, AgentCard], Task]


class RemoteAgentConnections:
    """持有远程智能体连接的类"""

    def __init__(self, client: httpx.AsyncClient, agent_card: AgentCard):
        self.agent_client = A2AClient(client, agent_card)
        self.card = agent_card
        self.pending_tasks = set()

    def get_agent(self) -> AgentCard:
        return self.card

    async def send_message(
        self,
        request: MessageSendParams,
        task_callback: TaskUpdateCallback | None,
    ) -> Task | Message | None:
        """
        Send message to remote agent via A2A protocol.
        This implements the A2A client communication layer from the sequence diagram.

        Flow:
        1. Host Agent -> RemoteAgentConnections: send_message()
        2. Check agent capabilities (streaming vs non-streaming)
        3. Send via A2A protocol to Remote Agent
        4. Handle response and task updates
        5. Return result to Host Agent

        Args:
            request: The A2A message send parameters
            task_callback: Callback for handling task updates

        Returns:
            Task for async operations or Message for immediate responses
        """
        # Generate correlation ID for this A2A communication
        correlation_id = RemoteAgentLogger.generate_correlation_id()
        start_time = time.time()

        # Log A2A communication start
        RemoteAgentLogger.log_flow_event(
            correlation_id=correlation_id,
            event="a2a_communication",
            agent_name=self.card.name,
            details=f"操作:send_message,目标:{self.card.name}"
        )

        # Check if agent supports streaming
        if self.card.capabilities.streaming:
            # Log streaming request
            RemoteAgentLogger.log_a2a_request(
                correlation_id=correlation_id,
                agent_name=self.card.name,
                message_id=request.message.messageId,
                streaming=True
            )

            task = None
            response_count = 0
            async for response in self.agent_client.send_message_streaming(
                SendStreamingMessageRequest(params=request)
            ):
                response_count += 1

                # Check for errors in the response
                if isinstance(response.root, JSONRPCErrorResponse):
                    RemoteAgentLogger.log_flow_event(
                        correlation_id=correlation_id,
                        event="error_handling",
                        agent_name=self.card.name,
                        details="处理错误"
                    )
                    return None

                # Get the event from successful response
                if hasattr(response.root, 'result') and response.root.result:
                    event = response.root.result

                    # Handle immediate message response (end of streaming)
                    if isinstance(event, Message):
                        duration_ms = (time.time() - start_time) * 1000

                        RemoteAgentLogger.log_a2a_response(
                            correlation_id=correlation_id,
                            agent_name=self.card.name,
                            duration_ms=duration_ms,
                            success=True
                        )

                        RemoteAgentLogger.log_flow_event(
                            correlation_id=correlation_id,
                            event="flow_completion",
                            agent_name=self.card.name,
                            details=f"streaming_message_completed, response_count: {response_count}, duration_ms: {duration_ms}"
                        )

                        return event

                    # Handle task update events during streaming
                    if task_callback and event:
                        task = task_callback(event, self.card)

            duration_ms = (time.time() - start_time) * 1000

            # Log streaming completion with task
            if task:
                RemoteAgentLogger.log_a2a_response(
                    correlation_id=correlation_id,
                    agent_name=self.card.name,
                    duration_ms=duration_ms,
                    success=True
                )

            RemoteAgentLogger.log_flow_event(
                correlation_id=correlation_id,
                event="flow_completion",
                agent_name=self.card.name,
                details=f"streaming_task_completed, response_count: {response_count}, duration_ms: {duration_ms}, task_id: {task.id if task else None}"
            )

            return task

        else:  # Non-streaming mode
            # Log non-streaming request
            RemoteAgentLogger.log_a2a_request(
                correlation_id=correlation_id,
                agent_name=self.card.name,
                message_id=request.message.messageId,
                streaming=False
            )

            response = await self.agent_client.send_message(
                SendMessageRequest(params=request)
            )

            duration_ms = (time.time() - start_time) * 1000

            # Handle error responses
            if isinstance(response.root, JSONRPCErrorResponse):
                error_details = {
                    "error": "Non-streaming request failed",
                    "duration_ms": duration_ms
                }

                RemoteAgentLogger.log_flow_event(
                    correlation_id=correlation_id,
                    event="error_handling",
                    agent_name=self.card.name,
                    details=f"Non-streaming request failed, duration_ms: {duration_ms}"
                )

                return None

            # Handle immediate message responses
            if hasattr(response.root, 'result') and isinstance(response.root.result, Message):
                message = response.root.result

                # Log non-streaming message response
                RemoteAgentLogger.log_a2a_response(
                    correlation_id=correlation_id,
                    agent_name=self.card.name,
                    duration_ms=duration_ms,
                    success=True
                )

                RemoteAgentLogger.log_flow_event(
                    correlation_id=correlation_id,
                    event="flow_completion",
                    agent_name=self.card.name,
                    details=f"non_streaming_message_completed, duration_ms: {duration_ms}, message_id: {message.messageId}"
                )

                return message

            # Handle task-based responses
            if hasattr(response.root, 'result'):
                task = response.root.result

                # Log non-streaming task response
                RemoteAgentLogger.log_a2a_response(
                    correlation_id=correlation_id,
                    agent_name=self.card.name,
                    duration_ms=duration_ms,
                    success=True
                )

                if task_callback and isinstance(task, (Task, TaskStatusUpdateEvent, TaskArtifactUpdateEvent)):
                    task_callback(task, self.card)

                RemoteAgentLogger.log_flow_event(
                    correlation_id=correlation_id,
                    event="flow_completion",
                    agent_name=self.card.name,
                    details=f"non_streaming_task_completed, duration_ms: {duration_ms}, task_id: {getattr(task, 'id', 'unknown')}"
                )

                return task

            return None
