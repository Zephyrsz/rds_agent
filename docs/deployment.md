# RDS Agent、DuckDB Tools 与 DeepSeek Harness 部署

RDS Agent 使用 SQLite runtime metadata 和只读 DuckDB 连接，为 DeepSeek Harness 提供 `query_data` MCP 工具。DuckDB Tools 负责导入数据、修改 DuckDB 和发布语义 metadata。

## 目录与共享文件

```text
/Users/rgwei/pj/pj_data/duckdb_tools/data/workspace.duckdb
/Users/rgwei/pj/pj_data/rds_agent/var/metadata.db
```

RDS Agent 和 DuckDB Tools 必须指向同一组文件。RDS Agent 不负责写入业务数据。

## 配置环境

```bash
export DUCKDB_TOOLS_ROOT=/Users/rgwei/pj/pj_data/duckdb_tools
export RDS_AGENT_ROOT=/Users/rgwei/pj/pj_data/rds_agent
export HARNESS_ROOT=/Users/rgwei/pj/pj_agent/deepseek-harness
export RDS_DB_PATH="$DUCKDB_TOOLS_ROOT/data/workspace.duckdb"
export RDS_METADATA_DB_PATH="$RDS_AGENT_ROOT/var/metadata.db"
export RDS_CONFIG_DIR="$RDS_AGENT_ROOT/config"
```

模型配置：

```bash
export RDS_LLM_API_KEY="$DEEPSEEK_API_KEY"
export RDS_LLM_BASE_URL=https://api.deepseek.com
export RDS_LLM_MODEL=deepseek-chat
```

`RDS_DB_PATH` 必须指向已存在的 DuckDB 文件；不存在时 RDS Agent 会直接报错。已有文件会以 `read_only=True` 打开。

## 安装与启动

```bash
cd "$RDS_AGENT_ROOT"
venv/bin/python -m pip install -r requirements.txt

cd "$DUCKDB_TOOLS_ROOT"
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
cd frontend && npm install
cd ..
./start.sh start
```

先通过 DuckDB Tools 导入 CSV/XLSX，完成语义扫描、编辑、校验和发布，再启动 Harness：

```bash
cd "$HARNESS_ROOT"
pnpm dsh --profile web \
  --patch "$RDS_AGENT_ROOT/integration/deepseek-harness.cordis.yml" \
  --no-open
```

Harness overlay 会启动：

```text
./venv/bin/python -m integration.mcp_server
```

MCP 工具为 `query_data`。

## 启动契约

- `RDS_DB_PATH`：共享 DuckDB 文件。
- `RDS_METADATA_DB_PATH`：共享 SQLite metadata 文件。
- `RDS_CONFIG_DIR`：YAML seed 配置目录；非空 metadata DB 不会被 YAML 自动覆盖。
- `RDS_LLM_API_KEY`、`RDS_LLM_BASE_URL`、`RDS_LLM_MODEL`：模型配置。

运行时语义读取 `SQLiteCatalog` 和 `SQLiteSemanticLayer`。DuckDB Tools 发布后，RDS Agent 无需重新生成 YAML。

## 验证

```bash
cd "$RDS_AGENT_ROOT"
venv/bin/python -m pytest -q
```

共享连接探针：

```bash
venv/bin/python - <<'PY'
import os
from integration.sdk import RDSAgent

agent = RDSAgent(db_path=os.environ["RDS_DB_PATH"], metadata_db_path=os.environ["RDS_METADATA_DB_PATH"])
assert agent.db_adapter.read_only is True
assert type(agent.catalog).__name__ == "SQLiteCatalog"
assert type(agent.semantic_layer).__name__ == "SQLiteSemanticLayer"
print("shared runtime: ok")
agent.close()
PY
```

## 安全边界

- DuckDB Tools 执行数据导入和修改。
- RDS Agent 仅执行经过 SQLGuard 校验的查询。
- RDS Agent 的 DuckDB 连接只读；对共享文件执行写入会被 DuckDB 拒绝。
- SQLite metadata 的发布由 DuckDB Tools 完成，RDS Agent 只消费已发布内容。

## 停止与排错

```bash
cd "$DUCKDB_TOOLS_ROOT" && ./start.sh stop
```

- `query_data` 不可用：检查 Harness patch 路径、`RDS_AGENT_ROOT` 和虚拟环境。
- 找不到表或指标：检查两个进程是否使用同一个 `RDS_METADATA_DB_PATH`。
- 数据为空：检查 `RDS_DB_PATH` 是否与 DuckDB Tools 的 `DUCKDB_TOOLS_DATABASE` 完全一致。
- 不要在共享生产配置中使用 `:memory:` 或相对路径。
