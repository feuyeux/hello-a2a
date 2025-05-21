# 添加这个函数到 __main__.py
@click.command(name='test')
@click.option('--query', '-q', help='要测试的单个查询')
@click.option('--all', '-a', is_flag=True, help='测试所有预定义的测试用例')
def test_agent_selection(query, all):
    """测试代理选择逻辑"""
    # 预定义的测试用例
    test_cases = [
        # 明确货币相关的查询
        "什么是美元与欧元的汇率？",
        "100美元可以换多少人民币？",
        "我想兑换一些日元",
        "最近比特币的价格怎么样？",
        "英镑和欧元的汇率是多少？",
        
        # 明确元素相关的查询
        "氢元素的原子量是多少？",
        "钠元素在周期表中的位置",
        "Fe是什么元素？",
        "碳元素有几种同位素？",
        "氧气的化学性质是什么？",
        
        # 模糊查询，可能是货币也可能是元素
        "黄金的价格是多少？",
        "黄金是第几周期的元素？",
        "银的导电性如何？", 
        "银的市场价格是多少？",
        "金和银哪个更值钱？",
        "金和银在元素周期表中的位置",
        
        # 极具挑战性的模糊查询
        "铂金和黄金哪个更稀有？",
        "Au的原子量和价格",
        "帮我查一下金的信息",
    ]
    
    # 配置本地测试日志器
    test_logger = logging.getLogger('agent_selection_test')
    test_logger.setLevel(logging.INFO)
    # 确保日志显示在控制台
    if not test_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(message)s'))
        test_logger.addHandler(handler)
    
    print("代理选择测试")
    print("=" * 50)
    
    if query:
        # 测试单个查询
        print(f"\n测试查询: '{query}'")
        agent_type, confidence = analyze_request_by_keywords(query, test_logger)
        print(f"分析结果: {agent_type} (置信度: {confidence:.1%})")
    
    elif all:
        # 测试所有预定义用例
        for i, test_query in enumerate(test_cases):
            print(f"\n[{i+1}/{len(test_cases)}] 测试查询: '{test_query}'")
            agent_type, confidence = analyze_request_by_keywords(test_query, test_logger)
            print(f"分析结果: {agent_type} (置信度: {confidence:.1%})")
    else:
        print("请指定 --query 参数测试单个查询，或 --all 测试所有预定义用例")
    
if __name__ == '__main__':
    # 添加子命令组
    cli = click.Group()
    cli.add_command(main)
    cli.add_command(test_agent_selection)
    
    cli()
