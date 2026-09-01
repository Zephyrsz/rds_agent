"""
Test workflow execution
"""

import pytest
from unittest.mock import Mock, MagicMock
from workflow.states import create_initial_state, AgentState
from workflow.nodes import WorkflowNodes


@pytest.fixture
def mock_components():
    """创建 mock 组件"""
    return {
        'catalog': Mock(),
        'semantic_layer': Mock(),
        'planner': Mock(),
        'generator': Mock(),
        'guard': Mock(),
        'executor': Mock(),
        'validator': Mock(),
        'composer': Mock(),
    }


@pytest.fixture
def nodes(mock_components):
    """创建工作流节点"""
    return WorkflowNodes(**mock_components)


def test_create_initial_state():
    """测试创建初始状态"""
    question = "测试问题"
    state = create_initial_state(question)

    assert state["question"] == question
    assert state["retry_count"] == 0
    assert state["max_retries"] == 3
    assert state["status"] == "pending"
    assert state["sql_history"] == []
    assert state["audit_trail"] == []


def test_classify_request_node(nodes, mock_components):
    """测试分类请求节点"""
    # 设置 mock
    mock_components['semantic_layer'].extract_intent.return_value = {
        "question_type": "simple_query",
        "metrics": ["sales_amount"],
        "dimensions": [],
    }

    # 创建初始状态
    state = create_initial_state("测试问题")

    # 执行节点
    result = nodes.classify_request(state)

    # 验证
    assert result["question_type"] == "simple_query"
    assert result["intent"] is not None
    assert len(result["audit_trail"]) == 1


def test_validate_sql_node_pass(nodes, mock_components):
    """测试 SQL 验证节点 - 通过"""
    # 设置 mock
    mock_components['guard'].validate_sql.return_value = (True, None)

    # 创建状态
    state = create_initial_state("测试问题")
    state["sql"] = "SELECT * FROM orders LIMIT 100"

    # 执行节点
    result = nodes.validate_sql(state)

    # 验证
    assert result["sql_validated"] == True
    assert result["validation_errors"] == []


def test_validate_sql_node_fail(nodes, mock_components):
    """测试 SQL 验证节点 - 失败"""
    # 设置 mock
    mock_components['guard'].validate_sql.return_value = (False, "缺少 LIMIT")

    # 创建状态
    state = create_initial_state("测试问题")
    state["sql"] = "SELECT * FROM orders"

    # 执行节点
    result = nodes.validate_sql(state)

    # 验证
    assert result["sql_validated"] == False
    assert len(result["validation_errors"]) == 1
    assert "LIMIT" in result["validation_errors"][0]


def test_execute_sql_node_success(nodes, mock_components):
    """测试 SQL 执行节点 - 成功"""
    # 创建 mock 查询结果
    mock_result = Mock()
    mock_result.success = True
    mock_result.query_id = "test-query-id"
    mock_result.row_count = 10
    mock_result.execution_time = 0.5
    mock_result.to_dict.return_value = {
        "query_id": "test-query-id",
        "row_count": 10,
        "execution_time": 0.5,
    }

    # 设置 mock
    mock_components['executor'].execute.return_value = mock_result

    # 创建状态
    state = create_initial_state("测试问题")
    state["sql"] = "SELECT * FROM orders LIMIT 100"

    # 执行节点
    result = nodes.execute_sql(state)

    # 验证
    assert result["query_result"] is not None
    assert result["execution_error"] is None


def test_execute_sql_node_failure(nodes, mock_components):
    """测试 SQL 执行节点 - 失败"""
    # 创建 mock 查询结果
    mock_result = Mock()
    mock_result.success = False
    mock_result.error = "Table not found"
    mock_result.query_id = "test-query-id"
    mock_result.to_dict.return_value = {"query_id": "test-query-id"}

    # 设置 mock
    mock_components['executor'].execute.return_value = mock_result

    # 创建状态
    state = create_initial_state("测试问题")
    state["sql"] = "SELECT * FROM nonexistent_table LIMIT 100"

    # 执行节点
    result = nodes.execute_sql(state)

    # 验证
    assert result["execution_error"] is not None
    assert "not found" in result["execution_error"].lower()


def test_retry_limit(nodes, mock_components):
    """测试重试次数限制"""
    # 设置 mock - 始终失败
    mock_components['guard'].validate_sql.return_value = (False, "验证失败")

    # 创建状态
    state = create_initial_state("测试问题")
    state["sql"] = "SELECT * FROM orders"
    state["retry_count"] = 3  # 已达到最大重试次数

    # 执行验证节点
    result = nodes.validate_sql(state)

    # 应该仍然标记为验证失败
    assert result["sql_validated"] == False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
