"""Tests for the embedded RDS Agent SDK."""

from unittest.mock import Mock

from integration.sdk import RDSAgent


def test_query_returns_structured_failure_when_workflow_has_no_result():
    """A failed workflow with optional result fields must not raise another error."""
    agent = RDSAgent.__new__(RDSAgent)
    agent.workflow = Mock()
    agent.workflow.run.return_value = {
        "error": None,
        "status": "pending",
        "query_result": None,
        "answer": None,
    }

    result = agent.query("查询销售额")

    assert result.success is False
    assert result.error == "工作流未返回查询结果"
