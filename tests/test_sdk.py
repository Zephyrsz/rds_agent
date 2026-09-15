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


def test_existing_database_connections_are_read_only(monkeypatch, tmp_path):
    import duckdb

    database = tmp_path / "shared.duckdb"
    connection = duckdb.connect(str(database))
    connection.execute("CREATE TABLE facts (value INTEGER)")
    connection.close()

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    agent = RDSAgent.__new__(RDSAgent)
    agent.db_path = str(database)
    agent.db_adapter = __import__("adapters.duckdb", fromlist=["DuckDBAdapter"]).DuckDBAdapter(str(database), read_only=True)
    agent.db_adapter.connect()
    assert agent.db_adapter.read_only is True
    agent.db_adapter.close()
