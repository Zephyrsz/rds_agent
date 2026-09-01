"""
Basic Query Example

演示如何使用 RDS Agent 进行简单查询
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

# 需要配置 OpenAI API Key
# export OPENAI_API_KEY=your_api_key
from langchain_openai import ChatOpenAI


def main():
    """运行基本查询示例"""

    print("=" * 60)
    print("RDS Agent - 基本查询示例")
    print("=" * 60)
    print()

    # 1. 创建示例数据库
    print("步骤 1: 创建示例数据库...")
    db_adapter = create_sample_database(":memory:")
    print()

    # 2. 初始化核心组件
    print("步骤 2: 初始化核心组件...")

    config_dir = project_root / "config"

    # 数据库目录
    catalog = DatabaseCatalog(config_dir)
    print(f"  ✓ 加载 {len(catalog.tables)} 个表定义")

    # 语义层
    semantic_layer = SemanticLayer(config_dir)
    print(f"  ✓ 加载 {len(semantic_layer.metrics)} 个指标定义")
    print(f"  ✓ 加载 {len(semantic_layer.dimensions)} 个维度定义")

    # 查询计划器
    planner = QueryPlanner(semantic_layer, catalog)

    # LLM（用于 SQL 生成）
    llm = ChatOpenAI(
        model="gpt-4",
        temperature=0,
    )

    # SQL 生成器
    generator = SQLGenerator(
        llm=llm,
        catalog=catalog,
        semantic_layer=semantic_layer,
        examples=[]  # 可以加载 examples.yaml
    )

    # SQL 安全网关
    guard = SQLGuard(
        allowed_tables=set(catalog.get_all_tables()),
        max_result_rows=10000,
        default_limit=1000,
        enforce_limit=True,
    )
    print("  ✓ SQL 安全网关已配置")

    # 查询执行器
    executor = QueryExecutor(
        db_connection=db_adapter.connection,
        timeout_seconds=30,
        max_result_rows=10000,
        enable_audit=True,
    )

    # 结果验证器
    validator = ResultValidator(semantic_layer)

    # 答案组织器
    composer = AnswerComposer(llm=llm)

    print()

    # 3. 创建工作流
    print("步骤 3: 创建 LangGraph 工作流...")
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
    print("  ✓ 工作流创建完成")
    print()

    # 4. 执行查询
    questions = [
        "最近一个月的总销售额是多少？",
        "华东地区的订单数有多少？",
        "各个地区的销售额分别是多少？",
    ]

    for i, question in enumerate(questions, 1):
        print("=" * 60)
        print(f"查询 {i}: {question}")
        print("=" * 60)

        try:
            # 执行工作流
            print("\n执行工作流...")
            final_state = workflow.run(question)

            # 显示结果
            if final_state.get("error"):
                print(f"\n❌ 错误: {final_state['error']}")
            elif final_state.get("answer"):
                print("\n✓ 查询成功!")
                print("\n生成的 SQL:")
                print("-" * 60)
                print(final_state.get("sql", "未生成"))
                print("-" * 60)

                query_result = final_state.get("query_result", {})
                print(f"\n返回行数: {query_result.get('row_count', 0)}")
                print(f"执行时间: {query_result.get('execution_time', 0):.3f} 秒")

                # 显示结果数据（前几行）
                rows = query_result.get("rows", [])
                if rows:
                    print("\n结果数据:")
                    print("-" * 60)
                    for row in rows[:5]:
                        print(row)
                    if len(rows) > 5:
                        print(f"... (共 {len(rows)} 行)")
                    print("-" * 60)
            else:
                print("\n⚠️  未生成答案")

            # 显示审计信息
            audit_trail = final_state.get("audit_trail", [])
            print(f"\n审计: 共 {len(audit_trail)} 个步骤")

        except Exception as e:
            print(f"\n❌ 异常: {str(e)}")
            import traceback
            traceback.print_exc()

        print()

    # 5. 显示统计信息
    print("=" * 60)
    print("执行统计")
    print("=" * 60)
    stats = executor.get_statistics()
    print(f"总查询数: {stats['total_queries']}")
    print(f"成功查询: {stats['successful_queries']}")
    print(f"失败查询: {stats['failed_queries']}")
    print(f"成功率: {stats['success_rate']:.1%}")
    print(f"平均执行时间: {stats['average_execution_time']:.3f} 秒")
    print()

    # 清理
    db_adapter.close()
    print("✓ 数据库连接已关闭")


if __name__ == "__main__":
    # 检查环境变量
    if not os.getenv("OPENAI_API_KEY"):
        print("错误: 请设置 OPENAI_API_KEY 环境变量")
        print("export OPENAI_API_KEY=your_api_key")
        sys.exit(1)

    main()
