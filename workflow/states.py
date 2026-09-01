"""
LangGraph workflow states definition
"""

from typing import TypedDict, Optional, Dict, List, Any
from enum import Enum


class WorkflowStatus(Enum):
    """工作流状态"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    REQUIRES_APPROVAL = "requires_approval"


class AgentState(TypedDict):
    """
    Agent 状态定义

    这个状态会在整个工作流中传递和更新
    """
    # 输入
    question: str  # 用户问题
    user_context: Optional[Dict]  # 用户上下文（权限、偏好等）

    # 问题理解
    question_type: Optional[str]  # 问题类型
    intent: Optional[Dict]  # 结构化意图

    # Schema 检索
    schema_context: Optional[Dict]  # 相关 Schema 信息
    relevant_tables: Optional[List[str]]  # 相关表

    # 查询计划
    query_plan: Optional[Dict]  # 查询计划
    current_step_index: int  # 当前执行的步骤索引

    # SQL 生成
    sql: Optional[str]  # 生成的 SQL
    sql_history: List[str]  # SQL 历史（用于重试）

    # 验证
    sql_validated: bool  # SQL 是否通过验证
    validation_errors: List[str]  # 验证错误

    # 执行
    explain_result: Optional[Dict]  # EXPLAIN 结果
    query_result: Optional[Dict]  # 查询结果
    execution_error: Optional[str]  # 执行错误

    # 结果验证
    result_validated: bool  # 结果是否通过验证
    validation_issues: List[Dict]  # 验证问题

    # 答案组织
    answer: Optional[Dict]  # 最终答案

    # 流程控制
    retry_count: int  # 重试次数
    max_retries: int  # 最大重试次数
    status: str  # 当前状态
    error: Optional[str]  # 错误信息

    # 审计
    audit_trail: List[Dict]  # 审计轨迹

    # 扩展
    metadata: Dict  # 元数据


# 默认状态
def create_initial_state(question: str, user_context: Optional[Dict] = None) -> AgentState:
    """创建初始状态"""
    return AgentState(
        question=question,
        user_context=user_context or {},
        question_type=None,
        intent=None,
        schema_context=None,
        relevant_tables=None,
        query_plan=None,
        current_step_index=0,
        sql=None,
        sql_history=[],
        sql_validated=False,
        validation_errors=[],
        explain_result=None,
        query_result=None,
        execution_error=None,
        result_validated=False,
        validation_issues=[],
        answer=None,
        retry_count=0,
        max_retries=3,
        status=WorkflowStatus.PENDING.value,
        error=None,
        audit_trail=[],
        metadata={},
    )
