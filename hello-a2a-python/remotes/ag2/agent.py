import asyncio
import json
import logging
import os
import re
import traceback

from collections.abc import AsyncIterable
from typing import Any, Literal

from autogen import AssistantAgent, LLMConfig
from autogen.mcp import create_toolkit
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import BaseModel

# Load environment variables
load_dotenv()


logger = logging.getLogger(__name__)


class ResponseModel(BaseModel):
    """Response model for the YouTube MCP agent."""

    text_reply: str
    closed_captions: str | None
    status: Literal['TERMINATE', '']

    def format(self) -> str:
        """Format the response as a string."""
        if self.closed_captions is None:
            return self.text_reply
        else:
            return (
                f'{self.text_reply}\n\nClosed Captions:\n{self.closed_captions}'
            )


class YoutubeMCPAgent:
    """Agent to access a Youtube MCP Server to download closed captions"""

    SUPPORTED_CONTENT_TYPES = ['text', 'text/plain']

    def __init__(self, llm_provider: str = "ollama", model_name: str = "qwen3:8b"):
        """初始化YouTube MCP智能体。

        参数:
            llm_provider: LLM 提供商，支持 "ollama" 或 "lmstudio"
            model_name: 模型名称，默认为 "qwen3:8b"
        """
        # Import AG2 dependencies here to isolate requirements
        try:
            # 根据提供商设置不同的配置
            if llm_provider.lower() == "ollama":
                llm_config = LLMConfig(
                    model=model_name,
                    api_type="ollama",
                    client_host="http://localhost:11434"
                )
            elif llm_provider.lower() == "lmstudio":
                llm_config = LLMConfig(
                    model=model_name,
                    api_type="openai",
                    base_url="http://localhost:1234/v1",
                    api_key="lm-studio"  # LM Studio requires any non-empty API key
                )
            else:
                raise ValueError(
                    f"不支持的 LLM 提供商: {llm_provider}。支持的选项: 'ollama', 'lmstudio'")

            # Create the assistant agent that will use MCP tools
            self.agent = AssistantAgent(
                name='YoutubeMCPAgent',
                llm_config=llm_config,
                system_message=(
                    'You are a specialized assistant for processing YouTube videos. '
                    'You can use MCP tools to fetch captions and process YouTube content. '
                    'You can provide captions, summarize videos, or analyze content from YouTube. '
                    "If the user asks about anything not related to YouTube videos or doesn't provide a YouTube URL, "
                    'politely state that you can only help with tasks related to YouTube videos.\n\n'
                    'WORKFLOW:\n'
                    '1. When you receive a YouTube URL, use the DownloadClosedCaptions tool to fetch captions\n'
                    '2. Wait for the tool execution to complete\n'
                    '3. ALWAYS provide a final summary response in the specified JSON format\n\n'
                    'CRITICAL: After using any tool, you MUST provide a final response that summarizes what you found. '
                    'Never end the conversation without providing a proper summary response.\n\n'
                    'RESPONSE FORMAT: Always respond using this JSON structure:\n'
                    '{\n'
                    '  "text_reply": "Your summary of the video captions or task result",\n'
                    '  "closed_captions": "The full caption text if applicable, or null",\n'
                    '  "status": "TERMINATE"\n'
                    '}\n\n'
                    'Example: After getting captions, respond with:\n'
                    '{\n'
                    '  "text_reply": "I successfully retrieved the captions for this YouTube video. The video discusses...",\n'
                    '  "closed_captions": "[The full caption text here]",\n'
                    '  "status": "TERMINATE"\n'
                    '}'
                ),
            )

            self.initialized = True
            logger.info(
                f'MCP智能体初始化成功 - 使用 {llm_provider} 提供商，模型: {model_name}')
        except ImportError as e:
            logger.error(f'Failed to import AG2 components: {e}')
            self.initialized = False

    def get_agent_response(self, response: str) -> dict[str, Any]:
        """Format agent response in a consistent structure."""
        try:
            # Extract JSON from response that may contain <think> tags or other text
            json_response = self._extract_json_from_response(response)

            # Try to parse the response as a ResponseModel JSON
            response_dict = json.loads(json_response)
            model = ResponseModel(**response_dict)

            # Return only text_reply and closed_captions as JSON
            clean_response = {
                "text_reply": model.text_reply,
                "closed_captions": model.closed_captions
            }

            # All final responses should be treated as complete
            return {
                'is_task_complete': True,
                'require_user_input': False,
                'content': json.dumps(clean_response, ensure_ascii=False, indent=2),
            }
        except Exception as e:
            # Log but continue with best-effort fallback
            logger.error(f'Error parsing response: {e}, response: {response}')

            # Default to treating it as a completed response
            return {
                'is_task_complete': True,
                'require_user_input': False,
                'content': response,
            }

    def _extract_json_from_response(self, response: str) -> str:
        """Extract JSON from response text that may contain <think> tags or other content."""
        try:
            # Remove <think> tags and everything between them
            cleaned_response = re.sub(
                r'<think>.*?</think>', '', response, flags=re.DOTALL).strip()

            # If the cleaned response is empty, fall back to looking for JSON in the original
            if not cleaned_response:
                cleaned_response = response

            # Look for JSON object boundaries in the cleaned response
            start_idx = cleaned_response.find('{')
            if start_idx == -1:
                # No JSON found, return the cleaned response as-is
                return cleaned_response

            # Find the matching closing brace
            brace_count = 0
            end_idx = start_idx
            for i, char in enumerate(cleaned_response[start_idx:], start_idx):
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_idx = i + 1
                        break

            # Extract the JSON part
            json_part = cleaned_response[start_idx:end_idx]

            # Verify it's valid JSON by attempting to parse it
            json.loads(json_part)
            return json_part

        except (json.JSONDecodeError, ValueError, Exception) as e:
            logger.debug(f"JSON extraction failed: {e}")
            # If extraction fails, try to return just the text without <think> tags
            try:
                cleaned = re.sub(r'<think>.*?</think>', '',
                                 response, flags=re.DOTALL).strip()
                return cleaned if cleaned else response
            except Exception:
                return response

    async def _provide_fallback_response(self, query: str, error_msg: str) -> str:
        """Provide fallback response when MCP server fails."""
        # Check if query contains a YouTube URL
        youtube_url_pattern = r'(?:https?://)?(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]+)'
        match = re.search(youtube_url_pattern, query)

        if match:
            video_id = match.group(1)
            return f"I encountered an error while trying to fetch captions from the YouTube video: {error_msg}\n\nThe video ID is: {video_id}\n\nThis could be due to:\n- The video has no captions available\n- The captions are auto-generated and restricted\n- The video is private or region-locked\n- Network connectivity issues with the MCP server\n\nPlease try with a different video that has manually created captions, or check if the video is publicly accessible."
        else:
            return f"I encountered an error while processing your request: {error_msg}\n\nPlease ensure you provide a valid YouTube URL and try again."

    async def stream(
        self, query: str, sessionId: str
    ) -> AsyncIterable[dict[str, Any]]:
        """Stream updates from the MCP agent."""
        if not self.initialized:
            yield {
                'is_task_complete': False,
                'require_user_input': True,
                'content': 'Agent initialization failed. Please check the dependencies and logs.',
            }
            return

        try:
            # Initial response to acknowledge the query
            yield {
                'is_task_complete': False,
                'require_user_input': False,
                'content': 'Processing request...',
            }

            logger.info(f'Processing query: {query[:50]}...')

            try:
                # Create stdio server parameters for mcp-youtube
                # Use uv tool run for cross-platform compatibility
                if os.name == 'nt':  # Windows
                    server_params = StdioServerParameters(
                        command="uv",
                        args=["tool", "run", "mcp-youtube", "run"],
                    )
                else:  # Unix-like systems
                    mcp_path = os.path.expanduser(
                        '~/.local/share/uv/tools/mcp-youtube/bin/mcp-youtube')
                    server_params = StdioServerParameters(
                        command=mcp_path,
                        args=["run"],  # Add the run subcommand for stdio mode
                    )

                # Use asyncio.timeout to prevent hanging - 180 seconds for longer videos
                async with asyncio.timeout(180):
                    # Connect to the MCP server using stdio client
                    async with (
                        stdio_client(server_params) as (read, write),
                        ClientSession(read, write) as session,
                    ):
                        # Initialize the connection
                        await session.initialize()
                        logger.info(
                            "MCP server connection initialized successfully")

                        # Create toolkit and register tools
                        toolkit = await create_toolkit(session=session)
                        logger.info(
                            f"MCP toolkit created with {len(toolkit.tools)} tools")

                        if not toolkit.tools:
                            raise ValueError(
                                "No tools available from MCP server")

                        toolkit.register_for_llm(self.agent)
                        logger.info("Tools registered for LLM")

                        # Log available tools for debugging
                        for tool in toolkit.tools:
                            logger.info(
                                f"Available tool: {tool.name} - {tool.description}")

                        logger.info(
                            f"Starting AG2 agent run with query: {query[:100]}...")

                        result = await self.agent.a_run(
                            message=query,
                            tools=toolkit.tools,
                            max_turns=8,  # Increased turns to ensure proper tool execution and final response
                            user_input=False,
                        )

                        # Debug: Log the result details
                        logger.info(f"AG2 result type: {type(result)}")
                        logger.info(
                            f"AG2 result attributes: {[attr for attr in dir(result) if not attr.startswith('_')]}")

                        # Process the result and get the response
                        await result.process()
                        logger.info("AG2 result processed successfully")

                        # Get the summary which contains the output
                        response = await result.summary
                        if response is None or not response.strip():
                            # If no summary, provide a helpful fallback
                            logger.warning(
                                "No summary available from AG2, using fallback")
                            response = (
                                "I successfully connected to the YouTube MCP server and "
                                "executed the captions retrieval tool. However, the final "
                                "summary was not generated properly. This may be due to "
                                "the video having no available captions or other processing issues. "
                                "Please try with a different YouTube video that has captions available."
                            )

                        logger.info(
                            f"Final response length: {len(response) if response else 0}")

                        # Final response
                        yield self.get_agent_response(response)

            except asyncio.TimeoutError:
                logger.error('Request timed out after 180 seconds')
                yield {
                    'is_task_complete': True,
                    'require_user_input': False,
                    'content': 'Request timed out after 3 minutes. The video may be extremely long or have processing issues. Please try a shorter video.',
                }

            except Exception as e:
                logger.error(
                    f'Error during MCP processing: {traceback.format_exc()}'
                )

                # Try to extract video info and provide fallback response
                fallback_response = await self._provide_fallback_response(query, str(e))
                yield {
                    'is_task_complete': True,
                    'require_user_input': False,
                    'content': fallback_response,
                }
        except Exception as e:
            logger.error(f'Error in streaming agent: {traceback.format_exc()}')
            yield {
                'is_task_complete': False,
                'require_user_input': True,
                'content': f'Error processing request: {str(e)}',
            }

    def invoke(self, query: str, sessionId: str) -> dict[str, Any]:
        """Synchronous invocation of the MCP agent."""
        raise NotImplementedError(
            'Synchronous invocation is not supported by this agent. Use the streaming endpoint (tasks/sendSubscribe) instead.'
        )
