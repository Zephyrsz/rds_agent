"""
Interactive Demo

交互式演示程序，允许用户输入问题并实时查看 Agent 的工作流程
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from adapters.duckdb import create_sample_database
from core import (
    DatabaseCatalog,
    SemanticLayer,
    QueryPlanner,
    SQLGenerator,
    SQLGuard,
    QueryExecutor,
    ResultValidator,
    AnswerComposer,
)
from workflow import DataAgentWorkflow

from langchain_openai import ChatOpenAI


def print_banner():
    """打印欢迎横幅"""
    print()
    print("=" * 70)
    print(" " * 20 + "RDS Agent 交互式演示")
    print("=" * 70)
    print()
    print("这是一个基于 LangGraph 的数据分析 Agent 演示")
    print("您可以用自然语言提问，Agent 会自动生成并执行 SQL 查询")
    print()
    print("示例问题:")
    print("  - 最近一个月的总销售额是多少？")
    print("  - 华东地区的订单数有多少？")
    print("  - 各个地区的销售额分别是多少？")
    print("  - TOP 5 销售额最高的客户")
    print()
    print("输入 'quit' 或 'exit' 退出")
    print("=" * 70)
    print()


def initialize_system():
    """初始化系统"""
    print("正在初始化系统...")

    # 创建示例数据库
    db_adapter = create_sample_database(":memory:")
    print("  ✓ 示例数据库已创建")

    config_dir = project_root / "config"

    # 初始化核心组件
    catalog = DatabaseCatalog(config_dir)
    semantic_layer = SemanticLayer(config_dir)
    planner = QueryPlanner(semantic_layer, catalog)

    llm = ChatOpenAI(model="gpt-4", temperature=0)

    generator = SQLGenerator(
        llm=llm,
        catalog=catalog,
        semantic_layer=semantic_layer,
        examples=[]
    )

    guard = SQLGuard(
        allowed_tables=set(catalog.get_all_tables()),
        max_result_rows=10000,
        default_limit=1000,
        enforce_limit=True,
    )

    executor = QueryExecutor(
        db_connection=db_adapter.connection,
        timeout_seconds=30,
        max_result_rows=10000,
        enable_audit=True,
    )

    validator = ResultValidator(semantic_layer)
    composer = AnswerComposer(llm=llm)

    print("  ✓ 核心组件已初始化")

    # 创建工作流
    workflow = DataAgentWorkflow(
        catalog=catalog,
        semantic_layer=semantic_layer,
        planner=planner,
        generator=generator,
        guard=guard,
        executor=executor,
        validator=validator,
        composer=composer,
    )
    print("  ✓ 工作流已创建")
    print()

    return workflow, db_adapter, executor


def display_result(final_state):
    """显示查询结果"""
    print()
    print("-" * 70)

    if final_state.get("error"):
        print(f"❌ 错误: {final_state['error']}")
        return

    # 显示生成的 SQL
    sql = final_state.get("sql")
    if sql:
        print("生成的 SQL:")
        print(sql)
        print()

    # 显示查询结果
    query_result = final_state.get("query_result", {})

    if not query_result:
        print("⚠️  未获取到查询结果")
        return

    print(f"✓ 查询成功")
    print(f"  - 返回行数: {query_result.get('row_count', 0)}")
    print(f"  - 执行时间: {query_result.get('execution_time', 0):.3f} 秒")
    print()

    # 显示数据
    rows = query_result.get("rows", [])
    if rows:
        print("结果数据:")

        # 计算列宽
        if rows:
            columns = list(rows[0].keys())
            col_widths = {col: len(col) for col in columns}
            for row in rows[:10]:
                for col in columns:
                    col_widths[col] = max(col_widths[col], len(str(row.get(col, ""))))

        # 打印表头
        header = " | ".join(
            col.ljust(col_widths[col]) for col in columns
        )
        print(header)
        print("-" * len(header))

        # 打印数据行（最多10行）
        for row in rows[:10]:
            print(" | ".join(
                str(row.get(col, "")).ljust(col_widths[col]) for col in columns
            ))

        if len(rows) > 10:
            print(f"... (共 {len(rows)} 行，仅显示前 10 行)")

    print("-" * 70)


def main():
    """主函数"""
    # 检查环境变量
    if not os.getenv("OPENAI_API_KEY"):
        print("错误: 请设置 OPENAI_API_KEY 环境变量")
        print("export OPENAI_API_KEY=your_api_key")
        sys.exit(1)

    # 打印欢迎信息
    print_banner()

    # 初始化系统
    workflow, db_adapter, executor = initialize_system()

    # 交互循环
    query_count = 0

    while True:
        try:
            # 获取用户输入
            question = input("您的问题 > ").strip()

            if not question:
                continue

            if question.lower() in ['quit', 'exit', 'q']:
                print("\n再见！")
                break

            # 特殊命令
            if question.lower() == 'stats':
                stats = executor.get_statistics()
                print()
                print("执行统计:")
                print(f"  - 总查询数: {stats['total_queries']}")
                print(f"  - 成功查询: {stats['successful_queries']}")
                print(f"  - 失败查询: {stats['failed_queries']}")
                print(f"  - 成功率: {stats['success_rate']:.1%}")
                print(f"  - 平均执行时间: {stats['average_execution_time']:.3f} 秒")
                continue

            # 执行查询
            query_count += 1
            print(f"\n[查询 {query_count}] 正在处理...")

            final_state = workflow.run(question)

            # 显示结果
            display_result(final_state)

        except KeyboardInterrupt:
            print("\n\n再见！")
            break
        except Exception as e:
            print(f"\n❌ 发生异常: {str(e)}")
            import traceback
            traceback.print_exc()

    # 清理
    print("\n正在清理资源...")
    db_adapter.close()
    print("✓ 完成")


if __name__ == "__main__":
    main()
