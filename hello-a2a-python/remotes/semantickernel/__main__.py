import logging
import sys
import os

import click
import httpx

# 确保在 Windows 上正确处理 UTF-8 编码
if sys.platform == "win32":
    import locale
    # 设置控制台输出编码为 UTF-8
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
    # 设置环境变量确保 UTF-8 编码
    os.environ['PYTHONIOENCODING'] = 'utf-8'

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryPushNotifier, InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from remotes.semantickernel.agent_executor import SemanticKernelTravelAgentExecutor
from dotenv import load_dotenv


# 配置日志输出支持 UTF-8 编码
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
# 确保日志处理器使用 UTF-8 编码
for handler in logging.root.handlers:
    if hasattr(handler.stream, 'reconfigure'):
        handler.stream.reconfigure(encoding='utf-8')

logger = logging.getLogger(__name__)

load_dotenv()


@click.command()
@click.option('--host', default='localhost')
@click.option('--port', default=10030)
@click.option('--llm-provider', 'llm_provider', default='lmstudio',
              type=click.Choice(['lmstudio', 'ollama'], case_sensitive=False),
              help='LLM 提供商：lmstudio 或 ollama')
@click.option('--model-name', 'model_name', default='qwen3-0.6b',
              help='模型名称，默认为 qwen3-0.6b')
def main(host, port, llm_provider, model_name):
    """Starts the Semantic Kernel Agent server using A2A.

    支持使用不同的 LLM 提供商：
    - lmstudio: 使用 LM Studio (默认端口 1234)
    - ollama: 使用 Ollama (默认端口 11434)
    """
    logger.info(
        f"启动Semantic Kernel旅行智能体服务器 - LLM 提供商: {llm_provider}, 模型: {model_name}")

    httpx_client = httpx.AsyncClient()
    request_handler = DefaultRequestHandler(
        agent_executor=SemanticKernelTravelAgentExecutor(
            llm_provider=llm_provider, model_name=model_name),
        task_store=InMemoryTaskStore(),
        push_notifier=InMemoryPushNotifier(httpx_client),
    )

    server = A2AStarletteApplication(
        agent_card=get_agent_card(host, port), http_handler=request_handler
    )
    import uvicorn

    uvicorn.run(server.build(), host=host, port=port)


def get_agent_card(host: str, port: int):
    """Returns the Agent Card for the Semantic Kernel Travel Agent."""
    # Build the agent card
    capabilities = AgentCapabilities(streaming=True)
    skill_trip_planning = AgentSkill(
        id='trip_planning_sk',
        name='Semantic Kernel Trip Planning',
        description=(
            'Handles comprehensive trip planning, including currency exchanges, itinerary creation, sightseeing, '
            'dining recommendations, and event bookings using Frankfurter API for currency conversions.'
        ),
        tags=['trip', 'planning', 'travel', 'currency', 'semantic-kernel'],
        examples=[
            'Plan a budget-friendly day trip to Seoul including currency exchange.',
            "What's the exchange rate and recommended itinerary for visiting Tokyo?",
        ],
    )

    agent_card = AgentCard(
        name='SK Travel Agent',
        description=(
            'Semantic Kernel-based travel agent providing comprehensive trip planning services '
            'including currency exchange and personalized activity planning.'
        ),
        url=f'http://{host}:{port}/',
        version='1.0.0',
        defaultInputModes=['text'],
        defaultOutputModes=['text'],
        capabilities=capabilities,
        skills=[skill_trip_planning],
    )

    return agent_card


if __name__ == '__main__':
    main()
