---
document_type: integration-guide
status: current
last_verified: 2026-09-04
source_revision: d612543 plus working-tree changes
---

# 外部集成指南

## 选择入口

| 场景 | 入口 | 推荐度 | 当前 metadata 路径 |
| --- | --- | --- | --- |
| 同一 Python 进程 | `RDSAgent` | 推荐 | SQLite + Compiler |
| 支持 MCP 的 Agent | `query_data` | 推荐 | SQLite + Compiler |
| 需要 HTTP | FastAPI REST | 兼容 | YAML + LLM，待统一 |
| OpenAI/Anthropic tool call | Function Calling | 示例 | YAML + LLM，待统一 |
| LangChain Agent | `rds_query` / `rds_schema` | 示例 | YAML + LLM，待统一 |

上层 Agent 只需要提供自然语言问题，不应自行拼接物理表名和 SQL。需要先探索能力时，SDK 提供 `get_schema()`、`get_metrics()` 和 `get_dimensions()`。

## Python SDK

```python
from integration.sdk import RDSAgent

with RDSAgent(
    db_path=":memory:",
    metadata_db_path="var/metadata.db",
) as agent:
    result = agent.query(
        "最近一个月华东地区的营收",
        user_context={"reference_date": "2024-09-30"},
    )
    print(result.sql)
    print(result.data)
```

公开方法：`query()`、`aquery()`、`get_schema()`、`get_metrics()`、`get_dimensions()`、`get_statistics()`、`close()`。完整字段和错误协议见 [语义层与 API 参考](../reference/semantic-layer-api.md)。

## MCP stdio

启动：

```bash
venv/bin/python -m integration.mcp_server \
  --config-dir /path/to/config \
  --db-path /path/to/business.duckdb
```

MCP 只暴露：

```text
query_data(question: string) -> Markdown string
```

结果包含 SQL、行数、执行时间、最多 20 行数据预览和 warning。失败会通过 `ToolError` 返回。可以设置 `RDS_CONFIG_DIR`、`RDS_DB_PATH` 和 `RDS_LLM_MODEL`。

当前 CLI 没有 `metadata_db_path` 参数；如需跨进程复用 SQLite metadata，应在自定义启动代码中构造 `RDSAgent(metadata_db_path=...)`，或后续补充 CLI 参数。

## REST

当前路径：`GET /health`、`POST /api/v1/query`、`GET /api/v1/schema`、`GET /api/v1/metrics`、`GET /api/v1/dimensions`。查询请求包含 `question`、可选 `user_id` 和 `context`。

REST 当前直接初始化 YAML Catalog/SemanticLayer，并无条件构造 ChatOpenAI；`verify_api_key` 和 CORS 仍是开发占位配置。生产化前必须改为封装 SDK/SQLite、接入真实认证、限制 CORS、修复 dataclass Schema 序列化，并补充持久化 metadata 参数。

## Function Calling

`integration.function_calling.FUNCTIONS` 定义：

- `query_database(question)`
- `get_database_schema(table_name?)`
- `get_available_metrics()`

`RDSAgentFunctionCalling.call_function()` 负责分发函数调用。当前包装器沿用 YAML + LLM 初始化，且 Schema 列对象序列化仍有 dataclass/字典兼容问题。统一时应直接委托 `RDSAgent`，并采用 provider 最新的 tool schema。

## LangChain Tool

当前工具名是 `rds_query` 和 `rds_schema`，支持同步 `_run()` 和异步 `_arun()`。工具输出 Markdown 文本，查询结果最多展示前 5 行。实现仍使用 YAML + LLM；示例中存在 `RDSSchemaTool` 与实际类名 `RDSSchematool` 的大小写不一致，使用前应修正。

## DeepSeek Harness

仓库保留 `integration/deepseek-harness.cordis.yml` 作为 MCP stdio patch。Harness 子进程应使用项目虚拟环境：

```bash
pnpm dsh --profile web \
  --patch /path/to/rds_agent/integration/deepseek-harness.cordis.yml
```

密钥只通过进程环境或凭据管理器传入，不写入 YAML、README 或 metadata。更完整的旧版 Harness 操作记录保存在 `docs/archive/root/`；当前架构仍以 SDK/MCP SQLite 路径为准。
