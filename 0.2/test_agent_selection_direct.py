#!/usr/bin/env python3
"""
直接测试代理选择功能，不需要运行服务器
"""
import logging
import os
import sys
import importlib.util

# 设置日志
logging.basicConfig(level=logging.DEBUG, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 导入要测试的函数，直接从文件加载
current_dir = os.path.dirname(os.path.abspath(__file__))
main_path = os.path.join(current_dir, "__main__.py")

spec = importlib.util.spec_from_file_location("main_module", main_path)
main_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(main_module)

# 从加载的模块中获取函数
analyze_request_by_keywords = main_module.analyze_request_by_keywords
analyze_ambiguous_term_context = main_module.analyze_ambiguous_term_context

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

def run_tests():
    """运行所有测试用例"""
    print("开始直接测试代理选择逻辑...")
    print("="*50)
    
    # 测试关键词分析
    print("\n关键词分析测试:")
    print("-"*50)
    for query in TEST_QUERIES:
        agent_type, confidence = analyze_request_by_keywords(query, logger)
        confidence_percent = f"{confidence:.1%}"
        print(f"查询: '{query}'")
        print(f"  结果: {agent_type} (置信度: {confidence_percent})")
    
    # 测试特殊术语上下文分析
    print("\n特殊术语上下文分析测试:")
    print("-"*50)
    ambiguous_terms = ["gold", "黄金", "silver", "白银", "au", "ag", "platinum", "铂"]
    ambiguous_contexts = [
        "what is the price of gold today?",  # 货币上下文
        "gold has atomic number 79",         # 元素上下文
        "gold price in USD",                 # 货币上下文
        "gold is a transition metal",        # 元素上下文
        "黄金价格最近上涨了",                # 货币上下文
        "黄金的熔点是多少？",                # 元素上下文
    ]
    
    for term in ambiguous_terms:
        print(f"\n测试术语: '{term}'")
        for context in ambiguous_contexts:
            result = analyze_ambiguous_term_context(context, term, logger)
            print(f"  上下文: '{context}'")
            print(f"  结果: {result}")
    
    print("\n所有测试完成！")

if __name__ == "__main__":
    run_tests()
