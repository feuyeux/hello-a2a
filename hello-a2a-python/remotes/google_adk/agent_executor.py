import json
import logging
import time

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    DataPart,
    Part,
    Task,
    TaskState,
    TextPart,
    UnsupportedOperationError,
)
from a2a.utils import (
    new_agent_parts_message,
    new_agent_text_message,
    new_task,
)
from a2a.utils.errors import ServerError
from remotes.google_adk.agent import ReimbursementAgent

# 设置日志记录
logger = logging.getLogger(__name__)


class ReimbursementAgentExecutor(AgentExecutor):
    """
    Google ADK报销智能体执行器
    
    该执行器负责运行报销智能体并处理表单生成任务。主要功能包括：
    - 执行报销相关的查询和表单生成
    - 管理任务状态和用户交互流程
    - 提供详细的大模型调用和响应日志记录
    - 处理表单验证和数据结构转换
    - 支持流式响应和实时状态更新
    
    该智能体专门用于处理企业报销场景，能够生成结构化的报销表单
    并验证用户输入的有效性。
    """

    def __init__(self, llm_provider: str = "lmstudio", model_name: str = "qwen3-8b"):
        """初始化报销智能体执行器，创建底层智能体实例"""
        self.agent = ReimbursementAgent(llm_provider=llm_provider, model_name=model_name)
        logger.info(f"🏗️ [GoogleADK执行器] 报销智能体执行器初始化完成 - LLM 提供商: {llm_provider}, 模型: {model_name}")

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """执行报销智能体任务，包含详细的大模型调用日志"""
        query = context.get_user_input()
        task = context.current_task
        
        # 记录智能体开始处理
        correlation_id = f"gdk_agent_{int(time.time() * 1000)}"
        logger.info(f"📨 [GoogleADK] 智能体开始处理 - 关联ID: {correlation_id}")
        logger.info(f"📝 [GoogleADK] 用户输入: {query[:200]}...")
        logger.info(f"🎯 [GoogleADK] 任务ID: {task.id if task else '新任务'}")

        # 此智能体总是产生Task对象。如果此请求没有当前任务，创建新的并使用它。
        if not task:
            task = new_task(context.message)
            event_queue.enqueue_event(task)
            logger.info(f"🆕 [GoogleADK] 创建新任务: {task.id}")
            
        updater = TaskUpdater(event_queue, task.id, task.contextId)
        
        # 记录大模型调用开始
        llm_start_time = time.time()
        logger.info(f"🤖 [GoogleADK] 开始调用大模型 - 模型: ollama_chat/qwen3:8b")
        logger.info(f"📤 [GoogleADK] 大模型输入长度: {len(query)} 字符")
        
        # 调用底层智能体，使用流式结果。流现在是更新事件。
        async for item in self.agent.stream(query, task.contextId):
            is_task_complete = item['is_task_complete']
            artifacts = None
            if not is_task_complete:
                updater.update_status(
                    TaskState.working,
                    new_agent_text_message(
                        item['updates'], task.contextId, task.id
                    ),
                )
                logger.info(f"🔄 [GoogleADK] 任务进行中: {item['updates'][:100]}...")
                continue
                
            # 记录大模型响应完成
            llm_duration = (time.time() - llm_start_time) * 1000
            logger.info(f"✅ [GoogleADK] 大模型响应完成 - 耗时: {llm_duration:.2f}ms")
            logger.info(f"📥 [GoogleADK] 响应内容长度: {len(str(item['content']))} 字符")
            
            # 如果响应是字典，检查是表单还是处理结果
            if isinstance(item['content'], dict):
                logger.info(f"📋 [GoogleADK] 检测到字典响应")
                logger.info(f"🔍 [GoogleADK] 响应内容结构: {item['content']}")
                
                # 检查是否为表单响应
                if (
                    'response' in item['content']
                    and 'type' in item['content']['response']
                    and item['content']['response']['type'] == 'form'
                    and 'form' in item['content']['response']
                ):
                    # 处理表单响应
                    form_response = item['content']['response']
                    data = {
                        'form': form_response['form'],
                        'form_data': form_response.get('form_data', {}),
                        'instructions': form_response.get('instructions', '请填写表单')
                    }
                    logger.info(f"✅ [GoogleADK] 有效表单数据: {list(data.keys())}")
                    updater.update_status(
                        TaskState.input_required,
                        new_agent_parts_message(
                            [Part(root=DataPart(data=data))],
                            task.contextId,
                            task.id,
                        ),
                        final=True,
                    )
                    continue
                
                # 检查是否为处理结果响应（如reimburse函数的返回）
                elif (
                    'response' in item['content']
                    and 'request_id' in item['content']['response']
                    and 'status' in item['content']['response']
                ):
                    # 处理报销结果响应
                    result = item['content']['response']
                    status_msg = f"申请ID: {result['request_id']}\n状态: {result['status']}"
                    logger.info(f"✅ [GoogleADK] 报销处理完成: {status_msg}")
                    updater.update_status(
                        TaskState.completed,
                        new_agent_text_message(
                            status_msg,
                            task.contextId,
                            task.id,
                        ),
                        final=True,
                    )
                    continue
                
                logger.error(f"❌ [GoogleADK] 无法识别的响应格式")
                updater.update_status(
                    TaskState.failed,
                    new_agent_text_message(
                        '智能体响应格式不正确，任务执行失败',
                        task.contextId,
                        task.id,
                    ),
                    final=True,
                )
                break
            
            # 处理文本响应内容
            logger.info(f"🎉 [GoogleADK] 任务完成，生成最终文本结果")
            updater.add_artifact(
                [Part(root=TextPart(text=item['content']))], name='response'
            )
            updater.complete()
            break

    async def cancel(
        self, request: RequestContext, event_queue: EventQueue
    ) -> Task | None:
        """
        取消正在执行的任务
        
        注意：当前Google ADK智能体不支持任务取消操作
        
        Args:
            request: 请求上下文，包含任务取消相关信息
            event_queue: 事件队列，用于发送取消状态更新
            
        Returns:
            None
            
        Raises:
            UnsupportedOperationError: 总是抛出此异常，因为不支持取消操作
        """
        logger.warning(f"⚠️ [GoogleADK] 尝试取消任务，但Google ADK智能体不支持取消操作")
        logger.info(f"📋 [GoogleADK] 取消请求详情 - 上下文ID: {request.context.id}")
        raise ServerError(error=UnsupportedOperationError())
