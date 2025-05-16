import unittest
from unittest.mock import patch, MagicMock
from agents.agent import ElementAgent, query_element, format_element_info, ResponseFormat
from agents.periodic_table import PERIODIC_TABLE
import pytest
import pytest_asyncio


class TestElementAgent(unittest.TestCase):
    """Test cases for ElementAgent class"""

    def setUp(self):
        """Set up test environment before each test method"""
        # 直接使用 ElementAgent，不做 mock 替换
        self.agent = ElementAgent()

    def tearDown(self):
        """Clean up after each test method"""
        # 不需要停止 mock，因为没有使用 mock
        pass

    def test_invoke(self):
        """Test invoking with multiple elements in the query"""
        # Call the invoke method with a query containing multiple elements
        result = self.agent.invoke("碳和氧的信息", "test-session-id")

        # Verify results
        self.assertTrue(result["is_task_complete"])
        self.assertFalse(result["require_user_input"])
        # Content should contain info for both carbon and oxygen
        self.assertIn("Carbon", result["content"])
        self.assertIn("Oxygen", result["content"])

    # 使用 pytest-asyncio 启用异步测试
    @pytest.mark.asyncio
    async def test_stream(self):
        """测试流式处理API的功能"""
        # 进行流式查询
        results = []
        async for item in self.agent.stream("请告诉我氢元素的信息", "test-stream-session"):
            results.append(item)
            print(f"Received stream item: {item}")  # 调试输出

        # 验证结果
        # 至少应该有最终结果
        self.assertTrue(len(results) > 0)
        # 最终结果应该包含氢元素的信息
        last_result = results[-1]
        self.assertTrue("content" in last_result,
                        f"Result doesn't contain 'content': {last_result}")
        print(f"Last result content: {last_result.get('content', '')}")  # 调试输出

        # 验证结果包含氢元素信息
        if "content" in last_result:
            self.assertTrue(
                "氢" in last_result["content"] or
                "Hydrogen" in last_result["content"] or
                "H" in last_result["content"],
                f"Result doesn't contain hydrogen info: {last_result['content']}"
            )


if __name__ == '__main__':
    unittest.main()
