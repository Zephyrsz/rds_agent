"""
MCP Server Implementation for RDS Agent

将 RDS Agent 暴露为 MCP (Model Context Protocol) Server，
供支持 MCP 的 Agent (如 Claude Desktop, Hermes Agent) 调用。

MCP 是 Anthropic 推出的标准协议，用于 LLM 与外部工具的集成。
"""

import asyncio
import json
from typing import Any, Optional
from pathlib import Path

# MCP SDK (需要安装: pip install mcp)
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource

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


class RDSAgentMCPServer:
    """RDS Agent MCP Server"""

    def __init__(self, config_dir: Path, db_path: str = ":memory:"):
        """初始化 MCP Server"""
        self.config_dir = config_dir
        self.db_path = db_path

        # 初始化 RDS Agent
        self._init_rds_agent()

        # 创建 MCP Server
        self.server = Server("rds-agent")

        # 注册工具
        self._register_tools()

    def _init_rds_agent(self):
        """初始化 RDS Agent 核心组件"""
        # 创建数据库
        self.db_adapter = create_sample_database(self.db_path)

        # 初始化组件
        self.catalog = DatabaseCatalog(self.config_dir)
        self.semantic_layer = SemanticLayer(self.config_dir)
        self.planner = QueryPlanner(self.semantic_layer, self.catalog)

        llm = ChatOpenAI(model="gpt-4", temperature=0)

        self.generator = SQLGenerator(
            llm=llm,
            catalog=self.catalog,
            semantic_layer=self.semantic_layer,
        )

        self.guard = SQLGuard(
            allowed_tables=set(self.catalog.get_all_tables()),
            max_result_rows=10000,
            default_limit=1000,
        )

        self.executor = QueryExecutor(
            db_connection=self.db_adapter.connection,
            timeout_seconds=30,
            max_result_rows=10000,
        )

        self.validator = ResultValidator(self.semantic_layer)
        self.composer = AnswerComposer(llm=llm)

        # 创建工作流
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

    def _register_tools(self):
        """注册 MCP 工具"""

        # 工具 1: 查询数据
        @self.server.call_tool()
        async def query_data(question: str) -> list[TextContent]:
            """
            查询数据库并返回结果

            Args:
                question: 用户的自然语言问题

            Returns:
                查询结果和分析
            """
            try:
                # 执行工作流
                final_state = self.workflow.run(question)

                # 格式化响应
                if final_state.get("error"):
                    return [TextContent(
                        type="text",
                        text=f"查询失败: {final_state['error']}"
                    )]

                # 提取结果
                answer = final_state.get("answer", {})
                query_result = final_state.get("query_result", {})
                sql = final_state.get("sql", "")

                # 构建响应文本
                response_text = f"""## 查询结果

**问题**: {question}

**生成的 SQL**:
```sql
{sql}
```

**执行情况**:
- 返回行数: {query_result.get('row_count', 0)}
- 执行时间: {query_result.get('execution_time', 0):.3f} 秒

**数据**:
"""
                # 添加数据行
                rows = query_result.get("rows", [])
                if rows:
                    # 表头
                    columns = list(rows[0].keys())
                    response_text += "\n| " + " | ".join(columns) + " |"
                    response_text += "\n|" + "|".join(["---"] * len(columns)) + "|"

                    # 数据行（最多显示 10 行）
                    for row in rows[:10]:
                        response_text += "\n| " + " | ".join(str(row.get(col, "")) for col in columns) + " |"

                    if len(rows) > 10:
                        response_text += f"\n\n... (共 {len(rows)} 行，仅显示前 10 行)"

                # 添加警告
                warnings = answer.get("warnings", [])
                if warnings:
                    response_text += "\n\n**注意事项**:\n"
                    for warning in warnings:
                        response_text += f"- {warning}\n"

                return [TextContent(type="text", text=response_text)]

            except Exception as e:
                return [TextContent(
                    type="text",
                    text=f"执行出错: {str(e)}"
                )]

        # 工具 2: 获取 Schema 信息
        @self.server.call_tool()
        async def get_schema(table_name: Optional[str] = None) -> list[TextContent]:
            """
            获取数据库 Schema 信息

            Args:
                table_name: 表名（可选），不提供则返回所有表

            Returns:
                Schema 信息
            """
            try:
                if table_name:
                    # 获取特定表的信息
                    table = self.catalog.get_table(table_name)
                    if not table:
                        return [TextContent(
                            type="text",
                            text=f"表 '{table_name}' 不存在"
                        )]

                    schema_text = table.get_ddl_summary()
                else:
                    # 获取所有表
                    tables = self.catalog.get_all_tables()
                    schema_text = f"数据库包含 {len(tables)} 个表:\n\n"

                    for table_name in tables:
                        table = self.catalog.get_table(table_name)
                        schema_text += f"### {table_name}\n"
                        schema_text += f"{table.description}\n\n"

                return [TextContent(type="text", text=schema_text)]

            except Exception as e:
                return [TextContent(
                    type="text",
                    text=f"获取 Schema 出错: {str(e)}"
                )]

        # 工具 3: 获取可用指标
        @self.server.call_tool()
        async def get_metrics() -> list[TextContent]:
            """
            获取所有可用的业务指标

            Returns:
                指标列表和说明
            """
            try:
                metrics_text = "## 可用的业务指标\n\n"

                for metric_name, metric in self.semantic_layer.metrics.items():
                    metrics_text += f"### {metric.display_name} ({metric_name})\n"
                    metrics_text += f"**说明**: {metric.description}\n"
                    metrics_text += f"**计算**: `{metric.expression}`\n"
                    metrics_text += f"**涉及表**: {', '.join(metric.tables)}\n"
                    if metric.filters:
                        metrics_text += f"**过滤条件**: {', '.join(metric.filters)}\n"
                    metrics_text += "\n"

                return [TextContent(type="text", text=metrics_text)]

            except Exception as e:
                return [TextContent(
                    type="text",
                    text=f"获取指标出错: {str(e)}"
                )]

        # 工具 4: 获取可用维度
        @self.server.call_tool()
        async def get_dimensions() -> list[TextContent]:
            """
            获取所有可用的业务维度

            Returns:
                维度列表和说明
            """
            try:
                dimensions_text = "## 可用的业务维度\n\n"

                for dim_name, dim in self.semantic_layer.dimensions.items():
                    dimensions_text += f"### {dim.display_name} ({dim_name})\n"
                    dimensions_text += f"**表**: {dim.table}.{dim.column}\n"
                    if dim.mappings:
                        dimensions_text += "**值映射**:\n"
                        for key, values in dim.mappings.items():
                            dimensions_text += f"  - {key}: {', '.join(values)}\n"
                    dimensions_text += "\n"

                return [TextContent(type="text", text=dimensions_text)]

            except Exception as e:
                return [TextContent(
                    type="text",
                    text=f"获取维度出错: {str(e)}"
                )]

    async def run(self):
        """运行 MCP Server"""
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options()
            )


async def main():
    """主函数"""
    # 配置目录
    project_root = Path(__file__).parent.parent
    config_dir = project_root / "config"

    # 创建并运行 MCP Server
    server = RDSAgentMCPServer(config_dir)
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())
