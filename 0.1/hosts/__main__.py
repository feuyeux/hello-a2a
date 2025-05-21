from common.client import A2AClient, A2ACardResolver
from common.types import TaskState, Task, TaskSendParams, Message, TextPart, PushNotificationConfig, AuthenticationInfo, TaskIdParams, GetTaskResponse, SendTaskResponse, SendTaskStreamingResponse
from common.utils.logger import setup_logger
from common.utils.push_notification_auth import PushNotificationReceiverAuth
import asyncio
from urllib.parse import urlparse
from uuid import uuid4
import datetime
import argparse
import sys
from typing import Dict, Any, List, Optional, cast

logger = setup_logger("HelloA2AClient")


async def main():
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='Hello A2A 客户端')
    parser.add_argument('--query', type=str, default="碳元素和硅元素",
                        help='查询内容, 默认为"碳元素和硅元素"')

    # 正确解析命令行参数
    args = parser.parse_args()
    query = args.query

    logger.info(f"将要查询的内容: \"{query}\"")

    use_push_notifications = False
    logger.info("初始化 A2A 代理卡片解析器")
    card_resolver = A2ACardResolver("http://localhost:10000")
    card = card_resolver.get_agent_card()

    logger.info("获取到代理卡片，内容如下：")
    logger.info(card.model_dump_json(exclude_none=True))

    notif_receiver_parsed = urlparse("http://localhost:5000")
    notification_receiver_host = notif_receiver_parsed.hostname or "localhost"  # 默认为localhost
    notification_receiver_port = notif_receiver_parsed.port or 5000  # 默认为5000

    if use_push_notifications:
        logger.info("启用推送通知监听器")
        from hosts.push_notification_listener import PushNotificationListener
        notification_receiver_auth = PushNotificationReceiverAuth()
        await notification_receiver_auth.load_jwks(f"http://localhost:10000/.well-known/jwks.json")

        push_notification_listener = PushNotificationListener(
            host=notification_receiver_host,
            port=notification_receiver_port,
            notification_receiver_auth=notification_receiver_auth,
        )
        push_notification_listener.start()
        logger.info(
            f"推送通知监听器已启动，监听 {notification_receiver_host}:{notification_receiver_port}")

    client = A2AClient(agent_card=card)

    is_support_stream = card.capabilities.streaming
    await completeTask(client, is_support_stream, use_push_notifications, notification_receiver_host, notification_receiver_port, query)


async def completeTask(client: A2AClient, streaming: bool, use_push_notifications: bool, notification_receiver_host: str, notification_receiver_port: int, prompt: str) -> bool:
    taskId = uuid4().hex
    sessionId = uuid4().hex

    # 创建消息对象
    message = Message(
        role="user",
        parts=[TextPart(text=prompt)]
    )

    # 创建任务参数
    task_params = TaskSendParams(
        id=taskId,
        sessionId=sessionId,
        message=message,
        acceptedOutputModes=["text"]
    )

    # 如果启用推送通知，添加相关配置
    if use_push_notifications:
        task_params.pushNotification = PushNotificationConfig(
            url=f"http://{notification_receiver_host}:{notification_receiver_port}/notify",
            authentication=AuthenticationInfo(
                schemes=["bearer"]
            )
        )
        logger.info("已添加推送通知参数到任务请求体。")

    # 将 task_params 转换为字典
    payload = task_params.model_dump()

    if streaming:
        logger.info(f"请求体: {payload} ,接收流式响应...")
        response_stream = client.send_task_streaming(payload)
        async for result in response_stream:
            result_obj = cast(SendTaskStreamingResponse, result)
            logger.info(
                f"收到流式事件: {result_obj.model_dump_json(exclude_none=True)}")

        logger.info("流式响应结束，获取最终任务结果...")
        task_result = await client.get_task(TaskIdParams(id=taskId).model_dump())
        logger.info(f"最终返回值: {task_result.model_dump_json(exclude_none=True)}")

        try:
            # 使用类型化的方式处理任务结果
            result_obj = cast(GetTaskResponse, task_result)
            if result_obj.result and result_obj.result.artifacts:
                artifact = result_obj.result.artifacts[0]
                if artifact.parts and artifact.parts[0].type == "text":
                    text = cast(TextPart, artifact.parts[0]).text
                    logger.info(f'最终返回文本: {text}')
                else:
                    logger.info("响应中没有找到有效的 text 内容")
            else:
                logger.info("响应中没有找到 artifacts")
        except Exception as e:
            logger.info(f"未能提取 text 字段: {e}")
    else:
        logger.info("以普通方式发送任务，等待响应...")
        task_result = await client.send_task(payload)
        logger.info(f"收到响应: {task_result.model_dump_json(exclude_none=True)}")

        try:
            # 使用类型化的方式处理任务结果
            result_obj = cast(SendTaskResponse, task_result)
            if result_obj.result and result_obj.result.artifacts:
                artifact = result_obj.result.artifacts[0]
                if artifact.parts and artifact.parts[0].type == "text":
                    text = cast(TextPart, artifact.parts[0]).text
                    logger.info(f'最终返回文本: {text}')
                else:
                    logger.info("响应中没有找到有效的 text 内容")
            else:
                logger.info("响应中没有找到 artifacts")
        except Exception as e:
            logger.info(f"未能提取 text 字段: {e}")

    # 简单检查任务状态并返回
    try:
        # 使用类型化的方式检查任务状态
        if isinstance(task_result, (SendTaskResponse, GetTaskResponse)) and task_result.result and task_result.result.status:
            logger.info("任务处理完成，流程结束。")
            return True
        return False
    except Exception as e:
        logger.error(f"检查任务状态时出错: {e}")
        return False


if __name__ == "__main__":
    asyncio.run(main())
