import mesop as me


@me.stateclass
class AgentState:
    """智能体列表状态管理类"""

    agent_dialog_open: bool = False  # 智能体对话框是否打开
    agent_address: str = ''  # 智能体地址
    agent_name: str = ''  # 智能体名称
    agent_description: str = ''  # 智能体描述
    input_modes: list[str]  # 支持的输入模式
    output_modes: list[str]  # 支持的输出模式
    stream_supported: bool = False  # 是否支持流式处理
    push_notifications_supported: bool = False  # 是否支持推送通知
    error: str = ''  # 错误信息
    agent_framework_type: str = ''  # 智能体框架类型
