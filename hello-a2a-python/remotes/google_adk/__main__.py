import logging
import os

import click

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
)
from remotes.google_adk.agent import ReimbursementAgent
from remotes.google_adk.agent_executor import ReimbursementAgentExecutor
from dotenv import load_dotenv


load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MissingAPIKeyError(Exception):
    """Exception for missing API key."""



@click.command()
@click.option('--host', default='localhost')
@click.option('--port', default=10020)
@click.option('--llm-provider', 'llm_provider', default='lmstudio', 
              type=click.Choice(['lmstudio', 'ollama'], case_sensitive=False),
              help='LLM 提供商：lmstudio 或 ollama')
@click.option('--model-name', 'model_name', default='qwen3-8b',
              help='模型名称，默认为 qwen3-8b')
def main(host, port, llm_provider, model_name):
    """启动 Google ADK 报销智能体服务器
    
    支持使用不同的 LLM 提供商：
    - lmstudio: 使用 LM Studio (默认端口 1234)
    - ollama: 使用 Ollama (默认端口 11434)
    """
    try:
        logger.info(f"启动 Google ADK 报销智能体服务器 - LLM 提供商: {llm_provider}, 模型: {model_name}")
        
        # Check for API key only if Vertex AI is not configured
        if not os.getenv('GOOGLE_GENAI_USE_VERTEXAI') == 'TRUE':
            if not os.getenv('GOOGLE_API_KEY'):
                raise MissingAPIKeyError(
                    'GOOGLE_API_KEY environment variable not set and GOOGLE_GENAI_USE_VERTEXAI is not TRUE.'
                )

        capabilities = AgentCapabilities(streaming=True)
        skill = AgentSkill(
            id='process_reimbursement',
            name='Process Reimbursement Tool',
            description='Helps with the reimbursement process for users given the amount and purpose of the reimbursement.',
            tags=['reimbursement'],
            examples=[
                'Can you reimburse me $20 for my lunch with the clients?'
            ],
        )
        agent_card = AgentCard(
            name='Reimbursement Agent',
            description='This agent handles the reimbursement process for the employees given the amount and purpose of the reimbursement.',
            url=f'http://{host}:{port}/',
            version='1.0.0',
            defaultInputModes=ReimbursementAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=ReimbursementAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[skill],
        )
        request_handler = DefaultRequestHandler(
            agent_executor=ReimbursementAgentExecutor(llm_provider=llm_provider, model_name=model_name),
            task_store=InMemoryTaskStore(),
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
