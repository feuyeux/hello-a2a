#!/usr/bin/env python3
import asyncio
import httpx
import json
import uuid

# 测试查询列表，包含货币类和元素类请求
TEST_QUERIES = [
    "什么是美元与欧元的汇率？",  # 货币
    "氢元素的原子量是多少？",    # 元素
    "100美元可以换多少人民币？", # 货币
    "钠元素在周期表中的位置",    # 元素
    "我想兑换一些日元",         # 货币
    "Fe是什么元素？",           # 元素
]

async def send_request(query: str):
    """向A2A服务器发送测试请求"""
    task_id = str(uuid.uuid4())
    message_id = str(uuid.uuid4())
    
    # 构建请求
    request_data = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "tasks/send",
        "params": {
            "id": task_id,
            "contextId": str(uuid.uuid4()),
            "message": {
                "id": message_id,
                "role": "user",
                "content": [{
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
        
    return response.json()

async def main():
    print("开始测试智能代理选择功能...")
    print("="*50)
    
    for query in TEST_QUERIES:
        print(f"测试查询: '{query}'")
        try:
            response = await send_request(query)
            print(f"服务器响应: {json.dumps(response, ensure_ascii=False, indent=2)}")
        except Exception as e:
            print(f"请求失败: {str(e)}")
        print("-"*50)
    
    print("所有测试完成！")

if __name__ == "__main__":
    asyncio.run(main())
