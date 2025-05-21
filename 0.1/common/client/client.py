import httpx
from httpx_sse import connect_sse
from typing import Any, AsyncIterable
from common.types import (
    AgentCard,
    GetTaskRequest,
    SendTaskRequest,
    SendTaskResponse,
    JSONRPCRequest,
    GetTaskResponse,
    CancelTaskResponse,
    CancelTaskRequest,
    SetTaskPushNotificationRequest,
    SetTaskPushNotificationResponse,
    GetTaskPushNotificationRequest,
    GetTaskPushNotificationResponse,
    A2AClientHTTPError,
    A2AClientJSONError,
    SendTaskStreamingRequest,
    SendTaskStreamingResponse,
)
import json


class A2AClient:
    """Agent-to-Agent客户端类，用于与智能体服务器进行通信"""

    def __init__(self, agent_card: AgentCard = None, url: str = None):
        """初始化客户端

        参数:
            agent_card: 智能体卡片信息，可从中获取URL
            url: 直接提供的智能体URL

        注意:
            必须提供agent_card或url中的一个
        """
        if agent_card:
            self.url = agent_card.url
        elif url:
            self.url = url
        else:
            raise ValueError("Must provide either agent_card or url")

    async def send_task(self, payload: dict[str, Any]) -> SendTaskResponse:
        """发送任务请求

        参数:
            payload: 任务参数

        返回:
            任务响应对象
        """
        request = SendTaskRequest(params=payload)
        return SendTaskResponse(**await self._send_request(request))

    async def send_task_streaming(
        self, payload: dict[str, Any]
    ) -> AsyncIterable[SendTaskStreamingResponse]:
        """发送流式任务请求

        参数:
            payload: 任务参数

        返回:
            流式任务响应生成器

        异常:
            A2AClientJSONError: JSON解析错误
            A2AClientHTTPError: HTTP请求错误
        """
        request = SendTaskStreamingRequest(params=payload)
        with httpx.Client(timeout=None) as client:
            with connect_sse(
                client, "POST", self.url, json=request.model_dump()
            ) as event_source:
                try:
                    for sse in event_source.iter_sse():
                        yield SendTaskStreamingResponse(**json.loads(sse.data))
                except json.JSONDecodeError as e:
                    raise A2AClientJSONError(str(e)) from e
                except httpx.RequestError as e:
                    raise A2AClientHTTPError(400, str(e)) from e

    async def _send_request(self, request: JSONRPCRequest) -> dict[str, Any]:
        """发送通用JSON-RPC请求

        参数:
            request: JSON-RPC请求对象

        返回:
            JSON响应数据

        异常:
            A2AClientHTTPError: HTTP状态错误
            A2AClientJSONError: JSON解析错误
        """
        async with httpx.AsyncClient() as client:
            try:
                # 图像生成可能需要较长时间，添加超时
                response = await client.post(
                    self.url, json=request.model_dump(), timeout=30
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                raise A2AClientHTTPError(e.response.status_code, str(e)) from e
            except json.JSONDecodeError as e:
                raise A2AClientJSONError(str(e)) from e

    async def get_task(self, payload: dict[str, Any]) -> GetTaskResponse:
        """获取任务信息

        参数:
            payload: 查询参数

        返回:
            任务信息响应
        """
        request = GetTaskRequest(params=payload)
        return GetTaskResponse(**await self._send_request(request))

    async def cancel_task(self, payload: dict[str, Any]) -> CancelTaskResponse:
        """取消任务

        参数:
            payload: 任务ID参数

        返回:
            取消任务响应
        """
        request = CancelTaskRequest(params=payload)
        return CancelTaskResponse(**await self._send_request(request))

    async def set_task_callback(
        self, payload: dict[str, Any]
    ) -> SetTaskPushNotificationResponse:
        """设置任务回调配置

        参数:
            payload: 推送通知配置参数

        返回:
            设置响应结果
        """
        request = SetTaskPushNotificationRequest(params=payload)
        return SetTaskPushNotificationResponse(**await self._send_request(request))

    async def get_task_callback(
        self, payload: dict[str, Any]
    ) -> GetTaskPushNotificationResponse:
        """获取任务回调配置

        参数:
            payload: 任务ID参数

        返回:
            当前推送通知配置
        """
        request = GetTaskPushNotificationRequest(params=payload)
        return GetTaskPushNotificationResponse(**await self._send_request(request))
