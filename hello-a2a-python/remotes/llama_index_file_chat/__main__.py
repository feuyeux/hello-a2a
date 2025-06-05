import logging

import click
import httpx

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryPushNotifier, InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
)
from dotenv import load_dotenv

from remotes.llama_index_file_chat.agent import ParseAndChat
from remotes.llama_index_file_chat.agent_executor import LlamaIndexAgentExecutor


load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MissingAPIKeyError(Exception):
    """Exception for missing API key."""



@click.command()
@click.option('--host', 'host', default='localhost')
@click.option('--port', 'port', default=10040)
@click.option('--llm-provider', 'llm_provider', default='lmstudio', 
              type=click.Choice(['lmstudio', 'ollama'], case_sensitive=False),
              help='LLM 提供商：lmstudio 或 ollama')
@click.option('--model-name', 'model_name', default='qwen3-0.6b',
              help='模型名称，默认为 qwen3-0.6b')
def main(host, port, llm_provider, model_name):
    """Starts the LlamaIndex file chat agent server.
    
    支持使用不同的 LLM 提供商：
    - lmstudio: 使用 LM Studio (默认端口 1234)
    - ollama: 使用 Ollama (默认端口 11434)
    """
    try:
        logger.info(f"启动LlamaIndex文件聊天智能体服务器 - LLM 提供商: {llm_provider}, 模型: {model_name}")
        
        # Note: We're using local models now, so no API keys needed

        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)

        skill = AgentSkill(
            id='parse_and_chat',
            name='Parse and Chat',
            description='Parses a file and then chats with a user using the parsed content as context.',
            tags=['parse', 'chat', 'file', 'llama_parse'],
            examples=['What does this file talk about?'],
        )

        agent_card = AgentCard(
            name='Parse and Chat',
            description='Parses a file and then chats with a user using the parsed content as context.',
            url=f'http://{host}:{port}/',
            version='1.0.0',
            defaultInputModes=LlamaIndexAgentExecutor.SUPPORTED_INPUT_TYPES,
            defaultOutputModes=LlamaIndexAgentExecutor.SUPPORTED_OUTPUT_TYPES,
            capabilities=capabilities,
            skills=[skill],
        )

        httpx_client = httpx.AsyncClient()
        request_handler = DefaultRequestHandler(
            agent_executor=LlamaIndexAgentExecutor(
                llm_provider=llm_provider,
                model_name=model_name,
            ),
            task_store=InMemoryTaskStore(),
            push_notifier=InMemoryPushNotifier(httpx_client),
        )
        server = A2AStarletteApplication(
            agent_card=agent_card, http_handler=request_handler
        )
        import uvicorn

        uvicorn.run(server.build(), host=host, port=port)
    except MissingAPIKeyError as e:
        logger.error(f'Error: {e}')
        exit(1)
    except Exception as e:
        logger.error(f'An error occurred during server startup: {e}')
        exit(1)


if __name__ == '__main__':
    main()
