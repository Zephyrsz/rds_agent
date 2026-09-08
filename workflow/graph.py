"""
LangGraph workflow graph definition
"""

from typing import Dict, Any
from langgraph.graph import StateGraph, END
from .states import AgentState, create_initial_state
from .nodes import WorkflowNodes


def create_workflow_graph(
    catalog,
    semantic_layer,
    planner,
    generator,
    guard,
    executor,
    validator,
    composer,
    compiler=None,
) -> StateGraph:
    """
    创建 LangGraph 工作流

    流程：
    START
      ↓
    classify_request
      ↓
    resolve_semantics
      ↓
    select_schema
      ↓
    create_query_plan
      ↓
    generate_sql
      ↓
    validate_sql
      ├─ rejected → revise_sql → validate_sql (最多重试3次)
      └─ passed
            ↓
          explain_sql
            ├─ too_expensive → revise_sql
            └─ accepted
                  ↓
              execute_sql
                  ├─ error → repair_sql → validate_sql (最多重试2次)
                  └─ success
                        ↓
                  validate_result
                        ↓
                  compose_answer
                        ↓
                       END
    """

    # 创建节点处理器
    nodes = WorkflowNodes(
        catalog=catalog,
        semantic_layer=semantic_layer,
        planner=planner,
        generator=generator,
        guard=guard,
        executor=executor,
        validator=validator,
        composer=composer,
        compiler=compiler,
    )

    # 创建状态图
    workflow = StateGraph(AgentState)

    # 添加节点
    workflow.add_node("classify_request", nodes.classify_request)
    workflow.add_node("resolve_semantics", nodes.resolve_semantics)
    workflow.add_node("select_schema", nodes.select_schema)
    workflow.add_node("create_query_plan", nodes.create_query_plan)
    workflow.add_node("generate_sql", nodes.generate_sql)
    workflow.add_node("validate_sql", nodes.validate_sql)
    workflow.add_node("explain_sql", nodes.explain_sql)
    workflow.add_node("execute_sql", nodes.execute_sql)
    workflow.add_node("validate_result", nodes.validate_result)
    workflow.add_node("compose_answer", nodes.compose_answer)
    workflow.add_node("revise_sql", nodes.revise_sql)
    workflow.add_node("repair_sql", nodes.repair_sql)

    # 设置入口
    workflow.set_entry_point("classify_request")

    # 添加边（确定性流程）
    workflow.add_edge("classify_request", "resolve_semantics")
    workflow.add_edge("resolve_semantics", "select_schema")
    workflow.add_edge("select_schema", "create_query_plan")
    workflow.add_edge("create_query_plan", "generate_sql")
    workflow.add_edge("generate_sql", "validate_sql")

    # 添加条件边：SQL 验证
    workflow.add_conditional_edges(
        "validate_sql",
        should_revise_sql,
        {
            "revise": "revise_sql",
            "proceed": "explain_sql",
            "fail": END,
        }
    )

    # revise_sql 后返回 validate_sql
    workflow.add_edge("revise_sql", "validate_sql")

    # 添加条件边：EXPLAIN 分析
    workflow.add_conditional_edges(
        "explain_sql",
        should_proceed_to_execution,
        {
            "proceed": "execute_sql",
            "revise": "revise_sql",
        }
    )

    # 添加条件边：SQL 执行
    workflow.add_conditional_edges(
        "execute_sql",
        should_repair_sql,
        {
            "repair": "repair_sql",
            "proceed": "validate_result",
            "fail": END,
        }
    )

    # repair_sql 后返回 validate_sql（重新验证）
    workflow.add_edge("repair_sql", "validate_sql")

    # 结果验证后组织答案
    workflow.add_edge("validate_result", "compose_answer")

    # 答案组织完成后结束
    workflow.add_edge("compose_answer", END)

    return workflow


def should_revise_sql(state: AgentState) -> str:
    """
    条件判断：是否需要修订 SQL

    Returns:
        "revise": 需要修订（验证失败且未超过重试次数）
        "proceed": 继续（验证通过）
        "fail": 失败（超过最大重试次数）
    """
    if state["error"]:
        return "fail"

    if state["sql_validated"]:
        return "proceed"

    # 检查是否超过最大重试次数
    if state["retry_count"] >= state["max_retries"]:
        return "fail"

    return "revise"


def should_proceed_to_execution(state: AgentState) -> str:
    """
    条件判断：是否继续执行

    检查 EXPLAIN 结果，判断查询成本是否可接受

    Returns:
        "proceed": 继续执行
        "revise": 需要修订（成本过高）
    """
    explain_result = state.get("explain_result", {})
    warnings = explain_result.get("warnings", [])

    # 简化实现：如果有严重警告则要求修订
    critical_warnings = [
        w for w in warnings
        if "SEQ_SCAN" in str(w).upper() or "CARTESIAN" in str(w).upper()
    ]

    if critical_warnings and state["retry_count"] < state["max_retries"]:
        return "revise"

    return "proceed"


def should_repair_sql(state: AgentState) -> str:
    """
    条件判断：是否需要修复 SQL

    Returns:
        "repair": 需要修复（执行失败且未超过重试次数）
        "proceed": 继续（执行成功）
        "fail": 失败（超过最大重试次数）
    """
    if state["error"]:
        return "fail"

    if state.get("execution_error"):
        # 检查是否超过最大重试次数
        if state["retry_count"] >= state["max_retries"]:
            return "fail"
        return "repair"

    return "proceed"


class DataAgentWorkflow:
    """
    Data Agent 工作流封装

    提供便捷的执行接口
    """

    def __init__(
        self,
        catalog,
        semantic_layer,
        planner,
        generator,
        guard,
        executor,
        validator,
        composer,
        compiler=None,
    ):
        """初始化工作流"""
        self.graph = create_workflow_graph(
            catalog=catalog,
            semantic_layer=semantic_layer,
            planner=planner,
            generator=generator,
            guard=guard,
            executor=executor,
            validator=validator,
            composer=composer,
            compiler=compiler,
        )

        # 编译工作流
        self.app = self.graph.compile()

    def run(self, question: str, user_context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        执行工作流

        Args:
            question: 用户问题
            user_context: 用户上下文

        Returns:
            最终状态字典
        """
        # 创建初始状态
        initial_state = create_initial_state(question, user_context)

        # 执行工作流
        final_state = self.app.invoke(initial_state)

        return final_state

    async def arun(self, question: str, user_context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        异步执行工作流

        Args:
            question: 用户问题
            user_context: 用户上下文

        Returns:
            最终状态字典
        """
        # 创建初始状态
        initial_state = create_initial_state(question, user_context)

        # 异步执行工作流
        final_state = await self.app.ainvoke(initial_state)

        return final_state

    def stream(self, question: str, user_context: Dict[str, Any] = None):
        """
        流式执行工作流

        Args:
            question: 用户问题
            user_context: 用户上下文

        Yields:
            每个节点的状态更新
        """
        # 创建初始状态
        initial_state = create_initial_state(question, user_context)

        # 流式执行工作流
        for state in self.app.stream(initial_state):
            yield state

    async def astream(self, question: str, user_context: Dict[str, Any] = None):
        """
        异步流式执行工作流

        Args:
            question: 用户问题
            user_context: 用户上下文

        Yields:
            每个节点的状态更新
        """
        # 创建初始状态
        initial_state = create_initial_state(question, user_context)

        # 异步流式执行工作流
        async for state in self.app.astream(initial_state):
            yield state
