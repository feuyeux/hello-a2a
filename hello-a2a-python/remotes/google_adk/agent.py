import json
import random

from typing import Any, Optional

from google.adk.agents.llm_agent import LlmAgent
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.tool_context import ToolContext
from .task_manager import AgentWithTaskManager


# 用于演示目的的已创建request_ids本地缓存。
request_ids = {
    'REQ-2024-0601-001', 
    'REQ-2024-0601-002', 
    'REQ-2024-0601-003',
    'REQ-2024-0602-001'
}


def create_request_form(
    date: Optional[str] = None,
    amount: Optional[str] = None,
    purpose: Optional[str] = None,
) -> dict[str, Any]:
    """创建员工填写的申请表单

    Args:
        date (str): 申请日期。可以为空字符串。
        amount (str): 申请金额。可以为空字符串。
        purpose (str): 申请目的。可以为空字符串。

    Returns:
        dict[str, Any]: 包含申请表单数据的字典。
    """
    request_id = 'request_id_' + str(random.randint(1000000, 9999999))
    request_ids.add(request_id)
    return {
        'request_id': request_id,
        'date': '<交易日期>' if not date else date,
        'amount': '<交易金额>' if not amount else amount,
        'purpose': '<业务理由/交易目的>'
        if not purpose
        else purpose,
    }


def return_form(
    form_request: dict[str, Any],
    tool_context: ToolContext,
    instructions: Optional[str] = None,
) -> dict[str, Any]:
    """返回一个结构化的json对象，指示需要完成的表单。

    参数：
        form_request (dict[str, Any]): 申请表单数据。
        tool_context (ToolContext): 工具运行的上下文。
        instructions (str): 处理表单的指令。可以是空字符串。

    返回：
        dict[str, Any]: 表单响应的JSON字典。
    """
    if isinstance(form_request, str):
        form_request = json.loads(form_request)

    tool_context.actions.skip_summarization = True
    tool_context.actions.escalate = True
    form_dict = {
        'type': 'form',
        'form': {
            'type': 'object',
            'properties': {
                'date': {
                    'type': 'string',
                    'format': 'date',
                    'description': '费用日期',
                    'title': '日期',
                },
                'amount': {
                    'type': 'string',
                    'format': 'number',
                    'description': '费用金额',
                    'title': '金额',
                },
                'purpose': {
                    'type': 'string',
                    'description': '费用目的',
                    'title': '目的',
                },
                'request_id': {
                    'type': 'string',
                    'description': '申请ID',
                    'title': '申请ID',
                },
            },
            'required': list(form_request.keys()),
        },
        'form_data': form_request,
        'instructions': instructions,
    }
    return form_dict


def reimburse(request_id: str, status: Optional[str] = None) -> dict[str, Any]:
    """为给定的申请ID向员工报销金额
    
    Args:
        request_id (str): 报销申请的唯一标识符。
        status (str, optional): 可选状态参数(如果提供则忽略)。
                               实际状态由函数逻辑确定。
    
    Returns:
        dict[str, Any]: 包含申请ID和状态的字典。
    """
    if request_id not in request_ids:
        return {
            'request_id': request_id,
            'status': '错误：无效的申请ID。',
        }
    return {'request_id': request_id, 'status': '已批准'}


class ReimbursementAgent(AgentWithTaskManager):
    """处理报销申请的智能体"""

    SUPPORTED_CONTENT_TYPES = ['text', 'text/plain']

    def __init__(self, llm_provider: str = "lmstudio", model_name: str = "qwen3-8b"):
        self.llm_provider = llm_provider
        self.model_name = model_name
        self._agent = self._build_agent()
        self._user_id = 'remote_agent'
        self._runner = Runner(
            app_name=self._agent.name,
            agent=self._agent,
            artifact_service=InMemoryArtifactService(),
            session_service=InMemorySessionService(),
            memory_service=InMemoryMemoryService(),
        )

    def get_processing_message(self) -> str:
        return '正在处理报销申请...'

    def _build_agent(self) -> LlmAgent:
        """构建报销智能体的大模型智能体"""
        # 根据 llm_provider 参数选择模型配置
        if self.llm_provider.lower() == "lmstudio":
            model = LiteLlm(
                model=f"openai/{self.model_name}", 
                api_base="http://localhost:1234/v1",
                api_key="lm-studio"
            )
        elif self.llm_provider.lower() == "ollama":
            model = LiteLlm(
                model=f"ollama/{self.model_name}",
                api_base="http://localhost:11434",
                api_key="ollama"
            )
        else:
            raise ValueError(f"不支持的 LLM 提供商: {self.llm_provider}. 支持的提供商: 'lmstudio', 'ollama'")
            
        return LlmAgent(
            model=model,
            name='reimbursement_agent',
            description=(
                '这个智能体处理员工的报销流程，根据金额和报销目的进行处理'
            ),
            instruction="""
    您是一个处理员工报销流程的智能体。

    当您收到报销申请时，您应该首先使用 create_request_form() 创建新的申请表单。只有在用户提供了默认值时才提供默认值，否则使用空字符串作为默认值。
      1. '日期'：交易日期。
      2. '金额'：交易的美元金额。
      3. '业务理由/目的'：报销的原因。

    创建表单后，您应该返回调用 return_form 并传入 create_request_form 调用的表单数据。

    从用户那里收到填写好的表单后，您应该检查表单是否包含所有必需信息：
      1. '日期'：交易日期。
      2. '金额'：申请报销的金额值。
      3. '业务理由/目的'：报销的项目/对象/工件。

    如果您没有所有信息，您应该直接拒绝申请，通过调用 return_form 方法，提供缺失的字段。

    对于有效的报销申请，您可以使用 reimburse() 来报销员工。
      * 在您的响应中，您应该包含申请ID和报销申请的状态。

    """,
            tools=[
                create_request_form,
                reimburse,
                return_form,
            ],
        )
