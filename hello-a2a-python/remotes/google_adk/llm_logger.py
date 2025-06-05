"""简洁的A2A系统日志记录模块"""

import json
import logging
import uuid
from typing import Any

logger = logging.getLogger("a2a.llm_logger")


class LLMLogger:
    """简洁的大模型日志记录器"""

    def __init__(self, component_name: str):
        self.component_name = component_name

    def log_request(self, request_id: str, model: str, prompt_length: int, correlation_id: str | None = None):
        """记录大模型请求"""
        logger.info(
            f"🔵 [{self.component_name}] 请求: {model} | ID:{request_id[:8]} | "
            f"关联:{correlation_id[:8] if correlation_id else '无'} | 长度:{prompt_length}"
        )

    def log_response(self, request_id: str, model: str, duration_ms: float, response_length: int):
        """记录大模型响应"""
        logger.info(
            f"🟢 [{self.component_name}] 响应: {model} | ID:{request_id[:8]} | "
            f"耗时:{round(duration_ms, 2)}ms | 长度:{response_length}"
        )

    def log_error(self, request_id: str, model: str, error: str):
        """记录大模型错误"""
        logger.error(f"🔴 [{self.component_name}] 错误: {model} | ID:{request_id[:8]} | {error}")


class RequestFlowLogger:
    """请求流程日志记录器"""

    @staticmethod
    def generate_correlation_id() -> str:
        """生成关联ID"""
        return str(uuid.uuid4())

    @staticmethod
    def log_flow_event(event_type: str, component: str, correlation_id: str, message: str):
        """记录流程事件"""
        emoji_map = {
            "request_start": "🚀", "processing": "⚙️", "delegation": "🔄",
            "response": "✅", "error": "❌", "a2a_request": "📡",
            "a2a_response": "📨", "agent_selection": "🎯"
        }
        emoji = emoji_map.get(event_type, "📋")
        logger.info(f"{emoji} [{component}] {event_type.upper()}: {message} (ID:{correlation_id[:8]})")


# 全局实例
adk_llm_logger = LLMLogger("GoogleADK")
host_llm_logger = LLMLogger("HostAgent")
request_flow_logger = RequestFlowLogger()


def log_google_adk_event(event: Any, session_id: str):
    """记录Google ADK事件"""
    if not logger.isEnabledFor(logging.DEBUG):
        return

    try:
        event_type = type(event).__name__
        logger.debug(f"🔍 [GoogleADK] 事件: {event_type} | 会话:{session_id[:8]}")
    except Exception as e:
        logger.warning(f"⚠️ [GoogleADK] 记录事件失败: {e}")


def enhance_remote_agent_logging(agent_name: str, correlation_id: str):
    """为远程智能体创建日志记录器"""
    return {
        "log_request": lambda msg: request_flow_logger.log_flow_event(
            "a2a_request", f"远程智能体[{agent_name}]", correlation_id, msg
        ),
        "log_response": lambda msg: request_flow_logger.log_flow_event(
            "a2a_response", f"远程智能体[{agent_name}]", correlation_id, msg
        ),
        "log_error": lambda msg: request_flow_logger.log_flow_event(
            "error", f"远程智能体[{agent_name}]", correlation_id, msg
        )
    }
