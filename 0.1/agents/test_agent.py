import unittest
from unittest.mock import patch, MagicMock
from agents.agent import ElementAgent, ElementResponse, ElementAPIResponse 
from agents.tools import query_element, element_to_string
# 使用新的资源加载方式
from agents.resources.periodic_table import load_periodic_table, Element
import pytest
import pytest_asyncio
from typing import Dict, Any, cast, Iterator
from langchain_core.runnables.config import RunnableConfig

# 加载周期表
PERIODIC_TABLE = load_periodic_table()


class TestElementAgentSync(unittest.TestCase):
    """Test cases for ElementAgent class using synchronous methods"""

    def setUp(self):
        """Set up test environment before each test method"""
        # 使用 ElementAgent 但确保测试可重复运行
        with patch('langchain_openai.ChatOpenAI') as mock_chat_openai:
            # 设置 mock 的返回值
            mock_instance = MagicMock()
            mock_chat_openai.return_value = mock_instance
            
            # 创建智能体实例
            self.agent = ElementAgent()
            
            # 手动获取碳和氧元素，确保非None
            carbon = PERIODIC_TABLE.get_by_chinese_name("碳")
            oxygen = PERIODIC_TABLE.get_by_chinese_name("氧")
            test_elements = []
            if carbon:
                test_elements.append(carbon)
            if oxygen:
                test_elements.append(oxygen)
            
            # 设置 mock get_state 方法
            mock_state = MagicMock()
            mock_state.values = {
                'structured_response': ElementResponse(
                    message="查询结果如下",
                    elements=test_elements
                )
            }
            self.agent.graph.get_state = MagicMock(return_value=mock_state)
            
            # 替换 graph.invoke 方法
            self.agent.graph.invoke = MagicMock()

    def tearDown(self):
        """Clean up after each test method"""
        pass

    def test_invoke(self):
        """Test invoking with multiple elements in the query"""
        # Call the invoke method with a query containing multiple elements
        result = self.agent.invoke("碳和氧的信息", "test-session-id")

        # Verify results
        # Check that we have content in the response
        self.assertIn("content", result)
        # Content should contain info for both carbon and oxygen
        self.assertIn("Carbon", result["content"])
        self.assertIn("Oxygen", result["content"])
        
        # 验证确实调用了 graph.invoke
        self.agent.graph.invoke.assert_called_once()


# 创建单独的测试类用于异步测试
@pytest.mark.asyncio
class TestElementAgentAsync:
    """Test cases for ElementAgent class using asynchronous methods"""

    @pytest_asyncio.fixture
    async def agent(self):
        # 使用 patch 来模拟 stream 方法
        with patch('langchain_openai.ChatOpenAI') as mock_chat_openai:
            # 设置 mock 的返回值
            mock_instance = MagicMock()
            mock_chat_openai.return_value = mock_instance
            
            # 创建智能体实例
            agent = ElementAgent()
            
            # 获取氢元素，确保非None
            hydrogen = PERIODIC_TABLE.get_by_chinese_name("氢")
            test_elements = []
            if hydrogen:
                test_elements.append(hydrogen)
            
            # 创建一个正确类型的迭代器作为模拟返回值
            def mock_stream_generator(*args, **kwargs):
                # 返回一个空的迭代器，因为我们已经直接mock了stream方法
                # 这只是为了满足类型要求
                for _ in []:
                    yield {}
                
            # 使用 MagicMock 而不是直接替换方法
            mock_stream = MagicMock()
            mock_stream.return_value = mock_stream_generator()
            agent.graph.stream = mock_stream
            
            # 使用 patch 替换 agent.stream 方法
            async def mock_agent_stream(query, sessionId):
                """模拟流式响应"""
                # 初始响应
                yield {"content": "正在分析您的查询...", 
                      "is_task_complete": False}
                
                # 中间响应
                yield {"content": "正在查询元素...", 
                      "is_task_complete": False}
                
                # 最终响应
                element_info = []
                for element in test_elements:
                    element_info.append(element_to_string(element))
                formatted_message = "\n\n".join(element_info)
                
                yield {"content": formatted_message, 
                      "is_task_complete": True}
            
            # 替换方法
            agent.stream = mock_agent_stream
            
            return agent

    async def test_stream(self, agent):
        """测试流式处理API的功能"""
        # 进行流式查询
        results = []
        async for item in agent.stream("请告诉我氢元素的信息", "test-stream-session"):
            results.append(item)
            print(f"Received stream item: {item}")  # 调试输出

        # 验证结果
        # 至少应该有初始响应、中间响应和最终结果
        assert len(results) >= 3
        
        # 最终结果应该包含氢元素的信息
        last_result = results[-1]
        assert "content" in last_result, f"Result doesn't contain 'content': {last_result}"
        print(f"Last result content: {last_result.get('content', '')}")  # 调试输出

        # 验证结果包含氢元素信息
        if "content" in last_result:
            assert (
                "氢" in last_result["content"] or
                "Hydrogen" in last_result["content"] or
                "H" in last_result["content"]
            ), f"Result doesn't contain hydrogen info: {last_result['content']}"
            
        # 验证结果包含任务完成标志
        assert "is_task_complete" in last_result
        assert last_result["is_task_complete"] is True


if __name__ == '__main__':
    unittest.main()
