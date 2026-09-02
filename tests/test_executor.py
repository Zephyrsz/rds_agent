"""Tests for query result serialization."""

from core.executor import QueryResult
from adapters.duckdb import create_sample_database


def test_query_result_to_dict_includes_rows():
    """Serialized workflow state must retain rows for SDK and MCP clients."""
    result = QueryResult(
        query_id="query-1",
        sql="SELECT 1 LIMIT 1",
        rows=[{"value": 1}],
        row_count=1,
        execution_time=0.01,
        columns=["value"],
    )

    assert result.to_dict()["rows"] == [{"value": 1}]


def test_sample_database_diagnostics_do_not_use_stdout(capsys):
    """Database startup diagnostics must not corrupt a stdio MCP stream."""
    adapter = create_sample_database()
    adapter.close()

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "示例数据库创建完成" in captured.err
