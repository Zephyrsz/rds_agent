# RDS Agent

RDS Agent 是面向固定业务数据库的数据分析 Agent。它把自然语言问题转换成结构化语义查询，再生成经过安全校验的只读 SQL，并在 DuckDB 上执行。当前版本的 metadata 运行时以 SQLite 为唯一来源，YAML 只作为可审查、可迁移的 seed 配置。

当前分支已经完成 Phase 0-2：

- SQLite metadata schema、YAML -> SQLite 迁移和兼容 API。
- Domain、Entity、Measure、Metric、Dimension、Term、Filter、Example 等语义对象。
- `SemanticQuery` 查询契约和 `SemanticQueryCompiler` 确定性 SQL 编译。
- LangGraph 查询流程、SQLGuard、DuckDB 执行器和结果验证。
- Python SDK 和 MCP 主路径使用 SQLite；REST、Function Calling、LangChain Tool 仍是待统一的兼容入口。

## 快速开始

```bash
python3 -m venv venv
venv/bin/python -m pip install -r requirements.txt
venv/bin/python -m pytest -q
```

无需 LLM key 即可运行内置 DuckDB 样例和 SQLite 确定性编译路径：

```python
from integration.sdk import RDSAgent

with RDSAgent() as agent:
    result = agent.query("最近一个月华东地区的营收")
    if not result.success:
        raise RuntimeError(result.error)
    print(result.sql)
    print(result.data)
```

使用内置测试数据时，参考日期默认为 `2024-09-30`，上述查询返回华东营收 `3891.00`。

## 运行时架构

```text
config/*.yaml --迁移--> SQLite metadata.db
                              |
               SQLiteCatalog + SQLiteSemanticLayer
                              |
Natural language -> SemanticQuery -> SemanticQueryCompiler
                              |
                         SQLGuard
                              |
                         DuckDB
                              |
                    ResultValidator -> SDK / MCP
```

主要代码入口：

| 领域 | 路径 |
| --- | --- |
| SQLite metadata schema | `adapters/sqlite_schema.sql` |
| YAML <-> SQLite 迁移 | `adapters/yaml_to_sqlite.py` |
| SQLite Catalog | `adapters/sqlite_catalog.py` |
| SQLite SemanticLayer | `adapters/sqlite_semantic.py` |
| SemanticQuery 编译器 | `core/compiler.py` |
| Workflow 节点和图 | `workflow/nodes.py`、`workflow/graph.py` |
| Python SDK | `integration/sdk.py` |
| MCP server | `integration/mcp_server.py` |

## 文档入口

- [文档索引](docs/README.md)
- [项目介绍](docs/project-overview.md)
- [当前架构](docs/architecture/current.md)
- [语义层与 API 参考](docs/reference/semantic-layer-api.md)
- [Phase 0-2 路线图](docs/roadmap/phase-0-2.md)
- [SQLite metadata 生命周期](docs/guides/metadata-lifecycle.md)
- [外部集成指南](docs/guides/integrations.md)
- [变更记录](docs/changelog.md)
- [历史文档归档](docs/archive/README.md)

## 配置和数据

`config/` 中的 YAML 文件是 metadata seed：`schema.yaml`、`metrics.yaml`、`dimensions.yaml`、`terms.yaml`、`examples.yaml`、`domains.yaml`、`measures.yaml` 和 `filters.yaml`。生产环境建议先显式执行迁移，再通过 `metadata_db_path` 让 SDK 复用持久化 SQLite 文件：

```python
from integration.sdk import RDSAgent

with RDSAgent(
    config_dir="config",
    db_path="var/business.duckdb",
    metadata_db_path="var/metadata.db",
) as agent:
    result = agent.query("按地区统计销售额")
```

SQLite metadata 与 DuckDB 业务数据是两个不同的存储边界。修改 YAML 不会自动覆盖已存在且非空的 metadata DB，发布 metadata 时应显式执行迁移并验证差异。

## 当前边界

确定性 Compiler 当前支持基础聚合、比率、分类维度、时间范围、标准过滤器和安全 many-to-one Join。Policy Engine、Trusted Assets、完整同比环比、向量检索、多租户和 Web 配置编辑器尚未实现。REST、Function Calling 和 LangChain Tool 的初始化路径仍需统一到 SDK/SQLite 后才能作为生产入口。

当前工作树的测试基线：`venv/bin/python -m pytest -q`，共 85 个测试通过。
