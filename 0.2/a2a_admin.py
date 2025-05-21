#!/usr/bin/env python3
"""
A2A智能代理系统管理工具

本工具提供命令行界面，用于测试、管理和监控A2A智能代理系统。
主要功能包括：
1. 批量测试代理选择逻辑
2. 查询和管理缓存
3. 测试单个查询的完整分析流程
4. 性能评估与报告
"""

import os
import sys
import time
import json
import logging
import argparse
from typing import Dict, Any, List, Tuple
from tabulate import tabulate
import matplotlib.pyplot as plt
from datetime import datetime

# 导入代理选择相关功能
from __main__ import (
    analyze_request, 
    analyze_request_by_keywords, 
    analyze_ambiguous_term_context,
    query_cache
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("a2a_admin")

# 预定义测试用例集
TEST_CASES = {
    "基础货币查询": [
        "美元和欧元的汇率是多少？",
        "100美元可以兑换多少人民币？",
        "日元现在的汇率怎么样？",
        "What is the current value of USD to EUR?",
        "How much is 50 GBP in JPY?",
    ],
    "基础元素查询": [
        "氢元素的性质是什么？",
        "铁元素的原子序数是多少？",
        "氧元素的原子量",
        "Tell me about carbon element",
        "What are the properties of Helium?",
    ],
    "歧义查询": [
        "黄金的价格是多少？",
        "Gold的性质是什么？",
        "AU是什么元素？",
        "Au的投资价值如何？",
        "Fe在周期表中的位置",
        "Ag元素和银币有什么区别？",
    ],
    "复杂混合查询": [
        "黄金(Au)的原子量和今日价格",
        "白银是贵金属还是贵金属元素？",
        "为什么黄金投资者要关注Au元素的密度？",
        "Which is more valuable, Gold or Platinum?",
        "Can I invest in Au and Ag?",
    ],
    "特殊情况": [
        "纯金和AU元素的区别",
        "Au元素可以用于催化吗？",
        "哪些国家的货币用Ag元素做币？",
        "Is Gold a good conductor of electricity?",
        "How is gold extracted from ore?",
    ]
}

def print_title(title: str) -> None:
    """打印格式化的标题"""
    print("\n" + "=" * 60)
    print(f" {title} ".center(60, "="))
    print("=" * 60)

def test_agent_selection(query: str, use_llm: bool = False) -> Dict[str, Any]:
    """
    测试代理选择逻辑，返回详细的分析结果
    
    Args:
        query: 要分析的用户查询
        use_llm: 是否使用大模型分析
        
    Returns:
        包含分析结果的字典
    """
    start_time = time.time()
    
    # 1. 先进行关键词匹配分析
    logger.info(f"分析查询: '{query}'")
    kw_result, kw_confidence = analyze_request_by_keywords(query, logger)
    kw_time = time.time() - start_time
    
    # 2. 如果需要，执行大模型分析
    llm_result = None
    llm_time = 0
    if use_llm:
        try:
            llm_start = time.time()
            import asyncio
            llm_result = asyncio.run(analyze_request(query))
            llm_time = time.time() - llm_start
        except Exception as e:
            logger.error(f"大模型分析失败: {str(e)}")
            llm_result = "error"
    
    total_time = time.time() - start_time
    
    # 3. 决定最终结果
    if llm_result is not None and llm_result != "error":
        if kw_result != llm_result and kw_confidence < 0.65:
            final_result = llm_result
            decision_method = "LLM (置信度优先)"
        elif kw_result != llm_result and kw_confidence >= 0.65:
            final_result = kw_result
            decision_method = "关键词 (高置信)"
        else:
            final_result = kw_result
            decision_method = "一致结果"
    else:
        final_result = kw_result
        decision_method = "纯关键词"
    
    # 4. 构建并返回结果
    result = {
        "query": query,
        "keyword_result": kw_result,
        "keyword_confidence": kw_confidence,
        "keyword_time": kw_time,
        "llm_result": llm_result,
        "llm_time": llm_time,
        "final_result": final_result,
        "decision_method": decision_method,
        "total_time": total_time,
        "cached": False  # 当从缓存获取结果时会被设为True
    }
    
    # 检查是否使用了缓存
    cache_entry = query_cache.get(query)
    if cache_entry and ("keyword_result" in cache_entry or "llm_result" in cache_entry):
        result["cached"] = True
    
    return result

def run_batch_test(test_set: List[str], use_llm: bool = False) -> List[Dict[str, Any]]:
    """
    运行批量测试
    
    Args:
        test_set: 要测试的查询列表
        use_llm: 是否使用大模型分析
        
    Returns:
        测试结果列表
    """
    results = []
    for i, query in enumerate(test_set):
        print(f"[{i+1}/{len(test_set)}] 测试: '{query}'")
        result = test_agent_selection(query, use_llm)
        results.append(result)
        
        # 打印简短结果
        if result["cached"]:
            cache_status = "✓(缓存)"
        else:
            cache_status = "✕(新分析)"
            
        kw_confidence = f"{result['keyword_confidence']:.1%}"
        
        if use_llm and result["llm_result"] != "error":
            print(f"  关键词结果: {result['keyword_result']} (置信度: {kw_confidence})")
            print(f"  大模型结果: {result['llm_result']}")
            print(f"  最终结果: {result['final_result']} (方法: {result['decision_method']})")
        else:
            print(f"  结果: {result['keyword_result']} (置信度: {kw_confidence})")
            
        print(f"  耗时: {result['total_time']:.3f}秒, 缓存: {cache_status}")
        print()
    
    return results

def display_test_results(results: List[Dict[str, Any]], detailed: bool = False) -> None:
    """
    展示测试结果
    
    Args:
        results: 测试结果列表
        detailed: 是否显示详细结果
    """
    if not results:
        print("没有测试结果可显示")
        return
        
    # 准备表格数据
    table_data = []
    for result in results:
        confidence = f"{result['keyword_confidence']:.1%}"
        
        if "llm_result" in result and result["llm_result"]:
            llm_result = result["llm_result"]
            if result['keyword_result'] == llm_result:
                agreement = "✓"
            else:
                agreement = "✕"
        else:
            llm_result = "-"
            agreement = "-"
            
        if result["cached"]:
            cache_status = "是"
        else:
            cache_status = "否"
            
        row = [
            result["query"][:30] + "..." if len(result["query"]) > 30 else result["query"],
            result["keyword_result"],
            confidence,
            llm_result,
            agreement,
            result["final_result"],
            f"{result['total_time']:.3f}s",
            cache_status
        ]
        table_data.append(row)
    
    # 打印表格
    headers = ["查询", "关键词结果", "置信度", "大模型结果", "一致性", "最终结果", "耗时", "使用缓存"]
    print(tabulate(table_data, headers=headers, tablefmt="pretty"))
    
    # 计算统计信息
    total = len(results)
    currency_count = sum(1 for r in results if r["final_result"] == "currency")
    element_count = sum(1 for r in results if r["final_result"] == "element")
    cached_count = sum(1 for r in results if r["cached"])
    
    if "llm_result" in results[0] and results[0]["llm_result"]:
        agreement_count = sum(1 for r in results 
                            if r["llm_result"] and r["keyword_result"] == r["llm_result"])
        agreement_rate = agreement_count / total
        print(f"\n大模型和关键词分析一致性: {agreement_count}/{total} ({agreement_rate:.1%})")
    
    avg_time = sum(r["total_time"] for r in results) / total
    
    print(f"\n统计信息:")
    print(f"- 总查询数: {total}")
    print(f"- 路由到货币代理: {currency_count} ({currency_count/total:.1%})")
    print(f"- 路由到元素代理: {element_count} ({element_count/total:.1%})")
    print(f"- 使用缓存查询: {cached_count} ({cached_count/total:.1%})")
    print(f"- 平均处理时间: {avg_time:.3f}秒")
    
    if detailed:
        print_title("详细分析")
        for result in results:
            print(f"查询: '{result['query']}'")
            print(f"- 关键词分析结果: {result['keyword_result']} (置信度: {result['keyword_confidence']:.1%})")
            if "llm_result" in result and result["llm_result"]:
                print(f"- 大模型分析结果: {result['llm_result']}")
            print(f"- 最终决策: {result['final_result']} (方法: {result.get('decision_method', '关键词')})")
            print(f"- 处理时间: {result['total_time']:.3f}秒 (关键词: {result['keyword_time']:.3f}秒)")
            if "llm_time" in result and result["llm_time"] > 0:
                print(f"  大模型: {result['llm_time']:.3f}秒")
            print(f"- 使用缓存: {'是' if result['cached'] else '否'}")
            print()
            
def visualize_results(results: List[Dict[str, Any]], filename: str = None) -> None:
    """
    可视化测试结果
    
    Args:
        results: 测试结果列表
        filename: 保存图表的文件名，如果为None则显示图表
    """
    # 准备数据
    categories = ["currency", "element"]
    counts = [
        sum(1 for r in results if r["final_result"] == "currency"),
        sum(1 for r in results if r["final_result"] == "element")
    ]
    
    # 创建饼图
    plt.figure(figsize=(10, 6))
    
    # 第一个子图 - 代理选择分布
    plt.subplot(1, 2, 1)
    plt.pie(counts, labels=["货币代理", "元素代理"], autopct='%1.1f%%',
            colors=['#66b3ff', '#99ff99'], startangle=90)
    plt.title("代理选择分布")
    
    # 第二个子图 - 置信度分布
    plt.subplot(1, 2, 2)
    confidences = [r["keyword_confidence"] for r in results]
    plt.hist(confidences, bins=10, range=(0, 1), color='#ff9999', edgecolor='black')
    plt.title("关键词分析置信度分布")
    plt.xlabel("置信度")
    plt.ylabel("查询数量")
    
    plt.tight_layout()
    
    if filename:
        plt.savefig(filename)
        print(f"图表已保存到 {filename}")
    else:
        plt.show()

def cache_info() -> None:
    """显示缓存统计信息"""
    info = query_cache.info()
    print("\n缓存统计信息:")
    print(f"- 当前条目数: {info['size']}")
    print(f"- 活跃条目数: {info['active_entries']}")
    print(f"- 最大条目数: {info['max_size']}")
    print(f"- 过期时间: {info['ttl']}秒")

def manage_cache(action: str) -> None:
    """
    管理缓存
    
    Args:
        action: 要执行的操作 ('clear'=清空缓存)
    """
    if action == "clear":
        query_cache.clear()
        print("缓存已清空")
    else:
        print(f"未知的缓存操作: {action}")

def detailed_analysis(query: str) -> None:
    """
    对单个查询进行详细分析
    
    Args:
        query: 要分析的用户查询
    """
    print_title(f"详细分析: '{query}'")
    
    # 1. 执行关键词分析
    print("执行关键词分析...")
    kw_result, kw_confidence = analyze_request_by_keywords(query, logger)
    print(f"关键词分析结果: {kw_result} (置信度: {kw_confidence:.1%})")
    
    # 检查缓存
    cache_entry = query_cache.get(query)
    if cache_entry:
        print("\n缓存内容:")
        for k, v in cache_entry.items():
            if k == "matched_currency_keywords" or k == "matched_element_keywords":
                if v:
                    keywords = [f"{kw}({weight})" for kw, weight in v.items()]
                    print(f"- {k}: {', '.join(keywords)}")
            elif k == "special_case_analysis":
                if v:
                    print(f"- {k}:")
                    for term, analysis in v.items():
                        print(f"  - {term}: {analysis}")
            else:
                print(f"- {k}: {v}")
    
    # 2. 检查特殊情况
    special_cases = ['gold', 'silver', '黄金', '白银', 'au', 'ag', 'pt', 'platinum', '铂']
    detected_specials = []
    for case in special_cases:
        if case in query.lower():
            detected_specials.append(case)
    
    if detected_specials:
        print("\n检测到特殊/歧义术语:")
        for term in detected_specials:
            context_result = analyze_ambiguous_term_context(query, term, logger)
            print(f"- '{term}' 上下文分析结果: {context_result}")

    # 3. 尝试大模型分析
    try:
        print("\n执行大模型分析...")
        import asyncio
        llm_result = asyncio.run(analyze_request(query))
        print(f"大模型分析结果: {llm_result}")
        
        # 4. 整合结果
        if kw_result != llm_result:
            if kw_confidence < 0.65:
                final_result = llm_result
                decision_method = "LLM (置信度优先)"
                print("\n分析结果不一致，大模型结果优先 (关键词置信度低)")
            else:
                final_result = kw_result
                decision_method = "关键词 (高置信)"
                print("\n分析结果不一致，关键词结果优先 (关键词置信度高)")
        else:
            final_result = kw_result
            decision_method = "一致结果"
            print("\n分析结果一致")
            
        print(f"\n最终决策: {final_result} (方法: {decision_method})")
        
    except Exception as e:
        print(f"\n大模型分析失败: {str(e)}")
        print(f"最终决策: {kw_result} (方法: 关键词 (LLM失败))")

def generate_report(results: List[Dict[str, Any]], output_path: str) -> None:
    """
    生成性能报告
    
    Args:
        results: 测试结果列表
        output_path: 保存报告的路径
    """
    # 创建报告目录
    if not os.path.exists(output_path):
        os.makedirs(output_path)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = os.path.join(output_path, f"a2a_report_{timestamp}.html")
    
    # 计算统计数据
    total = len(results)
    currency_count = sum(1 for r in results if r["final_result"] == "currency")
    element_count = sum(1 for r in results if r["final_result"] == "element")
    cached_count = sum(1 for r in results if r["cached"])
    avg_time = sum(r["total_time"] for r in results) / total if total > 0 else 0
    
    # 计算一致性
    agreement_count = 0
    if results and "llm_result" in results[0] and results[0]["llm_result"]:
        agreement_count = sum(1 for r in results 
                            if r["llm_result"] and r["keyword_result"] == r["llm_result"])
    
    # 生成图表
    chart_file = os.path.join(output_path, f"a2a_chart_{timestamp}.png")
    visualize_results(results, chart_file)
    
    # 创建HTML报告
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>A2A智能代理系统性能报告</title>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; margin: 0; padding: 20px; }}
            h1, h2 {{ color: #333; }}
            table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
            th, td {{ padding: 12px 15px; border-bottom: 1px solid #ddd; text-align: left; }}
            th {{ background-color: #f2f2f2; }}
            tr:hover {{ background-color: #f5f5f5; }}
            .stats {{ display: flex; flex-wrap: wrap; margin: 20px 0; }}
            .stat-card {{ background: #f9f9f9; border-radius: 5px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); 
                        margin: 10px; padding: 15px; flex: 1; min-width: 200px; }}
            .chart {{ text-align: center; margin: 20px 0; }}
            .chart img {{ max-width: 100%; height: auto; }}
        </style>
    </head>
    <body>
        <h1>A2A智能代理系统性能报告</h1>
        <p>生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
        
        <h2>测试概述</h2>
        <div class="stats">
            <div class="stat-card">
                <h3>总查询数</h3>
                <p>{total}</p>
            </div>
            <div class="stat-card">
                <h3>货币代理</h3>
                <p>{currency_count} ({currency_count/total:.1%})</p>
            </div>
            <div class="stat-card">
                <h3>元素代理</h3>
                <p>{element_count} ({element_count/total:.1%})</p>
            </div>
            <div class="stat-card">
                <h3>缓存命中</h3>
                <p>{cached_count} ({cached_count/total:.1%})</p>
            </div>
            <div class="stat-card">
                <h3>平均处理时间</h3>
                <p>{avg_time:.3f}秒</p>
            </div>
    """
    
    # 添加一致性数据
    if "llm_result" in results[0] and results[0]["llm_result"]:
        agreement_rate = agreement_count / total if total > 0 else 0
        html_content += f"""
            <div class="stat-card">
                <h3>LLM与关键词一致性</h3>
                <p>{agreement_count}/{total} ({agreement_rate:.1%})</p>
            </div>
        """
    
    html_content += """
        </div>
        
        <h2>可视化分析</h2>
        <div class="chart">
            <img src="{}" alt="代理选择分析图表">
        </div>
    """.format(os.path.basename(chart_file))
    
    # 添加详细结果表格
    html_content += """
        <h2>测试结果详情</h2>
        <table>
            <tr>
                <th>查询</th>
                <th>关键词结果</th>
                <th>置信度</th>
                <th>大模型结果</th>
                <th>最终结果</th>
                <th>处理时间</th>
                <th>缓存</th>
            </tr>
    """
    
    for r in results:
        confidence = f"{r['keyword_confidence']:.1%}"
        llm_result = r.get("llm_result", "-")
        cached = "是" if r.get("cached", False) else "否"
        
        html_content += f"""
            <tr>
                <td>{r['query']}</td>
                <td>{r['keyword_result']}</td>
                <td>{confidence}</td>
                <td>{llm_result}</td>
                <td>{r['final_result']}</td>
                <td>{r['total_time']:.3f}秒</td>
                <td>{cached}</td>
            </tr>
        """
    
    html_content += """
        </table>
    </body>
    </html>
    """
    
    # 写入HTML文件
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    print(f"报告已生成: {report_file}")

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='A2A智能代理系统管理工具')
    
    subparsers = parser.add_subparsers(dest='command', help='命令')
    
    # test命令
    test_parser = subparsers.add_parser('test', help='测试代理选择逻辑')
    test_parser.add_argument('--query', '-q', help='单个测试查询')
    test_parser.add_argument('--file', '-f', help='包含测试查询的文件，每行一个查询')
    test_parser.add_argument('--preset', '-p', choices=TEST_CASES.keys(), help='使用预设测试集')
    test_parser.add_argument('--all-presets', '-a', action='store_true', help='使用所有预设测试集')
    test_parser.add_argument('--llm', action='store_true', help='使用大模型分析')
    test_parser.add_argument('--detailed', '-d', action='store_true', help='显示详细结果')
    test_parser.add_argument('--report', '-r', help='生成HTML报告并保存到指定目录')
    
    # analyze命令
    analyze_parser = subparsers.add_parser('analyze', help='详细分析单个查询')
    analyze_parser.add_argument('query', help='要分析的查询')
    
    # cache命令
    cache_parser = subparsers.add_parser('cache', help='缓存管理')
    cache_parser.add_argument('action', choices=['info', 'clear'], help='缓存操作')
    
    args = parser.parse_args()
    
    # 处理命令
    if args.command == 'test':
        # 确定测试集
        test_queries = []
        
        if args.query:
            test_queries = [args.query]
        elif args.file:
            try:
                with open(args.file, 'r', encoding='utf-8') as f:
                    test_queries = [line.strip() for line in f if line.strip()]
            except Exception as e:
                print(f"读取文件失败: {str(e)}")
                return
        elif args.preset:
            test_queries = TEST_CASES[args.preset]
        elif args.all_presets:
            for category, queries in TEST_CASES.items():
                print_title(f"测试类别: {category}")
                test_queries.extend(queries)
        else:
            parser.print_help()
            return
        
        if test_queries:
            print_title("代理选择测试")
            results = run_batch_test(test_queries, args.llm)
            display_test_results(results, args.detailed)
            
            if args.report:
                generate_report(results, args.report)
            
    elif args.command == 'analyze':
        detailed_analysis(args.query)
        
    elif args.command == 'cache':
        if args.action == 'info':
            cache_info()
        else:
            manage_cache(args.action)
    
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
