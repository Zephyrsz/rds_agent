"""
Function Calling Implementation for RDS Agent

为 OpenAI/Anthropic 的 Function Calling 提供集成。

优势：
- LLM 原生支持
- 自动决策何时调用函数
- 支持并行调用
"""

from typing import Dict, Any, List
from pathlib import Path
import json

# OpenAI
from openai import OpenAI

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


# ============ Function Definitions ============

FUNCTIONS = [
    {
        "name": "query_database",
        "description": "查询数据库并返回结果。使用自然语言提问，系统会自动生成 SQL 并执行查询。",
        "parameters": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "用户的自然语言问题，例如：'最近一个月的销售额是多少？'"
                }
            },
            "required": ["question"]
        }
    },
    {
        "name": "get_database_schema",
        "description": "获取数据库表结构信息。可以查询特定表的详细结构，或获取所有表的列表。",
        "parameters": {
            "type": "object",
            "properties": {
                "table_name": {
                    "type": "string",
                    "description": "表名（可选）。如果提供，返回该表的详细结构；如果不提供，返回所有表的列表。"
                }
            },
            "required": []
        }
    },
    {
        "name": "get_available_metrics",
        "description": "获取所有可用的业务指标定义，包括指标名称、计算方式、涉及的表等。",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
]


# ============ RDS Agent Wrapper ============

class RDSAgentFunctionCalling:
    """RDS Agent Function Calling 包装器"""

    def __init__(self, config_dir: Path, db_path: str = ":memory:"):
        """初始化"""
        self.config_dir = config_dir
        self.db_path = db_path

        # 初始化 RDS Agent
        self._init_rds_agent()

    def _init_rds_agent(self):
        """初始化 RDS Agent"""
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

    def query_database(self, question: str) -> Dict[str, Any]:
        """查询数据库"""
        try:
            final_state = self.workflow.run(question)

            if final_state.get("error"):
                return {
                    "success": False,
                    "error": final_state["error"]
                }

            query_result = final_state.get("query_result", {})

            return {
                "success": True,
                "sql": final_state.get("sql"),
                "row_count": query_result.get("row_count", 0),
                "execution_time": query_result.get("execution_time", 0),
                "data": query_result.get("rows", [])[:10],  # 最多返回 10 行
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def get_database_schema(self, table_name: str = None) -> Dict[str, Any]:
        """获取 Schema"""
        try:
            if table_name:
                table = self.catalog.get_table(table_name)
                if not table:
                    return {
                        "success": False,
                        "error": f"表 '{table_name}' 不存在"
                    }

                return {
                    "success": True,
                    "table_name": table.name,
                    "description": table.description,
                    "columns": [
                        {
                            "name": col_name,
                            "type": col_info.get("type"),
                            "description": col_info.get("description"),
                        }
                        for col_name, col_info in table.columns.items()
                    ]
                }
            else:
                tables = self.catalog.get_all_tables()
                return {
                    "success": True,
                    "tables": [
                        {
                            "name": tbl_name,
                            "description": self.catalog.get_table(tbl_name).description
                        }
                        for tbl_name in tables
                    ]
                }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def get_available_metrics(self) -> Dict[str, Any]:
        """获取可用指标"""
        try:
            metrics = []
            for metric_name, metric in self.semantic_layer.metrics.items():
                metrics.append({
                    "name": metric.name,
                    "display_name": metric.display_name,
                    "description": metric.description,
                    "expression": metric.expression,
                    "tables": metric.tables,
                })

            return {
                "success": True,
                "metrics": metrics
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def call_function(self, function_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """调用函数"""
        if function_name == "query_database":
            return self.query_database(arguments.get("question", ""))
        elif function_name == "get_database_schema":
            return self.get_database_schema(arguments.get("table_name"))
        elif function_name == "get_available_metrics":
            return self.get_available_metrics()
        else:
            return {
                "success": False,
                "error": f"Unknown function: {function_name}"
            }


# ============ OpenAI Function Calling 示例 ============

def example_openai_function_calling():
    """OpenAI Function Calling 示例"""
    import os

    # 初始化
    project_root = Path(__file__).parent.parent
    config_dir = project_root / "config"
    rds_agent = RDSAgentFunctionCalling(config_dir)

    # OpenAI Client
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # 用户消息
    messages = [
        {
            "role": "user",
            "content": "帮我查询一下最近一个月的销售额，并告诉我华东地区的订单数"
        }
    ]

    print("用户问题:", messages[0]["content"])
    print("=" * 60)

    # 第一次调用：LLM 决定调用哪些函数
    response = client.chat.completions.create(
        model="gpt-4",
        messages=messages,
        functions=FUNCTIONS,
        function_call="auto",
    )

    message = response.choices[0].message

    # 处理函数调用
    if message.function_call:
        print(f"\nLLM 决定调用函数: {message.function_call.name}")
        print(f"参数: {message.function_call.arguments}")

        # 执行函数
        function_name = message.function_call.name
        arguments = json.loads(message.function_call.arguments)

        result = rds_agent.call_function(function_name, arguments)

        print(f"\n函数返回结果:")
        print(json.dumps(result, indent=2, ensure_ascii=False))

        # 将函数结果返回给 LLM
        messages.append({
            "role": "assistant",
            "content": None,
            "function_call": {
                "name": function_name,
                "arguments": message.function_call.arguments
            }
        })

        messages.append({
            "role": "function",
            "name": function_name,
            "content": json.dumps(result, ensure_ascii=False)
        })

        # 第二次调用：LLM 生成最终回答
        second_response = client.chat.completions.create(
            model="gpt-4",
            messages=messages
        )

        final_answer = second_response.choices[0].message.content
        print(f"\n最终回答:")
        print(final_answer)

    else:
        print("\nLLM 直接回答:")
        print(message.content)


# ============ Anthropic Function Calling 示例 ============

def example_anthropic_function_calling():
    """Anthropic Claude Function Calling 示例"""
    import anthropic

    # 初始化
    project_root = Path(__file__).parent.parent
    config_dir = project_root / "config"
    rds_agent = RDSAgentFunctionCalling(config_dir)

    # Anthropic Client
    client = anthropic.Anthropic()

    # 转换函数定义为 Anthropic 格式
    tools = [
        {
            "name": func["name"],
            "description": func["description"],
            "input_schema": func["parameters"]
        }
        for func in FUNCTIONS
    ]

    # 用户消息
    message = client.messages.create(
        model="claude-3-sonnet-20240229",
        max_tokens=1024,
        tools=tools,
        messages=[
            {
                "role": "user",
                "content": "帮我查询一下最近一个月的销售额"
            }
        ]
    )

    print("Claude 响应:")
    print(message.content)

    # 处理工具调用
    if message.stop_reason == "tool_use":
        for content_block in message.content:
            if content_block.type == "tool_use":
                tool_name = content_block.name
                tool_input = content_block.input

                print(f"\nClaude 调用工具: {tool_name}")
                print(f"参数: {tool_input}")

                # 执行工具
                result = rds_agent.call_function(tool_name, tool_input)

                print(f"\n工具返回:")
                print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    print("OpenAI Function Calling 示例")
    print("=" * 60)
    example_openai_function_calling()
