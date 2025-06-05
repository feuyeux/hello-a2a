import base64
import os
import tempfile

from typing import Any

from llama_index.core import SimpleDirectoryReader
from llama_index.core.llms import ChatMessage
from llama_index.core.workflow import (
    Context,
    Event,
    StartEvent,
    StopEvent,
    Workflow,
    step,
)
from llama_index.llms.ollama import Ollama
from llama_index.llms.openai import OpenAI
from pydantic import BaseModel, Field


# 工作流事件定义

class LogEvent(Event):
    """日志事件，用于记录工作流执行过程中的状态信息。"""
    msg: str


class InputEvent(StartEvent):
    """输入事件，用于启动文件聊天工作流。

    包含用户消息、可选的文件附件和文件名。
    """
    msg: str
    attachment: str | None = None
    file_name: str | None = None


class ParseEvent(Event):
    """解析事件，触发文档解析和处理流程。"""
    attachment: str
    file_name: str | None = None
    msg: str


class ChatEvent(Event):
    """聊天事件，触发与LLM的对话交互。"""
    msg: str


class ChatResponseEvent(StopEvent):
    """聊天响应事件，包含最终的回答和引用信息。"""
    response: str
    citations: dict[int, list[str]]


# 结构化输出模型


class Citation(BaseModel):
    """文档中特定行的引用信息。"""

    citation_number: int = Field(
        description='响应文本中使用的具体内联引用编号。'
    )
    line_numbers: list[int] = Field(
        description='被引用的文档中的行号。'
    )


class ChatResponse(BaseModel):
    """包含内联引用（如果有）的用户响应。"""

    response: str = Field(
        description='对用户的响应，包括内联引用（如果有）。'
    )
    citations: list[Citation] = Field(
        default_factory=list,
        description='引用列表，每个引用都是一个对象，将引用编号映射到文档中被引用的行号。',
    )


class ParseAndChat(Workflow):
    """基于LlamaIndex的文档解析与聊天工作流。

    支持上传文档文件并基于文档内容进行智能问答。
    提供准确的引用信息，将回答与文档的具体行号关联。
    """

    def __init__(
        self,
        timeout: float | None = None,
        verbose: bool = False,
        llm_provider: str = "lmstudio",
        model_name: str = "qwen3-0.6b",
        **workflow_kwargs: Any,
    ):
        super().__init__(timeout=timeout, verbose=verbose, **workflow_kwargs)

        # 根据 LLM 提供商配置客户端
        if llm_provider.lower() == "ollama":
            self._llm = Ollama(
                model=model_name,
                base_url="http://localhost:11434",
                temperature=0.7,
                request_timeout=60.0,
                timeout=60.0,
            )
        elif llm_provider.lower() == "lmstudio":
            # 设置环境变量以允许自定义模型
            import os
            os.environ["OPENAI_API_KEY"] = "lm-studio"
            os.environ["OPENAI_API_BASE"] = "http://localhost:1234/v1"

            # 使用标准OpenAI模型名称绕过验证，实际模型由LM Studio决定
            # LM Studio会忽略模型名称参数，使用当前加载的模型
            self._llm = OpenAI(
                model="gpt-3.5-turbo",  # 使用标准名称绕过验证
                base_url="http://localhost:1234/v1",
                api_key="lm-studio",
                temperature=0.7,
                timeout=60.0,
            )

            # 记录实际使用的模型（供调试）
            print(f"🤖 LM Studio配置完成，请求的模型: {model_name}，使用占位符: gpt-3.5-turbo")
        else:
            raise ValueError(
                f"不支持的 LLM 提供商: {llm_provider}. 支持的提供商: 'ollama', 'lmstudio'")
        self._system_prompt_template = """\
你是一个有用的助手，可以回答有关文档的问题，提供引用，并进行对话。

这是带有行号的文档：
<document_text>
{document_text}
</document_text>

引用文档内容时：
1. 你的内联引用应该在每个响应中从[1]开始，每增加一个内联引用就增加1
2. 每个引用编号应对应文档中的特定行
3. 如果内联引用涵盖多个连续行，请尽力优先使用涵盖所需行号的单个内联引用。
4. 如果引用需要涵盖多个非连续的行，可以使用[2, 3, 4]这样的引用格式。
5. 例如，如果响应包含"Transformer架构... [1]。"和"注意力机制... [2]。"，这些分别来自第10-12行和第45-46行，那么：citations = [[10, 11, 12], [45, 46]]
6. 始终从[1]开始引用，每增加一个内联引用就增加1。不要使用行号作为内联引用编号，否则我会失业。
"""

    @step
    def route(self, ev: InputEvent) -> ParseEvent | ChatEvent:
        """路由步骤：根据是否有附件决定工作流路径。"""
        print(f"调试: 路由步骤调用，附件存在: {ev.attachment is not None}", flush=True)
        if ev.attachment:
            print("调试: 路由到解析事件", flush=True)
            return ParseEvent(
                attachment=ev.attachment, file_name=ev.file_name, msg=ev.msg
            )
        print("调试: 路由到聊天事件", flush=True)
        return ChatEvent(msg=ev.msg)

    @step
    async def parse(self, ctx: Context, ev: ParseEvent) -> ChatEvent:
        """解析步骤：处理上传的文档并提取文本内容。"""
        ctx.write_event_to_stream(LogEvent(msg='正在解析文档...'))

        # 解码base64附件
        file_content = base64.b64decode(ev.attachment)

        # 创建临时文件保存附件
        with tempfile.NamedTemporaryFile(suffix=f"_{ev.file_name}", delete=False) as temp_file:
            temp_file.write(file_content)
            temp_file_path = temp_file.name

        try:
            # 使用SimpleDirectoryReader加载文档
            # 注意：这对文本文件效果最好，PDF可能需要额外设置
            reader = SimpleDirectoryReader(input_files=[temp_file_path])
            documents = reader.load_data()

            if not documents:
                # 如果SimpleDirectoryReader失败，尝试作为纯文本读取
                document_text = file_content.decode('utf-8', errors='ignore')
            else:
                document_text = documents[0].text

            ctx.write_event_to_stream(LogEvent(msg='文档解析成功。'))

        except Exception as e:
            # 回退：尝试作为纯文本读取
            try:
                document_text = file_content.decode('utf-8', errors='ignore')
                ctx.write_event_to_stream(LogEvent(msg='文档以纯文本方式读取。'))
            except Exception:
                document_text = f"文档读取错误: {e!s}"
                ctx.write_event_to_stream(LogEvent(msg=f'文档解析错误: {e!s}'))
        finally:
            # 清理临时文件
            try:
                os.unlink(temp_file_path)
            except:
                pass

        # 将文档分割成行并添加行号
        # 这将用于引用
        formatted_document_text = ''
        for idx, line in enumerate(document_text.split('\n')):
            formatted_document_text += f"<line idx='{idx}'>{line}</line>\n"

        await ctx.set('document_text', formatted_document_text)
        return ChatEvent(msg=ev.msg)

    @step
    async def chat(self, ctx: Context, event: ChatEvent) -> ChatResponseEvent:
        """聊天步骤：与LLM进行对话交互并生成响应。"""
        print(f"调试: 聊天步骤调用，消息: {event.msg}", flush=True)
        current_messages = await ctx.get('messages', default=[])
        current_messages.append(ChatMessage(role='user', content=event.msg))
        print("调试: 准备写入日志事件", flush=True)
        ctx.write_event_to_stream(
            LogEvent(
                msg=f'正在与{len(current_messages)}条初始消息进行聊天。'
            )
        )
        print("调试: 日志事件已写入", flush=True)

        document_text = await ctx.get('document_text', default='')
        if document_text:
            ctx.write_event_to_stream(
                LogEvent(msg='正在插入系统提示...')
            )
            input_messages = [
                ChatMessage(
                    role='system',
                    content=self._system_prompt_template.format(
                        document_text=document_text
                    ),
                ),
                *current_messages,
            ]
        else:
            input_messages = current_messages

        response = await self._llm.achat(input_messages)
        response_text = response.message.content or "抱歉，我无法生成响应。"
        ctx.write_event_to_stream(
            LogEvent(msg='收到LLM响应，正在解析引用...')
        )

        current_messages.append(
            ChatMessage(role='assistant', content=response_text)
        )
        await ctx.set('messages', current_messages)

        # 目前返回不包含结构化引用的响应，因为LM Studio不支持结构化输出
        # 在生产设置中，你可以在这里添加手动引用解析
        citations = {}

        return ChatResponseEvent(
            response=response_text, citations=citations
        )


async def main():
    """ParseAndChat智能体的测试脚本。"""
    agent = ParseAndChat()
    ctx = Context(agent)

    # 运行 `wget https://arxiv.org/pdf/1706.03762 -O attention.pdf` 来获取文件
    # 或者使用你自己的文件
    with open('attention.pdf', 'rb') as f:
        attachment = base64.b64encode(f.read()).decode('utf-8')

    handler = agent.run(
        start_event=InputEvent(
            msg='你好！你能告诉我关于这个文档的什么信息吗？',
            attachment=attachment,
            file_name='test.pdf',
        ),
        ctx=ctx,
    )

    async for event in handler.stream_events():
        if not isinstance(event, StopEvent):
            print(event)

    response: ChatResponseEvent = await handler

    print(response.response)
    for citation_number, citation_texts in response.citations.items():
        print(f'引用 {citation_number}: {citation_texts}')

    # 测试上下文持续性
    handler = agent.run(
        '我刚才问你的最后一个问题是什么？',
        ctx=ctx,
    )
    response: ChatResponseEvent = await handler
    print(response.response)


if __name__ == '__main__':
    import asyncio

    asyncio.run(main())
