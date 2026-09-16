"""Expose the RDS Agent query workflow as one MCP stdio tool."""

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
import structlog

from .sdk import RDSAgent


class QueryResultLike(Protocol):
    """Result fields consumed by the MCP presentation adapter."""

    success: bool
    question: str
    sql: str | None
    data: list[dict] | None
    row_count: int
    execution_time: float
    error: str | None
    warnings: list[str] | None


Query = Callable[[str], QueryResultLike]


def _format_query_result(result: QueryResultLike) -> str:
    """Render one successful query result for a model-facing MCP response."""
    rows = result.data or []
    preview = rows[:20]
    lines = [
        "## RDS query result",
        "",
        f"Question: {result.question}",
        f"Rows: {result.row_count}",
        f"Execution time: {result.execution_time:.3f} seconds",
    ]

    if result.sql:
        lines.extend(["", "SQL:", "```sql", result.sql, "```"])

    lines.extend([
        "",
        "Data preview:",
        "```json",
        json.dumps(preview, ensure_ascii=False, indent=2, default=str),
        "```",
    ])
    if result.row_count > len(preview):
        lines.append(f"Preview truncated to {len(preview)} rows.")
    if result.warnings:
        lines.extend(["", "Warnings:", *[f"- {warning}" for warning in result.warnings]])

    return "\n".join(lines)


def create_mcp_server(query: Query) -> FastMCP:
    """Create an MCP server exposing only the coarse-grained RDS query tool."""
    server = FastMCP("rds-agent")

    @server.tool(name="query_data", structured_output=False)
    async def query_data(question: str) -> str:
        """Answer a natural-language business question using the configured read-only database."""
        result = await asyncio.to_thread(query, question)
        if not result.success:
            raise ToolError(result.error or "RDS query failed")
        return _format_query_result(result)

    return server


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the RDS Agent MCP stdio server.")
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=Path(os.environ.get("RDS_CONFIG_DIR", Path(__file__).parent.parent / "config")),
    )
    parser.add_argument("--db-path", default=os.environ.get("RDS_DB_PATH", ":memory:"))
    parser.add_argument("--metadata-db-path", default=os.environ.get("RDS_METADATA_DB_PATH"))
    parser.add_argument("--llm-model", default=os.environ.get("RDS_LLM_MODEL", "gpt-4"))
    return parser.parse_args()


def create_request_scoped_query(args: argparse.Namespace) -> Query:
    """Create a query callable that releases the shared DuckDB after each request."""

    def query(question: str) -> QueryResultLike:
        with RDSAgent(
            config_dir=args.config_dir,
            db_path=args.db_path,
            metadata_db_path=args.metadata_db_path,
            read_only=True,
            llm_model=args.llm_model,
        ) as agent:
            return agent.query(question)

    return query


def main() -> None:
    """Run the MCP server on stdin/stdout until the client disconnects."""
    # MCP stdio reserves stdout for JSON-RPC frames; route workflow logs to stderr.
    structlog.configure(logger_factory=structlog.PrintLoggerFactory(file=sys.stderr))
    args = _parse_args()
    create_mcp_server(create_request_scoped_query(args)).run(transport="stdio")


if __name__ == "__main__":
    main()
