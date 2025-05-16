from common.client import A2AClient, A2ACardResolver
from common.types import TaskState, Task
from common.utils.logger import setup_logger
from common.utils.push_notification_auth import PushNotificationReceiverAuth
import asyncio
from uuid import uuid4
import urllib
import datetime

logger = setup_logger("HelloA2AClient")


async def main():
    use_push_notifications = False
    logger.info("初始化 A2A 代理卡片解析器")
    card_resolver = A2ACardResolver("http://localhost:10000")
    card = card_resolver.get_agent_card()

    logger.info("获取到代理卡片，内容如下：")
    logger.info(card.model_dump_json(exclude_none=True))

    notif_receiver_parsed = urllib.parse.urlparse("http://localhost:5000")
    notification_receiver_host = notif_receiver_parsed.hostname
    notification_receiver_port = notif_receiver_parsed.port

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

    await completeTask(client, card.capabilities.streaming, use_push_notifications, notification_receiver_host, notification_receiver_port, "碳元素和硅元素")


async def completeTask(client: A2AClient, streaming, use_push_notifications: bool, notification_receiver_host: str, notification_receiver_port: int, prompt: str):
    taskId = uuid4().hex
    sessionId = uuid4().hex
    payload = {
        "id": taskId,
        "sessionId": sessionId,
        "acceptedOutputModes": ["text"],
        "message": {
            "role": "user",
            "parts": [
                {
                    "type": "text",
                    "text": prompt,
                }
            ],
        },
    }

    if use_push_notifications:
        payload["pushNotification"] = {
            "url": f"http://{notification_receiver_host}:{notification_receiver_port}/notify",
            "authentication": {
                "schemes": ["bearer"],
            },
        }
        logger.info("已添加推送通知参数到任务请求体。")

    if streaming:
        logger.info("以流式方式发送任务，开始接收流式响应……")
        response_stream = client.send_task_streaming(payload)
        async for result in response_stream:
            logger.info(f"收到流式事件: {result.model_dump_json(exclude_none=True)}")
        logger.info("流式响应结束，获取最终任务结果……")
        taskResult = await client.get_task({"id": taskId})
        logger.info(f"最终返回值: {taskResult.model_dump_json(exclude_none=True)}")
        # 独立输出 text 字段
        try:
            text = taskResult.result.status.message.parts[0].text
            logger.info(f'独立输出: {text}')
        except Exception as e:
            logger.info(f"未能提取 text 字段: {e}")
    else:
        logger.info("以普通方式发送任务，等待响应……")
        taskResult = await client.send_task(payload)
        logger.info(f"收到响应: {taskResult.model_dump_json(exclude_none=True)}")
        # 独立输出 text 字段
        try:
            text = taskResult.result.status.message.parts[0].text
            logger.info(f'独立输出: {text}')
        except Exception as e:
            logger.info(f"未能提取 text 字段: {e}")

    # if the result is that more input is required, loop again.
    state = TaskState(taskResult.result.status.state)
    if state.name == TaskState.INPUT_REQUIRED.name:
        logger.warning("任务需要更多输入，进入递归输入流程。")
        return False
    else:
        logger.info("任务已完成，流程结束。")
        logger.info(f"最终返回值: {taskResult.model_dump_json(exclude_none=True)}")
        return True


if __name__ == "__main__":
    asyncio.run(main())
