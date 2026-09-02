"""Protocol tests for the RDS Agent MCP adapter."""

from dataclasses import dataclass, field
from datetime import timedelta

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import TextContent

from integration.mcp_server import create_mcp_server


@dataclass
class StubQueryResult:
    """Minimum query result returned by the MCP adapter's test backend."""

    success: bool
    question: str
    sql: str | None = None
    data: list[dict] | None = None
    row_count: int = 0
    execution_time: float = 0.0
    error: str | None = None
    warnings: list[str] = field(default_factory=list)


@pytest.mark.asyncio
async def test_server_exposes_only_query_data_and_calls_backend():
    questions = []

    def query(question: str) -> StubQueryResult:
        questions.append(question)
        return StubQueryResult(
            success=True,
            question=question,
            sql="SELECT SUM(net_amount) AS sales FROM order_items LIMIT 1000",
            data=[{"sales": 1234.5}],
            row_count=1,
            execution_time=0.125,
        )

    server = create_mcp_server(query)

    async with create_connected_server_and_client_session(
        server,
        read_timeout_seconds=timedelta(seconds=5),
    ) as session:
        listed = await session.list_tools()
        assert [tool.name for tool in listed.tools] == ["query_data"]
        assert listed.tools[0].inputSchema == {
            "properties": {"question": {"title": "Question", "type": "string"}},
            "required": ["question"],
            "title": "query_dataArguments",
            "type": "object",
        }

        result = await session.call_tool(
            "query_data",
            {"question": "最近一个月的销售额是多少？"},
        )

    assert result.isError is False
    assert questions == ["最近一个月的销售额是多少？"]
    assert len(result.content) == 1
    assert isinstance(result.content[0], TextContent)
    assert "1234.5" in result.content[0].text
    assert "SELECT SUM(net_amount)" in result.content[0].text


@pytest.mark.asyncio
async def test_query_failure_is_an_mcp_tool_error():
    def query(question: str) -> StubQueryResult:
        return StubQueryResult(
            success=False,
            question=question,
            error="query rejected by SQL policy",
        )

    server = create_mcp_server(query)

    async with create_connected_server_and_client_session(
        server,
        read_timeout_seconds=timedelta(seconds=5),
    ) as session:
        result = await session.call_tool("query_data", {"question": "删除订单表"})

    assert result.isError is True
    assert len(result.content) == 1
    assert isinstance(result.content[0], TextContent)
    assert "query rejected by SQL policy" in result.content[0].text
