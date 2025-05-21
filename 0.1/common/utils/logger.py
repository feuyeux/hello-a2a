"""
日志工具模块

本模块提供了统一的日志配置和工具函数，确保在整个A2A应用程序中
使用一致的日志格式和处理方式。支持标准日志级别和自定义格式化输出。
"""

import logging
import uvicorn


def setup_logger(name: str, level=logging.INFO):
    """
    设置并返回配置好的logger实例

    参数:
        name: logger名称
        level: 日志级别，默认为INFO

    返回:
        配置好的logger实例
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(level)
        logger.propagate = False
    return logger


def configure_uvicorn_logging():
    """
    配置Uvicorn的日志格式，返回日志配置字典

    返回:
        uvicorn日志配置字典
    """
    log_config = uvicorn.config.LOGGING_CONFIG.copy()
    format_string = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    # 为所有formatter设置统一格式
    for formatter in log_config["formatters"].values():
        formatter["fmt"] = format_string

    return log_config
