#!/usr/bin/env python3
"""
Host Agent CLI for A2A Multi-Agent System

This CLI acts as a host agent that manages and communicates with multiple remote agents:
1. Auto-startup of 5 remote agents with A2A protocol registration
2. LLM-based intelligent agent selection for user queries  
3. A2A protocol communication with selected remote agents
4. Streaming and non-streaming response handling

Usage:
    python host_agent_cli.py [--auto-start] [--llm-provider ollama|lmstudio] [--model-name MODEL]
"""

import asyncio
import base64
import json
import os
import subprocess
import time
import signal
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

import asyncclick as click
import httpx
from a2a.client import A2ACardResolver, A2AClient
from a2a.types import (
    AgentCard,
    FilePart,
    FileWithBytes,
    GetTaskRequest,
    JSONRPCErrorResponse,
    Message,
    MessageSendConfiguration,
    MessageSendParams,
    Part,
    SendMessageRequest,
    SendStreamingMessageRequest,
    Task,
    TaskArtifactUpdateEvent,
    TaskQueryParams,
    TaskState,
    TaskStatusUpdateEvent,
    TextPart,
    Role,
)

# Remote agent configurations (following README port assignments)
REMOTE_AGENTS = {
    'langgraph': {'port': 10000, 'description': 'Currency exchange agent'},
    'ag2': {'port': 10010, 'description': 'YouTube video analysis agent'},
    'google_adk': {'port': 10020, 'description': 'Reimbursement processing agent'},
    'semantickernel': {'port': 10030, 'description': 'Travel planning agent'},
    'llama_index_file_chat': {'port': 10040, 'description': 'File parsing and chat agent'}
}


class RemoteAgentProcess:
    """Manages a single remote agent process"""

    def __init__(self, agent_type: str, port: int, host: str = 'localhost',
                 llm_provider: str = 'lmstudio', model_name: str = 'qwen3-8b'):
        self.agent_type = agent_type
        self.port = port
        self.host = host
        self.llm_provider = llm_provider
        self.model_name = model_name
        self.process: Optional[subprocess.Popen] = None
        self.url = f"http://{host}:{port}"

    async def start(self) -> bool:
        """Start the agent process"""
        try:
            print(f"🚀 Starting {self.agent_type} agent on port {self.port}...")

            # Build command
            cmd = [
                sys.executable, '-m', f'remotes.{self.agent_type}',
                '--host', self.host,
                '--port', str(self.port),
                '--llm-provider', self.llm_provider,
                '--model-name', self.model_name
            ]

            # Start process
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # Wait for startup (check if agent is responding)
            for attempt in range(30):  # 30 second timeout
                try:
                    async with httpx.AsyncClient(timeout=2) as client:
                        response = await client.get(f"{self.url}/.well-known/agent-card")
                        if response.status_code == 200:
                            print(
                                f"✅ {self.agent_type} agent started successfully")
                            return True
                except:
                    pass
                await asyncio.sleep(1)

            print(f"❌ Failed to start {self.agent_type} agent")
            return False

        except Exception as e:
            print(f"❌ Error starting {self.agent_type}: {e}")
            return False

    def stop(self):
        """Stop the agent process"""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
                print(f"🛑 Stopped {self.agent_type} agent")
            except subprocess.TimeoutExpired:
                self.process.kill()
                print(f"🔥 Killed {self.agent_type} agent")
            except Exception as e:
                print(f"⚠️ Error stopping {self.agent_type}: {e}")


class RemoteAgentRegistry:
    """Manages registration and communication with remote agents"""

    def __init__(self, http_client: httpx.AsyncClient):
        self.http_client = http_client
        self.agents: Dict[str, AgentCard] = {}
        self.clients: Dict[str, A2AClient] = {}

    async def register_agent(self, url: str) -> Optional[AgentCard]:
        """Register an agent by resolving its card"""
        try:
            resolver = A2ACardResolver(self.http_client, url)
            card = await resolver.get_agent_card()
            card.url = url

            # Create A2A client for this agent
            client = A2AClient(self.http_client, agent_card=card)

            self.agents[card.name] = card
            self.clients[card.name] = client

            print(f"📋 Registered agent: {card.name}")
            print(f"   Description: {card.description}")
            print(f"   URL: {url}")

            return card

        except Exception as e:
            print(f"❌ Failed to register agent at {url}: {e}")
            return None

    def list_agents(self) -> List[Dict[str, str]]:
        """List all registered agents"""
        return [
            {
                'name': card.name,
                'description': card.description,
                'url': card.url or 'unknown'
            }
            for card in self.agents.values()
        ]


class LLMAgentSelector:
    """Uses LLM to select appropriate agent for user queries"""

    def __init__(self, llm_provider: str = 'lmstudio', model_name: str = 'qwen3-8b'):
        self.llm_provider = llm_provider
        self.model_name = model_name

        # Configure LLM client based on provider
        if llm_provider.lower() == 'ollama':
            self.base_url = "http://localhost:11434/v1"
            self.api_key = "ollama"
        else:  # lmstudio
            self.base_url = "http://localhost:1234/v1"
            self.api_key = "lm-studio"

    async def select_agent(self, user_query: str, available_agents: List[Dict[str, str]]) -> Optional[str]:
        """Select the best agent for the user query using LLM"""

        if not available_agents:
            return None

        # Build prompt for agent selection
        agent_list = "\n".join([
            f"- {agent['name']}: {agent['description']}"
            for agent in available_agents
        ])

        prompt = f"""Choose the best agent for this task.

Available agents:
{agent_list}

User request: "{user_query}"

Rules:
1. For currency/exchange queries → Currency Agent
2. For YouTube/video queries → YouTube Captions Agent  
3. For travel planning → SK Travel Agent
4. For expense/reimbursement → Reimbursement Agent
5. For file/document queries → Parse and Chat

Respond with ONLY the agent name exactly as listed above. No explanations."""

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.api_key}"
                    },
                    json={
                        "model": self.model_name,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.1,
                        "max_tokens": 50
                    }
                )

                if response.status_code == 200:
                    result = response.json()
                    raw_response = result["choices"][0]["message"]["content"]

                    selected_agent = raw_response.strip()

                    # Clean up the response - remove any tags, extra text, etc.
                    selected_agent = selected_agent.replace(
                        "<think>", "").replace("</think>", "")
                    selected_agent = selected_agent.replace(
                        "```", "").replace("`", "")
                    selected_agent = selected_agent.replace(
                        '"', '').replace("'", "")

                    # Extract just the agent name if there's extra text
                    lines = selected_agent.split('\n')
                    for line in lines:
                        line = line.strip()
                        if line and not line.startswith('Selected') and not line.startswith('Agent') and not line.startswith('For'):
                            selected_agent = line
                            break

                    selected_agent = selected_agent.strip()

                    # Validate the selection
                    agent_names = [agent['name'] for agent in available_agents]

                    # Exact match first
                    if selected_agent in agent_names:
                        return selected_agent
                    elif selected_agent == "NONE":
                        return None

                    # Try partial matching if exact match fails
                    for agent_name in agent_names:
                        if agent_name.lower() in selected_agent.lower() or selected_agent.lower() in agent_name.lower():
                            return agent_name

                    # Fallback: if it's clearly a currency query, use Currency Agent
                    if any(word in user_query.lower() for word in ['convert', 'currency', 'exchange', 'usd', 'cny', 'eur', 'gbp']):
                        for agent_name in agent_names:
                            if 'currency' in agent_name.lower():
                                return agent_name

                    print(
                        f"⚠️ Could not match LLM response to any agent: {selected_agent}")
                    return None
                else:
                    print(f"❌ LLM request failed: {response.status_code}")
                    return None

        except Exception as e:
            print(f"❌ Error selecting agent with LLM: {e}")
            return None


class HostAgentCLI:
    """Host Agent CLI for managing and communicating with remote agents via A2A protocol"""

    def __init__(self, auto_start: bool = False, llm_provider: str = 'lmstudio',
                 model_name: str = 'qwen3-8b'):
        self.auto_start = auto_start
        self.llm_provider = llm_provider
        self.model_name = model_name
        self.agent_processes: Dict[str, RemoteAgentProcess] = {}
        self.registry: Optional[RemoteAgentRegistry] = None
        self.selector: Optional[LLMAgentSelector] = None
        self.http_client: Optional[httpx.AsyncClient] = None

    async def start_remote_agents(self) -> bool:
        """Start all remote agents"""
        print("🔄 Starting remote agents...")

        success_count = 0
        for agent_type, config in REMOTE_AGENTS.items():
            agent_process = RemoteAgentProcess(
                agent_type,
                config['port'],
                llm_provider=self.llm_provider,
                model_name=self.model_name
            )

            if await agent_process.start():
                self.agent_processes[agent_type] = agent_process
                success_count += 1
            else:
                print(f"⚠️ Failed to start {agent_type}")

        print(f"✅ Started {success_count}/{len(REMOTE_AGENTS)} agents")
        return success_count > 0

    async def register_all_agents(self) -> bool:
        """Register all started agents"""
        print("📋 Registering agents...")

        success_count = 0
        for agent_type, process in self.agent_processes.items():
            card = await self.registry.register_agent(process.url)
            if card:
                success_count += 1

        print(
            f"✅ Registered {success_count}/{len(self.agent_processes)} agents")
        return success_count > 0

    async def handle_user_query(self, query: str) -> bool:
        """Handle a user query by selecting and communicating with an agent"""

        # Get available agents
        available_agents = self.registry.list_agents()
        if not available_agents:
            print("❌ No agents available")
            return False

        print(f"\n🤔 Analyzing query: '{query}'")
        print("🔍 Available agents:")
        for agent in available_agents:
            print(f"   - {agent['name']}: {agent['description']}")

        # Use LLM to select agent
        selected_agent_name = await self.selector.select_agent(query, available_agents)

        if not selected_agent_name:
            print("❌ No suitable agent found for this query")
            return False

        print(f"🎯 Selected agent: {selected_agent_name}")

        # Get agent client
        if selected_agent_name not in self.registry.clients:
            print(f"❌ Client for {selected_agent_name} not found")
            return False

        client = self.registry.clients[selected_agent_name]
        card = self.registry.agents[selected_agent_name]

        # Prepare message
        message = Message(
            role=Role.user,
            parts=[Part(root=TextPart(text=query))],
            messageId=str(uuid4()),
        )

        payload = MessageSendParams(
            message=message,
            configuration=MessageSendConfiguration(
                acceptedOutputModes=['text', 'text/plain'],
            ),
        )

        print(f"📤 Sending message to {selected_agent_name}...")

        try:
            # Check if agent supports streaming
            if card.capabilities and card.capabilities.streaming:
                print("🌊 Using streaming communication...")

                response_stream = client.send_message_streaming(
                    SendStreamingMessageRequest(params=payload)
                )

                message_received = False
                task_received = False

                async for result in response_stream:
                    if isinstance(result.root, JSONRPCErrorResponse):
                        print(f"❌ Agent error: {result.root.error}")
                        return False

                    event = result.root.result
                    print(f"📨 Received event type: {type(event).__name__}")

                    # Handle different event types
                    if isinstance(event, Message):
                        message_received = True
                        if event.role == 'assistant':
                            print(f"\n🤖 {selected_agent_name} message:")
                            for i, part in enumerate(event.parts):
                                print(f"   Part {i+1}:")
                                if hasattr(part, 'root') and hasattr(part.root, 'text'):
                                    print(f"      Text: {part.root.text}")
                                elif hasattr(part, 'text'):
                                    print(f"      Text: {part.text}")
                                else:
                                    print(f"      Raw part: {part}")

                    elif isinstance(event, Task):
                        task_received = True
                        print(f"\n📋 {selected_agent_name} task:")
                        print(f"   Task ID: {event.id}")
                        print(
                            f"   Status: {event.status.state if event.status else 'Unknown'}")

                        # Print artifacts if available
                        if hasattr(event, 'artifacts') and event.artifacts:
                            print(f"   📎 Artifacts ({len(event.artifacts)}):")
                            for i, artifact in enumerate(event.artifacts):
                                print(
                                    f"      Artifact {i+1}: {artifact.name if hasattr(artifact, 'name') else 'Unnamed'}")
                                if hasattr(artifact, 'parts') and artifact.parts:
                                    for j, part in enumerate(artifact.parts):
                                        if hasattr(part, 'root') and hasattr(part.root, 'text'):
                                            print(
                                                f"         Part {j+1}: {part.root.text}")
                                        elif hasattr(part, 'text'):
                                            print(
                                                f"         Part {j+1}: {part.text}")
                                        elif hasattr(part, 'kind') and part.kind == 'text':
                                            print(
                                                f"         Part {j+1}: {getattr(part, 'text', str(part))}")
                                        else:
                                            print(
                                                f"         Part {j+1}: {part}")

                    elif isinstance(event, TaskStatusUpdateEvent):
                        print(f"   📊 Task Status Update: {event.status}")

                    elif isinstance(event, TaskArtifactUpdateEvent):
                        print(
                            f"   📎 Task Artifact Update: {getattr(event, 'artifactId', 'Unknown')}")
                        if hasattr(event, 'artifact') and event.artifact:
                            artifact = event.artifact
                            print(
                                f"      Artifact: {artifact.name if hasattr(artifact, 'name') else 'Unnamed'}")
                            if hasattr(artifact, 'parts') and artifact.parts:
                                for j, part in enumerate(artifact.parts):
                                    if hasattr(part, 'root') and hasattr(part.root, 'text'):
                                        print(
                                            f"         Content: {part.root.text}")
                                    elif hasattr(part, 'text'):
                                        print(f"         Content: {part.text}")
                                    elif hasattr(part, 'kind') and part.kind == 'text':
                                        print(
                                            f"         Content: {getattr(part, 'text', str(part))}")

                    else:
                        print(f"   ❓ Unknown event: {event}")

                if not message_received and not task_received:
                    print("⚠️ No message or task received from agent")

            else:
                print("📞 Using non-streaming communication...")

                response = await client.send_message(
                    SendMessageRequest(params=payload)
                )

                if isinstance(response.root, JSONRPCErrorResponse):
                    print(f"❌ Agent error: {response.root.error}")
                    return False

                result = response.root.result
                print(f"📨 Received result type: {type(result).__name__}")

                if isinstance(result, Message):
                    print(f"\n🤖 {selected_agent_name} message:")
                    for i, part in enumerate(result.parts):
                        print(f"   Part {i+1}:")
                        if hasattr(part, 'root') and hasattr(part.root, 'text'):
                            print(f"      Text: {part.root.text}")
                        elif hasattr(part, 'text'):
                            print(f"      Text: {part.text}")
                        else:
                            print(f"      Raw part: {part}")

                elif isinstance(result, Task):
                    print(f"\n📋 {selected_agent_name} task:")
                    print(f"   Task ID: {result.id}")
                    print(
                        f"   Status: {result.status.state if result.status else 'Unknown'}")

                    # Print artifacts
                    if hasattr(result, 'artifacts') and result.artifacts:
                        print(f"   📎 Artifacts ({len(result.artifacts)}):")
                        for i, artifact in enumerate(result.artifacts):
                            print(
                                f"      Artifact {i+1}: {artifact.name if hasattr(artifact, 'name') else 'Unnamed'}")
                            if hasattr(artifact, 'parts') and artifact.parts:
                                for j, part in enumerate(artifact.parts):
                                    if hasattr(part, 'root') and hasattr(part.root, 'text'):
                                        print(
                                            f"         Part {j+1}: {part.root.text}")
                                    elif hasattr(part, 'text'):
                                        print(
                                            f"         Part {j+1}: {part.text}")
                                    elif hasattr(part, 'kind') and part.kind == 'text':
                                        print(
                                            f"         Part {j+1}: {getattr(part, 'text', str(part))}")
                                    else:
                                        print(f"         Part {j+1}: {part}")

                    # Print task history if available
                    if hasattr(result, 'history') and result.history:
                        print(
                            f"   📜 History ({len(result.history)} messages):")
                        for i, msg in enumerate(result.history):
                            if hasattr(msg, 'role'):
                                print(f"      Message {i+1} ({msg.role}):")
                                if hasattr(msg, 'parts'):
                                    for j, part in enumerate(msg.parts):
                                        if hasattr(part, 'root') and hasattr(part.root, 'text'):
                                            print(f"         {part.root.text}")
                                        elif hasattr(part, 'text'):
                                            print(f"         {part.text}")

                else:
                    print(f"   ❓ Unknown result type: {result}")

            return True

        except Exception as e:
            print(f"❌ Error communicating with {selected_agent_name}: {e}")
            return False

    async def run_interactive_mode(self):
        """Run interactive CLI mode for the host agent"""
        print("\n🎉 Host Agent CLI Ready!")
        print("As a host agent, I can help you communicate with remote agents.")
        print("Type your queries below. Type 'quit' or ':q' to exit.")
        print("Type 'agents' to list available remote agents.")
        print("-" * 60)

        while True:
            try:
                query = input("\n💬 Your query: ").strip()

                if query.lower() in ['quit', ':q', 'exit']:
                    break
                elif query.lower() == 'agents':
                    agents = self.registry.list_agents()
                    print("\n📋 Available remote agents:")
                    for agent in agents:
                        print(f"   • {agent['name']}: {agent['description']}")
                elif query:
                    await self.handle_user_query(query)

            except KeyboardInterrupt:
                break
            except EOFError:
                break

    def cleanup(self):
        """Cleanup processes and resources"""
        print("\n🧹 Cleaning up...")

        # Stop all agent processes
        for process in self.agent_processes.values():
            process.stop()

        print("✅ Cleanup completed")

    async def run(self):
        """Main run method"""
        try:
            # Initialize HTTP client
            self.http_client = httpx.AsyncClient(timeout=30)
            self.registry = RemoteAgentRegistry(self.http_client)
            self.selector = LLMAgentSelector(
                self.llm_provider, self.model_name)

            if self.auto_start:
                # Start remote agents
                if not await self.start_remote_agents():
                    print("❌ Failed to start agents")
                    return

                # Wait a bit for agents to stabilize
                await asyncio.sleep(2)

                # Register agents
                if not await self.register_all_agents():
                    print("❌ Failed to register agents")
                    return
            else:
                print("🔧 Manual mode: Agents should be started separately")
                # Try to register any already running agents
                for agent_type, config in REMOTE_AGENTS.items():
                    url = f"http://localhost:{config['port']}"
                    await self.registry.register_agent(url)

            # Run interactive mode
            await self.run_interactive_mode()

        finally:
            if self.http_client:
                await self.http_client.aclose()


@click.command()
@click.option('--auto-start', is_flag=True, help='Automatically start remote agents')
@click.option('--llm-provider',
              type=click.Choice(['lmstudio', 'ollama'], case_sensitive=False),
              default='lmstudio', help='LLM provider for agent selection')
@click.option('--model-name', default='qwen3-8b', help='LLM model name')
async def main(auto_start: bool, llm_provider: str, model_name: str):
    """Host Agent CLI with automatic remote agent management and LLM-based agent selection"""

    cli = HostAgentCLI(auto_start, llm_provider, model_name)

    def signal_handler(sig, frame):
        print("\n🛑 Received interrupt signal")
        cli.cleanup()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        await cli.run()
    finally:
        cli.cleanup()

if __name__ == '__main__':
    main()
