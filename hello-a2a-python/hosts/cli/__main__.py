import asyncio
import base64
import os
import urllib

from uuid import uuid4

import asyncclick as click
import httpx

from a2a.client import A2ACardResolver, A2AClient
from a2a.types import (
    FilePart,
    FileWithBytes,
    GetTaskRequest,
    JSONRPCErrorResponse,
    Message,
    MessageSendConfiguration,
    MessageSendParams,
    Part,
    SendMessageRequest,
    SendStreamingMessageRequest,
    Task,
    TaskArtifactUpdateEvent,
    TaskQueryParams,
    TaskState,
    TaskStatusUpdateEvent,
    TextPart,
)


@click.command()
@click.option('--agent', default='http://localhost:10000')
@click.option('--session', default=0)
@click.option('--history', default=False)
async def cli(
    agent,
    session,
    history,
):
    """A2A命令行客户端，用于与智能体进行交互。

    参数:
        agent: 智能体服务器地址
        session: 会话ID
        history: 是否显示历史记录
    """
    async with httpx.AsyncClient(timeout=30) as httpx_client:
        card_resolver = A2ACardResolver(httpx_client, agent)
        card = await card_resolver.get_agent_card()

        client = A2AClient(httpx_client, agent_card=card)

        continue_loop = True
        streaming = card.capabilities.streaming

        while continue_loop:
            continue_loop, contextId, taskId = await completeTask(
                client,
                streaming,
                None,
                None,
            )

        if history and continue_loop:
            task_response = await client.get_task(
                {'id': taskId, 'historyLength': 10}
            )


async def completeTask(
    client: A2AClient,
    streaming,
    taskId,
    contextId,
):
    """
    完成一个任务的交互流程

    Args:
        client: A2A客户端实例
        streaming: 是否支持流式处理
        taskId: 任务ID（可选）
        contextId: 上下文ID（可选）

    Returns:
        tuple: (是否继续循环, 上下文ID, 任务ID)
    """
    prompt = click.prompt(
        '\n您想向智能体发送什么消息？（输入 :q 或 quit 退出）'
    )
    if prompt == ':q' or prompt == 'quit':
        return False, None, None

    message = Message(
        role='user',
        parts=[TextPart(text=prompt)],
        messageId=str(uuid4()),
        taskId=taskId,
        contextId=contextId,
    )

    file_path = click.prompt(
        '选择要附加的文件路径？（直接回车跳过）',
        default='',
        show_default=False,
    )
    if file_path and file_path.strip() != '':
        # 展开环境变量和用户主目录
        file_path = os.path.expandvars(os.path.expanduser(file_path))
        with open(file_path, 'rb') as f:
            file_content = base64.b64encode(f.read()).decode('utf-8')
            file_name = os.path.basename(file_path)

        message.parts.append(
            Part(
                root=FilePart(
                    file=FileWithBytes(
                        name=file_name, bytes=file_content
                    )
                )
            )
        )

    payload = MessageSendParams(
        id=str(uuid4()),
        message=message,
        configuration=MessageSendConfiguration(
            acceptedOutputModes=['text'],
        ),
    )

    taskResult = None
    message = None
    if streaming:
        response_stream = client.send_message_streaming(
            SendStreamingMessageRequest(
                id=str(uuid4()),
                params=payload,
            )
        )
        async for result in response_stream:
            if isinstance(result.root, JSONRPCErrorResponse):
                print("Agent错误: ", result.root.error)
                return False, contextId, taskId
            event = result.root.result
            contextId = event.contextId
            if (
                isinstance(event, Task)
            ):
                taskId = event.id
            elif (isinstance(event, TaskStatusUpdateEvent)
                  or isinstance(event, TaskArtifactUpdateEvent)
                  ):
                taskId = event.taskId
            elif isinstance(event, Message):
                message = event
                # 只输出agent的消息内容，不输出系统事件
                if message.role == 'assistant':
                    print(
                        f'Agent响应: {[part.text for part in message.parts if hasattr(part, "text")]}')
        # 流式处理完成后，如果有任务则获取完整任务信息
        if taskId:
            taskResult = await client.get_task(
                GetTaskRequest(
                    id=str(uuid4()),
                    params=TaskQueryParams(id=taskId),
                )
            )
            taskResult = taskResult.root.result
    else:
        try:
            # 对于非流式处理，假设响应是任务或消息
            event = await client.send_message(
                SendMessageRequest(
                    id=str(uuid4()),
                    params=payload,
                )
            )
            event = event.root.result
        except Exception as e:
            print("完成调用失败", e)
        if not contextId:
            contextId = event.contextId
        if isinstance(event, Task):
            if not taskId:
                taskId = event.id
            taskResult = event
        elif isinstance(event, Message):
            message = event

    if message:
        # 只输出agent的回复内容
        if message.role == 'assistant':
            text_parts = [
                part.text for part in message.parts if hasattr(part, 'text')]
            if text_parts:
                print(f'Agent: {" ".join(text_parts)}')
        return True, contextId, taskId
    if taskResult:
        # 显示任务状态
        state = TaskState(taskResult.status.state)
        print(f'任务状态: {state.name}')

        # 显示任务的artifacts（智能体的结果内容）
        if hasattr(taskResult, 'artifacts') and taskResult.artifacts:
            print('\n=== Agent结果 ===')
            for artifact in taskResult.artifacts:
                if hasattr(artifact, 'parts') and artifact.parts:
                    for part in artifact.parts:
                        # 处理Part对象，需要访问root属性
                        if hasattr(part, 'root') and part.root:
                            root = part.root
                            if hasattr(root, 'text') and root.text:
                                print(root.text)
                            elif hasattr(root, 'kind') and root.kind == 'text' and hasattr(root, 'text'):
                                print(root.text)
                        # 兼容直接是TextPart的情况
                        elif hasattr(part, 'text') and part.text:
                            print(part.text)

        # 显示任务历史中最后的智能体回复
        if hasattr(taskResult, 'history') and taskResult.history:
            print('\n=== Agent回复 ===')
            # 查找最后一个assistant角色的消息
            for msg in reversed(taskResult.history):
                if hasattr(msg, 'role') and msg.role == 'assistant':
                    for part in msg.parts:
                        if hasattr(part, 'root') and part.root:
                            root = part.root
                            if hasattr(root, 'text') and root.text:
                                print(root.text)
                        elif hasattr(part, 'text') and part.text:
                            print(part.text)
                    break

        # 如果status中有message，也显示
        if hasattr(taskResult, 'status') and taskResult.status and hasattr(taskResult.status, 'message') and taskResult.status.message:
            status_msg = taskResult.status.message
            if hasattr(status_msg, 'role') and status_msg.role == 'assistant':
                print('\n=== Status消息 ===')
                for part in status_msg.parts:
                    if hasattr(part, 'root') and part.root:
                        root = part.root
                        if hasattr(root, 'text') and root.text:
                            print(root.text)
                    elif hasattr(part, 'text') and part.text:
                        print(part.text)

        # 如果结果是需要更多输入，则再次循环
        if state.name == TaskState.input_required.name:
            return (
                await completeTask(
                    client,
                    streaming,
                    taskId,
                    contextId,
                ),
                contextId,
                taskId,
            )
        # 任务完成
        return True, contextId, taskId
    # 失败情况，不应该到达这里
    return True, contextId, taskId


if __name__ == '__main__':
    cli()
