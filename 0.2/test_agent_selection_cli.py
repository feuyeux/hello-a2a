#!/usr/bin/env python3
"""
直接测试代理选择功能的命令行工具
"""
import argparse
import logging
import os
import subprocess
import sys

# 设置日志
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 测试用例
TEST_QUERIES = [
    # 明确货币相关的查询
    "什么是美元与欧元的汇率？",      # 货币
    "100美元可以换多少人民币？",     # 货币
    "我想兑换一些日元",             # 货币
    "最近比特币的价格怎么样？",      # 货币
    "英镑和欧元的汇率是多少？",      # 货币
    
    # 明确元素相关的查询
    "氢元素的原子量是多少？",        # 元素
    "钠元素在周期表中的位置",        # 元素
    "Fe是什么元素？",              # 元素
    "碳元素有几种同位素？",          # 元素
    "氧气的化学性质是什么？",        # 元素
    
    # 模糊查询，可能是货币也可能是元素
    "黄金的价格是多少？",           # 货币上下文
    "黄金是第几周期的元素？",        # 元素上下文
    "银的导电性如何？",             # 元素上下文
    "银的市场价格是多少？",          # 货币上下文
    "金和银哪个更值钱？",           # 货币上下文
    "金和银在元素周期表中的位置",     # 元素上下文
    
    # 极具挑战性的模糊查询
    "铂金和黄金哪个更稀有？",        # 混合上下文，可能同时涉及货币和元素
    "Au的原子量和价格",            # 混合上下文
    "帮我查一下金的信息",           # 非常模糊，没有明确上下文
]

def main():
    """单一查询或批量测试代理选择算法"""
    parser = argparse.ArgumentParser(description='测试代理选择逻辑')
    parser.add_argument('--query', '-q', help='要测试的查询文本')
    parser.add_argument('--all', '-a', action='store_true', help='测试所有内置测试用例')
    
    args = parser.parse_args()
    
    if args.query:
        # 单一查询测试
        print(f"测试代理选择: '{args.query}'")
        run_test_query(args.query)
    elif args.all:
        # 测试所有内置测试用例
        print("测试所有内置测试用例...")
        for i, query in enumerate(TEST_QUERIES):
            print(f"\n[{i+1}/{len(TEST_QUERIES)}] 测试: '{query}'")
            run_test_query(query)
    else:
        parser.print_help()

def run_test_query(query):
    """运行一个测试查询"""
    # 构建执行脚本的命令
    cmd = f"""
import logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger()

from __main__ import analyze_request_by_keywords

# 测试查询
query = "{query}"
agent_type, confidence = analyze_request_by_keywords(query, logger)
print(f"查询: '{query}'")
print(f"分析结果: {{agent_type}} (置信度: {{confidence:.1%}})")
"""
    
    # 使用subprocess运行Python代码
    try:
        # 在当前目录下运行python -c命令
        result = subprocess.run(
            ['python', '-c', cmd],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            capture_output=True,
            text=True,
            check=True
        )
        print(result.stdout)
        if result.stderr:
            print(f"警告/错误: {result.stderr}")
    except subprocess.CalledProcessError as e:
        print(f"执行失败: {e}")
        print(f"错误输出: {e.stderr}")

if __name__ == "__main__":
    main()
