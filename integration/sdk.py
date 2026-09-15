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
from datetime import date
import os
import tempfile

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from adapters.duckdb import create_sample_database, DuckDBAdapter
from adapters.sqlite_catalog import SQLiteCatalog
from adapters.sqlite_semantic import SQLiteSemanticLayer
from adapters.yaml_to_sqlite import migrate_yaml_to_sqlite
from core import (
    DatabaseCatalog,
    SemanticLayer,
    QueryPlanner,
    SQLGenerator,
    SQLGuard,
    QueryExecutor,
    ResultValidator,
    AnswerComposer,
    SemanticQueryCompiler,
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
        metadata_db_path: Optional[str] = None,
        reference_date: Optional[date] = None,
        read_only: bool = True,
    ):
        """
        初始化 RDS Agent

        Args:
            config_dir: 配置文件目录（默认为项目 config 目录）
            db_path: 数据库路径（默认内存数据库）
            metadata_db_path: 共享 SQLite metadata 路径
            read_only: 是否以只读模式连接已有 DuckDB 文件
            llm_model: LLM 模型名称
            llm_temperature: LLM 温度参数
        """
        # 配置目录
        if config_dir is None:
            project_root = Path(__file__).parent.parent
            config_dir = project_root / "config"

        self.config_dir = Path(config_dir)
        self.db_path = db_path
        self.read_only = read_only
        self.reference_date = reference_date or (date(2024, 9, 30) if db_path == ":memory:" else None)
        self._metadata_temp_path = None

        if metadata_db_path in (None, ":memory:"):
            fd, temp_path = tempfile.mkstemp(prefix="rds_agent_metadata_", suffix=".db")
            os.close(fd)
            self.metadata_db_path = temp_path
            self._metadata_temp_path = temp_path
        else:
            self.metadata_db_path = str(metadata_db_path)

        metadata_path = Path(self.metadata_db_path)
        if not metadata_path.exists() or metadata_path.stat().st_size == 0:
            migrate_yaml_to_sqlite(self.config_dir, self.metadata_db_path)

        # 初始化数据库
        if db_path == ":memory:":
            self.db_adapter = create_sample_database(db_path)
        elif not Path(db_path).exists():
            raise FileNotFoundError(f"DuckDB database not found: {db_path}")
        else:
            self.db_adapter = DuckDBAdapter(db_path, read_only=read_only)
            self.db_adapter.connect()

        # 初始化核心组件
        self._init_components(llm_model, llm_temperature)

    def _init_components(self, llm_model: str, llm_temperature: float):
        """初始化核心组件"""
        # SQLite 是运行时 metadata 的唯一来源；YAML 仅在初始化时作为种子迁移。
        self.catalog = SQLiteCatalog(self.metadata_db_path)
        self.semantic_layer = SQLiteSemanticLayer(self.metadata_db_path, reference_date=self.reference_date)
        self.compiler = SemanticQueryCompiler(self.semantic_layer, self.catalog)

        # Planner
        self.planner = QueryPlanner(self.semantic_layer, self.catalog)

        # LLM
        llm = None
        if os.getenv("OPENAI_API_KEY"):
            llm = ChatOpenAI(model=llm_model, temperature=llm_temperature)

        # Generator
        self.generator = SQLGenerator(
            llm=llm,
            catalog=self.catalog,
            semantic_layer=self.semantic_layer,
            compiler=self.compiler,
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
            compiler=self.compiler,
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
            context = user_context or {}
            if context.get("reference_date"):
                value = context["reference_date"]
                self.semantic_layer.reference_date = date.fromisoformat(value) if isinstance(value, str) else value
            # 执行工作流
            final_state = self.workflow.run(
                question=question,
                user_context=context
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
            context = user_context or {}
            if context.get("reference_date"):
                value = context["reference_date"]
                self.semantic_layer.reference_date = date.fromisoformat(value) if isinstance(value, str) else value
            # 异步执行工作流
            final_state = await self.workflow.arun(
                question=question,
                user_context=context
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
                            "type": col_info.type,
                            "description": col_info.description,
                            "primary_key": col_info.primary_key,
                            "foreign_key": col_info.foreign_key,
                            "enum": col_info.enum,
                        }
                        for col_name, col_info in table.columns.items()
                    ],
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
        for metric in self.semantic_layer.get_all_metrics():
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
        for dim in self.semantic_layer.get_all_dimensions():
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
        if self.catalog:
            self.catalog.close()
        if self.semantic_layer:
            self.semantic_layer.close()
        if self._metadata_temp_path:
            try:
                os.unlink(self._metadata_temp_path)
            except FileNotFoundError:
                pass

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
