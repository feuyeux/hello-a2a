#!/usr/bin/env python3
"""
A2A智能代理系统 - 性能监控与评估工具

此工具用于:
1. 收集和记录代理选择系统的性能指标
2. 评估代理选择系统的准确度和置信度
3. 生成性能趋势报告和可视化结果
"""

import os
import sys
import time
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from tabulate import tabulate

# 配置日志
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 性能指标存储路径
METRICS_DIR = "metrics"
METRICS_FILE = os.path.join(METRICS_DIR, "agent_selection_metrics.json")

# 默认测试用例集
DEFAULT_TEST_CASES = [
    {"query": "美元与欧元的汇率是多少?", "expected": "currency", "category": "货币明确"},
    {"query": "日元兑换人民币的汇率", "expected": "currency", "category": "货币明确"},
    {"query": "氢元素的原子量是多少?", "expected": "element", "category": "元素明确"},
    {"query": "铁元素在周期表中的位置", "expected": "element", "category": "元素明确"},
    {"query": "黄金价格最近怎么样", "expected": "currency", "category": "歧义-投资"},
    {"query": "AU元素的电子结构", "expected": "element", "category": "歧义-科学"},
    {"query": "白银的市场行情", "expected": "currency", "category": "歧义-投资"},
    {"query": "AG是什么元素", "expected": "element", "category": "歧义-科学"},
    {"query": "黄金的原子序数", "expected": "element", "category": "混合语境"},
    {"query": "Au的投资价值", "expected": "currency", "category": "混合语境"}
]

class PerformanceMetrics:
    """性能指标收集和管理类"""
    
    def __init__(self, metrics_file: str = METRICS_FILE):
        """
        初始化性能指标管理器
        
        Args:
            metrics_file: 性能指标存储文件路径
        """
        self.metrics_file = metrics_file
        self._ensure_metrics_dir()
        self.metrics = self._load_metrics()
    
    def _ensure_metrics_dir(self) -> None:
        """确保指标目录存在"""
        os.makedirs(os.path.dirname(self.metrics_file), exist_ok=True)
    
    def _load_metrics(self) -> List[Dict[str, Any]]:
        """加载现有性能指标数据"""
        if os.path.exists(self.metrics_file):
            try:
                with open(self.metrics_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"加载性能指标失败: {str(e)}")
                return []
        return []
    
    def _save_metrics(self) -> None:
        """保存性能指标数据"""
        try:
            with open(self.metrics_file, 'w', encoding='utf-8') as f:
                json.dump(self.metrics, f, ensure_ascii=False, indent=2)
            logger.info(f"性能指标已保存至 {self.metrics_file}")
        except Exception as e:
            logger.error(f"保存性能指标失败: {str(e)}")
    
    def add_test_run(self, results: List[Dict[str, Any]], 
                   version: str = "current", notes: str = "") -> None:
        """
        添加测试运行结果
        
        Args:
            results: 测试结果列表
            version: 系统版本标识
            notes: 测试说明
        """
        # 计算统计数据
        total_cases = len(results)
        correct_cases = sum(1 for r in results if r.get("correct", False))
        accuracy = correct_cases / total_cases if total_cases > 0 else 0
        
        # 按类别计算准确率
        categories = {}
        for result in results:
            category = result.get("category", "未分类")
            if category not in categories:
                categories[category] = {"total": 0, "correct": 0}
            
            categories[category]["total"] += 1
            if result.get("correct", False):
                categories[category]["correct"] += 1
        
        for cat, stats in categories.items():
            if stats["total"] > 0:
                stats["accuracy"] = stats["correct"] / stats["total"]
            else:
                stats["accuracy"] = 0
        
        # 计算平均置信度
        avg_confidence = sum(r.get("confidence", 0) for r in results) / total_cases if total_cases > 0 else 0
        
        # 计算置信度分布
        confidence_ranges = [0, 0.6, 0.7, 0.8, 0.9, 1.0]
        confidence_bins = {f"{a*100:.0f}-{b*100:.0f}%": 0 for a, b in zip(confidence_ranges[:-1], confidence_ranges[1:])}
        
        for result in results:
            confidence = result.get("confidence", 0)
            for i, (lower, upper) in enumerate(zip(confidence_ranges[:-1], confidence_ranges[1:])):
                if lower <= confidence < upper:
                    bin_key = f"{lower*100:.0f}-{upper*100:.0f}%"
                    confidence_bins[bin_key] += 1
                    break
        
        # 创建指标记录
        metric_record = {
            "timestamp": datetime.now().isoformat(),
            "version": version,
            "notes": notes,
            "total_cases": total_cases,
            "correct_cases": correct_cases,
            "accuracy": accuracy,
            "avg_confidence": avg_confidence,
            "categories": categories,
            "confidence_distribution": confidence_bins,
            "results": results  # 保存详细结果
        }
        
        # 添加到指标列表
        self.metrics.append(metric_record)
        
        # 保存更新后的指标
        self._save_metrics()
        
        logger.info(f"已添加新的测试运行记录 - 准确率: {accuracy:.1%}, 用例数: {total_cases}")
    
    def get_recent_metrics(self, days: int = 30) -> List[Dict[str, Any]]:
        """
        获取最近一段时间的性能指标
        
        Args:
            days: 返回最近几天的指标
            
        Returns:
            最近的性能指标列表
        """
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
        return [m for m in self.metrics if m["timestamp"] >= cutoff_date]
    
    def get_trend_data(self) -> Tuple[List[datetime], List[float], List[float]]:
        """
        获取性能趋势数据
        
        Returns:
            (时间戳列表, 准确率列表, 置信度列表)
        """
        dates = []
        accuracies = []
        confidences = []
        
        for record in self.metrics:
            try:
                timestamp = datetime.fromisoformat(record["timestamp"])
                accuracy = record["accuracy"]
                confidence = record["avg_confidence"]
                
                dates.append(timestamp)
                accuracies.append(accuracy)
                confidences.append(confidence)
            except (ValueError, KeyError):
                continue
                
        return dates, accuracies, confidences
    
    def analyze_error_patterns(self, 
                             record_index: int = -1) -> Dict[str, Any]:
        """
        分析错误模式
        
        Args:
            record_index: 要分析的记录索引，默认为最新记录
            
        Returns:
            错误模式分析结果
        """
        if not self.metrics:
            return {"error": "没有可用的指标记录"}
        
        try:
            record = self.metrics[record_index]
            results = record.get("results", [])
            
            # 筛选错误用例
            error_cases = [r for r in results if not r.get("correct", True)]
            
            # 分析错误类型
            error_types = {}
            for case in error_cases:
                expected = case.get("expected", "unknown")
                result = case.get("result", "unknown")
                error_key = f"{expected} -> {result}"
                
                if error_key not in error_types:
                    error_types[error_key] = []
                
                error_types[error_key].append(case)
            
            # 对错误分类
            categorized_errors = {}
            for case in error_cases:
                category = case.get("category", "未分类")
                if category not in categorized_errors:
                    categorized_errors[category] = []
                
                categorized_errors[category].append(case)
            
            # 计算每个类别的错误率
            category_error_rates = {}
            for category, errors in categorized_errors.items():
                # 查找该类别的总用例数
                total_in_category = sum(1 for r in results if r.get("category") == category)
                if total_in_category > 0:
                    error_rate = len(errors) / total_in_category
                else:
                    error_rate = 0
                category_error_rates[category] = {
                    "total": total_in_category,
                    "errors": len(errors),
                    "error_rate": error_rate
                }
                
            return {
                "total_errors": len(error_cases),
                "error_rate": len(error_cases) / len(results) if results else 0,
                "error_types": {k: len(v) for k, v in error_types.items()},
                "error_examples": {k: [e.get("query") for e in v[:3]] for k, v in error_types.items()},
                "category_error_rates": category_error_rates
            }
        except Exception as e:
            return {"error": f"分析错误模式失败: {str(e)}"}

def run_tests(test_cases: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """
    运行测试用例
    
    Args:
        test_cases: 测试用例列表，如果为None则使用默认测试集
        
    Returns:
        测试结果列表
    """
    if test_cases is None:
        test_cases = DEFAULT_TEST_CASES
    
    try:
        # 导入代理选择逻辑
        from __main__ import analyze_request_by_keywords
        
        results = []
        for i, case in enumerate(test_cases):
            query = case["query"]
            expected = case["expected"]
            
            print(f"\r测试进度: [{i+1}/{len(test_cases)}]", end="", flush=True)
            
            # 计时并执行分析
            start_time = time.time()
            result, confidence = analyze_request_by_keywords(query, logger)
            elapsed_time = time.time() - start_time
            
            # 检查结果是否正确
            is_correct = (result == expected)
            
            results.append({
                "query": query,
                "expected": expected,
                "result": result,
                "confidence": confidence,
                "correct": is_correct,
                "time": elapsed_time,
                "category": case.get("category", "未分类")
            })
            
        return results
        
    except ImportError:
        logger.error("无法导入代理选择逻辑，请确保在正确的环境中运行")
        return []
    except Exception as e:
        logger.error(f"测试运行失败: {str(e)}")
        return []

def generate_report(metrics_manager: PerformanceMetrics, 
                   run_index: int = -1, 
                   output_file: Optional[str] = None) -> None:
    """
    生成性能报告
    
    Args:
        metrics_manager: 性能指标管理器
        run_index: 要报告的运行索引，默认为最新
        output_file: 输出文件路径，如果为None则仅打印到控制台
    """
    if not metrics_manager.metrics:
        print("没有可用的性能指标记录")
        return
    
    try:
        # 获取指定的运行记录
        record = metrics_manager.metrics[run_index]
        
        # 格式化时间戳
        timestamp = datetime.fromisoformat(record["timestamp"])
        formatted_time = timestamp.strftime("%Y-%m-%d %H:%M:%S")
        
        # 准备报告文本
        report_text = f"""
A2A 智能代理系统性能报告
=================================
生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
测试运行时间: {formatted_time}
版本: {record["version"]}
{record["notes"]}

总体性能
---------------------------------
总用例数: {record["total_cases"]}
正确分类数: {record["correct_cases"]}
准确率: {record["accuracy"]:.1%}
平均置信度: {record["avg_confidence"]:.1%}

按类别分析
---------------------------------
"""
        
        # 添加类别分析
        categories = record.get("categories", {})
        if categories:
            cat_table = []
            for cat, stats in sorted(categories.items()):
                cat_table.append([
                    cat, 
                    stats["total"],
                    stats["correct"],
                    f"{stats.get('accuracy', 0):.1%}"
                ])
            
            report_text += tabulate(
                cat_table,
                headers=["类别", "用例数", "正确数", "准确率"],
                tablefmt="simple"
            )
        
        # 添加置信度分布
        conf_dist = record.get("confidence_distribution", {})
        if conf_dist:
            report_text += "\n\n置信度分布\n---------------------------------\n"
            conf_table = []
            for range_str, count in sorted(conf_dist.items()):
                conf_table.append([range_str, count])
            
            report_text += tabulate(
                conf_table,
                headers=["置信度范围", "用例数"],
                tablefmt="simple"
            )
        
        # 添加错误分析
        error_analysis = metrics_manager.analyze_error_patterns(run_index)
        if error_analysis and "error" not in error_analysis:
            report_text += "\n\n错误分析\n---------------------------------\n"
            report_text += f"总错误数: {error_analysis['total_errors']}\n"
            report_text += f"错误率: {error_analysis['error_rate']:.1%}\n\n"
            
            # 错误类型
            report_text += "错误类型分布:\n"
            for error_type, count in error_analysis["error_types"].items():
                report_text += f"- {error_type}: {count}个\n"
            
            # 类别错误率
            report_text += "\n类别错误率:\n"
            for category, stats in error_analysis["category_error_rates"].items():
                report_text += f"- {category}: {stats['errors']}/{stats['total']} "
                report_text += f"({stats['error_rate']:.1%})\n"
            
            # 错误示例
            report_text += "\n错误示例:\n"
            for error_type, examples in error_analysis["error_examples"].items():
                report_text += f"- {error_type}:\n"
                for ex in examples:
                    report_text += f"  * '{ex}'\n"
        
        # 输出报告
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(report_text)
            print(f"报告已保存到: {output_file}")
        else:
            print(report_text)
            
    except (IndexError, KeyError) as e:
        print(f"生成报告失败: {str(e)}")

def visualize_trends(metrics_manager: PerformanceMetrics, 
                    output_file: Optional[str] = None) -> None:
    """
    可视化性能趋势
    
    Args:
        metrics_manager: 性能指标管理器
        output_file: 输出文件路径，如果为None则显示图表
    """
    try:
        # 获取趋势数据
        dates, accuracies, confidences = metrics_manager.get_trend_data()
        
        if not dates:
            print("没有足够的数据来生成趋势图")
            return
        
        # 创建图表
        plt.figure(figsize=(12, 6))
        
        # 绘制准确率和置信度曲线
        plt.plot(dates, accuracies, 'b-', label='准确率', marker='o')
        plt.plot(dates, confidences, 'r--', label='平均置信度', marker='s')
        
        # 设置图表格式
        plt.title('A2A智能代理系统性能趋势')
        plt.xlabel('日期')
        plt.ylabel('比率')
        plt.ylim(0, 1)
        plt.grid(True, linestyle='--', alpha=0.7)
        plt.legend()
        
        # 设置日期格式
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        plt.gca().xaxis.set_major_locator(mdates.AutoDateLocator())
        plt.gcf().autofmt_xdate()
        
        # 保存或显示
        if output_file:
            plt.savefig(output_file)
            print(f"趋势图已保存到: {output_file}")
        else:
            plt.show()
            
    except Exception as e:
        print(f"生成趋势图失败: {str(e)}")

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='A2A智能代理系统性能监控与评估工具')
    subparsers = parser.add_subparsers(dest='command', help='命令')
    
    # test命令
    test_parser = subparsers.add_parser('test', help='运行测试并记录性能指标')
    test_parser.add_argument('--file', '-f', help='包含测试用例的JSON文件')
    test_parser.add_argument('--version', '-v', default='current', help='系统版本标识')
    test_parser.add_argument('--notes', '-n', default='', help='测试说明')
    
    # report命令
    report_parser = subparsers.add_parser('report', help='生成性能报告')
    report_parser.add_argument('--index', '-i', type=int, default=-1, 
                              help='要报告的运行索引，默认为最新')
    report_parser.add_argument('--output', '-o', help='报告输出文件')
    
    # trend命令
    trend_parser = subparsers.add_parser('trend', help='显示性能趋势')
    trend_parser.add_argument('--output', '-o', help='趋势图输出文件')
    
    # list命令
    list_parser = subparsers.add_parser('list', help='列出所有测试运行')
    
    args = parser.parse_args()
    
    # 创建性能指标管理器
    metrics_manager = PerformanceMetrics()
    
    if args.command == 'test':
        # 加载测试用例
        test_cases = None
        if args.file:
            try:
                with open(args.file, 'r', encoding='utf-8') as f:
                    test_cases = json.load(f)
            except Exception as e:
                print(f"加载测试用例失败: {str(e)}")
                return
        
        print("=" * 50)
        print(" A2A 智能代理系统性能测试 ")
        print("=" * 50)
        
        # 运行测试
        results = run_tests(test_cases)
        if results:
            print("\n测试完成！")
            
            # 计算统计数据
            total = len(results)
            correct = sum(1 for r in results if r.get("correct", False))
            accuracy = correct / total if total > 0 else 0
            
            print(f"总体准确率: {correct}/{total} ({accuracy:.1%})")
            
            # 记录结果
            metrics_manager.add_test_run(results, args.version, args.notes)
            
    elif args.command == 'report':
        generate_report(metrics_manager, args.index, args.output)
        
    elif args.command == 'trend':
        visualize_trends(metrics_manager, args.output)
        
    elif args.command == 'list':
        if metrics_manager.metrics:
            print("\nA2A系统性能测试记录:")
            print("-" * 60)
            for i, record in enumerate(metrics_manager.metrics):
                try:
                    timestamp = datetime.fromisoformat(record["timestamp"])
                    formatted_time = timestamp.strftime("%Y-%m-%d %H:%M:%S")
                    accuracy = record["accuracy"]
                    cases = record["total_cases"]
                    version = record["version"]
                    notes = record["notes"]
                    
                    print(f"{i}. [{formatted_time}] 版本: {version}, 准确率: {accuracy:.1%}, "
                         f"用例数: {cases}{' - ' + notes if notes else ''}")
                except (KeyError, ValueError):
                    print(f"{i}. [格式错误的记录]")
            print("-" * 60)
        else:
            print("没有性能测试记录")
    
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
