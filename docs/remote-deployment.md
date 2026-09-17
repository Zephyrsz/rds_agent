---
document_type: operations-guide
status: current
last_verified: 2026-09-16
source_revision: f922ca8 plus remote deployment configuration
---

# AWS Oregon 远程部署架构

本文说明 AWS Oregon 服务器上 `duckdb_tools`、`rds_agent` 和 DeepSeek Harness 的目录、共享数据、启动顺序和统一运维入口。

## 1. 运行拓扑

```text
浏览器
  │
  ├── :5175  DuckDB Tools Vite 前端
  │              │ /api 代理
  │              ▼
  └────────── :8001  DuckDB Tools FastAPI（唯一写入入口）
                       │
                       ├── 写入 /app/rds_agent/data/workspace.duckdb
                       └── 发布 /app/rds_agent/data/metadata.db

DeepSeek Harness :3090（仅监听 127.0.0.1）
  │ stdio MCP 子进程
  ▼
RDS Agent MCP Server
  ├── 每次 query_data 请求创建只读 RDSAgent
  ├── 读取同一个 workspace.duckdb
  ├── 读取同一个 metadata.db
  └── 请求结束关闭连接，释放 DuckDB 文件锁
```

三个服务的职责固定如下：

- `duckdb_tools` 负责 CSV/XLSX 导入、业务数据变更、语义草稿扫描和 SQLite metadata 发布。
- `rds_agent` 只读消费 DuckDB 和 SQLite metadata，并通过 SQLGuard 执行查询。
- DeepSeek Harness 提供 Web/MCP 宿主，将 `query_data` 暴露给模型。

RDS Agent 的 MCP 服务按请求打开和关闭 DuckDB，只读连接。这样 Harness 可以常驻，同时 DuckDB Tools 在没有正在执行的 Agent 查询时能够写入共享文件。业务导入和 Agent 查询应避免并发操作同一 DuckDB 文件。

## 2. 服务器目录与端口

| 项目 | 路径/端口 |
| --- | --- |
| RDS Agent | `/app/rds_agent` |
| DuckDB Tools | `/app/duckdb_tools` |
| DeepSeek Harness | `/app/deepseek-harness` |
| Python | `/home/ubuntu/venv_314/bin/python` |
| 共享 DuckDB | `/app/rds_agent/data/workspace.duckdb` |
| 共享 SQLite metadata | `/app/rds_agent/data/metadata.db` |
| DuckDB Tools API | `0.0.0.0:8001` |
| DuckDB Tools 前端 | `0.0.0.0:5175` |
| Harness | `127.0.0.1:3090` |

统一配置文件是 `/app/rds_agent/config/remote-stack.env`。DeepSeek key 放在未纳入 Git 的 `/app/rds_agent/config/remote-secrets.env`，权限应为 `600`。

## 3. 启动顺序

统一入口为 `/app/rds_agent/start.sh`，它委托 `/app/rds_agent/remote-stack.sh`：

1. `remote-service.sh start` 初始化共享 DuckDB 文件，并启动 FastAPI 后端 `8001`。
2. 等待 `/api/health` 成功后启动 Vite 前端 `5175`。
3. 检查共享 DuckDB 和 SQLite 文件存在。
4. 启动 DeepSeek Harness `3090`，加载 `deepseek-harness.remote.cordis.yml`。
5. Harness 启动 MCP stdio 子进程，指向 `/home/ubuntu/venv_314/bin/python -m integration.mcp_server`。
6. `status` 输出三个服务的 PID、端口和共享路径。

停止顺序相反：先停止 Harness，释放 RDS Agent 连接，再停止前端和后端。重启执行完整的 stop/start 流程。

## 4. 常用命令

```bash
cd /app/rds_agent

# 首次安装/更新依赖
./start.sh setup

# 启动全部服务
./start.sh start

# 查看状态
./start.sh status

# 重启全部服务
./start.sh restart

# 停止全部服务
./start.sh stop

# 查看最近日志
./start.sh logs
```

健康检查：

```bash
curl http://127.0.0.1:8001/api/health
curl -I http://127.0.0.1:5175/
curl -I http://127.0.0.1:3090/
```

Harness 页面需要 token；未带 token 时返回 `401` 属于正常行为。日志位置：

```text
/app/duckdb_tools/logs/remote/backend.log
/app/duckdb_tools/logs/remote/frontend.log
/app/rds_agent/logs/remote/harness.log
```

## 5. 首次配置

```bash
cd /app/rds_agent
cp config/remote-secrets.env.example config/remote-secrets.env
chmod 600 config/remote-secrets.env
$EDITOR config/remote-secrets.env
```

设置真实 key：

```bash
RDS_LLM_API_KEY=your-deepseek-api-key
```

不要将 `remote-secrets.env` 提交到 Git。启动前确认统一配置中的 `DUCKDB_TOOLS_DATABASE`、`RDS_DB_PATH` 和 `RDS_METADATA_DB_PATH` 指向同一组共享文件。

## 6. 数据和语义层流程

1. 访问 `http://<服务器地址>:5175`。
2. 在 DuckDB Tools 导入 CSV/XLSX。
3. 执行语义扫描，编辑和校验自动生成的草稿。
4. 发布语义层，写入 `metadata.db`。
5. 通过 Harness 使用 `query_data` 查询业务指标。

RDS Agent 不会从 YAML 覆盖已有 SQLite metadata；SQLite 是运行时语义层的来源。

## 7. 故障排查

- `workspace.duckdb` 不存在：执行 `./start.sh start`，脚本会先初始化写端数据库。
- Harness 启动失败：检查 `remote-secrets.env`、Harness 日志和 `/app/deepseek-harness` 依赖。
- `/api/database` 出现 DuckDB lock：确认没有正在执行的 Agent 查询，等待查询结束后重试。
- 端口冲突：检查 `ss -ltnp`，并修改 `remote-stack.env` 中的端口。
- Harness 外部访问：它只监听 `127.0.0.1`，使用 SSH 隧道，例如 `ssh -L 3090:127.0.0.1:3090 ubuntu@54.70.213.240`。
