import requests

from a2a.types import AgentCard


def get_agent_card(remote_agent_address: str) -> AgentCard:
    """Get the agent card."""
    # Handle URLs with and without protocol
    if remote_agent_address.startswith(('http://', 'https://')):
        url = f'{remote_agent_address}/.well-known/agent.json'
    else:
        url = f'http://{remote_agent_address}/.well-known/agent.json'

    agent_card = requests.get(url)
    return AgentCard(**agent_card.json())
