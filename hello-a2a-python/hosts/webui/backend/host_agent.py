import base64
import json
import os
import uuid
import time
import logging
from datetime import datetime
import asyncio
from functools import wraps

from typing import List, Optional, Dict, Any, Union

import httpx

from a2a.client import A2ACardResolver
from a2a.types import (
    AgentCard,
    DataPart,
    FileWithBytes,
    FileWithUri,
    Message,
    MessageSendConfiguration,
    MessageSendParams,
    Part,
    Task,
    TaskState,
    TextPart,
)
from google.adk import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools.tool_context import ToolContext
from google.genai import types
from google.adk.models.lite_llm import LiteLlm
# Convert relative import to absolute for command-line execution
try:
    from .remote_agent_connection import RemoteAgentConnections, TaskUpdateCallback
    from .ollama_response_fixer import OllamaResponseFixer
except ImportError:
    from remote_agent_connection import RemoteAgentConnections, TaskUpdateCallback
    from ollama_response_fixer import OllamaResponseFixer


def llm_error_handler(func):
    """装饰器：处理LLM调用中的错误，特别是JSON解析错误"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            error_msg = str(e).lower()
            if 'json' in error_msg and ('unterminated' in error_msg or 'decode' in error_msg):
                logger.error(f"LLM JSON解析错误: {e}")
                # 重试机制：降低参数再试一次
                logger.info("尝试使用简化的LLM配置重试...")
                # 这里可以实现重试逻辑
                raise Exception(f"LLM响应格式错误，请重试。原始错误: {str(e)}")
            else:
                logger.error(f"LLM调用错误: {e}")
                raise
    return wrapper

# 增强的日志配置
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
# 禁用httpx、httpcore和asyncio的噪音日志
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)

# 本地大模型使用占位符API密钥
os.environ['OPENAI_API_KEY'] = 'sk-ollama-local'

# 使用Ollama配置本地大模型 - 针对qwen3模型的<think>问题优化
LITELLM_CONFIG = {
    "model": "ollama_chat/qwen3:8b",  # 使用8b模型
    "api_base": "http://localhost:11434",
    "api_key": "sk-ollama-local",
    "stream": False,  # 强制禁用流式
    "timeout": 60,  # 8b模型响应更快
    "custom_llm_provider": "ollama_chat",
    # 优化的参数配置 - 不使用stop参数避免过度截断
    "num_predict": 200,  # 较短输出减少<think>问题
    "temperature": 0.1,  # 很低的温度
    "top_p": 0.7,
    # 移除stop参数，让响应修复器处理<think>标签
}

logger.info(f"🔧 LiteLLM 配置已设置: {LITELLM_CONFIG['model']}")

# 检查Ollama是否正在运行


def is_ollama_running():
    """检查Ollama服务是否正在运行"""
    try:
        with httpx.Client(timeout=2.0) as client:
            response = client.get("http://localhost:11434/api/version")
            if response.status_code == 200:
                print("✅ Ollama服务正在运行")
                return True
            else:
                print(
                    f"⚠️ Ollama服务返回状态码 {response.status_code}")
                return False
    except Exception as e:
        print(f"❌ Ollama服务不可用: {e}")
        return False


# 启动时检查Ollama
is_ollama_running()


class HostAgent:
    """主机智能体

    这是负责选择将任务发送给哪些远程智能体并协调其工作的智能体。
    """

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        task_callback: TaskUpdateCallback | None = None,
    ):
        self.task_callback = task_callback
        self.httpx_client = http_client
        self.remote_agent_connections: dict[str, RemoteAgentConnections] = {}
        self.cards: dict[str, AgentCard] = {}
        self.agents = ""
        self.response_fixer = OllamaResponseFixer()  # 添加响应修复器

    @classmethod
    async def create(cls,
                     remote_agent_addresses: list[str],
                     http_client: httpx.AsyncClient,
                     task_callback: TaskUpdateCallback | None = None):
        """异步工厂方法，用于创建HostAgent实例"""
        instance = cls(http_client, task_callback)

        for address in remote_agent_addresses:
            try:
                card_resolver = A2ACardResolver(http_client, address)
                card = await card_resolver.get_agent_card()
                remote_connection = RemoteAgentConnections(http_client, card)
                instance.remote_agent_connections[card.name] = remote_connection
                instance.cards[card.name] = card
            except Exception as e:
                print(f"连接到智能体 {address} 时出错: {e}")

        agent_info = []
        for ra in instance.list_remote_agents():
            agent_info.append(json.dumps(ra))
        instance.agents = '\n'.join(agent_info)

        return instance

    def register_agent_card(self, card: AgentCard):
        remote_connection = RemoteAgentConnections(self.httpx_client, card)
        self.remote_agent_connections[card.name] = remote_connection
        self.cards[card.name] = card
        agent_info = []
        for ra in self.list_remote_agents():
            agent_info.append(json.dumps(ra))
        self.agents = '\n'.join(agent_info)

    def create_agent(self) -> Agent:
        return Agent(
            model=LiteLlm(**LITELLM_CONFIG),
            name='host_agent',
            instruction=self.root_instruction,
            before_model_callback=self.before_model_callback,
            after_model_callback=self.after_model_callback,
            description=(
                '此智能体协调将用户请求分解为子智能体可以执行的任务'
            ),
            tools=[
                self.list_remote_agents,
                self.send_message,
            ],
        )

    def root_instruction(self, context: ReadonlyContext) -> str:
        """
        为主机智能体大模型生成根指令。
        此指令指导大模型如何分析用户请求并选择智能体。

        流程：主机智能体大模型需要有关可用智能体和当前状态的上下文
        """
        # 为此指令生成请求生成关联ID
        correlation_id = str(uuid.uuid4())
        start_time = time.time()

        # 记录根指令生成开始
        print(
            f"[HostAgent] 🔄 开始生成根指令 - ID: {correlation_id}")
        print(
            f"[HostAgent] 🤝 可用智能体: {len(self.remote_agent_connections)}")

        print(f"[HostAgent] 📋 为主机大模型生成根指令")

        current_agent = self.check_state(context)
        print(
            f"[HostAgent] 🎯 当前智能体状态: {current_agent['active_agent']}")
        print(
            f"[HostAgent] 🤖 可用智能体: {len(self.remote_agent_connections)} 个远程智能体")

        # 记录智能体发现和状态检查
        print(
            f"[HostAgent] 🔍 智能体发现 - 远程智能体: {list(self.remote_agent_connections.keys())}")

        instruction = f"""您是一个专业的任务分配专家，能够将用户请求分配给合适的远程智能体。

重要提示：您只能使用以下两个工具：
1. `list_remote_agents()` - 发现可用的智能体
2. `send_message(agent_name, message, tool_context)` - 与智能体通信

绝不要尝试直接调用智能体名称作为函数（例如，不要调用 "Currency Agent()" 或 "Reimbursement Agent()"）。
总是使用 send_message 工具，将智能体名称作为第一个参数。

发现阶段：
- 使用 `list_remote_agents()` 列出可用的远程智能体

执行阶段：
- 使用 `send_message(agent_name, message, tool_context)` 与远程智能体交互
- 示例：send_message("Currency Agent", "将100美元转换为欧元", tool_context)
- 示例：send_message("Reimbursement Agent", "处理费用报告", tool_context)

关键点：智能体名称不是可调用的函数。它们是 send_message 工具的参数。

在回复用户时，请务必包含远程智能体的名称。

请依靠工具来处理请求，不要编造响应。如果您不确定，请向用户询问更多详情。
主要关注会话的最新部分。

智能体列表：
{self.agents}

当前智能体：{current_agent['active_agent']}
"""

        # 计算时间并记录指令生成完成
        duration_ms = (time.time() - start_time) * 1000

        print(
            f"[HostAgent] 📝 已生成根指令 - 长度: {len(instruction)} 字符")
        print(
            f"[HostAgent] ⏱️ 指令生成耗时 {duration_ms:.1f}ms")

        print(
            f"[HostAgent] ✅ 根指令完成 - 智能体描述: {len(self.agents.split('\n')) if self.agents else 0}")

        print(
            f"[HostAgent] ✅ 根指令已生成，包含 {len(self.agents.split('\n'))} 个智能体描述")
        return instruction

    def check_state(self, context: ReadonlyContext):
        state = context.state
        if (
            'context_id' in state
            and 'session_active' in state
            and state['session_active']
            and 'agent' in state
        ):
            return {'active_agent': f'{state["agent"]}'}
        return {'active_agent': 'None'}

    def before_model_callback(
        self, callback_context: CallbackContext, llm_request
    ):
        """增强的before_model_callback，包含主机智能体的输入日志记录"""
        # 为此大模型交互生成关联ID
        correlation_id = str(uuid.uuid4())

        # 在状态中存储关联ID供after_model_callback使用
        state = callback_context.state
        state['correlation_id'] = correlation_id
        state['llm_start_time'] = time.time()

        if 'session_active' not in state or not state['session_active']:
            state['session_active'] = True

        # 提取并记录输入信息
        input_text = ""
        if hasattr(llm_request, 'contents') and llm_request.contents:
            for content in llm_request.contents:
                if hasattr(content, 'parts'):
                    for part in content.parts:
                        if hasattr(part, 'text') and part.text is not None:
                            input_text += part.text
        elif hasattr(llm_request, 'messages') and llm_request.messages:
            for message in llm_request.messages:
                if hasattr(message, 'content'):
                    input_text += str(message.content)

        # 记录大模型请求
        print(
            f"[HostAgent] 🤖 主机智能体大模型输入 - 关联ID: {correlation_id}")
        print(f"[HostAgent] 📝 输入长度: {len(input_text)} 字符")
        print(
            f"[HostAgent] 🔧 模型: {getattr(llm_request, 'model', 'ollama/qwen3:8b')}")

    def after_model_callback(
        self, callback_context: CallbackContext, llm_response
    ):
        """增强的after_model_callback，包含主机智能体的输出日志记录和响应清理"""
        state = callback_context.state
        correlation_id = state.get('correlation_id', 'unknown')
        start_time = state.get('llm_start_time', time.time())
        duration_ms = (time.time() - start_time) * 1000

        # 提取并记录输出信息，同时清理响应
        output_text = ""
        response_cleaned = False
        
        if hasattr(llm_response, 'candidates') and llm_response.candidates:
            for candidate in llm_response.candidates:
                if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                    for part in candidate.content.parts:
                        if hasattr(part, 'text') and part.text is not None:
                            original_text = part.text
                            output_text += original_text
                            
                            # 清理响应文本
                            cleaned_text = self.response_fixer.clean_response(original_text)
                            if cleaned_text != original_text:
                                part.text = cleaned_text
                                response_cleaned = True
                                print(f"[HostAgent] 🧹 已清理响应文本（移除<think>标签等）")
                                
        elif hasattr(llm_response, 'content'):
            output_text = str(llm_response.content)
        elif hasattr(llm_response, 'text'):
            output_text = llm_response.text

        # 记录大模型响应
        print(
            f"[HostAgent] ✅ 主机智能体大模型输出 - 关联ID: {correlation_id}")
        print(f"[HostAgent] 📤 输出长度: {len(output_text)} 字符")
        print(f"[HostAgent] ⏱️ 处理时间: {duration_ms:.2f}ms")
        print(f"[HostAgent] 🔧 模型: {LITELLM_CONFIG['model']}")
        if response_cleaned:
            print(f"[HostAgent] ✨ 响应已自动清理优化")

    def list_remote_agents(self):
        """
        列出您可以用来委派任务的可用远程智能体。
        这是主机大模型调用的工具函数，用于发现可用的智能体。

        流程：主机大模型 -> list_remote_agents() -> 可用智能体能力
        """
        # 为智能体发现请求生成关联ID
        correlation_id = str(uuid.uuid4())
        start_time = time.time()

        # 记录智能体发现开始
        print(f"[HostAgent] 🔍 开始智能体发现 - ID: {correlation_id}")
        print(
            f"[HostAgent] 🤖 可用连接: {len(self.remote_agent_connections)}")

        print(f"[HostAgent] 🔍 主机大模型请求可用远程智能体列表")

        if not self.remote_agent_connections:
            print(f"[HostAgent] ⚠️ 无可用远程智能体")
            duration_ms = (time.time() - start_time) * 1000
            print(f"[HostAgent] ⏱️ 智能体发现耗时 {duration_ms:.1f}ms")
            return []

        print(
            f"[HostAgent] 📊 找到 {len(self.remote_agent_connections)} 个远程智能体")

        remote_agent_info = []
        agent_capabilities = []

        for agent_name, card in self.cards.items():
            agent_info = {'name': card.name, 'description': card.description}
            remote_agent_info.append(agent_info)
            agent_capabilities.append({
                "name": card.name,
                "description_length": len(card.description),
                "agent_type": "remote_agent"
            })
            print(
                f"[HostAgent] 🤖 智能体: {card.name} - {card.description[:100]}...")

        # 计算时间并记录发现完成
        duration_ms = (time.time() - start_time) * 1000

        print(
            f"[HostAgent] ✅ 发现完成 - 找到 {len(remote_agent_info)} 个智能体")
        print(
            f"[HostAgent] 🏷️ 智能体名称: {[info['name'] for info in remote_agent_info]}")
        print(f"[HostAgent] ⏱️ 发现耗时 {duration_ms:.1f}ms")

        print(f"[HostAgent] ✅ 向主机大模型返回智能体列表")
        return remote_agent_info

    @llm_error_handler
    async def send_message(
        self, agent_name: str, message: str, tool_context: ToolContext
    ):
        """发送任务，支持流式（如果支持）或非流式。

        这将向名为 agent_name 的远程智能体发送消息。
        此方法实现了序列图中的智能体选择和消息委派逻辑。

        流程：
        1. 主机大模型调用此工具将任务委派给远程智能体
        2. 验证智能体存在且可用
        3. 准备具有适当上下文的A2A消息
        4. 通过A2A协议发送到远程智能体
        5. 处理响应（流式或非流式）
        6. 将响应转换回主机大模型格式

        参数：
          agent_name: 要发送任务到的智能体名称。
          message: 要发送给智能体的任务消息。
          tool_context: 此方法运行的工具上下文。

        生成：
          JSON数据字典。
        """
        # 为任务委派生成关联ID
        correlation_id = str(uuid.uuid4())
        start_time = time.time()

        # 记录任务委派开始
        print(f"[HostAgent] 🚀 开始任务委派 - ID: {correlation_id}")
        print(f"[HostAgent] 🎯 目标智能体: {agent_name}")
        print(f"[HostAgent] 📝 消息长度: {len(message)} 字符")

        print(
            f"[HostAgent] 🎯 主机大模型请求委派给智能体: {agent_name}")
        print(f"[HostAgent] 📝 要委派的消息: {message[:100]}...")

        # 验证智能体是否存在
        if agent_name not in self.remote_agent_connections:
            print(
                f"[HostAgent] ❌ 在可用连接中未找到智能体 {agent_name}")
            raise ValueError(f'智能体 {agent_name} 未找到')

        print(f"[HostAgent] ✅ 在远程连接中找到智能体 {agent_name}")

        # 使用选定的智能体更新工具上下文状态
        state = tool_context.state
        state['agent'] = agent_name
        print(
            f"[HostAgent] 🔄 已更新工具上下文状态 - 选定智能体: {agent_name}")

        # 获取选定智能体的A2A客户端
        client = self.remote_agent_connections[agent_name]
        if not client:
            print(f"[HostAgent] ❌ 智能体 {agent_name} 的客户端不可用")
            raise ValueError(f'智能体 {agent_name} 的客户端不可用')

        print(f"[HostAgent] 🌐 智能体 {agent_name} 的A2A客户端已准备好")

        # 从工具状态中提取上下文信息
        taskId = state.get('task_id', None)
        contextId = state.get('context_id', None)
        messageId = state.get('message_id', None)

        print(
            f"[HostAgent] 📋 上下文 - 任务ID: {taskId}, 上下文ID: {contextId}, 消息ID: {messageId}")

        if not messageId:
            messageId = str(uuid.uuid4())
            print(f"[HostAgent] 🆔 生成新消息ID: {messageId}")

        # 导入A2A消息构造所需的类型
        from a2a.types import Role, Part

        print(f"[HostAgent] 🔧 为远程智能体构造A2A消息")

        # 创建TextPart并包装在Part中
        text_part = TextPart(text=message)
        part = Part(root=text_part)

        # 准备A2A消息请求
        request: MessageSendParams = MessageSendParams(
            message=Message(
                role=Role.user,  # 委派给远程智能体时主机充当用户
                parts=[part],    # 以适当的A2A格式包装的消息内容
                messageId=messageId,
                contextId=contextId,
                taskId=taskId,
            ),
            configuration=MessageSendConfiguration(
                acceptedOutputModes=['text', 'text/plain', 'image/png'],
            ),
        )

        print(
            f"[HostAgent] 📤 向远程智能体 {agent_name} 发送A2A消息")
        print(
            f"[HostAgent] 🔄 消息格式: 角色={Role.user}, 部件=1, 上下文={contextId}")

        # 通过A2A协议发送消息
        response = await client.send_message(request, self.task_callback)

        print(
            f"[HostAgent] 📥 收到来自远程智能体 {agent_name} 的响应")
        print(f"[HostAgent] 🔍 响应类型: {type(response)}")

        # 处理立即消息响应（非流式）
        if isinstance(response, Message):
            print(f"[HostAgent] 💬 远程智能体返回立即消息响应")
            return await convert_parts(response.parts, tool_context)

        # 处理基于任务的响应（流式或复杂处理）
        if isinstance(response, Task):
            task: Task = response
            print(f"[HostAgent] 📋 远程智能体返回基于任务的响应")
            print(
                f"[HostAgent] 🎯 任务ID: {task.id}, 状态: {task.status.state}")

            # 根据任务状态更新会话状态
            session_active = task.status.state not in [
                TaskState.completed,
                TaskState.canceled,
                TaskState.failed,
                TaskState.unknown,
            ]
            state['session_active'] = session_active
            print(f"[HostAgent] 🔄 会话活跃: {session_active}")

            # 从响应更新上下文和任务ID
            if task.contextId:
                state['context_id'] = task.contextId
                print(f"[HostAgent] 🔄 已更新上下文ID: {task.contextId}")

            state['task_id'] = task.id
            print(f"[HostAgent] 🔄 已更新任务ID: {task.id}")

            # 处理不同的任务状态
            if task.status.state == TaskState.input_required:
                print(f"[HostAgent] ⏸️ 远程智能体需要用户输入")
                # 强制用户输入回到对话
                tool_context.actions.skip_summarization = True
                tool_context.actions.escalate = True
            elif task.status.state == TaskState.canceled:
                print(f"[HostAgent] ❌ 远程智能体任务已取消")
                raise ValueError(f'智能体 {agent_name} 任务 {task.id} 已取消')
            elif task.status.state == TaskState.failed:
                print(f"[HostAgent] ❌ 远程智能体任务失败")
                raise ValueError(f'智能体 {agent_name} 任务 {task.id} 失败')

            # 提取并转换响应内容
            print(f"[HostAgent] 🔄 将远程智能体响应转换为主机大模型格式")
            response_content = []

            # 处理任务状态消息（如果存在）
            if task.status.message:
                print(f"[HostAgent] 📄 处理任务状态消息")
                response_content.extend(
                    await convert_parts(task.status.message.parts, tool_context)
                )

            # 处理任务工件（如果存在）
            if task.artifacts:
                print(
                    f"[HostAgent] 📎 处理 {len(task.artifacts)} 个任务工件")
                for artifact in task.artifacts:
                    response_content.extend(
                        await convert_parts(artifact.parts, tool_context)
                    )

            print(f"[HostAgent] ✅ 远程智能体委派成功完成")
            print(
                f"[HostAgent] 📊 向主机大模型返回 {len(response_content)} 个响应元素")

            return response_content

        # 如果响应既不是Message也不是Task，则处理未知响应类型
        print(f"[HostAgent] ❓ 收到未知响应类型: {type(response)}")
        raise ValueError(f'收到未知响应类型: {type(response)}')


async def convert_parts(parts: list[Part], tool_context: ToolContext):
    """
    将A2A部件列表转换为ADK格式，供主机智能体大模型处理。
    根据A2A协议规范处理文本、数据和文件部件。

    流程：A2A部件列表 -> 单个部件转换 -> ADK格式列表
    """
    print(f"[HostAgent] 🔄 将 {len(parts)} 个A2A部件转换为ADK格式")

    rval = []
    for i, p in enumerate(parts):
        print(
            f"[HostAgent] 🔧 转换部件 {i+1}/{len(parts)}: {getattr(p.root, 'kind', 'unknown') if hasattr(p, 'root') else 'no_root'}")
        converted_part = await convert_part(p, tool_context)
        rval.append(converted_part)
        print(f"[HostAgent] ✅ 部件 {i+1} 转换成功")

    print(f"[HostAgent] 🎉 所有 {len(parts)} 个部件已转换为ADK格式")
    return rval


async def convert_part(part: Part, tool_context: ToolContext):
    """
    将单个A2A部件转换为ADK格式，供主机智能体大模型处理。
    处理不同的部件类型：文本、数据和文件部件，并进行适当验证。

    流程：A2A部件 -> 类型检测 -> 格式转换 -> ADK兼容格式

    参数：
        part: 包含内容的A2A部件对象
        tool_context: 用于工件操作的ADK工具上下文

    返回：
        适合ADK处理的转换内容
    """
    print(f"[HostAgent] 🔍 将A2A部件转换为ADK格式")

    # 验证部件结构
    if not hasattr(part, 'root'):
        print(f"[HostAgent] ❌ 部件缺少root属性: {part}")
        return f'部件缺少root: {part}'

    part_kind = getattr(part.root, 'kind', 'unknown')
    print(f"[HostAgent] 📝 检测到部件类型: {part_kind}")

    # 处理文本部件
    if hasattr(part.root, 'kind') and part.root.kind == 'text':
        if hasattr(part.root, 'text'):
            print(
                f"[HostAgent] ✅ 文本部件已转换: {len(part.root.text)} 字符")
            return part.root.text
        print(f"[HostAgent] ❌ 文本部件缺少text属性")
        return '文本部件缺少text属性'

    # 处理数据部件
    elif hasattr(part.root, 'kind') and part.root.kind == 'data':
        if hasattr(part.root, 'data'):
            print(f"[HostAgent] ✅ 数据部件已转换: {type(part.root.data)}")
            return part.root.data
        print(f"[HostAgent] ❌ 数据部件缺少data属性")
        return '数据部件缺少data属性'

    # 处理文件部件
    elif hasattr(part.root, 'kind') and part.root.kind == 'file':
        print(f"[HostAgent] 📁 处理文件部件")

        # 验证文件结构
        if not hasattr(part.root, 'file'):
            print(f"[HostAgent] ❌ 文件部件缺少file属性")
            return '文件部件缺少file属性'

        file_obj = part.root.file
        if not hasattr(file_obj, 'name') or not file_obj.name:
            print(f"[HostAgent] ❌ 文件缺少name属性")
            return '文件缺少name属性'

        file_id = file_obj.name
        print(f"[HostAgent] 📋 处理文件: {file_id}")

        # 处理文件内容 - 处理FileWithBytes和FileWithUri
        if isinstance(file_obj, FileWithBytes):
            # 处理FileWithBytes（包含base64编码内容）
            try:
                print(f"[HostAgent] 🔓 解码base64文件内容")
                file_bytes = base64.b64decode(file_obj.bytes)
                print(
                    f"[HostAgent] ✅ 文件字节已解码: {len(file_bytes)} 字节")

                # 获取MIME类型
                mime_type = 'application/octet-stream'  # 默认值
                if file_obj.mimeType:
                    mime_type = file_obj.mimeType
                print(f"[HostAgent] 📄 文件MIME类型: {mime_type}")

                # 创建ADK Blob
                file_part = types.Part(
                    inline_data=types.Blob(
                        mime_type=mime_type, data=file_bytes
                    )
                )
                print(f"[HostAgent] 🔧 已创建ADK Blob部件")

                # 保存为工件
                print(f"[HostAgent] 💾 将文件保存为工件: {file_id}")
                await tool_context.save_artifact(file_id, file_part)
                tool_context.actions.skip_summarization = True
                tool_context.actions.escalate = True
                print(f"[HostAgent] ✅ 文件工件保存成功")

                # 返回数据部件引用
                result = DataPart(data={'artifact-file-id': file_id})
                print(f"[HostAgent] 📎 返回工件引用: {file_id}")
                return result

            except Exception as e:
                print(f"[HostAgent] ❌ 处理文件字节时出错: {str(e)}")
                return f'处理文件字节时出错: {str(e)}'
        elif isinstance(file_obj, FileWithUri):
            # 处理FileWithUri（具有URI引用）
            print(f"[HostAgent] 🔗 文件具有URI引用: {file_obj.uri}")
            print(
                f"[HostAgent] ⚠️ 基于URI的文件尚不支持工件保存")
            return f'尚不支持基于URI的文件: {file_obj.uri}'
        else:
            print(f"[HostAgent] ❌ 文件缺少字节和uri内容")
            return '文件缺少内容（无字节或uri）'

    # 处理未知类型
    print(f"[HostAgent] ❓ 未知部件类型: {part_kind}")
    return f'未知类型: {part_kind}'
