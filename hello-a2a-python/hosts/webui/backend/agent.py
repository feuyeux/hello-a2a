import asyncio

import httpx

from .host_agent import HostAgent


async def initialize_agent():
    """初始化主机智能体"""
    # 创建HTTP客户端
    http_client = httpx.AsyncClient(timeout=30.0)
    # 异步创建主机智能体
    host_agent = await HostAgent.create(['http://localhost:10000'], http_client)
    # 创建ADK智能体
    return host_agent.create_agent()

# 执行异步函数
root_agent = asyncio.run(initialize_agent())
