#!/usr/bin/env python3
"""Simple test client for the A2A agents."""
import asyncio
import httpx
import argparse
import sys
from a2a.client import A2AClient
from a2a.types import (
    MessageSendParams,
    SendMessageRequest,
    GetTaskRequest,
    TaskQueryParams,
)
from uuid import uuid4

# Sample queries by agent type
SAMPLE_QUERIES = {
    'element': [
        '氢元素的信息',  # Information about hydrogen
        'Tell me about carbon',
        'Fe and Cu properties',
    ],
    'currency': [
        'Convert 100 USD to EUR',
        'Exchange rate JPY to GBP',
        'What is 50 CAD in CNY?',
    ]
}


async def simple_query(url: str, query: str):
    """Execute a simple query against the agent."""
    print(f"Sending query to {url}: '{query}'")
    
    # Create the message payload
    payload = {
        'message': {
            'role': 'user',
            'parts': [{'kind': 'text', 'text': query}],
            'messageId': uuid4().hex,
        }
    }
    
    request = SendMessageRequest(params=MessageSendParams(**payload))
    
    # Connect to the agent
    client = httpx.AsyncClient(timeout=30.0)  # Increase timeout
    try:
        print(f"Connecting to agent at {url}...")
        a2a_client = await A2AClient.get_client_from_agent_card_url(client, url)
        print("Connected to agent successfully")
        
        print(f"Sending query: {query}")
        # Send the query
        response = await a2a_client.send_message(request)
        
        # Print the response
        print("\n----- Response from Agent -----")
        if hasattr(response, 'root'):
            print(f"Response type: {type(response.root)}")
            print(response.root.model_dump_json(indent=2, exclude_none=True))
            
            # Check if we have a task result
            if hasattr(response.root, 'result') and response.root.result:
                task_id = response.root.result.id
                print(f"Task ID: {task_id}")
                
                # Get task details
                get_request = GetTaskRequest(params=TaskQueryParams(id=task_id))
                get_response = await a2a_client.get_task(get_request)
                print("\n----- Task Details -----")
                print(get_response.model_dump_json(indent=2, exclude_none=True))
        else:
            print(response.model_dump_json(indent=2, exclude_none=True))
        print("----- End of Response -----\n")
        
    except Exception as e:
        print(f"Error interacting with agent: {e}")
    finally:
        await client.aclose()


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Simple test client for A2A agents")
    parser.add_argument("--url", default="http://localhost:10000", help="URL of the agent server")
    parser.add_argument("--agent-type", choices=["currency", "element"], default="element", 
                        help="Type of agent to test")
    parser.add_argument("--query", help="Custom query to send to the agent")
    parser.add_argument("--tests", action="store_true", help="Run predefined test suite")
    parser.add_argument("--streaming", action="store_true", help="Use streaming mode")
    return parser.parse_args()


async def main():
    """Run the simple test client."""
    args = parse_args()
    
    url = args.url
    agent_type = args.agent_type
    
    print(f"Testing {agent_type.capitalize()} Agent at {url}")
    
    if args.query:
        # Run a single custom query
        await simple_query(url, args.query)
    elif args.tests:
        # Run all predefined queries for the selected agent type
        queries = SAMPLE_QUERIES.get(agent_type, [])
        if not queries:
            print(f"No sample queries available for {agent_type} agent")
            return
        
        for query in queries:
            await simple_query(url, query)
            print("\n" + "="*50 + "\n")  # Separator between queries
            await asyncio.sleep(1)
    else:
        # Default: run first sample query for the selected agent
        queries = SAMPLE_QUERIES.get(agent_type, [])
        if not queries:
            print(f"No sample queries available for {agent_type} agent")
            return
        
        await simple_query(url, queries[0])


if __name__ == "__main__":
    asyncio.run(main())
