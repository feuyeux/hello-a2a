import logging

import click

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from .agent import YoutubeMCPAgent
from .agent_executor import AG2AgentExecutor
from dotenv import load_dotenv


load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@click.command()
@click.option('--host', 'host', default='localhost')
@click.option('--port', 'port', default=10010)
@click.option('--llm-provider', 'llm_provider', default='lmstudio',
              type=click.Choice(['lmstudio', 'ollama'], case_sensitive=False),
              help='LLM provider: lmstudio or ollama')
@click.option('--model-name', 'model_name', default='qwen2.5-7b-instruct',
              help='Model name, default is qwen2.5-7b-instruct')
def main(host, port, llm_provider, model_name):
    """Starts the AG2 MCP Agent server.

    Supports different LLM providers:
    - lmstudio: Use LM Studio (default port 1234)
    - ollama: Use Ollama (default port 11434)
    """
    logger.info(
        f"Starting AG2 MCP Agent server - LLM provider: {llm_provider}, model: {model_name}")

    request_handler = DefaultRequestHandler(
        agent_executor=AG2AgentExecutor(
            llm_provider=llm_provider, model_name=model_name),
        task_store=InMemoryTaskStore(),
    )
    server = A2AStarletteApplication(
        agent_card=get_agent_card(host, port), http_handler=request_handler
    )
    import uvicorn

    uvicorn.run(server.build(), host=host, port=port)


def get_agent_card(host: str, port: int):
    """Returns the Agent Card for the AG2 Agent."""
    capabilities = AgentCapabilities(streaming=True)
    skill = AgentSkill(
        id='download_closed_captions',
        name='Download YouTube Closed Captions',
        description='Retrieve closed captions/transcripts from YouTube videos',
        tags=['youtube', 'captions', 'transcription', 'video'],
        examples=[
            'Extract the transcript from this YouTube video: https://www.youtube.com/watch?v=xxxxxx',
            'Download the captions for this YouTube tutorial',
        ],
    )
    return AgentCard(
        name='YouTube Captions Agent',
        description='AI agent that can extract closed captions and transcripts from YouTube videos. This agent provides raw transcription data that can be used for further processing.',
        url=f'http://{host}:{port}/',
        version='1.0.0',
        defaultInputModes=YoutubeMCPAgent.SUPPORTED_CONTENT_TYPES,
        defaultOutputModes=YoutubeMCPAgent.SUPPORTED_CONTENT_TYPES,
        capabilities=capabilities,
        skills=[skill],
    )


if __name__ == '__main__':
    main()
