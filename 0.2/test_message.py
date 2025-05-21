#!/usr/bin/env python3
import asyncio
import httpx
import json
import uuid
import os

# 测试查询
TEST_QUERIES = [
    "什么是美元与欧元的汇率？",  # 货币
    "氢元素的原子量是多少？",    # 元素
]

async def send_message(query: str):
    """向A2A服务器发送正确格式的消息请求"""
    message_id = str(uuid.uuid4())
    
    # 构建请求 - 使用正确的 message/send 格式
    request_data = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "message/send",
        "params": {
            "conversationId": str(uuid.uuid4()),
            "message": {
                "messageId": message_id,
                "role": "user",
                "parts": [{
                    "type": "text",
                    "text": query
                }]
            }
        }
    }
    
    # 发送请求
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:10000/",
            json=request_data,
            timeout=30
        )
        
    print(f"请求: {query}")
    print(f"响应状态码: {response.status_code}")
    
    # 清理终端输出，查看服务器日志
    os.system('echo "\n--- 查看服务器日志中的代理选择信息 ---"')

async def main():
    print("=== 测试智能代理选择功能 ===")
    
    for query in TEST_QUERIES:
        await send_message(query)
        # 等待片刻以便于观察日志
        await asyncio.sleep(1)
    
    print("测试完成！")

if __name__ == "__main__":
    asyncio.run(main())
