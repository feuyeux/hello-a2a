from typing import Union, Any
from pydantic import BaseModel, Field, TypeAdapter
from typing import Literal, List, Annotated, Optional
from datetime import datetime
from pydantic import model_validator, ConfigDict, field_serializer
from uuid import uuid4
from enum import Enum
from typing_extensions import Self


class TaskState(str, Enum):
    """任务状态枚举，定义了任务的核心状态"""
    SUBMITTED = "submitted"  # 已提交
    WORKING = "working"      # 处理中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"        # 失败


class TextPart(BaseModel):
    """文本部分模型，表示消息中的文本内容"""
    type: Literal["text"] = "text"  # 类型标识，固定为"text"
    text: str                       # 文本内容
    metadata: dict[str, Any] | None = None  # 可选的元数据


class FileContent(BaseModel):
    """文件内容模型，表示文件数据"""
    name: str | None = None        # 文件名
    mimeType: str | None = None    # MIME类型
    bytes: str | None = None       # Base64编码的文件内容
    uri: str | None = None         # 文件URI

    @model_validator(mode="after")
    def check_content(self) -> Self:
        """验证文件内容，确保bytes或uri至少有一个存在且不能同时存在"""
        if not (self.bytes or self.uri):
            raise ValueError(
                "Either 'bytes' or 'uri' must be present in the file data")
        if self.bytes and self.uri:
            raise ValueError(
                "Only one of 'bytes' or 'uri' can be present in the file data"
            )
        return self


class FilePart(BaseModel):
    """文件部分模型，表示消息中的文件内容"""
    type: Literal["file"] = "file"  # 类型标识，固定为"file"
    file: FileContent               # 文件内容
    metadata: dict[str, Any] | None = None  # 可选的元数据


class DataPart(BaseModel):
    """数据部分模型，表示消息中的结构化数据"""
    type: Literal["data"] = "data"  # 类型标识，固定为"data"
    data: dict[str, Any]            # 结构化数据
    metadata: dict[str, Any] | None = None  # 可选的元数据


# 消息部分联合类型，可以是文本、文件或数据
Part = Annotated[Union[TextPart, FilePart,
                       DataPart], Field(discriminator="type")]


class Message(BaseModel):
    """消息模型，表示用户或智能体的一条消息"""
    role: Literal["user", "agent"]  # 消息发送者角色
    parts: List[Part]               # 消息部分列表
    metadata: dict[str, Any] | None = None  # 可选的元数据


class TaskStatus(BaseModel):
    """任务状态模型，表示任务的当前状态"""
    state: TaskState                # 任务状态
    message: Message | None = None  # 可选的相关消息
    timestamp: datetime = Field(default_factory=datetime.now)  # 状态更新时间戳

    @field_serializer("timestamp")
    def serialize_dt(self, dt: datetime, _info):
        """将时间戳序列化为ISO格式字符串"""
        return dt.isoformat()


class Artifact(BaseModel):
    """成品模型，表示任务产生的结果"""
    name: str | None = None         # 成品名称
    description: str | None = None  # 成品描述
    parts: List[Part]               # 成品部分列表
    metadata: dict[str, Any] | None = None  # 可选的元数据
    index: int = 0                  # 成品索引
    append: bool | None = None      # 是否追加模式
    lastChunk: bool | None = None   # 是否为最后一块


class Task(BaseModel):
    """任务模型，表示一个完整的任务"""
    id: str                         # 任务ID
    sessionId: str | None = None    # 会话ID
    status: TaskStatus              # 任务状态
    artifacts: List[Artifact] | None = None  # 成品列表
    history: List[Message] | None = None     # 消息历史
    metadata: dict[str, Any] | None = None   # 可选的元数据


class TaskStatusUpdateEvent(BaseModel):
    """任务状态更新事件模型"""
    id: str                         # 任务ID
    status: TaskStatus              # 更新后的任务状态
    final: bool = False             # 是否为最终状态
    metadata: dict[str, Any] | None = None  # 可选的元数据


class TaskArtifactUpdateEvent(BaseModel):
    """任务成品更新事件模型"""
    id: str                         # 任务ID
    artifact: Artifact              # 更新的成品
    metadata: dict[str, Any] | None = None  # 可选的元数据


class AuthenticationInfo(BaseModel):
    """认证信息模型"""
    model_config = ConfigDict(extra="allow")  # 允许额外字段

    schemes: List[str]              # 认证方案列表
    credentials: str | None = None  # 认证凭据


class PushNotificationConfig(BaseModel):
    """推送通知配置模型"""
    url: str                        # 推送通知URL
    token: str | None = None        # 可选的令牌
    authentication: AuthenticationInfo | None = None  # 认证信息


class TaskIdParams(BaseModel):
    """任务ID参数模型"""
    id: str                         # 任务ID
    metadata: dict[str, Any] | None = None  # 可选的元数据


class TaskQueryParams(TaskIdParams):
    """任务查询参数模型，扩展自TaskIdParams"""
    historyLength: int | None = None  # 历史长度限制


class TaskSendParams(BaseModel):
    """任务发送参数模型"""
    id: str                         # 任务ID
    sessionId: str = Field(
        default_factory=lambda: uuid4().hex)  # 会话ID，默认生成新的UUID
    message: Message                # 消息内容
    acceptedOutputModes: Optional[List[str]] = None  # 接受的输出模式
    pushNotification: PushNotificationConfig | None = None  # 推送通知配置
    historyLength: int | None = None  # 历史长度限制
    metadata: dict[str, Any] | None = None  # 可选的元数据


class TaskPushNotificationConfig(BaseModel):
    """任务推送通知配置模型"""
    id: str                         # 任务ID
    pushNotificationConfig: PushNotificationConfig  # 推送通知配置


# RPC消息

class JSONRPCMessage(BaseModel):
    """JSON-RPC消息基类"""
    jsonrpc: Literal["2.0"] = "2.0"  # JSON-RPC版本
    id: int | str | None = Field(default_factory=lambda: uuid4().hex)  # 消息ID


class JSONRPCRequest(JSONRPCMessage):
    """JSON-RPC请求模型"""
    method: str                     # 方法名
    params: dict[str, Any] | None = None  # 参数


class JSONRPCError(BaseModel):
    """JSON-RPC错误模型"""
    code: int                       # 错误代码
    message: str                    # 错误消息
    data: Any | None = None         # 可选的错误数据


class JSONRPCResponse(JSONRPCMessage):
    """JSON-RPC响应模型"""
    result: Any | None = None       # 结果
    error: JSONRPCError | None = None  # 错误信息


class SendTaskRequest(JSONRPCRequest):
    """发送任务请求模型"""
    method: Literal["tasks/send"] = "tasks/send"  # 固定方法名
    params: TaskSendParams          # 任务发送参数


class SendTaskResponse(JSONRPCResponse):
    """发送任务响应模型"""
    result: Task | None = None      # 任务结果


class SendTaskStreamingRequest(JSONRPCRequest):
    """发送流式任务请求模型"""
    method: Literal["tasks/sendSubscribe"] = "tasks/sendSubscribe"  # 固定方法名
    params: TaskSendParams          # 任务发送参数


class SendTaskStreamingResponse(JSONRPCResponse):
    """发送流式任务响应模型"""
    result: TaskStatusUpdateEvent | TaskArtifactUpdateEvent | None = None  # 事件结果


class GetTaskRequest(JSONRPCRequest):
    """获取任务请求模型"""
    method: Literal["tasks/get"] = "tasks/get"  # 固定方法名
    params: TaskQueryParams         # 任务查询参数


class GetTaskResponse(JSONRPCResponse):
    """获取任务响应模型"""
    result: Task | None = None      # 任务结果


class CancelTaskRequest(JSONRPCRequest):
    """取消任务请求模型"""
    method: Literal["tasks/cancel",] = "tasks/cancel"  # 固定方法名
    params: TaskIdParams            # 任务ID参数


class CancelTaskResponse(JSONRPCResponse):
    """取消任务响应模型"""
    result: Task | None = None      # 任务结果


class SetTaskPushNotificationRequest(JSONRPCRequest):
    """设置任务推送通知请求模型"""
    method: Literal["tasks/pushNotification/set",
                    ] = "tasks/pushNotification/set"  # 固定方法名
    params: TaskPushNotificationConfig  # 任务推送通知配置


class SetTaskPushNotificationResponse(JSONRPCResponse):
    """设置任务推送通知响应模型"""
    result: TaskPushNotificationConfig | None = None  # 任务推送通知配置结果


class GetTaskPushNotificationRequest(JSONRPCRequest):
    """获取任务推送通知请求模型"""
    method: Literal["tasks/pushNotification/get",
                    ] = "tasks/pushNotification/get"  # 固定方法名
    params: TaskIdParams            # 任务ID参数


class GetTaskPushNotificationResponse(JSONRPCResponse):
    """获取任务推送通知响应模型"""
    result: TaskPushNotificationConfig | None = None  # 任务推送通知配置结果


class TaskResubscriptionRequest(JSONRPCRequest):
    """任务重新订阅请求模型"""
    method: Literal["tasks/resubscribe",] = "tasks/resubscribe"  # 固定方法名
    params: TaskIdParams            # 任务ID参数


# A2A请求类型适配器，用于处理不同类型的请求
A2ARequest = TypeAdapter(
    Annotated[
        Union[
            SendTaskRequest,
            GetTaskRequest,
            CancelTaskRequest,
            SetTaskPushNotificationRequest,
            GetTaskPushNotificationRequest,
            TaskResubscriptionRequest,
            SendTaskStreamingRequest,
        ],
        Field(discriminator="method"),
    ]
)

# 错误类型


class JSONParseError(JSONRPCError):
    """JSON解析错误"""
    code: int = -32700
    message: str = "Invalid JSON payload"
    data: Any | None = None


class InvalidRequestError(JSONRPCError):
    """无效请求错误"""
    code: int = -32600
    message: str = "Request payload validation error"
    data: Any | None = None


class MethodNotFoundError(JSONRPCError):
    """方法未找到错误"""
    code: int = -32601
    message: str = "Method not found"
    data: None = None


class InvalidParamsError(JSONRPCError):
    """无效参数错误"""
    code: int = -32602
    message: str = "Invalid parameters"
    data: Any | None = None


class InternalError(JSONRPCError):
    """内部错误"""
    code: int = -32603
    message: str = "Internal error"
    data: Any | None = None


class TaskNotFoundError(JSONRPCError):
    """任务未找到错误"""
    code: int = -32001
    message: str = "Task not found"
    data: None = None


class TaskNotCancelableError(JSONRPCError):
    """任务不可取消错误"""
    code: int = -32002
    message: str = "Task cannot be canceled"
    data: None = None


class PushNotificationNotSupportedError(JSONRPCError):
    """推送通知不支持错误"""
    code: int = -32003
    message: str = "Push Notification is not supported"
    data: None = None


class UnsupportedOperationError(JSONRPCError):
    """不支持的操作错误"""
    code: int = -32004
    message: str = "This operation is not supported"
    data: None = None


class ContentTypeNotSupportedError(JSONRPCError):
    """内容类型不支持错误"""
    code: int = -32005
    message: str = "Incompatible content types"
    data: None = None


class AgentProvider(BaseModel):
    """智能体提供者模型"""
    organization: str               # 组织名称
    url: str | None = None          # 可选的URL


class AgentCapabilities(BaseModel):
    """智能体能力模型"""
    streaming: bool = False         # 是否支持流式响应
    pushNotifications: bool = False  # 是否支持推送通知
    stateTransitionHistory: bool = False  # 是否支持状态转换历史


class AgentAuthentication(BaseModel):
    """智能体认证模型"""
    schemes: List[str]              # 认证方案列表
    credentials: str | None = None  # 可选的认证凭据


class AgentSkill(BaseModel):
    """智能体技能模型"""
    id: str                         # 技能ID
    name: str                       # 技能名称
    description: str | None = None  # 可选的技能描述
    tags: List[str] | None = None   # 可选的标签列表
    examples: List[str] | None = None  # 可选的示例列表
    inputModes: List[str] | None = None  # 可选的输入模式列表
    outputModes: List[str] | None = None  # 可选的输出模式列表


class AgentCard(BaseModel):
    """智能体卡片模型，定义智能体的元数据和能力"""
    name: str                       # 智能体名称
    description: str | None = None  # 可选的描述
    url: str                        # 智能体URL
    provider: AgentProvider | None = None  # 可选的提供者信息
    version: str                    # 版本号
    documentationUrl: str | None = None  # 可选的文档URL
    capabilities: AgentCapabilities  # 智能体能力
    authentication: AgentAuthentication | None = None  # 可选的认证信息
    defaultInputModes: List[str] = ["text"]  # 默认输入模式
    defaultOutputModes: List[str] = ["text"]  # 默认输出模式
    skills: List[AgentSkill]        # 智能体技能列表


class A2AClientError(Exception):
    """A2A客户端错误基类"""
    pass


class A2AClientHTTPError(A2AClientError):
    """A2A客户端HTTP错误"""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"HTTP Error {status_code}: {message}")


class A2AClientJSONError(A2AClientError):
    """A2A客户端JSON错误"""

    def __init__(self, message: str):
        self.message = message
        super().__init__(f"JSON Error: {message}")


class MissingAPIKeyError(Exception):
    """API密钥缺失异常"""
    pass
