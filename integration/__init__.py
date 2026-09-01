"""
RDS Agent Integration Module

提供多种方式将 RDS Agent 集成到外部 Agent 中：

1. MCP Server - 适用于支持 MCP 协议的 Agent（如 Claude Desktop）
2. RESTful API - 通用的 HTTP API，适用于任何支持 HTTP 的 Agent
3. LangChain Tool - 适用于基于 LangChain 的 Agent
4. Function Calling - 适用于使用 OpenAI/Anthropic Function Calling 的 Agent
5. Python SDK - 适用于 Python Agent 的嵌入式集成
"""

from .sdk import RDSAgent, QueryResult, quick_query

__all__ = [
    "RDSAgent",
    "QueryResult",
    "quick_query",
]
