import click
import asyncio
from a2a.client import A2AClient
from typing import Any, Dict, List, Optional
from uuid import uuid4
from a2a.types import (
    SendMessageResponse,
    SendMessageSuccessResponse,
    Task,
    TaskState,
    SendMessageRequest,
    MessageSendParams,
    GetTaskRequest,
    GetTaskResponse,
    TaskQueryParams,
    SendStreamingMessageRequest,
)
import httpx
import traceback

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


def create_send_message_payload(
    text: str, task_id: str | None = None, context_id: str | None = None
) -> dict[str, Any]:
    """Helper function to create the payload for sending a task."""
    payload: dict[str, Any] = {
        'message': {
            'role': 'user',
            'parts': [{'kind': 'text', 'text': text}],
            'messageId': uuid4().hex,
        },
    }

    if task_id:
        payload['message']['taskId'] = task_id

    if context_id:
        payload['message']['contextId'] = context_id
    return payload


def print_json_response(response: Any, description: str) -> None:
    """Helper function to print the JSON representation of a response."""
    print(f'--- {description} ---')
    if hasattr(response, 'root'):
        print(f'{response.root.model_dump_json(exclude_none=True)}\n')
    else:
        print(f'{response.model_dump(mode="json", exclude_none=True)}\n')


async def run_single_turn_test(client: A2AClient) -> None:
    """Runs a single-turn non-streaming test."""

    send_payload = create_send_message_payload(
        text='how much is 100 USD in CAD?'
    )
    request = SendMessageRequest(params=MessageSendParams(**send_payload))

    print('--- Single Turn Request ---')
    # Send Message
    send_response: SendMessageResponse = await client.send_message(request)
    print_json_response(send_response, 'Single Turn Request Response')
    if not isinstance(send_response.root, SendMessageSuccessResponse):
        print('received non-success response. Aborting get task ')
        return

    if not isinstance(send_response.root.result, Task):
        print('received non-task response. Aborting get task ')
        return

    task_id: str = send_response.root.result.id
    print('---Query Task---')
    # query the task
    get_request = GetTaskRequest(params=TaskQueryParams(id=task_id))
    get_response: GetTaskResponse = await client.get_task(get_request)
    print_json_response(get_response, 'Query Task Response')


async def run_streaming_test(client: A2AClient) -> None:
    """Runs a single-turn streaming test."""

    send_payload = create_send_message_payload(
        text='how much is 50 EUR in JPY?'
    )

    request = SendStreamingMessageRequest(
        params=MessageSendParams(**send_payload)
    )

    print('--- Single Turn Streaming Request ---')
    stream_response = client.send_message_streaming(request)
    async for chunk in stream_response:
        print_json_response(chunk, 'Streaming Chunk')


async def run_multi_turn_test(client: A2AClient) -> None:
    """Runs a multi-turn non-streaming test."""
    print('--- Multi-Turn Request ---')
    # --- First Turn ---

    first_turn_payload = create_send_message_payload(
        text='how much is 100 USD?'
    )
    request1 = SendMessageRequest(
        params=MessageSendParams(**first_turn_payload)
    )
    first_turn_response: SendMessageResponse = await client.send_message(
        request1
    )
    print_json_response(first_turn_response, 'Multi-Turn: First Turn Response')

    context_id: str | None = None
    if isinstance(
        first_turn_response.root, SendMessageSuccessResponse
    ) and isinstance(first_turn_response.root.result, Task):
        task: Task = first_turn_response.root.result
        context_id = task.contextId  # Capture context ID

        # --- Second Turn (if input required) ---
        if task.status.state == TaskState.input_required and context_id:
            print('--- Multi-Turn: Second Turn (Input Required) ---')
            second_turn_payload = create_send_message_payload(
                'in GBP', task.id, context_id
            )
            request2 = SendMessageRequest(
                params=MessageSendParams(**second_turn_payload)
            )
            second_turn_response = await client.send_message(request2)
            print_json_response(
                second_turn_response, 'Multi-Turn: Second Turn Response'
            )
        elif not context_id:
            print('Warning: Could not get context ID from first turn response.')
        else:
            print(
                'First turn completed, no further input required for this test case.'
            )


async def run_custom_query(client: A2AClient, query: str, streaming: bool = False) -> None:
    """Runs a custom query against the agent."""
    print(f'--- Custom Query: "{query}" ---')

    send_payload = create_send_message_payload(text=query)

    if streaming:
        request = SendStreamingMessageRequest(
            params=MessageSendParams(**send_payload))
        print('Streaming response:')
        stream_response = client.send_message_streaming(request)
        async for chunk in stream_response:
            print_json_response(chunk, 'Response Chunk')
    else:
        request = SendMessageRequest(params=MessageSendParams(**send_payload))
        response: SendMessageResponse = await client.send_message(request)
        print_json_response(response, 'Response')


@click.command()
@click.option('--url', default=AGENT_URL, help='URL of the A2A agent server')
@click.option('--agent-type', type=click.Choice(['currency', 'element']),
              default='element', help='Type of agent to test')
@click.option('--streaming/--no-streaming', default=False,
              help='Whether to use streaming mode for queries')
@click.option('--query', help='Custom query to send to the agent')
@click.option('--run-tests', is_flag=True, help='Run predefined test suite')
async def main(url: str, agent_type: str, streaming: bool, query: str, run_tests: bool) -> None:
    """Main function to run tests against an A2A agent."""
    print(f'Connecting to {agent_type} agent at {url}...')

    try:
        async with httpx.AsyncClient() as httpx_client:
            client = await A2AClient.get_client_from_agent_card_url(
                httpx_client, url
            )
            print('Connection successful.')

            if query:
                # Run a custom query
                await run_custom_query(client, query, streaming)
            elif run_tests:
                # Run the standard test suite
                await run_single_turn_test(client)
                await run_streaming_test(client)
                await run_multi_turn_test(client)
            else:
                # Run sample queries based on agent type
                queries = ELEMENT_QUERIES if agent_type == 'element' else CURRENCY_QUERIES
                print(f"Running sample {agent_type} queries...")
                for sample_query in queries:
                    await run_custom_query(client, sample_query, streaming)

    except Exception as e:
        traceback.print_exc()
        print(f'An error occurred: {e}')
        print('Ensure the agent server is running.')


async def main_async(url: str, agent_type: str, streaming: bool, query: Optional[str], run_tests: bool) -> None:
    """Main function to run tests against an A2A agent."""
    print(f'Connecting to {agent_type} agent at {url}...')
    
    try:
        async with httpx.AsyncClient() as httpx_client:
            client = await A2AClient.get_client_from_agent_card_url(
                httpx_client, url
            )
            print('Connection successful.')
            
            if query:
                # Run a custom query
                await run_custom_query(client, query, streaming)
            elif run_tests:
                # Run the standard test suite
                await run_single_turn_test(client)
                await run_streaming_test(client)
                await run_multi_turn_test(client)
            else:
                # Run sample queries based on agent type
                queries = ELEMENT_QUERIES if agent_type == 'element' else CURRENCY_QUERIES
                print(f"Running sample {agent_type} queries...")
                for sample_query in queries:
                    await run_custom_query(client, sample_query, streaming)

    except Exception as e:
        traceback.print_exc()
        print(f'An error occurred: {e}')
        print('Ensure the agent server is running.')


@click.command()
@click.option('--url', default=AGENT_URL, help='URL of the A2A agent server')
@click.option('--agent-type', type=click.Choice(['currency', 'element']),
              default='element', help='Type of agent to test')
@click.option('--streaming/--no-streaming', default=False,
              help='Whether to use streaming mode for queries')
@click.option('--query', help='Custom query to send to the agent')
@click.option('--run-tests', is_flag=True, help='Run predefined test suite')
def cli(url: str, agent_type: str, streaming: bool, query: Optional[str], run_tests: bool) -> None:
    """Command-line interface for the A2A test client."""
    asyncio.run(main_async(url, agent_type, streaming, query, run_tests))


if __name__ == '__main__':
    cli()
