import asyncio
import base64
import json
import logging
import os
import threading
import uuid

from datetime import datetime
from typing import Any

import httpx

from a2a.types import FilePart, FileWithUri, Message, Part
from fastapi import FastAPI, Request, Response

from service.types import (
    CreateConversationResponse,
    GetEventResponse,
    ListAgentResponse,
    ListConversationResponse,
    ListMessageResponse,
    ListTaskResponse,
    MessageInfo,
    PendingMessageResponse,
    RegisterAgentResponse,
    SendMessageResponse,
)

from .adk_host_manager import ADKHostManager, get_message_id
from .application_manager import ApplicationManager
from .in_memory_manager import InMemoryFakeAgentManager


# Enhanced logging setup
logger = logging.getLogger(__name__)


class WebUIFlowLogger:
    """简洁的WebUI流程日志记录器"""

    @staticmethod
    def log_user_request_start(correlation_id: str, message: Message):
        """记录用户请求开始"""
        logger.info(f"🚀 用户请求开始: ID:{correlation_id[:8]} | 消息:{message.messageId}")

    @staticmethod
    def log_request_delegated_to_manager(correlation_id: str, manager_type: str, background_processing: bool):
        """记录请求委托给管理器"""
        logger.info(f"📤 请求委托: {manager_type} | ID:{correlation_id[:8]} | 后台:{background_processing}")

    @staticmethod
    def log_immediate_response_sent(correlation_id: str, response_info: MessageInfo):
        """记录立即响应"""
        logger.info(f"↩️ 立即响应: ID:{correlation_id[:8]} | 响应:{response_info.message_id}")

    @staticmethod
    def log_error(correlation_id: str, error: str, context: dict[str, Any] | None = None):
        """记录错误"""
        logger.error(f"❌ 流程错误: ID:{correlation_id[:8]} | {error}")


class ConversationServer:
    """ConversationServer is the backend to serve the agent interactions in the UI

    This defines the interface that is used by the Mesop system to interact with
    agents and provide details about the executions.
    """

    def __init__(self, app: FastAPI, http_client: httpx.AsyncClient):
        agent_manager = os.environ.get('A2A_HOST', 'ADK')
        self.manager: ApplicationManager

        # Get API key from environment
        api_key = os.environ.get('GOOGLE_API_KEY', '')
        uses_vertex_ai = (
            os.environ.get('GOOGLE_GENAI_USE_VERTEXAI', '').upper() == 'TRUE'
        )

        if agent_manager.upper() == 'ADK':
            self.manager = ADKHostManager(
                http_client,
                api_key=api_key,
                uses_vertex_ai=uses_vertex_ai,
            )
        else:
            self.manager = InMemoryFakeAgentManager()
        # dict[str, FilePart] maps file id to message data
        self._file_cache = {}
        # dict[str, str] maps message id to cache id
        self._message_to_cache = {}

        app.add_api_route(
            '/conversation/create', self._create_conversation, methods=['POST']
        )
        app.add_api_route(
            '/conversation/list', self._list_conversation, methods=['POST']
        )
        app.add_api_route(
            '/message/send', self._send_message, methods=['POST'])
        app.add_api_route('/events/get', self._get_events, methods=['POST'])
        app.add_api_route(
            '/message/list', self._list_messages, methods=['POST']
        )
        app.add_api_route(
            '/message/pending', self._pending_messages, methods=['POST']
        )
        app.add_api_route('/task/list', self._list_tasks, methods=['POST'])
        app.add_api_route(
            '/agent/register', self._register_agent, methods=['POST']
        )
        app.add_api_route('/agent/list', self._list_agents, methods=['POST'])
        app.add_api_route(
            '/message/file/{file_id}', self._files, methods=['GET']
        )
        app.add_api_route(
            '/api_key/update', self._update_api_key, methods=['POST']
        )

    # Update API key in manager
    def update_api_key(self, api_key: str):
        if isinstance(self.manager, ADKHostManager):
            self.manager.update_api_key(api_key)

    async def _create_conversation(self):
        c = await self.manager.create_conversation()
        return CreateConversationResponse(result=c)

    async def _send_message(self, request: Request):
        """Handle incoming message from Web Interface.
        This is the entry point for the message processing flow as shown in the sequence diagram.

        Flow:
        1. UI -> ConversationServer: POST /message/send
        2. Parse and validate message
        3. Delegate to ADKHostManager for processing
        4. Return immediate response while processing continues in background
        """
        # Generate correlation ID for complete flow tracking
        correlation_id = str(uuid.uuid4())

        try:
            print("[ConversationServer] 📨 Received message request from Web Interface")

            message_data = await request.json()
            print("[ConversationServer] 📋 Parsing message data")

            # Parse message from JSON request
            message = Message(**message_data['params'])

            # Log user request start
            WebUIFlowLogger.log_user_request_start(correlation_id, message)

            # Sanitize and validate the message through manager
            message = self.manager.sanitize_message(message)
            print(
                f"[WebUIFlow:{correlation_id}] 🧹 Message sanitized and validated")

            # Pass correlation ID to manager for complete flow tracking
            manager_type = type(self.manager).__name__

            # Log delegation to manager
            WebUIFlowLogger.log_request_delegated_to_manager(
                correlation_id=correlation_id,
                manager_type=manager_type,
                background_processing=True
            )

            # Start message processing in background thread to avoid blocking the UI
            print(
                f"[WebUIFlow:{correlation_id}] 🚀 Starting background message processing thread")

            # Create a wrapper function to pass correlation_id to process_message
            def background_processing():
                # Set correlation ID in the message context for downstream tracking
                if hasattr(message, '__dict__'):
                    message.__dict__['_correlation_id'] = correlation_id

                # Call with keyword argument
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(
                        self.manager.process_message(message, correlation_id))
                finally:
                    loop.close()

            t = threading.Thread(target=background_processing)
            t.start()

            # Return immediate response to UI while processing continues
            response_info = MessageInfo(
                message_id=message.messageId,
                context_id=message.contextId if message.contextId else '',
            )

            # Log immediate response
            WebUIFlowLogger.log_immediate_response_sent(
                correlation_id, response_info)

            return SendMessageResponse(result=response_info)

        except Exception as e:
            # Log error in WebUI flow
            WebUIFlowLogger.log_error(
                correlation_id=correlation_id,
                error=str(e),
                context={"method": "_send_message",
                         "step": "message_processing"}
            )
            raise

    async def _list_messages(self, request: Request):
        message_data = await request.json()
        conversation_id = message_data['params']

        conversation = self.manager.get_conversation(conversation_id)
        if conversation:
            cached_messages = self.cache_content(conversation.messages)
            return ListMessageResponse(result=cached_messages)

        return ListMessageResponse(result=[])

    def cache_content(self, messages: list[Message]):
        rval = []
        for m in messages:
            message_id = get_message_id(m)
            if not message_id:
                rval.append(m)
                continue
            new_parts: list[Part] = []
            for i, p in enumerate(m.parts):
                part = p.root
                if part.kind != 'file':
                    new_parts.append(p)
                    continue
                message_part_id = f'{message_id}:{i}'
                if message_part_id in self._message_to_cache:
                    cache_id = self._message_to_cache[message_part_id]
                else:
                    cache_id = str(uuid.uuid4())
                    self._message_to_cache[message_part_id] = cache_id
                # Replace the part data with a url reference
                new_parts.append(
                    Part(
                        root=FilePart(
                            file=FileWithUri(
                                mimeType=part.file.mimeType,
                                uri=f'/message/file/{cache_id}',
                            )
                        )
                    )
                )
                if cache_id not in self._file_cache:
                    self._file_cache[cache_id] = part
            m.parts = new_parts
            rval.append(m)
        return rval

    async def _pending_messages(self):
        pending_messages = self.manager.get_pending_messages()
        return PendingMessageResponse(result=pending_messages)

    def _list_conversation(self):
        conversations = self.manager.conversations
        return ListConversationResponse(result=conversations)

    def _get_events(self):
        events = self.manager.events
        return GetEventResponse(result=events)

    def _list_tasks(self):
        tasks = self.manager.tasks
        return ListTaskResponse(result=tasks)

    async def _register_agent(self, request: Request):
        message_data = await request.json()
        url = message_data['params']
        self.manager.register_agent(url)
        return RegisterAgentResponse()

    async def _list_agents(self):
        return ListAgentResponse(result=self.manager.agents)

    def _files(self, file_id):
        if file_id not in self._file_cache:
            raise Exception('file not found')
        part = self._file_cache[file_id]
        if 'image' in part.file.mimeType:
            return Response(
                content=base64.b64decode(part.file.bytes),
                media_type=part.file.mimeType,
            )
        return Response(content=part.file.bytes, media_type=part.file.mimeType)

    async def _update_api_key(self, request: Request):
        """Update the API key"""
        try:
            data = await request.json()
            api_key = data.get('api_key', '')

            if api_key:
                # Update in the manager
                self.update_api_key(api_key)
                return {'status': 'success'}
            return {'status': 'error', 'message': 'No API key provided'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
