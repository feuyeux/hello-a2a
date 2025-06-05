from typing import Annotated, Any, Literal
from uuid import uuid4

from a2a.types import (
    AgentCard,
    Message,
    Task,
)
from pydantic import BaseModel, Field, TypeAdapter


class JSONRPCMessage(BaseModel):
    """JSON-RPC消息基类"""
    jsonrpc: Literal['2.0'] = '2.0'
    id: int | str | None = Field(default_factory=lambda: uuid4().hex)


class JSONRPCRequest(JSONRPCMessage):
    """JSON-RPC请求消息"""
    method: str
    params: Any | None = None


class JSONRPCError(BaseModel):
    """JSON-RPC错误信息"""
    code: int
    message: str
    data: Any | None = None


class JSONRPCResponse(JSONRPCMessage):
    """JSON-RPC响应消息"""
    result: Any | None = None
    error: JSONRPCError | None = None


class Conversation(BaseModel):
    """对话会话模型"""
    conversation_id: str  # 会话唯一标识符
    is_active: bool  # 会话是否活跃
    name: str = ''  # 会话名称
    task_ids: list[str] = Field(default_factory=list)  # 关联的任务ID列表
    messages: list[Message] = Field(default_factory=list)  # 消息列表


class Event(BaseModel):
    """事件模型"""
    id: str  # 事件唯一标识符
    actor: str = ''  # 事件发起者
    # TODO: 扩展支持模型内部概念，如函数调用
    content: Message  # 事件内容
    timestamp: float  # 时间戳


class SendMessageRequest(JSONRPCRequest):
    """发送消息请求"""
    method: Literal['message/send'] = 'message/send'
    params: Message


class ListMessageRequest(JSONRPCRequest):
    """列出消息请求"""
    method: Literal['message/list'] = 'message/list'
    # 这是会话ID
    params: str


class ListMessageResponse(JSONRPCResponse):
    """列出消息响应"""
    result: list[Message] | None = None


class MessageInfo(BaseModel):
    """消息信息"""
    message_id: str  # 消息ID
    context_id: str  # 上下文ID


class SendMessageResponse(JSONRPCResponse):
    """发送消息响应"""
    result: Message | MessageInfo | None = None


class GetEventRequest(JSONRPCRequest):
    """获取事件请求"""
    method: Literal['events/get'] = 'events/get'


class GetEventResponse(JSONRPCResponse):
    """获取事件响应"""
    result: list[Event] | None = None


class ListConversationRequest(JSONRPCRequest):
    """列出会话请求"""
    method: Literal['conversation/list'] = 'conversation/list'


class ListConversationResponse(JSONRPCResponse):
    """列出会话响应"""
    result: list[Conversation] | None = None


class PendingMessageRequest(JSONRPCRequest):
    """待处理消息请求"""
    method: Literal['message/pending'] = 'message/pending'


class PendingMessageResponse(JSONRPCResponse):
    """待处理消息响应"""
    result: list[tuple[str, str]] | None = None


class CreateConversationRequest(JSONRPCRequest):
    """创建会话请求"""
    method: Literal['conversation/create'] = 'conversation/create'


class CreateConversationResponse(JSONRPCResponse):
    """创建会话响应"""
    result: Conversation | None = None


class ListTaskRequest(JSONRPCRequest):
    """列出任务请求"""
    method: Literal['task/list'] = 'task/list'


class ListTaskResponse(JSONRPCResponse):
    """列出任务响应"""
    result: list[Task] | None = None


class RegisterAgentRequest(JSONRPCRequest):
    """注册智能体请求"""
    method: Literal['agent/register'] = 'agent/register'
    # 这是智能体卡片的基础URL
    params: str | None = None


class RegisterAgentResponse(JSONRPCResponse):
    """注册智能体响应"""
    result: str | None = None


class ListAgentRequest(JSONRPCRequest):
    """列出智能体请求"""
    method: Literal['agent/list'] = 'agent/list'


class ListAgentResponse(JSONRPCResponse):
    """列出智能体响应"""
    result: list[AgentCard] | None = None


AgentRequest = TypeAdapter(
    Annotated[
        SendMessageRequest | ListConversationRequest,
        Field(discriminator='method'),
    ]
)


class AgentClientError(Exception):
    """智能体客户端错误基类"""
    pass


class AgentClientHTTPError(AgentClientError):
    """智能体客户端HTTP错误"""
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f'HTTP错误 {status_code}: {message}')


class AgentClientJSONError(AgentClientError):
    """智能体客户端JSON错误"""
    def __init__(self, message: str):
        self.message = message
        super().__init__(f'JSON错误: {message}')
