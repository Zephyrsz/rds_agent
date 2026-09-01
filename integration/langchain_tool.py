"""
LangChain Tool Implementation for RDS Agent

将 RDS Agent 封装为 LangChain Tool，供基于 LangChain 的 Agent 直接调用。

优势：
- 原生集成，无需额外服务
- 可以访问 Agent 的完整上下文
- 支持同步和异步调用
"""

from typing import Optional, Type
from pathlib import Path

from langchain.tools import BaseTool
from langchain.callbacks.manager import CallbackManagerForToolRun, AsyncCallbackManagerForToolRun
from pydantic import BaseModel, Field

# RDS Agent 核心组件
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

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


class RDSQueryInput(BaseModel):
    """RDS 查询工具输入"""
    question: str = Field(description="用户的自然语言问题，例如：'最近一个月的销售额是多少？'")


class RDSQueryTool(BaseTool):
    """
    RDS Agent 查询工具

    允许 LangChain Agent 通过自然语言查询数据库。

    示例用法:
    ```python
    from langchain.agents import initialize_agent, AgentType
    from langchain_openai import ChatOpenAI

    # 创建工具
    rds_tool = RDSQueryTool()

    # 创建 Agent
    llm = ChatOpenAI(temperature=0)
    tools = [rds_tool]
    agent = initialize_agent(
        tools,
        llm,
        agent=AgentType.OPENAI_FUNCTIONS,
        verbose=True
    )

    # 使用 Agent
    agent.run("最近一个月的销售额是多少？")
    ```
    """

    name: str = "rds_query"
    description: str = (
        "查询数据库并返回结果。"
        "输入应该是一个自然语言问题，例如：'最近一个月的销售额是多少？'。"
        "该工具会自动生成 SQL、执行查询并返回格式化的结果。"
    )
    args_schema: Type[BaseModel] = RDSQueryInput

    # RDS Agent 工作流（延迟初始化）
    workflow: Optional[DataAgentWorkflow] = None
    _initialized: bool = False

    def _ensure_initialized(self):
        """确保工作流已初始化"""
        if self._initialized and self.workflow is not None:
            return

        # 初始化 RDS Agent
        project_root = Path(__file__).parent.parent
        config_dir = project_root / "config"

        # 创建数据库
        db_adapter = create_sample_database(":memory:")

        # 初始化组件
        catalog = DatabaseCatalog(config_dir)
        semantic_layer = SemanticLayer(config_dir)
        planner = QueryPlanner(semantic_layer, catalog)

        llm = ChatOpenAI(model="gpt-4", temperature=0)

        generator = SQLGenerator(
            llm=llm,
            catalog=catalog,
            semantic_layer=semantic_layer,
        )

        guard = SQLGuard(
            allowed_tables=set(catalog.get_all_tables()),
            max_result_rows=10000,
            default_limit=1000,
        )

        executor = QueryExecutor(
            db_connection=db_adapter.connection,
            timeout_seconds=30,
            max_result_rows=10000,
        )

        validator = ResultValidator(semantic_layer)
        composer = AnswerComposer(llm=llm)

        # 创建工作流
        self.workflow = DataAgentWorkflow(
            catalog=catalog,
            semantic_layer=semantic_layer,
            planner=planner,
            generator=generator,
            guard=guard,
            executor=executor,
            validator=validator,
            composer=composer,
        )

        self._initialized = True

    def _run(
        self,
        question: str,
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        """
        同步执行查询

        Args:
            question: 用户问题
            run_manager: 回调管理器

        Returns:
            查询结果（格式化的字符串）
        """
        self._ensure_initialized()

        try:
            # 执行工作流
            final_state = self.workflow.run(question)

            # 检查错误
            if final_state.get("error"):
                return f"查询失败: {final_state['error']}"

            # 格式化结果
            return self._format_result(final_state)

        except Exception as e:
            return f"执行出错: {str(e)}"

    async def _arun(
        self,
        question: str,
        run_manager: Optional[AsyncCallbackManagerForToolRun] = None,
    ) -> str:
        """
        异步执行查询

        Args:
            question: 用户问题
            run_manager: 回调管理器

        Returns:
            查询结果（格式化的字符串）
        """
        self._ensure_initialized()

        try:
            # 执行工作流（异步）
            final_state = await self.workflow.arun(question)

            # 检查错误
            if final_state.get("error"):
                return f"查询失败: {final_state['error']}"

            # 格式化结果
            return self._format_result(final_state)

        except Exception as e:
            return f"执行出错: {str(e)}"

    def _format_result(self, final_state: dict) -> str:
        """格式化查询结果"""
        sql = final_state.get("sql", "")
        query_result = final_state.get("query_result", {})
        answer = final_state.get("answer", {})

        # 构建响应
        lines = []

        # SQL
        if sql:
            lines.append("生成的 SQL:")
            lines.append(f"```sql\n{sql}\n```")
            lines.append("")

        # 执行情况
        lines.append(f"返回行数: {query_result.get('row_count', 0)}")
        lines.append(f"执行时间: {query_result.get('execution_time', 0):.3f} 秒")
        lines.append("")

        # 数据
        rows = query_result.get("rows", [])
        if rows:
            lines.append("查询结果:")

            # 表头
            columns = list(rows[0].keys())
            lines.append("| " + " | ".join(columns) + " |")
            lines.append("|" + "|".join(["---"] * len(columns)) + "|")

            # 数据行（最多 5 行）
            for row in rows[:5]:
                lines.append("| " + " | ".join(str(row.get(col, "")) for col in columns) + " |")

            if len(rows) > 5:
                lines.append(f"\n... (共 {len(rows)} 行，仅显示前 5 行)")

            lines.append("")

        # 警告
        warnings = answer.get("warnings", [])
        if warnings:
            lines.append("注意事项:")
            for warning in warnings:
                lines.append(f"- {warning}")

        return "\n".join(lines)


class RDSSchematool(BaseTool):
    """
    RDS Schema 查询工具

    允许 Agent 查询数据库的 Schema 信息。
    """

    name: str = "rds_schema"
    description: str = (
        "获取数据库 Schema 信息。"
        "可以查询特定表的结构，或者获取所有表的列表。"
        "输入可以是表名（返回该表的详细信息）或空（返回所有表）。"
    )

    catalog: Optional[DatabaseCatalog] = None
    _initialized: bool = False

    def _ensure_initialized(self):
        """确保已初始化"""
        if self._initialized and self.catalog is not None:
            return

        project_root = Path(__file__).parent.parent
        config_dir = project_root / "config"

        self.catalog = DatabaseCatalog(config_dir)
        self._initialized = True

    def _run(
        self,
        table_name: str = "",
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        """同步执行"""
        self._ensure_initialized()

        try:
            if table_name:
                # 特定表
                table = self.catalog.get_table(table_name)
                if not table:
                    return f"表 '{table_name}' 不存在"

                return table.get_ddl_summary()
            else:
                # 所有表
                tables = self.catalog.get_all_tables()
                lines = [f"数据库包含 {len(tables)} 个表:\n"]

                for tbl_name in tables:
                    table = self.catalog.get_table(tbl_name)
                    lines.append(f"- {tbl_name}: {table.description}")

                return "\n".join(lines)

        except Exception as e:
            return f"获取 Schema 出错: {str(e)}"

    async def _arun(
        self,
        table_name: str = "",
        run_manager: Optional[AsyncCallbackManagerForToolRun] = None,
    ) -> str:
        """异步执行"""
        return self._run(table_name, run_manager)


# ============ 示例用法 ============

def example_usage():
    """示例：如何在 LangChain Agent 中使用 RDS Tool"""
    from langchain.agents import initialize_agent, AgentType
    from langchain_openai import ChatOpenAI

    # 创建工具
    tools = [
        RDSQueryTool(),
        RDSSchemaTool(),
    ]

    # 创建 Agent
    llm = ChatOpenAI(temperature=0, model="gpt-4")
    agent = initialize_agent(
        tools,
        llm,
        agent=AgentType.OPENAI_FUNCTIONS,
        verbose=True
    )

    # 使用 Agent
    questions = [
        "数据库里有哪些表？",
        "最近一个月的销售额是多少？",
        "华东地区的订单数有多少？",
    ]

    for question in questions:
        print(f"\n问题: {question}")
        print("=" * 60)
        response = agent.run(question)
        print(response)
        print()


if __name__ == "__main__":
    # 直接测试工具
    tool = RDSQueryTool()
    result = tool.run("最近一个月的销售额是多少？")
    print(result)
