---
document_type: operations-guide
status: current
last_verified: 2026-09-04
source_revision: d612543 plus working-tree changes
---

# Metadata 生命周期

## 存储职责

| 存储 | 职责 | 是否为查询时 source of truth |
| --- | --- | --- |
| `config/*.yaml` | 人工编辑、代码审查、迁移输入 | 否 |
| SQLite metadata DB | 运行时语义和 Catalog 查询 | 是（SDK/MCP） |
| DuckDB | 业务事实和维度数据 | 是（业务 SQL 执行） |

## Seed 文件

当前配置文件及迁移目标：

| 文件 | 内容 | SQLite 表 |
| --- | --- | --- |
| `schema.yaml` | 表、列、grain、实体和 Join | `tables`、`columns`、`entities`、`joins` |
| `metrics.yaml` | 面向用户的指标 | `metrics` |
| `dimensions.yaml` | 业务维度和值映射 | `dimensions` |
| `terms.yaml` | 术语、同义词和映射 | `terms`、FTS |
| `examples.yaml` | 问题、意图和示例 SQL | `examples`、FTS |
| `domains.yaml` | 业务域和允许范围 | `domains` |
| `measures.yaml` | 原子度量 | `measures` |
| `filters.yaml` | 可复用过滤器 | `filters` |

## 创建和升级

```python
from adapters.yaml_to_sqlite import migrate_yaml_to_sqlite

migrate_yaml_to_sqlite("config", "var/metadata.db")
```

迁移器负责初始化 schema、补充旧 DB 的新字段、写入对象、维护 FTS，并在失败时回滚。重复执行是幂等的，但不应把它当作无条件覆盖生产配置的发布批准。

SDK 初始化行为：

- `metadata_db_path=None` 或 `":memory:"`：创建临时 `.db` 文件，启动时从 YAML seed 迁移，关闭时删除。
- 指定路径不存在或为空：从 YAML 创建该文件。
- 指定路径已存在且非空：直接复用，不自动覆盖。

## 发布流程

1. 修改 `config/*.yaml` 并审查 diff。
2. 在临时 SQLite 文件执行迁移。
3. 检查 `metadata_versions` 和对象数量，验证引用完整性。
4. 使用示例问题运行 Compiler、SQLGuard 和 DuckDB smoke test。
5. 将 SQLite 文件发布到目标环境，或在部署阶段显式迁移。
6. 记录代码 revision、metadata revision、测试结果和文档 revision。

示例检查：

```bash
venv/bin/python -m pytest -q
```

## 缓存和更新

`SQLiteCatalog` 和 `SQLiteSemanticLayer` 含进程内缓存。外部更新 SQLite 后，应在安全窗口重建实例或显式调用两者的 `clear_cache()`；长生命周期服务不得假设外部更新会自动推送到已有对象。

## 回滚

SQLite 文件发布前保留上一份完整文件或备份；发现 schema、Join 或指标错误时，优先回滚到上一份 metadata 文件，再修正 YAML 并生成新的迁移结果。不要直接手工改写已经对外使用的历史发布文件。

## 常见错误

- 修改 YAML 后复用旧的非空 metadata DB，导致查询仍使用旧口径。
- 把 metadata SQLite DB 当成业务查询数据库；业务表仍在 DuckDB。
- 只验证对象数量，不验证指标表达式、Join 基数和示例查询结果。
- 让不同入口分别初始化 YAML 和 SQLite，造成同一问题得到不同 SQL。
