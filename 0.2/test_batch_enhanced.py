#!/usr/bin/env python3
"""
增强版批量测试工具 - 用于测试A2A智能代理系统的代理选择逻辑

功能:
1. 运行预定义的批量测试用例
2. 生成详细的性能报告
3. 跟踪准确率和置信度分布
"""
import os
import sys
import time
import json
import logging
from typing import Dict, List, Any, Tuple
import pandas as pd
import matplotlib.pyplot as plt
from tabulate import tabulate

# 导入代理选择逻辑
from __main__ import analyze_request_by_keywords, query_cache


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

# 测试用例 - 每个用例包含查询和预期的正确结果
TEST_CASES = [
    # 明确货币相关的查询
    {"query": "什么是美元与欧元的汇率？", "expected": "currency"},
    {"query": "100美元可以换多少人民币？", "expected": "currency"},
    {"query": "我想兑换一些日元", "expected": "currency"},
    {"query": "英镑和欧元哪个更值钱?", "expected": "currency"},
    {"query": "The current exchange rate for USD to CNY", "expected": "currency"},
    {"query": "汇率查询 美元 日元", "expected": "currency"},
    
    # 明确元素相关的查询
    {"query": "氢元素的原子量是多少？", "expected": "element"},
    {"query": "钠元素在周期表中的位置", "expected": "element"},
    {"query": "Fe是什么元素？", "expected": "element"},
    {"query": "Silicon properties in periodic table", "expected": "element"},
    {"query": "氧化钠的化学式", "expected": "element"},
    {"query": "最常见的金属元素有哪些", "expected": "element"},
    
    # 投资相关的歧义查询
    {"query": "我想投资Au", "expected": "currency"},
    {"query": "金价最近怎么样", "expected": "currency"},
    {"query": "Ag元素的特性", "expected": "element"},
    {"query": "如何看待黄金市场", "expected": "currency"},
    {"query": "铂金催化剂", "expected": "element"},
    {"query": "platinum作为催化剂的作用", "expected": "element"},
    {"query": "白银的市场价格", "expected": "currency"},
    {"query": "购买黄金的最佳时机", "expected": "currency"},
    {"query": "黄金ETF和实物黄金的区别", "expected": "currency"},
    
    # 极具挑战性的混合查询
    {"query": "Au的价格和原子量", "expected": "element"},  # 混合查询，但元素语境占优
    {"query": "黄金是贵金属吗", "expected": "currency"},  # 模糊，但偏向货币
    {"query": "白银的元素符号和今日价格", "expected": "currency"},  # 混合，但偏向货币
    {"query": "投资Au元素好还是Ag元素好", "expected": "currency"},  # 虽然提到元素，但明确投资语境
    {"query": "Gold element investment opportunities", "expected": "currency"},
    {"query": "Silver electron configuration and market price", "expected": "element"},
    
    # 特殊情况
    {"query": "Au元素在电子产品中的应用", "expected": "element"},
    {"query": "黄金首饰的成分", "expected": "currency"},
    {"query": "How is gold used in electronics?", "expected": "element"},
    {"query": "铂金和白金的区别是什么", "expected": "currency"},
    
    # 更多挑战性用例
    {"query": "银行的黄金业务", "expected": "currency"},
    {"query": "金属和非金属元素的区别", "expected": "element"},
    {"query": "Au和Ag哪个更稀有", "expected": "element"},
    {"query": "AU 珠宝的含金量", "expected": "currency"},
    {"query": "纯金和AU元素一样吗？", "expected": "element"},
    {"query": "黄金TD是什么", "expected": "currency"},
]

def run_test(test_case: Dict[str, str]) -> Dict[str, Any]:
    """
    运行单个测试用例
    
    Args:
        test_case: 包含查询和预期结果的字典
    
    Returns:
        测试结果字典
    """
    query = test_case["query"]
    expected = test_case["expected"]
    
    # 记录开始时间
    start_time = time.time()
    
    # 运行代理选择逻辑
    result, confidence = analyze_request_by_keywords(query, logger)
    
    # 记录结束时间
    end_time = time.time()
    elapsed_time = end_time - start_time
    
    # 检查结果是否正确
    is_correct = (result == expected)
    
    # 检查是否使用了缓存
    cache_entry = query_cache.get(query)
    from_cache = cache_entry is not None
    
    # 返回结果
    return {
        "query": query,
        "expected": expected,
        "result": result,
        "confidence": confidence,
        "correct": is_correct,
        "time": elapsed_time,
        "from_cache": from_cache
    }

def generate_report(results: List[Dict[str, Any]]) -> None:
    """
    生成测试报告
    
    Args:
        results: 测试结果列表
    """
    # 基本统计
    total_cases = len(results)
    correct_cases = sum(1 for r in results if r["correct"])
    accuracy = correct_cases / total_cases if total_cases > 0 else 0
    
    currency_cases = len([r for r in results if r["expected"] == "currency"])
    element_cases = len([r for r in results if r["expected"] == "element"])
    
    currency_correct = sum(1 for r in results 
                         if r["expected"] == "currency" and r["correct"])
    element_correct = sum(1 for r in results 
                        if r["expected"] == "element" and r["correct"])
    
    currency_accuracy = currency_correct / currency_cases if currency_cases > 0 else 0
    element_accuracy = element_correct / element_cases if element_cases > 0 else 0
    
    avg_time = sum(r["time"] for r in results) / total_cases
    avg_confidence = sum(r["confidence"] for r in results) / total_cases
    
    # 显示结果表格
    print("\n测试结果:")
    table_data = []
    for i, r in enumerate(results):
        confidence = f"{r['confidence']:.1%}"
        status = "✓" if r["correct"] else "✗"
        cache = "是" if r["from_cache"] else "否"
        row = [i+1, r["query"][:30] + "..." if len(r["query"]) > 30 else r["query"],
              r["expected"], r["result"], confidence, status, f"{r['time']:.3f}s", cache]
        table_data.append(row)
    
    headers = ["#", "查询", "预期", "结果", "置信度", "正确", "时间", "缓存"]
    print(tabulate(table_data, headers=headers, tablefmt="grid"))
    
    # 显示统计信息
    print("\n测试统计:")
    print(f"总用例数: {total_cases}")
    print(f"总体准确率: {correct_cases}/{total_cases} ({accuracy:.1%})")
    print(f"货币用例准确率: {currency_correct}/{currency_cases} ({currency_accuracy:.1%})")
    print(f"元素用例准确率: {element_correct}/{element_cases} ({element_accuracy:.1%})")
    print(f"平均置信度: {avg_confidence:.1%}")
    print(f"平均执行时间: {avg_time:.3f}秒")
    
    # 使用Pandas进行数据分析
    try:
        df = pd.DataFrame(results)
        
        print("\n置信度分布:")
        confidence_ranges = [0, 0.6, 0.7, 0.8, 0.9, 1.0]
        confidence_labels = ["< 60%", "60-70%", "70-80%", "80-90%", "90-100%"]
        df["confidence_range"] = pd.cut(df["confidence"], 
                                      bins=confidence_ranges, 
                                      labels=confidence_labels, 
                                      right=False)
        
        confidence_counts = df["confidence_range"].value_counts().sort_index()
        
        for range_label, count in confidence_counts.items():
            range_results = df[df["confidence_range"] == range_label]
            range_correct = sum(range_results["correct"])
            range_accuracy = range_correct / len(range_results) if len(range_results) > 0 else 0
            print(f"- {range_label}: {count}个查询, 准确率: {range_accuracy:.1%}")
        
        # 错误分析
        if total_cases - correct_cases > 0:
            print("\n错误分析:")
            error_cases = df[~df["correct"]]
            
            # 按预期结果分组计算错误数量
            errors_by_expected = error_cases["expected"].value_counts()
            for exp, count in errors_by_expected.items():
                print(f"- 将{exp}误分类: {count}个查询")
            
            # 详细错误列表
            print("\n错误详情:")
            for i, row in error_cases.iterrows():
                print(f"- '{row['query']}' - 预期: {row['expected']}, 得到: {row['result']}, "
                    f"置信度: {row['confidence']:.1%}")
    except Exception as e:
        print(f"无法生成详细分析报告: {str(e)}")

def visualize_results(results: List[Dict[str, Any]]) -> None:
    """
    可视化测试结果
    
    Args:
        results: 测试结果列表
    """
    try:
        import matplotlib
        matplotlib.use('TkAgg')  # 使用Tkinter后端以便显示
        
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
        
        # 图1: 分类准确率
        df = pd.DataFrame(results)
        accuracy_by_type = df.groupby("expected")["correct"].mean()
        accuracy_by_type.plot(kind="bar", ax=ax1, color=["#ff9999", "#99ff99"])
        ax1.set_title("分类准确率")
        ax1.set_xlabel("预期类别")
        ax1.set_ylabel("准确率")
        ax1.set_ylim(0, 1)
        
        for i, v in enumerate(accuracy_by_type):
            ax1.text(i, v + 0.02, f"{v:.1%}", ha="center")
        
        # 图2: 置信度分布
        df["confidence_bin"] = pd.cut(df["confidence"], 
                                    bins=[0, 0.6, 0.7, 0.8, 0.9, 1.0], 
                                    labels=["<60%", "60-70%", "70-80%", "80-90%", "90-100%"])
        
        confidence_counts = df["confidence_bin"].value_counts().sort_index()
        confidence_counts.plot(kind="bar", ax=ax2, color="#66b3ff")
        ax2.set_title("置信度分布")
        ax2.set_xlabel("置信度范围")
        ax2.set_ylabel("查询数量")
        
        for i, v in enumerate(confidence_counts):
            ax2.text(i, v + 0.5, str(v), ha="center")
        
        plt.tight_layout()
        plt.show()
        
    except Exception as e:
        print(f"无法生成图表: {str(e)}")
        print("请确保已安装matplotlib和pandas库")

def main():
    """主函数"""
    print("=" * 50)
    print(" A2A智能代理系统 - 增强版批量测试工具 ")
    print("=" * 50)
    
    # 清除缓存以确保公平测试
    query_cache.clear()
    
    # 运行所有测试用例
    results = []
    for i, test_case in enumerate(TEST_CASES):
        print(f"\r进度: [{i+1}/{len(TEST_CASES)}]", end="", flush=True)
        result = run_test(test_case)
        results.append(result)
    
    print("\n\n测试完成!")
    
    # 生成报告
    generate_report(results)
    
    # 询问是否显示可视化结果
    try:
        show_viz = input("\n是否显示可视化结果? [y/n]: ").strip().lower()
        if show_viz == 'y':
            visualize_results(results)
    except Exception:
        pass

if __name__ == "__main__":
    main()
