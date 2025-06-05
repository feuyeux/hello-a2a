import base64
import datetime
import json
import logging
import os
import time
import uuid

import httpx

from a2a.types import (
    AgentCard,
    Artifact,
    DataPart,
    FilePart,
    FileWithBytes,
    FileWithUri,
    Message,
    Part,
    Role,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)
from google.adk import Runner
from google.adk.artifacts import InMemoryArtifactService
from google.adk.events.event import Event as ADKEvent
from google.adk.events.event_actions import EventActions as ADKEventActions
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types
from hosts.webui.backend.host_agent import HostAgent
from hosts.webui.backend.remote_agent_connection import (
    TaskCallbackArg,
)
from utils.agent_card import get_agent_card

from service.server.application_manager import ApplicationManager
from service.types import Conversation, Event


# 简化日志配置
logger = logging.getLogger(__name__)


class WebUIFlowLogger:
    """简洁的WebUI流程日志记录器"""

    @staticmethod
    def generate_correlation_id() -> str:
        return str(uuid.uuid4())

    @staticmethod
    def log_user_request(correlation_id: str, message_id: str, context_id: str, message_length: int):
        """记录用户请求"""
        logger.info(
            f"👤 用户请求: ID:{correlation_id[:8]} | 上下文:{context_id[:8]} | 长度:{message_length}")

    @staticmethod
    def log_llm_analysis_start(correlation_id: str, context_id: str, agent_count: int):
        """记录分析开始"""
        logger.info(f"🧠 分析开始: ID:{correlation_id[:8]} | 智能体:{agent_count}个")

    @staticmethod
    def log_agent_selection(correlation_id: str, selected_agent: str, reasoning: str = ""):
        """记录智能体选择"""
        logger.info(f"🎯 智能体选择: {selected_agent} | ID:{correlation_id[:8]}")

    @staticmethod
    def log_remote_agent_request(correlation_id: str, agent_name: str, message_length: int):
        """记录远程智能体请求"""
        logger.info(
            f"📤 远程请求: {agent_name} | ID:{correlation_id[:8]} | 长度:{message_length}")

    @staticmethod
    def log_remote_agent_response(correlation_id: str, agent_name: str, duration_ms: float, success: bool = True):
        """记录远程智能体响应"""
        status = "✅" if success else "❌"
        logger.info(
            f"{status} 远程响应: {agent_name} | ID:{correlation_id[:8]} | 耗时:{round(duration_ms, 2)}ms")

    @staticmethod
    def log_final_response(correlation_id: str, response_length: int):
        """记录最终响应"""
        logger.info(f"🎉 最终响应: ID:{correlation_id[:8]} | 长度:{response_length}")

    @staticmethod
    def log_flow_event(correlation_id: str, event: str, details: str = ""):
        """记录流程事件"""
        logger.info(f"🔄 流程事件: {event} | ID:{correlation_id[:8]} | {details}")


class LLMInteractionLogger:
    """简洁的大模型交互日志记录器"""

    @staticmethod
    def log_llm_prompt(correlation_id: str, prompt_length: int, model: str = "gemini"):
        """记录大模型请求"""
        logger.info(
            f"🤖 大模型输入: {model} | ID:{correlation_id[:8]} | 长度:{prompt_length}")

    @staticmethod
    def log_llm_response(correlation_id: str, response_length: int, duration_ms: float, model: str = "gemini"):
        """记录大模型响应"""
        logger.info(
            f"✅ 大模型输出: {model} | ID:{correlation_id[:8]} | 耗时:{round(duration_ms, 2)}ms | 长度:{response_length}")

    @staticmethod
    def log_tool_execution(correlation_id: str, tool_name: str, duration_ms: float = 0):
        """记录工具执行"""
        logger.info(
            f"🔧 工具执行: {tool_name} | ID:{correlation_id[:8]} | 耗时:{round(duration_ms, 2)}ms")


class ADKHostManager(ApplicationManager):
    """
    ADK主机管理器 - 处理WebUI消息和多智能体协调

    该类负责：
    1. 接收用户消息并启动主机大模型分析
    2. 协调远程智能体调用
    3. 管理任务状态和会话
    4. 提供详细的日志追踪
    """
    """An implementation of memory based management with fake agent actions

    This implements the interface of the ApplicationManager to plug into
    the AgentServer. This acts as the service contract that the Mesop app
    uses to send messages to the agent and provide information for the frontend.
    """

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        api_key: str = '',
        uses_vertex_ai: bool = False,
    ):
        self._conversations: list[Conversation] = []
        self._messages: list[Message] = []
        self._tasks: list[Task] = []
        self._events: dict[str, Event] = {}
        self._pending_message_ids: list[str] = []
        self._agents: list[AgentCard] = []
        self._artifact_chunks: dict[str, list[Artifact]] = {}
        self._session_service = InMemorySessionService()
        self._artifact_service = InMemoryArtifactService()
        self._memory_service = InMemoryMemoryService()
        self._host_agent = HostAgent(http_client, self.task_callback)
        self._context_to_conversation: dict[str, str] = {}
        self.user_id = 'test_user'
        self.app_name = 'A2A'
        self.api_key = api_key or os.environ.get('GOOGLE_API_KEY', '')
        self.uses_vertex_ai = (
            uses_vertex_ai
            or os.environ.get('GOOGLE_GENAI_USE_VERTEXAI', '').upper() == 'TRUE'
        )

        # 添加循环检测机制
        self._processing_tasks = set()  # 正在处理的任务ID集合
        self._callback_depth = {}  # 每个任务的回调深度计数器

        # Set environment variables based on auth method
        if self.uses_vertex_ai:
            os.environ['GOOGLE_GENAI_USE_VERTEXAI'] = 'TRUE'

        elif self.api_key:
            # Use API key authentication
            os.environ['GOOGLE_GENAI_USE_VERTEXAI'] = 'FALSE'
            os.environ['GOOGLE_API_KEY'] = self.api_key

        self._initialize_host()

        # Map of message id to task id
        self._task_map: dict[str, str] = {}
        # Map to manage 'lost' message ids until protocol level id is introduced
        self._next_id: dict[
            str, str
        ] = {}  # dict[str, str]: previous message to next message

    def _initialize_host(self):
        agent = self._host_agent.create_agent()
        self._host_runner = Runner(
            app_name=self.app_name,
            agent=agent,
            artifact_service=self._artifact_service,
            session_service=self._session_service,
            memory_service=self._memory_service,
        )

    async def create_conversation(self) -> Conversation:
        session = await self._session_service.create_session(
            app_name=self.app_name, user_id=self.user_id
        )
        conversation_id = session.id
        c = Conversation(conversation_id=conversation_id, is_active=True)
        self._conversations.append(c)
        return c

    def update_api_key(self, api_key: str):
        """Update the API key and reinitialize the host if needed"""
        if api_key and api_key != self.api_key:
            self.api_key = api_key

            # Only update if not using Vertex AI
            if not self.uses_vertex_ai:
                os.environ['GOOGLE_API_KEY'] = api_key
                # Reinitialize host with new API key
                self._initialize_host()

                # Map of message id to task id
                self._task_map = {}

    def sanitize_message(self, message: Message) -> Message:
        """Sanitize and validate incoming message.
        This ensures message consistency and handles task continuation scenarios.

        Flow:
        1. Check if message has valid context ID
        2. Retrieve conversation if exists
        3. Check for open tasks that should be continued
        4. Attach task ID to message if task continuation is needed
        """
        print(f"[ADKHostManager] 🧹 Sanitizing message: {message.messageId}")

        if message.contextId:
            print(
                f"[ADKHostManager] 🔍 Looking up conversation for context: {message.contextId}")
            conversation = self.get_conversation(message.contextId)
            if not conversation:
                print(
                    f"[ADKHostManager] ⚠️ No conversation found for context: {message.contextId}")
                return message

            print(
                f"[ADKHostManager] ✅ Conversation found with {len(conversation.messages)} messages")

            # Check if the last message in conversation was tied to an open task
            if conversation.messages:
                last_message = conversation.messages[-1]
                task_id = last_message.taskId

                if task_id:
                    print(
                        f"[ADKHostManager] 🔍 Checking if task {task_id} is still open")

                    # Find the task and check if it's still open
                    task = next(
                        filter(lambda x: x and x.id == task_id, self._tasks),
                        None,
                    )

                    if task_still_open(task):
                        print(
                            f"[ADKHostManager] 🔄 Task {task_id} is still open, attaching to current message")
                        message.taskId = task_id
                    else:
                        print(
                            f"[ADKHostManager] ✅ Task {task_id} is closed, message starts new context")
                else:
                    print("[ADKHostManager] ℹ️ Last message had no task ID")
            else:
                print("[ADKHostManager] ℹ️ Conversation has no previous messages")
        else:
            print("[ADKHostManager] ℹ️ Message has no context ID")

        print("[ADKHostManager] ✅ Message sanitization completed")
        return message

    async def process_message(self, message: Message, correlation_id: str | None = None):
        """Process incoming message through the ADK Host Manager.
        This is the core orchestration method that handles the complete message processing flow.

        Flow from sequence diagram:
        1. Server -> Manager: process_message()
        2. Sanitize and validate message
        3. Manager -> Host: run_async()
        4. Host orchestration begins with LLM analysis
        5. Agent selection and task execution
        6. Result synthesis and response
        """
        # Use provided correlation ID or generate a new one for tracking this entire request flow
        if correlation_id is None:
            correlation_id = WebUIFlowLogger.generate_correlation_id()
        flow_start_time = time.time()

        print(
            f"[ADKHostManager] 🎯 Starting message processing - ID: {message.messageId}, Correlation: {correlation_id}")

        # Log the incoming user request
        user_message_text = ""
        if message.parts:
            for part in message.parts:
                if part.root.kind == 'text' and hasattr(part.root, 'text') and part.root.text is not None:
                    user_message_text += part.root.text + " "

        WebUIFlowLogger.log_user_request(
            correlation_id=correlation_id,
            message_id=message.messageId,
            context_id=message.contextId or "",
            message_length=len(user_message_text.strip())
        )

        message_id = message.messageId
        if message_id:
            self._pending_message_ids.append(message_id)
            print(
                f"[ADKHostManager] 📝 Added message to pending queue: {message_id}")

        context_id = message.contextId
        if not context_id:
            print("[ADKHostManager] ❌ Message context_id is required but missing")
            raise ValueError("Message context_id is required")

        print(
            f"[ADKHostManager] 🔍 Processing message for context: {context_id}")

        # Get or create conversation context
        conversation = self.get_conversation(context_id)
        print(
            f"[ADKHostManager] 💬 Conversation context: {'Found' if conversation else 'Not found'}")

        # Log LLM analysis start with available agents
        available_agents = [
            {"name": card.name, "description": card.description} for card in self._agents]
        conversation_length = len(conversation.messages) if conversation else 0

        WebUIFlowLogger.log_llm_analysis_start(
            correlation_id=correlation_id,
            context_id=context_id,
            agent_count=len(available_agents)
        )

        # 将消息存储到对话历史中
        self._messages.append(message)
        if conversation:
            conversation.messages.append(message)
            print("[ADKHostManager] 📚 消息已添加到对话历史")

        # 为用户消息创建事件
        self.add_event(
            Event(
                id=str(uuid.uuid4()),
                actor='user',
                content=message,
                timestamp=datetime.datetime.utcnow().timestamp(),
            )
        )
        print("[ADKHostManager] 📊 用户消息事件已创建")

        final_event = None

        # 获取ADK处理所需的会话
        print(
            f"[ADKHostManager] 🔐 正在获取上下文会话: {context_id}")
        session = await self._session_service.get_session(
            app_name='A2A', user_id='test_user', session_id=context_id
        )
        if not session:
            print(
                f"[ADKHostManager] ❌ 未找到对应的会话 context_id: {context_id}")
            raise ValueError(f"Session not found for context_id: {context_id}")

        print("[ADKHostManager] ✅ 会话获取成功")

        task_id = message.taskId
        print(
            f"[ADKHostManager] 🎯 任务ID: {task_id if task_id else '无任务ID(新任务)'}")

        # 用当前消息上下文和关联ID更新会话状态
        state_update = {
            'task_id': task_id,
            'context_id': context_id,
            'message_id': message.messageId,
            'correlation_id': correlation_id,  # 跨流程追踪关联
        }
        print(f"[ADKHostManager] 🔄 正在更新会话状态: {state_update}")

        # 将状态更新事件添加到会话中
        await self._session_service.append_event(
            session,
            ADKEvent(
                id=ADKEvent.new_id(),
                author='host_agent',
                invocation_id=ADKEvent.new_id(),
                actions=ADKEventActions(state_delta=state_update),
            ),
        )
        print("[ADKHostManager] 📝 会话状态已更新")

        # 通过ADK主机智能体处理消息(这是核心AI协调处理)
        print("[ADKHostManager] 🤖 开始ADK主机智能体处理...")
        print("[ADKHostManager] 🧠 正在将消息转换为ADK格式进行大模型处理")

        llm_start_time = time.time()
        async for event in self._host_runner.run_async(
            user_id=self.user_id,
            session_id=context_id,
            new_message=self.adk_content_from_message(message),
        ):
            # 记录主机智能体的每个事件
            if event.content:
                event_text = ""
                # 安全提取ADK事件中的文本内容
                if hasattr(event.content, 'parts') and event.content.parts:
                    for part in event.content.parts:
                        if hasattr(part, 'text') and part.text:
                            event_text += part.text + " "

                # 记录大模型交互(捕获工具调用和响应)
                if event.author == 'host_agent' and event_text.strip():
                    llm_duration = (time.time() - llm_start_time) * 1000

                    # 检查这是否是工具调用或响应
                    if 'send_message' in event_text or 'list_remote_agents' in event_text:
                        # 这像是工具调用 - 尽可能提取智能体名称
                        agent_name = "unknown"
                        if 'send_message' in event_text:
                            # 尝试从工具调用中提取智能体名称
                            import re
                            agent_match = re.search(
                                r'agent_name["\s:]+([^",\s]+)', event_text)
                            if agent_match:
                                agent_name = agent_match.group(1)

                        WebUIFlowLogger.log_agent_selection(
                            correlation_id=correlation_id,
                            selected_agent=agent_name,
                            reasoning=event_text[:500]
                        )

                        LLMInteractionLogger.log_tool_execution(
                            correlation_id=correlation_id,
                            tool_name="send_message" if "send_message" in event_text else "list_remote_agents",
                            duration_ms=llm_duration
                        )
                    else:
                        # 常规大模型响应
                        LLMInteractionLogger.log_llm_response(
                            correlation_id=correlation_id,
                            response_length=len(event_text),
                            duration_ms=llm_duration,
                            model="ADK_Host_Agent"
                        )

            # 如果事件中存在任务ID则更新
            if (
                event.actions.state_delta
                and 'task_id' in event.actions.state_delta
            ):
                task_id = str(
                    event.actions.state_delta['task_id']) if event.actions.state_delta['task_id'] is not None else None
                # print(f"[ADKHostManager] 🎯 从事件更新任务ID: {task_id}")

            # 如果存在事件内容则处理
            if event.content:
                # print(f"[ADKHostManager] 📄 正在处理来自主机智能体的事件内容")
                self.add_event(
                    Event(
                        id=event.id,
                        actor=event.author,
                        content=await self.adk_content_to_message(
                            event.content, context_id, task_id
                        ),
                        timestamp=event.timestamp,
                    )
                )
                # print(f"[ADKHostManager] ✅ 事件内容已处理并存储")
            final_event = event

        print("[ADKHostManager] 🏁 主机智能体处理完成")

        # 生成最终响应消息
        response: Message | None = None
        if final_event:
            print("[ADKHostManager] 📝 正在从主机智能体输出生成最终响应")

            # 从最终事件更新任务ID
            if (
                final_event.actions.state_delta
                and 'task_id' in final_event.actions.state_delta
            ):
                task_id = str(
                    final_event.actions.state_delta['task_id']) if final_event.actions.state_delta['task_id'] is not None else None
                print(f"[ADKHostManager] 🎯 Final task ID: {task_id}")

            # Convert final event content to response message
            if final_event.content:
                final_event.content.role = 'model'
                response = await self.adk_content_to_message(
                    final_event.content, context_id, task_id
                )
                self._messages.append(response)
                print(
                    f"[ADKHostManager] ✅ Final response message created: {response.messageId}")

        # Add response to conversation history
        if conversation and response:
            conversation.messages.append(response)
            print("[ADKHostManager] 📚 Response added to conversation history")
            print(
                f"[ADKHostManager] 📊 Conversation now has {len(conversation.messages)} total messages")

        # Remove message from pending queue
        if message_id:
            self._pending_message_ids.remove(message_id)
            print(
                f"[ADKHostManager] ✅ Message removed from pending queue: {message_id}")
            print(
                f"[ADKHostManager] 📋 Pending queue now has {len(self._pending_message_ids)} messages")

        # print(f"[ADKHostManager] 🎉 Message processing completed successfully")
        # print(f"[ADKHostManager] 📡 Processing complete - UI will detect changes via polling")
        # print(f"[ADKHostManager] 🔄 No direct notification sent to ConversationServer")
        # print(f"[ADKHostManager] ⏰ UI polling will discover: updated conversation, empty queue, new events")

    def add_task(self, task: Task):
        self._tasks.append(task)

    def update_task(self, task: Task):
        for i, t in enumerate(self._tasks):
            if t.id == task.id:
                self._tasks[i] = task
                return

    def task_callback(self, task: TaskCallbackArg, agent_card: AgentCard):
        """Handle task callback events from remote agents.
        This processes task updates, status changes, and artifacts from remote agents.

        Flow:
        1. Remote Agent -> Host Agent: Task update via A2A
        2. Process different types of task events
        3. Update internal task state
        4. Create events for UI updates
        5. Handle task completion or continuation

        Args:
            task: Task update event (Task, TaskStatusUpdateEvent, or TaskArtifactUpdateEvent)
            agent_card: The agent card of the remote agent sending the update
        """
        # print(f"[ADKHostManager] 📞 Task callback received from remote agent: {agent_card.name}")
        # print(f"[ADKHostManager] 🔍 Task event type: {type(task).__name__}")

        # Log the task ID using defensive property access
        task_id = getattr(task, 'id', getattr(task, 'taskId', 'unknown'))
        # print(f"[ADKHostManager] 🎯 Task ID: {task_id}")

        # 循环检测：防止同一任务的递归调用
        if task_id in self._processing_tasks:
            print(f"[ADKHostManager] ⚠️ 检测到循环调用，跳过任务: {task_id}")
            # 返回一个基本任务而不是None以满足类型要求
            context_id = getattr(task, 'contextId', None) or 'unknown'
            return Task(
                id=task_id,
                status=TaskStatus(state=TaskState.submitted),
                artifacts=[],
                contextId=context_id,
            )

        # 检查回调深度，防止深度递归
        current_depth = self._callback_depth.get(task_id, 0)
        if current_depth > 5:  # 最大深度限制
            print(
                f"[ADKHostManager] ⚠️ 回调深度过深 ({current_depth})，跳过任务: {task_id}")
            # 清理深度计数器
            self._callback_depth[task_id] = 0
            # 返回一个基本任务以满足类型要求
            context_id = getattr(task, 'contextId', None) or 'unknown'
            return Task(
                id=task_id,
                status=TaskStatus(state=TaskState.submitted),
                artifacts=[],
                contextId=context_id,
            )

        # 标记任务正在处理
        self._processing_tasks.add(task_id)
        self._callback_depth[task_id] = current_depth + 1

        try:
            # Create UI event for task update first
            # print(f"[ADKHostManager] 📡 Creating UI event for task update")
            # print(f"[ADKHostManager] 📡 Emitting UI event for task update")
            # print(f"[ADKHostManager] 🤖 Agent: {agent_card.name}")
            # print(f"[ADKHostManager] 📊 Task type: {type(task).__name__}")
            # print(f"[ADKHostManager] 🎯 Context ID: {context_id}")
            self.emit_event(task, agent_card)

            # Handle different types of task events
            if isinstance(task, TaskStatusUpdateEvent):
                # print(f"[ADKHostManager] 📊 Processing task status update event")
                current_task = self.add_or_get_task(task)
                current_task.status = task.status
                # print(f"[ADKHostManager] 🔄 Updated task status: {task.status.state}")

                self.attach_message_to_task(
                    task.status.message, current_task.id)
                self.insert_message_history(current_task, task.status.message)
                self.update_task(current_task)
                # print(f"[ADKHostManager] ✅ Task status update completed")
                return current_task

            if isinstance(task, TaskArtifactUpdateEvent):
                # print(f"[ADKHostManager] 📎 Processing task artifact update event")
                current_task = self.add_or_get_task(task)
                self.process_artifact_event(current_task, task)
                self.update_task(current_task)
                # print(f"[ADKHostManager] ✅ Task artifact update completed")
                return current_task

            # Handle new or updated Task objects
            if isinstance(task, Task) and not any(filter(lambda x: isinstance(x, Task) and x.id == task.id, self._tasks)):
                # print(f"[ADKHostManager] 🆕 Processing new task")
                self.attach_message_to_task(task.status.message, task.id)
                self.add_task(task)
                # print(f"[ADKHostManager] ✅ New task added successfully")
                return task

            if isinstance(task, Task):
                # print(f"[ADKHostManager] 🔄 Processing existing task update")
                self.attach_message_to_task(task.status.message, task.id)
                self.update_task(task)
                # print(f"[ADKHostManager] ✅ Existing task updated successfully")
                return task

            print(f"[ADKHostManager] ❌ Unexpected task type: {type(task)}")
            # This shouldn't happen if TaskCallbackArg is properly typed
            raise ValueError(f"Unexpected task type: {type(task)}")

        finally:
            # 清理处理标记
            self._processing_tasks.discard(task_id)
            # 递减回调深度
            if task_id in self._callback_depth:
                self._callback_depth[task_id] = max(
                    0, self._callback_depth[task_id] - 1)
                # 如果深度回到0，清理计数器
                if self._callback_depth[task_id] == 0:
                    del self._callback_depth[task_id]

    def emit_event(self, task: TaskCallbackArg, agent_card: AgentCard):
        """Emit UI event for task updates from remote agents.
        Creates appropriate message content based on task type and stores it as an event.

        Flow:
        1. Analyze task type (TaskStatusUpdateEvent, TaskArtifactUpdateEvent, or Task)
        2. Extract relevant content and context
        3. Create appropriate Message object
        4. Store as Event for UI display

        Args:
            task: Task update from remote agent
            agent_card: Agent card of the remote agent sending the update
        """
        # print(f"[ADKHostManager] 📡 Emitting UI event for task update")
        # print(f"[ADKHostManager] 🤖 Agent: {agent_card.name}")
        # print(f"[ADKHostManager] 📊 Task type: {type(task)}")

        content = None
        context_id = task.contextId
        # print(f"[ADKHostManager] 🎯 Context ID: {context_id}")

        # Handle TaskStatusUpdateEvent
        if isinstance(task, TaskStatusUpdateEvent):
            # print(f"[ADKHostManager] 📈 Processing TaskStatusUpdateEvent")
            # print(f"[ADKHostManager] 🔄 Task status: {task.status.state}")

            if task.status.message:
                content = task.status.message
                # print(f"[ADKHostManager] 💬 Using status message as content")
            else:
                # Create message from status state
                content = Message(
                    parts=[Part(root=TextPart(text=str(task.status.state)))],
                    role=Role.agent,
                    messageId=str(uuid.uuid4()),
                    contextId=context_id,
                    taskId=getattr(task, 'id', getattr(
                        task, 'taskId', 'unknown')),
                )
                # print(f"[ADKHostManager] 📝 Created message from status state: {task.status.state}")

        # Handle TaskArtifactUpdateEvent
        elif isinstance(task, TaskArtifactUpdateEvent):
            # print(f"[ADKHostManager] 📎 Processing TaskArtifactUpdateEvent")
            # print(f"[ADKHostManager] 🗂️ Artifact has {len(task.artifact.parts)} parts")

            content = Message(
                parts=task.artifact.parts,
                role=Role.agent,
                messageId=str(uuid.uuid4()),
                contextId=context_id,
                taskId=getattr(task, 'id', getattr(task, 'taskId', 'unknown')),
            )
            # print(f"[ADKHostManager] 📄 Created message from artifact parts")

        # Handle Task object with status and message
        elif task.status and task.status.message:
            # print(f"[ADKHostManager] 📋 Processing Task with status message")
            # print(f"[ADKHostManager] 🔄 Task status: {task.status.state}")
            content = task.status.message
            # print(f"[ADKHostManager] 💬 Using task status message as content")

        # Handle Task object with artifacts
        elif task.artifacts:
            # print(f"[ADKHostManager] 🗃️ Processing Task with {len(task.artifacts)} artifacts")
            parts = []
            for i, a in enumerate(task.artifacts):
                parts.extend(a.parts)
                # print(f"[ADKHostManager] 📎 Added {len(a.parts)} parts from artifact {i+1}")

            content = Message(
                parts=parts,
                role=Role.agent,
                messageId=str(uuid.uuid4()),
                taskId=task.id,
                contextId=context_id,
            )
            # print(f"[ADKHostManager] 📄 Created message from {len(parts)} total artifact parts")

        # Fallback: create message from task status
        else:
            # print(f"[ADKHostManager] ⚠️ Fallback: creating message from task status")
            content = Message(
                parts=[Part(root=TextPart(text=str(task.status.state)))],
                role=Role.agent,
                messageId=str(uuid.uuid4()),
                taskId=task.id,
                contextId=context_id,
            )
            # print(f"[ADKHostManager] 📝 Created fallback message with status: {task.status.state}")

        # Store event if content was created
        if content:
            event_id = str(uuid.uuid4())
            # print(f"[ADKHostManager] 💾 Storing UI event: {event_id}")

            self.add_event(
                Event(
                    id=event_id,
                    actor=agent_card.name,
                    content=content,
                    timestamp=datetime.datetime.utcnow().timestamp(),
                )
            )
            # print(f"[ADKHostManager] ✅ UI event emitted successfully")
            # print(f"[ADKHostManager] 📊 Total events: {len(self._events)}")
        else:
            # print(f"[ADKHostManager] ❌ No content created for event emission")
            pass

    def attach_message_to_task(self, message: Message | None, task_id: str):
        if message:
            self._task_map[message.messageId] = task_id

    def insert_message_history(self, task: Task, message: Message | None):
        if not message:
            return
        if task.history is None:
            task.history = []
        message_id = message.messageId
        if not message_id:
            return
        if task.history and (
            task.status.message
            and task.status.message.messageId
            not in [x.messageId for x in task.history]
        ):
            task.history.append(task.status.message)
        elif not task.history and task.status.message:
            task.history = [task.status.message]
        else:
            print(
                'Message id already in history',
                task.status.message.messageId if task.status.message else '',
                task.history,
            )

    def add_or_get_task(self, event: TaskCallbackArg):
        task_id = None
        if isinstance(event, Message):
            task_id = event.taskId
        elif isinstance(event, Task):
            task_id = event.id
        else:
            task_id = event.taskId
        if not task_id:
            task_id = str(uuid.uuid4())
        current_task = next(
            filter(lambda x: x.id == task_id, self._tasks), None
        )
        if not current_task:
            context_id = event.contextId
            current_task = Task(
                id=task_id,
                # initialize with submitted
                status=TaskStatus(state=TaskState.submitted),
                artifacts=[],
                contextId=context_id,
            )
            self.add_task(current_task)
            return current_task

        return current_task

    def process_artifact_event(
        self, current_task: Task, task_update_event: TaskArtifactUpdateEvent
    ):
        """Process artifact update events for streaming support.
        Handles both complete artifacts and chunked/streaming artifacts.

        Flow:
        1. Check if this is an append or replace operation
        2. Handle complete artifacts vs chunks
        3. Assemble chunks when lastChunk is received
        4. Update task with final artifacts

        Args:
            current_task: The task being updated
            task_update_event: The artifact update event from remote agent
        """
        artifact = task_update_event.artifact
        print("[ADKHostManager] 📎 Processing artifact event")
        print(f"[ADKHostManager] 🆔 Artifact ID: {artifact.artifactId}")
        print(
            f"[ADKHostManager] 📄 Artifact name: {artifact.name or 'unnamed'}")
        print(f"[ADKHostManager] 📊 Artifact parts: {len(artifact.parts)}")
        print(f"[ADKHostManager] ➕ Append mode: {task_update_event.append}")
        print(f"[ADKHostManager] 🏁 Last chunk: {task_update_event.lastChunk}")

        if not task_update_event.append:
            print("[ADKHostManager] 🔄 Processing non-append artifact (replace mode)")

            # Received the first chunk or entire payload for an artifact
            if (
                task_update_event.lastChunk is None
                or task_update_event.lastChunk
            ):
                print(
                    "[ADKHostManager] ✅ Complete artifact received - adding to task")

                # Complete artifact - add directly to task
                if not current_task.artifacts:
                    current_task.artifacts = []
                current_task.artifacts.append(artifact)
                print(
                    f"[ADKHostManager] 📋 Task now has {len(current_task.artifacts)} artifacts")
            else:
                print(
                    "[ADKHostManager] 📦 First chunk of streaming artifact - storing in temp cache")

                # This is a chunk of an artifact, stash it in temp store for assembling
                if artifact.artifactId not in self._artifact_chunks:
                    self._artifact_chunks[artifact.artifactId] = []
                self._artifact_chunks[artifact.artifactId].append(artifact)
                print(
                    f"[ADKHostManager] 💾 Stored chunk {len(self._artifact_chunks[artifact.artifactId])} for artifact {artifact.artifactId}")
        else:
            print("[ADKHostManager] ➕ Processing append chunk")

            # We received an append chunk, add to the existing temp artifact
            if artifact.artifactId not in self._artifact_chunks or not self._artifact_chunks[artifact.artifactId]:
                print(
                    f"[ADKHostManager] ❌ No existing chunks found for append operation: {artifact.artifactId}")
                return

            current_temp_artifact = self._artifact_chunks[artifact.artifactId][-1]
            print(
                f"[ADKHostManager] 🔗 Appending {len(artifact.parts)} parts to existing artifact")

            # Extend parts of the current temporary artifact
            current_temp_artifact.parts.extend(artifact.parts)
            print(
                f"[ADKHostManager] 📊 Temp artifact now has {len(current_temp_artifact.parts)} total parts")

            if task_update_event.lastChunk:
                print("[ADKHostManager] 🏁 Last chunk received - finalizing artifact")

                # Final chunk - move from temp to task artifacts
                if current_task.artifacts:
                    current_task.artifacts.append(current_temp_artifact)
                else:
                    current_task.artifacts = [current_temp_artifact]

                # Clean up temp storage
                del self._artifact_chunks[artifact.artifactId][-1]
                if not self._artifact_chunks[artifact.artifactId]:
                    del self._artifact_chunks[artifact.artifactId]

                print("[ADKHostManager] ✅ Artifact finalized and added to task")
                print("[ADKHostManager] 🧹 Temp storage cleaned up")
                print(
                    f"[ADKHostManager] 📋 Task now has {len(current_task.artifacts)} total artifacts")
            else:
                print("[ADKHostManager] ⏳ More chunks expected for this artifact")

        print("[ADKHostManager] ✅ Artifact event processing completed")

    def add_event(self, event: Event):
        self._events[event.id] = event

    def get_conversation(
        self, conversation_id: str | None
    ) -> Conversation | None:
        if not conversation_id:
            return None
        return next(
            filter(
                lambda c: c and c.conversation_id == conversation_id,
                self._conversations,
            ),
            None,
        )

    def get_pending_messages(self) -> list[tuple[str, str]]:
        rval = []
        for message_id in self._pending_message_ids:
            if message_id in self._task_map:
                task_id = self._task_map[message_id]
                task = next(
                    filter(lambda x: x.id == task_id, self._tasks), None
                )
                if not task:
                    rval.append((message_id, ''))
                elif task.history and task.history[-1].parts:
                    if len(task.history) == 1:
                        rval.append((message_id, 'Working...'))
                    else:
                        part = task.history[-1].parts[0]
                        rval.append(
                            (
                                message_id,
                                part.root.text
                                if part.root.kind == 'text'
                                else 'Working...',
                            )
                        )
            else:
                rval.append((message_id, ''))
        return rval

    def register_agent(self, url):
        """Register a new remote agent with the Host Agent.
        This implements the agent registration flow from the sequence diagram.

        Flow:
        1. User provides agent URL/address
        2. Resolve agent card from URL
        3. Validate agent capabilities
        4. Store agent in connections
        5. Reinitialize Host Agent with new agent list

        Args:
            url: The URL or address of the remote agent to register
        """
        print(f"[ADKHostManager] 🔗 Registering new remote agent: {url}")

        try:
            # Resolve agent card from the provided URL
            print("[ADKHostManager] 🔍 Resolving agent card from URL")
            agent_data = get_agent_card(url)

            if not agent_data.url:
                print(f"[ADKHostManager] 🔧 Setting agent URL: {url}")
                agent_data.url = url

            print("[ADKHostManager] ✅ Agent card resolved successfully")
            print(f"[ADKHostManager] 🤖 Agent name: {agent_data.name}")
            print(
                f"[ADKHostManager] 📝 Agent description: {agent_data.description[:100]}...")
            print(
                f"[ADKHostManager] 🔄 Streaming support: {agent_data.capabilities.streaming if agent_data.capabilities else 'Unknown'}")

            # Add agent to the list of available agents
            self._agents.append(agent_data)
            print("[ADKHostManager] 📋 Added agent to available agents list")

            # Register agent card with the Host Agent
            self._host_agent.register_agent_card(agent_data)
            print("[ADKHostManager] 🤖 Registered agent card with Host Agent")

            # Reinitialize Host Agent with updated agent list
            print(
                "[ADKHostManager] 🔄 Reinitializing Host Agent with updated agent list")
            self._initialize_host()

            print("[ADKHostManager] ✅ Agent registration completed successfully")
            print(
                f"[ADKHostManager] 📊 Total available agents: {len(self._agents)}")

        except Exception as e:
            print(f"[ADKHostManager] ❌ Failed to register agent {url}: {e!s}")
            raise

    @property
    def agents(self) -> list[AgentCard]:
        return self._agents

    @property
    def conversations(self) -> list[Conversation]:
        return self._conversations

    @property
    def tasks(self) -> list[Task]:
        return self._tasks

    @property
    def events(self) -> list[Event]:
        return sorted(self._events.values(), key=lambda x: x.timestamp)

    def adk_content_from_message(self, message: Message) -> types.Content:
        """Convert A2A Message format to ADK Content format.
        This transformation is required before sending to the Host Agent LLM.

        Flow: A2A Message -> ADK Content -> Host Agent LLM processing
        """
        # print(f"[ADKHostManager] 🔄 Converting A2A Message to ADK Content format")
        # print(f"[ADKHostManager] 📝 Message has {len(message.parts)} parts to convert")

        parts: list[types.Part] = []
        for i, p in enumerate(message.parts):
            part = p.root
            # print(f"[ADKHostManager] 🔧 Converting part {i+1}: {part.kind}")

            if part.kind == 'text':
                parts.append(types.Part.from_text(text=part.text))
                # print(f"[ADKHostManager] ✅ Text part converted: {len(part.text)} characters")
            elif part.kind == 'data':
                json_string = json.dumps(part.data)
                parts.append(types.Part.from_text(text=json_string))
                # print(f"[ADKHostManager] ✅ Data part converted to JSON: {len(json_string)} characters")
            elif part.kind == 'file':
                if isinstance(part.file, FileWithUri):
                    parts.append(
                        types.Part.from_uri(
                            file_uri=part.file.uri,
                            mime_type=part.file.mimeType,
                        )
                    )
                    # print(f"[ADKHostManager] ✅ File URI part converted: {part.file.uri}")
                else:
                    parts.append(
                        types.Part.from_bytes(
                            data=part.file.bytes.encode('utf-8'),
                            mime_type=part.file.mimeType or 'application/octet-stream',
                        )
                    )
                    # print(f"[ADKHostManager] ✅ File bytes part converted: {len(part.file.bytes)} bytes")

        content = types.Content(parts=parts, role=str(message.role))
        # print(f"[ADKHostManager] ✅ A2A Message successfully converted to ADK Content")
        return content

    async def adk_content_to_message(
        self,
        content: types.Content,
        context_id: str | None,
        task_id: str | None,
    ) -> Message:
        """Convert ADK Content format back to A2A Message format.
        This transformation is required after Host Agent LLM processing.

        Flow: Host Agent LLM output -> ADK Content -> A2A Message -> UI display
        """
        print("[ADKHostManager] 🔄 Converting ADK Content to A2A Message format")
        print(
            f"[ADKHostManager] 📝 Content has {len(content.parts) if content.parts else 0} parts to convert")
        print(
            f"[ADKHostManager] 🎯 Context ID: {context_id}, Task ID: {task_id}")

        parts: list[Part] = []
        if not content.parts:
            print("[ADKHostManager] ⚠️ No content parts found, creating empty message")
            return Message(
                parts=[],
                role=Role.user if content.role == "user" else Role.agent,
                contextId=context_id,
                taskId=task_id,
                messageId=str(uuid.uuid4()),
            )
        for part in content.parts:
            if part.text:
                # try parse as data
                try:
                    data = json.loads(part.text)
                    parts.append(Part(root=DataPart(data=data)))
                except:
                    parts.append(Part(root=TextPart(text=part.text)))
            elif part.inline_data:
                # Handle inline data safely with proper null checks
                if hasattr(part.inline_data, 'data') and part.inline_data.data is not None:
                    data_bytes = part.inline_data.data
                    if isinstance(data_bytes, bytes):
                        try:
                            data_str = data_bytes.decode('utf-8')
                        except UnicodeDecodeError:
                            data_str = base64.b64encode(
                                data_bytes).decode('utf-8')
                    else:
                        data_str = str(data_bytes)
                else:
                    data_str = str(
                        part.inline_data) if part.inline_data else ""

                parts.append(
                    Part(
                        root=FilePart(
                            file=FileWithBytes(
                                bytes=data_str,
                                mimeType=getattr(
                                    part.file_data, 'mime_type', 'application/octet-stream') if part.file_data else 'application/octet-stream',
                            ),
                        )
                    )
                )
            elif part.file_data:
                parts.append(
                    Part(
                        root=FilePart(
                            file=FileWithUri(
                                uri=part.file_data.file_uri or '',
                                mimeType=getattr(
                                    part.file_data, 'mime_type', 'application/octet-stream'),
                            )
                        )
                    )
                )
            # These aren't managed by the A2A message structure, these are internal
            # details of ADK, we will simply flatten these to json representations.
            elif part.video_metadata:
                parts.append(
                    Part(root=DataPart(data=part.video_metadata.model_dump()))
                )
            elif part.thought:
                parts.append(Part(root=TextPart(text='thought')))
            elif part.executable_code:
                parts.append(
                    Part(root=DataPart(data=part.executable_code.model_dump()))
                )
            elif part.function_call:
                parts.append(
                    Part(root=DataPart(data=part.function_call.model_dump()))
                )
            elif part.function_response:
                parts.extend(
                    await self._handle_function_response(
                        part, context_id, task_id
                    )
                )
            else:
                raise ValueError('Unexpected content, unknown type')

        message = Message(
            role=Role.user if content.role == "user" else Role.agent,
            parts=parts,
            contextId=context_id,
            taskId=task_id,
            messageId=str(uuid.uuid4()),
        )

        print("[ADKHostManager] ✅ ADK Content successfully converted to A2A Message")
        print(
            f"[ADKHostManager] 📄 Final message has {len(parts)} parts, Role: {message.role}")
        print(f"[ADKHostManager] 🆔 Message ID: {message.messageId}")

        return message

    async def _handle_function_response(
        self, part: types.Part, context_id: str | None, task_id: str | None
    ) -> list[Part]:
        """Handle function response from ADK and convert to A2A Parts.
        Processes different types of function response data including artifacts and files.

        Flow:
        1. Validate function response exists
        2. Process each result item based on its type (string, dict, DataPart)
        3. Handle special cases like artifact files
        4. Convert to appropriate A2A Part types

        Args:
            part: ADK Part containing function response
            context_id: Context identifier for artifact loading
            task_id: Task identifier for tracking

        Returns:
            List of A2A Parts converted from function response
        """
        print("[ADKHostManager] 🔧 Processing function response")
        print(f"[ADKHostManager] 🎯 Context ID: {context_id}")
        print(f"[ADKHostManager] 📋 Task ID: {task_id}")

        parts = []
        try:
            # Check if function_response and response exist and are not None
            if not part.function_response or not part.function_response.response:
                print(
                    "[ADKHostManager] ⚠️ No function response or response data found")
                return parts

            response_data = part.function_response.response.get('result', [])
            print(
                f"[ADKHostManager] 📊 Processing {len(response_data)} response items")

            for i, p in enumerate(part.function_response.response['result']):
                print(
                    f"[ADKHostManager] 🔧 Processing response item {i+1}: {type(p).__name__}")

                if isinstance(p, str):
                    print(
                        f"[ADKHostManager] 📝 Converting string response: {len(p)} characters")
                    parts.append(Part(root=TextPart(text=p)))

                elif isinstance(p, dict):
                    if 'kind' in p and p['kind'] == 'file':
                        print(
                            "[ADKHostManager] 📁 Converting dictionary file response")
                        parts.append(Part(root=FilePart(**p)))
                    else:
                        print(
                            f"[ADKHostManager] 📋 Converting dictionary data response: {len(p)} keys")
                        parts.append(Part(root=DataPart(data=p)))

                elif isinstance(p, DataPart):
                    if 'artifact-file-id' in p.data:
                        print(
                            f"[ADKHostManager] 🎨 Processing artifact file: {p.data['artifact-file-id']}")

                        # Check context_id is not None before using it
                        if not context_id:
                            print(
                                "[ADKHostManager] ⚠️ No context_id provided for artifact loading, skipping")
                            continue

                        print("[ADKHostManager] 📂 Loading artifact from service")
                        file_part = await self._artifact_service.load_artifact(
                            user_id=self.user_id,
                            session_id=context_id,
                            app_name=self.app_name,
                            filename=p.data['artifact-file-id'],
                        )

                        if file_part and file_part.inline_data:
                            file_data = file_part.inline_data
                            if file_data.data is not None:
                                print(
                                    f"[ADKHostManager] 📦 Encoding artifact data to base64: {len(file_data.data)} bytes")
                                base64_data = base64.b64encode(file_data.data).decode(
                                    'utf-8'
                                )
                                parts.append(
                                    Part(
                                        root=FilePart(
                                            file=FileWithBytes(
                                                bytes=base64_data,
                                                mimeType=file_data.mime_type,
                                                name='artifact_file',
                                            )
                                        )
                                    )
                                )
                                print(
                                    "[ADKHostManager] ✅ Artifact file converted successfully")
                            else:
                                print(
                                    "[ADKHostManager] ⚠️ Artifact file data is None")
                        else:
                            print(
                                "[ADKHostManager] ⚠️ Failed to load artifact or no inline data")
                    else:
                        print(
                            f"[ADKHostManager] 📋 Converting DataPart: {len(p.data)} data items")
                        parts.append(Part(root=DataPart(data=p.data)))

                else:
                    print(
                        "[ADKHostManager] ❓ Unknown response type, creating default content")
                    content = Message(
                        parts=[Part(root=TextPart(text='Unknown content'))],
                        role=Role.agent,
                        messageId=str(uuid.uuid4()),
                        taskId=task_id,
                        contextId=context_id,
                    )

            print(
                f"[ADKHostManager] ✅ Function response processing completed: {len(parts)} parts created")

        except Exception as e:
            print(
                f"[ADKHostManager] ❌ Error converting function response to messages: {e!s}")
            print("[ADKHostManager] 🔧 Creating fallback response")

            # Check if function_response exists before calling model_dump
            if part.function_response:
                print(
                    "[ADKHostManager] 📋 Using function_response model dump as fallback")
                parts.append(
                    Part(root=DataPart(data=part.function_response.model_dump()))
                )
            else:
                print("[ADKHostManager] 📝 Using error text as fallback")
                parts.append(
                    Part(root=TextPart(text="Error processing function response"))
                )

        print(f"[ADKHostManager] 🎯 Returning {len(parts)} converted parts")
        return parts


def get_message_id(m: Message | None) -> str | None:
    """Extract message ID from Message metadata.
    Used for tracking message lineage in the A2A flow.

    Args:
        m: Message object to extract ID from

    Returns:
        Message ID if found, None otherwise
    """
    if not m:
        print("[ADKHostManager] ⚠️ get_message_id: No message provided")
        return None

    if not m.metadata or 'message_id' not in m.metadata:
        # print(f"[ADKHostManager] ⚠️ get_message_id: No message_id in metadata")
        return None

    message_id = m.metadata['message_id']
    print(f"[ADKHostManager] 🆔 get_message_id: Found message ID: {message_id}")
    return message_id


def task_still_open(task: Task | None) -> bool:
    """Check if a task is still in an active state.
    Used to determine whether task processing should continue.

    Active states: submitted, working, input_required
    Inactive states: completed, failed, cancelled

    Args:
        task: Task object to check status

    Returns:
        True if task is still active, False otherwise
    """
    if not task:
        print("[ADKHostManager] ⚠️ task_still_open: No task provided")
        return False

    is_open = task.status.state in [
        TaskState.submitted,
        TaskState.working,
        TaskState.input_required,
    ]

    print(
        f"[ADKHostManager] 📋 task_still_open: Task {task.id} state: {task.status.state}, open: {is_open}")
    return is_open
