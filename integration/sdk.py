"""
Python SDK for RDS Agent

提供简化的 Python API，供其他 Python Agent 直接集成。

优势：
- 性能最好（无网络开销）
- 可以共享上下文
- 易于调试
"""

from typing import Optional, Dict, Any, List
from pathlib import Path
from dataclasses import dataclass

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from adapters.duckdb import create_sample_database, DuckDBAdapter
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


@dataclass
class QueryResult:
    """查询结果"""
    success: bool
    question: str
    sql: Optional[str] = None
    data: Optional[List[Dict]] = None
    row_count: int = 0
    execution_time: float = 0.0
    error: Optional[str] = None
    warnings: Optional[List[str]] = None


class RDSAgent:
    """
    RDS Agent Python SDK

    简化的 API，用于嵌入式集成。

    示例用法:
    ```python
    from integration.sdk import RDSAgent

    # 初始化
    agent = RDSAgent()

    # 查询
    result = agent.query("最近一个月的销售额是多少？")

    if result.success:
        print(f"SQL: {result.sql}")
        print(f"数据: {result.data}")
    else:
        print(f"错误: {result.error}")

    # 获取 Schema
    schema = agent.get_schema()
    print(schema)

    # 获取指标
    metrics = agent.get_metrics()
    print(metrics)
    ```
    """

    def __init__(
        self,
        config_dir: Optional[Path] = None,
        db_path: str = ":memory:",
        llm_model: str = "gpt-4",
        llm_temperature: float = 0.0,
    ):
        """
        初始化 RDS Agent

        Args:
            config_dir: 配置文件目录（默认为项目 config 目录）
            db_path: 数据库路径（默认内存数据库）
            llm_model: LLM 模型名称
            llm_temperature: LLM 温度参数
        """
        # 配置目录
        if config_dir is None:
            project_root = Path(__file__).parent.parent
            config_dir = project_root / "config"

        self.config_dir = Path(config_dir)
        self.db_path = db_path

        # 初始化数据库
        if db_path == ":memory:" or not Path(db_path).exists():
            self.db_adapter = create_sample_database(db_path)
        else:
            self.db_adapter = DuckDBAdapter(db_path)
            self.db_adapter.connect()

        # 初始化核心组件
        self._init_components(llm_model, llm_temperature)

    def _init_components(self, llm_model: str, llm_temperature: float):
        """初始化核心组件"""
        # Catalog 和 Semantic Layer
        self.catalog = DatabaseCatalog(self.config_dir)
        self.semantic_layer = SemanticLayer(self.config_dir)

        # Planner
        self.planner = QueryPlanner(self.semantic_layer, self.catalog)

        # LLM
        llm = ChatOpenAI(model=llm_model, temperature=llm_temperature)

        # Generator
        self.generator = SQLGenerator(
            llm=llm,
            catalog=self.catalog,
            semantic_layer=self.semantic_layer,
        )

        # Guard
        self.guard = SQLGuard(
            allowed_tables=set(self.catalog.get_all_tables()),
            max_result_rows=10000,
            default_limit=1000,
        )

        # Executor
        self.executor = QueryExecutor(
            db_connection=self.db_adapter.connection,
            timeout_seconds=30,
            max_result_rows=10000,
        )

        # Validator 和 Composer
        self.validator = ResultValidator(self.semantic_layer)
        self.composer = AnswerComposer(llm=llm)

        # Workflow
        self.workflow = DataAgentWorkflow(
            catalog=self.catalog,
            semantic_layer=self.semantic_layer,
            planner=self.planner,
            generator=self.generator,
            guard=self.guard,
            executor=self.executor,
            validator=self.validator,
            composer=self.composer,
        )

    def query(self, question: str, user_context: Optional[Dict] = None) -> QueryResult:
        """
        执行查询

        Args:
            question: 用户问题
            user_context: 用户上下文（可选）

        Returns:
            QueryResult 对象
        """
        try:
            # 执行工作流
            final_state = self.workflow.run(
                question=question,
                user_context=user_context or {}
            )

            # 检查错误
            if final_state.get("error"):
                return QueryResult(
                    success=False,
                    question=question,
                    error=final_state["error"]
                )

            # 提取结果
            query_result = final_state.get("query_result")
            if not isinstance(query_result, dict):
                return QueryResult(
                    success=False,
                    question=question,
                    sql=final_state.get("sql"),
                    error="工作流未返回查询结果",
                )

            answer = final_state.get("answer") or {}

            return QueryResult(
                success=True,
                question=question,
                sql=final_state.get("sql"),
                data=query_result.get("rows", []),
                row_count=query_result.get("row_count", 0),
                execution_time=query_result.get("execution_time", 0),
                warnings=answer.get("warnings", [])
            )

        except Exception as e:
            return QueryResult(
                success=False,
                question=question,
                error=str(e)
            )

    async def aquery(self, question: str, user_context: Optional[Dict] = None) -> QueryResult:
        """
        异步执行查询

        Args:
            question: 用户问题
            user_context: 用户上下文（可选）

        Returns:
            QueryResult 对象
        """
        try:
            # 异步执行工作流
            final_state = await self.workflow.arun(
                question=question,
                user_context=user_context or {}
            )

            # 检查错误
            if final_state.get("error"):
                return QueryResult(
                    success=False,
                    question=question,
                    error=final_state["error"]
                )

            # 提取结果
            query_result = final_state.get("query_result")
            if not isinstance(query_result, dict):
                return QueryResult(
                    success=False,
                    question=question,
                    sql=final_state.get("sql"),
                    error="工作流未返回查询结果",
                )

            answer = final_state.get("answer") or {}

            return QueryResult(
                success=True,
                question=question,
                sql=final_state.get("sql"),
                data=query_result.get("rows", []),
                row_count=query_result.get("row_count", 0),
                execution_time=query_result.get("execution_time", 0),
                warnings=answer.get("warnings", [])
            )

        except Exception as e:
            return QueryResult(
                success=False,
                question=question,
                error=str(e)
            )

    def get_schema(self, table_name: Optional[str] = None) -> Dict[str, Any]:
        """
        获取 Schema 信息

        Args:
            table_name: 表名（可选）

        Returns:
            Schema 信息字典
        """
        try:
            if table_name:
                table = self.catalog.get_table(table_name)
                if not table:
                    return {"error": f"表 '{table_name}' 不存在"}

                return {
                    "table_name": table.name,
                    "description": table.description,
                    "columns": [
                        {
                            "name": col_name,
                            **col_info
                        }
                        for col_name, col_info in table.columns.items()
                    ]
                }
            else:
                tables = self.catalog.get_all_tables()
                return {
                    "tables": [
                        {
                            "name": tbl_name,
                            "description": self.catalog.get_table(tbl_name).description
                        }
                        for tbl_name in tables
                    ]
                }

        except Exception as e:
            return {"error": str(e)}

    def get_metrics(self) -> List[Dict[str, Any]]:
        """
        获取所有可用指标

        Returns:
            指标列表
        """
        metrics = []
        for metric_name, metric in self.semantic_layer.metrics.items():
            metrics.append({
                "name": metric.name,
                "display_name": metric.display_name,
                "description": metric.description,
                "expression": metric.expression,
                "tables": metric.tables,
            })
        return metrics

    def get_dimensions(self) -> List[Dict[str, Any]]:
        """
        获取所有可用维度

        Returns:
            维度列表
        """
        dimensions = []
        for dim_name, dim in self.semantic_layer.dimensions.items():
            dimensions.append({
                "name": dim.name,
                "display_name": dim.display_name,
                "table": dim.table,
                "column": dim.column,
                "mappings": dim.mappings,
            })
        return dimensions

    def get_statistics(self) -> Dict[str, Any]:
        """
        获取执行统计

        Returns:
            统计信息字典
        """
        return self.executor.get_statistics()

    def close(self):
        """关闭数据库连接"""
        if self.db_adapter:
            self.db_adapter.close()

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.close()


# ============ 便捷函数 ============

def quick_query(question: str) -> QueryResult:
    """
    快速查询（单次使用）

    Args:
        question: 用户问题

    Returns:
        QueryResult 对象

    示例:
    ```python
    result = quick_query("最近一个月的销售额是多少？")
    print(result.data)
    ```
    """
    with RDSAgent() as agent:
        return agent.query(question)


# ============ 示例 ============

def example_basic_usage():
    """基本用法示例"""
    print("=" * 60)
    print("RDS Agent SDK - 基本用法")
    print("=" * 60)
    print()

    # 创建 Agent
    agent = RDSAgent()

    # 查询 1
    print("查询 1: 最近一个月的销售额")
    result = agent.query("最近一个月的销售额是多少？")

    if result.success:
        print(f"  ✓ 成功")
        print(f"  SQL: {result.sql}")
        print(f"  行数: {result.row_count}")
        print(f"  耗时: {result.execution_time:.3f}s")
        print(f"  数据: {result.data}")
    else:
        print(f"  ✗ 失败: {result.error}")

    print()

    # 查询 2
    print("查询 2: 华东地区的订单数")
    result = agent.query("华东地区的订单数有多少？")

    if result.success:
        print(f"  ✓ 成功")
        print(f"  数据: {result.data}")
    else:
        print(f"  ✗ 失败: {result.error}")

    print()

    # 获取统计
    print("执行统计:")
    stats = agent.get_statistics()
    print(f"  总查询数: {stats['total_queries']}")
    print(f"  成功率: {stats['success_rate']:.1%}")

    # 关闭
    agent.close()


def example_context_manager():
    """上下文管理器用法示例"""
    print("=" * 60)
    print("RDS Agent SDK - 上下文管理器")
    print("=" * 60)
    print()

    with RDSAgent() as agent:
        # 查询
        result = agent.query("各个地区的销售额分别是多少？")

        if result.success:
            print("查询成功!")
            for row in result.data:
                print(f"  {row}")
        else:
            print(f"查询失败: {result.error}")

    # 自动关闭连接


def example_quick_query():
    """快速查询示例"""
    print("=" * 60)
    print("RDS Agent SDK - 快速查询")
    print("=" * 60)
    print()

    # 单次查询
    result = quick_query("TOP 5 销售额最高的客户")

    if result.success:
        print("TOP 5 客户:")
        for row in result.data:
            print(f"  {row}")


if __name__ == "__main__":
    import os

    # 检查环境变量
    if not os.getenv("OPENAI_API_KEY"):
        print("错误: 请设置 OPENAI_API_KEY 环境变量")
        sys.exit(1)

    # 运行示例
    example_basic_usage()
    print()
    example_context_manager()
    print()
    example_quick_query()
