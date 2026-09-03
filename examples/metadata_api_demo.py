"""
RDS Agent Metadata API 调用示例

本文件展示在真实查询场景中，各个节点如何调用 metadata API。
"""

from pathlib import Path
from typing import Dict, Any, List

# 假设我们已经初始化了组件
# config_dir = Path("config")
# catalog = DatabaseCatalog(config_dir)
# semantic_layer = SemanticLayer(config_dir)


# ====================
# 场景：用户提问 "最近一个月华东地区的销售额是多少？"
# ====================

def example_full_flow():
    """完整流程示例"""

    question = "最近一个月华东地区的销售额是多少？"

    print("=" * 80)
    print(f"用户问题: {question}")
    print("=" * 80)
    print()

    # ========== 节点 1: classify_request ==========
    print("【节点 1】classify_request - 分类请求")
    print("-" * 80)

    # API 调用 1.1: 提取意图
    print("API 调用: semantic_layer.extract_intent(question)")
    intent = semantic_layer.extract_intent(question)

    print(f"返回结果:")
    print(f"  question_type: {intent['question_type']}")
    print(f"  metrics: {intent['metrics']}")
    print(f"  dimensions: {intent['dimensions']}")
    print(f"  time_range: {intent['time_range']}")
    print(f"  filters: {intent['filters']}")
    print()

    # 内部访问的 metadata:
    print("内部 metadata 访问:")
    print(f"  - semantic_layer.metrics (所有指标定义)")
    print(f"  - semantic_layer.dimensions (所有维度定义)")
    print(f"  - semantic_layer.terms (业务术语字典)")
    print()


    # ========== 节点 2: resolve_semantics ==========
    print("【节点 2】resolve_semantics - 解析语义")
    print("-" * 80)

    # API 调用 2.1: 解析指标
    print("API 调用: semantic_layer.resolve_metric('sales_amount')")
    metric_def = semantic_layer.resolve_metric("sales_amount")

    print(f"返回结果:")
    print(f"  name: {metric_def.name}")
    print(f"  display_name: {metric_def.display_name}")
    print(f"  expression: {metric_def.expression}")
    print(f"  tables: {metric_def.tables}")
    print(f"  filters: {metric_def.filters}")
    print()

    # API 调用 2.2: 解析维度
    print("API 调用: semantic_layer.resolve_dimension('region')")
    dim_def = semantic_layer.resolve_dimension("region")

    print(f"返回结果:")
    print(f"  name: {dim_def.name}")
    print(f"  display_name: {dim_def.display_name}")
    print(f"  table: {dim_def.table}")
    print(f"  column: {dim_def.column}")
    print(f"  mappings: {dim_def.mappings}")
    print()

    # API 调用 2.3: 解析业务术语
    print("API 调用: semantic_layer.resolve_business_term('华东')")
    region_values = semantic_layer.resolve_business_term("华东")

    print(f"返回结果: {region_values}")
    print(f"  '华东' → {region_values}")
    print()

    # API 调用 2.4: 解析时间范围
    print("API 调用: semantic_layer.resolve_time_range('最近一个月')")
    time_spec = semantic_layer.resolve_time_range("最近一个月")

    print(f"返回结果:")
    print(f"  start_date: {time_spec['start_date']}")
    print(f"  end_date: {time_spec['end_date']}")
    print(f"  column: {time_spec['column']}")
    print()


    # ========== 节点 3: select_schema ==========
    print("【节点 3】select_schema - 选择 Schema")
    print("-" * 80)

    # API 调用 3.1: 检索相关表
    required_tables = ["orders", "order_items", "regions"]
    print(f"API 调用: catalog.search_schema(required_tables={required_tables})")
    relevant_tables = catalog.search_schema(required_tables=required_tables)

    print(f"返回结果: {relevant_tables}")
    print()

    # API 调用 3.2: 获取表详细信息
    print("API 调用: catalog.get_table('orders')")
    orders_table = catalog.get_table("orders")

    print(f"返回结果:")
    print(f"  name: {orders_table.name}")
    print(f"  description: {orders_table.description}")
    print(f"  columns: {list(orders_table.columns.keys())[:5]}... (共 {len(orders_table.columns)} 列)")
    print()

    # API 调用 3.3: 获取 Join 路径
    print(f"API 调用: catalog.get_join_paths({relevant_tables})")
    join_paths = catalog.get_join_paths(relevant_tables)

    print(f"返回结果: (共 {len(join_paths)} 个 Join)")
    for join in join_paths:
        print(f"  - {join.left_table}.{join.left_column} → {join.right_table}.{join.right_column}")
        print(f"    类型: {join.join_type}, 基数: {join.cardinality}")
    print()


    # ========== 节点 4: create_query_plan ==========
    print("【节点 4】create_query_plan - 创建查询计划")
    print("-" * 80)

    # API 调用 4.1: 创建计划
    print("API 调用: planner.create_plan(intent, schema_context)")
    query_plan = planner.create_plan(
        intent=intent,
        schema_context={
            "tables": relevant_tables,
            "joins": join_paths,
            "table_details": [orders_table, ...]
        }
    )

    print(f"返回结果:")
    print(f"  plan_type: {query_plan['plan_type']}")
    print(f"  metrics: {query_plan['metrics']}")
    print(f"  dimensions: {query_plan['dimensions']}")
    print(f"  tables: {query_plan['tables']}")
    print()

    # 内部访问的 metadata:
    print("内部 metadata 访问:")
    print(f"  - semantic_layer.metrics['sales_amount'] (指标定义)")
    print(f"  - catalog.get_join_paths() (Join 路径)")
    print()


    # ========== 节点 5: generate_sql ==========
    print("【节点 5】generate_sql - 生成 SQL")
    print("-" * 80)

    # API 调用 5.1: 获取示例 SQL
    print("API 调用: semantic_layer.get_examples('simple_query')")
    examples = semantic_layer.get_examples("simple_query", limit=3)

    print(f"返回结果: (共 {len(examples)} 个示例)")
    for i, ex in enumerate(examples, 1):
        print(f"  示例 {i}:")
        print(f"    问题: {ex.question}")
        print(f"    SQL: {ex.sql[:60]}...")
    print()

    # API 调用 5.2: 生成 SQL
    print("API 调用: generator.generate(query_plan, schema_context, examples)")

    # Generator 内部会访问:
    print("内部 metadata 访问:")
    print(f"  - catalog.get_table('orders') (每个涉及的表)")
    print(f"  - semantic_layer.metrics['sales_amount'].expression")
    print(f"  - semantic_layer.metrics['sales_amount'].filters")
    print()

    sql = """
SELECT
    r.region_name,
    SUM(oi.net_amount) as sales_amount
FROM orders o
INNER JOIN order_items oi ON o.order_id = oi.order_id
INNER JOIN customers c ON o.customer_id = c.customer_id
INNER JOIN regions r ON c.region_id = r.region_id
WHERE o.status IN ('paid', 'completed')
    AND o.order_date >= '2026-08-01'
    AND o.order_date < '2026-09-01'
    AND r.region_name IN ('上海', '江苏', '浙江')
GROUP BY r.region_name
LIMIT 1000
    """.strip()

    print(f"返回的 SQL:")
    print(sql)
    print()


    # ========== 节点 6: validate_sql ==========
    print("【节点 6】validate_sql - 验证 SQL")
    print("-" * 80)

    # API 调用 6.1: 获取允许的表
    print("API 调用: catalog.get_all_tables()")
    allowed_tables = catalog.get_all_tables()

    print(f"返回结果: {allowed_tables}")
    print()

    # API 调用 6.2: 验证 SQL
    print("API 调用: guard.validate_sql(sql)")

    # Guard 内部会访问:
    print("内部 metadata 访问:")
    print(f"  - catalog.get_all_tables() (表白名单)")
    print(f"  - catalog.get_table('orders').columns (字段白名单)")
    print(f"  - catalog.is_valid_join('orders', 'order_items') (Join 验证)")
    print()

    is_valid, error = guard.validate_sql(sql)

    print(f"验证结果: {'通过' if is_valid else '失败'}")
    if error:
        print(f"错误信息: {error}")
    print()


    # ========== 节点 7: explain_sql ==========
    print("【节点 7】explain_sql - 分析执行计划")
    print("-" * 80)

    # API 调用 7.1: 执行 EXPLAIN
    print("API 调用: executor.explain(sql)")
    explain_result = executor.explain(sql)

    print(f"返回结果:")
    print(f"  estimated_rows: {explain_result.get('estimated_rows')}")
    print(f"  estimated_cost: {explain_result.get('estimated_cost')}")
    print(f"  scan_type: {explain_result.get('scan_type')}")
    print()

    print("内部 metadata 访问:")
    print(f"  - 数据库统计信息 (表大小、索引、数据分布)")
    print()


    # ========== 节点 8: execute_sql ==========
    print("【节点 8】execute_sql - 执行查询")
    print("-" * 80)

    # API 调用 8.1: 执行 SQL
    print("API 调用: executor.execute(sql)")
    query_result = executor.execute(sql)

    print(f"返回结果:")
    print(f"  row_count: {query_result.row_count}")
    print(f"  execution_time: {query_result.execution_time}s")
    print(f"  columns: {[col['name'] for col in query_result.columns]}")
    print(f"  rows: {query_result.rows}")
    print()

    print("返回的 metadata:")
    print(f"  - 结果集 schema (列名、类型)")
    print()


    # ========== 节点 9: validate_result ==========
    print("【节点 9】validate_result - 验证结果")
    print("-" * 80)

    # API 调用 9.1: 验证结果
    print("API 调用: validator.validate(query_result, query_plan)")

    # Validator 内部会访问:
    print("内部 metadata 访问:")
    print(f"  - semantic_layer.get_metric('sales_amount')")
    print(f"    → data_type: DECIMAL")
    print(f"    → min_value: 0")
    print(f"    → max_value: None")
    print()

    issues = validator.validate(query_result, query_plan, intent)

    print(f"验证结果: {len(issues)} 个问题")
    for issue in issues:
        print(f"  - {issue}")
    print()


    # ========== 节点 10: compose_answer ==========
    print("【节点 10】compose_answer - 组织答案")
    print("-" * 80)

    # API 调用 10.1: 获取指标展示信息
    print("API 调用: semantic_layer.get_metric('sales_amount')")
    metric_info = semantic_layer.get_metric("sales_amount")

    print(f"返回结果:")
    print(f"  display_name: {metric_info.display_name}")
    print(f"  unit: {metric_info.unit}")
    print(f"  description: {metric_info.description}")
    print()

    # API 调用 10.2: 组织答案
    print("API 调用: composer.compose(question, query_result, query_plan)")
    answer = composer.compose(
        question=question,
        query_result=query_result,
        query_plan=query_plan,
        validation_issues=issues
    )

    print(f"返回结果:")
    print(f"  summary: {answer['summary']}")
    print(f"  data: {answer['data']}")
    print(f"  warnings: {answer['warnings']}")
    print()


    # ========== 最终答案 ==========
    print("=" * 80)
    print("最终答案")
    print("=" * 80)
    print()
    print(answer['summary'])
    print()


# ====================
# 各个 Metadata API 的详细示例
# ====================

def example_catalog_apis():
    """DatabaseCatalog API 示例"""

    print("=" * 80)
    print("DatabaseCatalog API 示例")
    print("=" * 80)
    print()

    # 1. get_all_tables
    print("1. catalog.get_all_tables()")
    tables = catalog.get_all_tables()
    print(f"   返回: {tables}")
    print()

    # 2. get_table
    print("2. catalog.get_table('orders')")
    table = catalog.get_table("orders")
    print(f"   名称: {table.name}")
    print(f"   描述: {table.description}")
    print(f"   列数: {len(table.columns)}")
    print(f"   标签: {table.tags}")
    print()

    # 3. search_schema
    print("3. catalog.search_schema(question='订单和客户')")
    tables = catalog.search_schema(question="订单和客户")
    print(f"   返回: {tables}")
    print()

    # 4. get_join_paths
    print("4. catalog.get_join_paths(['orders', 'customers'])")
    joins = catalog.get_join_paths(["orders", "customers"])
    for join in joins:
        print(f"   {join.left_table}.{join.left_column} → {join.right_table}.{join.right_column}")
    print()

    # 5. find_join_path
    print("5. catalog.find_join_path('orders', 'regions')")
    path = catalog.find_join_path("orders", "regions")
    print(f"   路径长度: {len(path)}")
    for i, join in enumerate(path, 1):
        print(f"   步骤 {i}: {join.left_table} → {join.right_table}")
    print()

    # 6. is_valid_join
    print("6. catalog.is_valid_join('orders', 'customers')")
    is_valid = catalog.is_valid_join("orders", "customers")
    print(f"   返回: {is_valid}")
    print()


def example_semantic_layer_apis():
    """SemanticLayer API 示例"""

    print("=" * 80)
    print("SemanticLayer API 示例")
    print("=" * 80)
    print()

    # 1. resolve_metric
    print("1. semantic_layer.resolve_metric('sales_amount')")
    metric = semantic_layer.resolve_metric("sales_amount")
    print(f"   表达式: {metric.expression}")
    print(f"   涉及表: {metric.tables}")
    print(f"   过滤条件: {metric.filters}")
    print()

    # 2. resolve_dimension
    print("2. semantic_layer.resolve_dimension('region')")
    dim = semantic_layer.resolve_dimension("region")
    print(f"   表: {dim.table}")
    print(f"   列: {dim.column}")
    print(f"   映射: {dim.mappings}")
    print()

    # 3. resolve_time_range
    print("3. semantic_layer.resolve_time_range('最近一周')")
    time_spec = semantic_layer.resolve_time_range("最近一周")
    print(f"   开始: {time_spec['start_date']}")
    print(f"   结束: {time_spec['end_date']}")
    print()

    # 4. resolve_business_term
    print("4. semantic_layer.resolve_business_term('华东')")
    values = semantic_layer.resolve_business_term("华东")
    print(f"   返回: {values}")
    print()

    # 5. get_all_metrics
    print("5. semantic_layer.get_all_metrics()")
    metrics = semantic_layer.get_all_metrics()
    print(f"   总数: {len(metrics)}")
    for m in metrics[:3]:
        print(f"   - {m.name}: {m.display_name}")
    print()

    # 6. get_examples
    print("6. semantic_layer.get_examples('simple_query', limit=2)")
    examples = semantic_layer.get_examples("simple_query", limit=2)
    for ex in examples:
        print(f"   问题: {ex.question}")
        print(f"   SQL: {ex.sql[:50]}...")
        print()


def example_metadata_access_frequency():
    """统计 metadata 访问频率"""

    print("=" * 80)
    print("Metadata 访问频率统计")
    print("=" * 80)
    print()

    access_log = {
        "semantic_layer.metrics": [
            "classify_request (提取意图)",
            "resolve_semantics (解析指标)",
            "generate_sql (构建表达式)",
            "validate_result (验证类型)",
            "compose_answer (展示信息)",
        ],
        "semantic_layer.dimensions": [
            "classify_request (提取意图)",
            "resolve_semantics (解析维度)",
            "generate_sql (构建 SQL)",
            "validate_result (验证维度)",
        ],
        "catalog.tables": [
            "select_schema (检索表)",
            "select_schema (获取详情)",
            "generate_sql (构建 Schema 上下文)",
            "validate_sql (表白名单)",
            "validate_sql (字段白名单)",
            "validate_sql (Join 验证)",
        ],
        "semantic_layer.terms": [
            "classify_request (识别术语)",
            "resolve_semantics (解析术语)",
        ],
        "semantic_layer.examples": [
            "generate_sql (Few-shot 示例)",
        ],
    }

    for metadata_source, accesses in access_log.items():
        print(f"{metadata_source}:")
        print(f"  访问次数: {len(accesses)}")
        print(f"  访问位置:")
        for access in accesses:
            print(f"    - {access}")
        print()


if __name__ == "__main__":
    # 运行完整流程示例
    example_full_flow()

    print("\n" + "=" * 80 + "\n")

    # 运行各个 API 示例
    example_catalog_apis()
    example_semantic_layer_apis()

    print("\n" + "=" * 80 + "\n")

    # 统计访问频率
    example_metadata_access_frequency()
