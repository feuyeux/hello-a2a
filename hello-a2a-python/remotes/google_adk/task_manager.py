import logging
import time

from abc import ABC, abstractmethod
from collections.abc import AsyncIterable
from typing import Any

from google.genai import types
from .llm_logger import adk_llm_logger, log_google_adk_event


logger = logging.getLogger(__name__)


class AgentWithTaskManager(ABC):
    """
    带任务管理功能的智能体抽象基类
    
    该类提供了智能体任务执行的通用框架，包括：
    - 与Google ADK运行器的集成
    - 会话状态管理  
    - 大模型调用的日志记录
    - 同步和异步执行模式
    - 错误处理和性能监控
    
    子类需要实现get_processing_message方法来提供处理状态消息
    """
    
    # 子类需要实现的抽象属性
    _agent: Any      # Google ADK智能体实例
    _user_id: str    # 用户标识符
    _runner: Any     # ADK运行器实例

    @abstractmethod
    def get_processing_message(self) -> str:
        """
        获取任务处理中的状态消息
        
        Returns:
            str: 显示给用户的处理状态消息
        """
        pass

    async def invoke(self, query, session_id) -> str:
        """
        同步执行智能体任务
        
        该方法会等待智能体完成整个任务后返回最终结果，适用于：
        - 需要完整结果的场景
        - 批处理任务
        - 简单的问答交互
        
        Args:
            query (str): 用户查询或任务描述
            session_id (str): 会话标识符，用于维护对话上下文
            
        Returns:
            str: 智能体的完整响应结果
            
        Raises:
            Exception: 智能体执行过程中的任何错误
        """
        logger.info(f"[大模型调用] 开始同步执行任务，查询内容: {query[:100]}...")
        start_time = time.time()

        # 获取或创建会话
        session = await self._runner.session_service.get_session(
            app_name=self._agent.name,
            user_id=self._user_id,
            session_id=session_id,
        )
        content = types.Content(
            role='user', parts=[types.Part.from_text(text=query)]
        )

        # 记录用户输入到大模型的请求日志
        adk_llm_logger.log_request(
            request_id=session_id,
            model="ollama_chat/qwen3:0.6b",
            prompt_length=len(query),
            correlation_id=session_id
        )

        if session is None:
            logger.info(f"[会话管理] 为用户 {self._user_id} 创建新会话: {session_id}")
            session = await self._runner.session_service.create_session(
                app_name=self._agent.name,
                user_id=self._user_id,
                state={},
                session_id=session_id,
            )

        try:
            # 执行智能体任务并收集所有事件
            logger.info(f"[任务执行] 开始运行智能体 {self._agent.name}")
            events = list(
                self._runner.run(
                    user_id=self._user_id,
                    session_id=session.id,
                    new_message=content,
                )
            )

            # 记录所有执行事件用于调试
            for i, event in enumerate(events):
                log_google_adk_event(event, session_id)
                logger.debug(f"[事件追踪] 第{i+1}个事件: {type(event).__name__}")

            duration_ms = (time.time() - start_time) * 1000

            # 提取最终响应内容
            if not events or not events[-1].content or not events[-1].content.parts:
                response = ''
                logger.warning(f"[响应处理] 智能体 {self._agent.name} 没有返回有效响应")
            else:
                response = '\n'.join([p.text for p in events[-1].content.parts if p.text])
                logger.info(f"[响应处理] 智能体 {self._agent.name} 返回响应，长度: {len(response)} 字符")

            # 记录大模型的最终响应日志
            adk_llm_logger.log_response(
                request_id=session_id,
                model="ollama_chat/qwen3:0.6b",
                duration_ms=duration_ms,
                response_length=len(response)
            )

            return response

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(f"[任务执行] 智能体 {self._agent.name} 执行失败: {str(e)}")
            adk_llm_logger.log_error(
                request_id=session_id,
                error=str(e),
                model="ollama_chat/qwen3:0.6b",
                session_id=session_id,
                user_id=self._user_id,
                metadata={
                    "method": "invoke",
                    "agent_name": self._agent.name,
                    "duration_ms": duration_ms
                }
            )
            raise

    async def stream(self, query, session_id) -> AsyncIterable[dict[str, Any]]:
        """
        流式执行智能体任务
        
        该方法以流式方式执行任务，实时返回处理状态和中间结果，适用于：
        - 长时间运行的任务
        - 需要实时反馈的交互
        - 复杂的多步骤处理
        
        Args:
            query (str): 用户查询或任务描述
            session_id (str): 会话标识符，用于维护对话上下文
            
        Yields:
            dict[str, Any]: 包含任务状态和内容的字典
                - is_task_complete (bool): 任务是否完成
                - content (str): 最终结果（仅当任务完成时）
                - updates (str): 处理状态消息（任务进行中时）
                
        Raises:
            Exception: 智能体执行过程中的任何错误
        """
        logger.info(f"[大模型调用] 开始流式执行任务，查询内容: {query[:100]}...")
        start_time = time.time()

        # 获取或创建会话
        session = await self._runner.session_service.get_session(
            app_name=self._agent.name,
            user_id=self._user_id,
            session_id=session_id,
        )
        content = types.Content(
            role='user', parts=[types.Part.from_text(text=query)]
        )

        # 记录流式请求的用户输入日志
        adk_llm_logger.log_request(
            request_id=session_id,
            model="ollama_chat/qwen3:0.6b",
            prompt_length=len(query),
            correlation_id=session_id
        )

        if session is None:
            logger.info(f"[会话管理] 为用户 {self._user_id} 创建新流式会话: {session_id}")
            session = await self._runner.session_service.create_session(
                app_name=self._agent.name,
                user_id=self._user_id,
                state={},
                session_id=session_id,
            )

        event_count = 0
        try:
            logger.info(f"[流式执行] 开始流式运行智能体 {self._agent.name}")
            async for event in self._runner.run_async(
                user_id=self._user_id, session_id=session.id, new_message=content
            ):
                event_count += 1

                # 记录每个流式事件
                log_google_adk_event(event, session_id)
                logger.debug(f"[流式事件] 第{event_count}个事件: {type(event).__name__}")

                if event.is_final_response():
                    # 处理最终响应
                    duration_ms = (time.time() - start_time) * 1000
                    response = ''

                    if (
                        event.content
                        and event.content.parts
                        and event.content.parts[0].text
                    ):
                        response = '\n'.join(
                            [p.text for p in event.content.parts if p.text]
                        )
                        logger.info(f"[流式完成] 智能体返回文本响应，长度: {len(response)} 字符")
                    elif (
                        event.content
                        and event.content.parts
                        and any(
                            [
                                True
                                for p in event.content.parts
                                if p.function_response
                            ]
                        )
                    ):
                        response = next(
                            p.function_response.model_dump()
                            for p in event.content.parts
                        )
                        logger.info(f"[流式完成] 智能体返回功能调用响应: {type(response)}")

                    # 记录最终流式响应日志
                    adk_llm_logger.log_response(
                        request_id=session_id,
                        model="ollama_chat/qwen3:0.6b",
                        duration_ms=duration_ms,
                        response_length=len(str(response))
                    )

                    yield {
                        'is_task_complete': True,
                        'content': response,
                    }
                else:
                    # 返回处理中状态
                    logger.debug(f"[流式进度] 智能体 {self._agent.name} 处理中，已处理 {event_count} 个事件")
                    yield {
                        'is_task_complete': False,
                        'updates': self.get_processing_message(),
                    }

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(f"[流式执行] 智能体 {self._agent.name} 执行失败: {str(e)}")
            adk_llm_logger.log_error(
                request_id=session_id,
                model="ollama_chat/qwen3:0.6b",
                error=str(e)
            )
            raise
