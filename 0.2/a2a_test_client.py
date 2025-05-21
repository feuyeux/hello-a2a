#!/usr/bin/env python3
"""Enhanced test client for A2A agents."""
import click
import asyncio
from typing import Any, Dict, List
from uuid import uuid4
import httpx
import traceback

from a2a.client import A2AClient
from a2a.types import (
    SendMessageResponse,
    SendMessageSuccessResponse,
    Task,
    TaskState,
    SendMessageRequest,
    MessageSendParams,
    GetTaskRequest,
    TaskQueryParams,
    SendStreamingMessageRequest,
)

# Default agent URL
AGENT_URL = 'http://localhost:10000'

# Sample queries for each agent type
CURRENCY_QUERIES = [
    'how much is 100 USD in CAD?',
    'convert 50 EUR to JPY',
    'what is the exchange rate from GBP to USD?',
]

ELEMENT_QUERIES = [
    '氢元素的信息',  # Information about hydrogen
    'Tell me about carbon',
    'Fe and Cu properties',
]


def create_message_payload(text: str) -> dict[str, Any]:
    """Helper function to create the payload for sending a message."""
    return {
        'message': {
            'role': 'user',
            'parts': [{'kind': 'text', 'text': text}],
            'messageId': uuid4().hex,
        },
    }


async def send_query(client: httpx.AsyncClient, a2a_client: A2AClient, text: str, streaming: bool) -> None:
    """Send a query to an A2A agent."""
    print(f"Sending query: '{text}'")
    
    payload = create_message_payload(text)
    
    if streaming:
        request = SendStreamingMessageRequest(params=MessageSendParams(**payload))
        result = await a2a_client.send_streaming_message(request)
        
        print("\n----- Streaming Response -----")
        async for chunk in result:
            if chunk.delta:
                print(chunk.delta.content or "", end="", flush=True)
        print("\n----- End of Streaming Response -----\n")
        
    else:
        request = SendMessageRequest(params=MessageSendParams(**payload))
        response = await a2a_client.send_message(request)
        
        print("\n----- Response -----")
        if isinstance(response, SendMessageSuccessResponse) and response.result:
            task_id = response.result.id
            print(f"Task ID: {task_id}")
            
            # Get task details
            task_request = GetTaskRequest(params=TaskQueryParams(id=task_id))
            task_response = await a2a_client.get_task(task_request)
            
            if task_response.task:
                task = task_response.task
                
                # Print task status
                print(f"Task status: {task.status.state}")
                
                if task.status.message and task.status.message.content:
                    print("\nAgent response:")
                    print(f"{task.status.message.content}")
                
                # Print artifacts if present
                if task.artifacts:
                    print("\nArtifacts:")
                    for artifact in task.artifacts:
                        if artifact.text:
                            print(f"{artifact.text}")
            else:
                print("No task information returned")
        else:
            print(f"Unexpected response: {response}")
        print("----- End of Response -----\n")


async def test_agent(url: str, agent_type: str, streaming: bool, query: str = None, run_tests: bool = False) -> None:
    """Test an A2A agent with queries."""
    print(f"Testing {agent_type.capitalize()} Agent at {url}")
    print(f"Mode: {'Streaming' if streaming else 'Standard'}")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            print(f"Connecting to agent at {url}...")
            a2a_client = await A2AClient.get_client_from_agent_card_url(client, url)
            print("Connected to agent successfully\n")
            
            if query:
                # Send a single custom query
                await send_query(client, a2a_client, query, streaming)
                
            elif run_tests:
                # Run all predefined queries for the selected agent type
                queries = CURRENCY_QUERIES if agent_type == 'currency' else ELEMENT_QUERIES
                
                for i, test_query in enumerate(queries):
                    print(f"\nTest {i+1}/{len(queries)}: {test_query}")
                    print("=" * 50)
                    await send_query(client, a2a_client, test_query, streaming)
                    print("=" * 50)
                    await asyncio.sleep(1)  # Pause between queries
                    
            else:
                # Default: run the first sample query for the selected agent type
                default_query = CURRENCY_QUERIES[0] if agent_type == 'currency' else ELEMENT_QUERIES[0]
                await send_query(client, a2a_client, default_query, streaming)
                
        except Exception as e:
            print(f"Error interacting with agent: {e}")
            traceback.print_exc()


@click.command()
@click.option('--url', default=AGENT_URL, help='URL of the A2A agent server')
@click.option('--agent-type', type=click.Choice(['currency', 'element']), 
              default='element', help='Type of agent to test')
@click.option('--streaming/--no-streaming', default=False, 
              help='Whether to use streaming mode for queries')
@click.option('--query', help='Custom query to send to the agent')
@click.option('--run-tests', is_flag=True, help='Run predefined test suite')
def cli(url: str, agent_type: str, streaming: bool, query: str, run_tests: bool) -> None:
    """Command-line entry point for the test client."""
    asyncio.run(test_agent(url, agent_type, streaming, query, run_tests))


if __name__ == "__main__":
    try:
        cli()
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()
