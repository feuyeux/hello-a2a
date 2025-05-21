#!/usr/bin/env python3
"""
测试代理选择逻辑的批量测试工具
"""
import logging
import os
import sys

# 设置日志
logging.basicConfig(level=logging.INFO, 
                    format='%(message)s')
logger = logging.getLogger()

# 复制模块便于导入
os.system('cp __main__.py app.py')

# 导入要测试的函数
from app import analyze_request_by_keywords

# 测试用例
TEST_CASES = [
    # 明确货币相关的查询
    "什么是美元与欧元的汇率？",
    "100美元可以换多少人民币？",
    "我想兑换一些日元",
    
    # 明确元素相关的查询
    "氢元素的原子量是多少？",
    "钠元素在周期表中的位置",
    "Fe是什么元素？",
    
    # 投资相关的歧义查询
    "我想投资Au",
    "金价最近怎么样",
    "Ag元素的特性",
    "如何看待黄金市场",
    "铂金催化剂",
    "platinum作为催化剂的作用",
    "白银的市场价格",
    "购买黄金的最佳时机",
    
    # 极具挑战性的混合查询
    "Au的价格和原子量",
    "黄金是贵金属吗"
]

def main():
    print("代理选择逻辑批量测试")
    print("=" * 50)
    
    for i, query in enumerate(TEST_CASES):
        agent_type, confidence = analyze_request_by_keywords(query, logger)
        confidence_percent = f"{confidence:.1%}"
        print(f"[{i+1}/{len(TEST_CASES)}] '{query}'")
        print(f"  结果: {agent_type} (置信度: {confidence_percent})")
        print()

if __name__ == "__main__":
    main()
