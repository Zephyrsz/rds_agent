---
document_type: adr
id: ADR-0001
title: SQLite 作为运行时 metadata source of truth
status: accepted
date: 2026-09-04
deciders: [RDS Agent maintainers]
supersedes: null
superseded_by: null
source_revision: d612543 plus working-tree changes
---

# ADR-0001：SQLite 作为运行时 metadata source of truth

## 背景

RDS Agent 原先在启动时直接加载 YAML 到内存。随着 Domain、Entity、Measure、Filter、FTS 和 Join 安全属性加入，metadata 需要结构化查询、幂等迁移、运行时缓存和可扩展版本字段。继续让每个入口直接读取 YAML 会造成 SDK、MCP、REST 和 Tool 的行为分叉。

## 选项

1. 继续以 YAML 为运行时唯一来源：编辑简单，但查询、全文检索、动态更新和多入口一致性较弱。
2. 以 SQLite 为运行时来源，YAML 作为迁移 seed：增加迁移和连接管理，但有稳定 schema、索引、FTS、事务和统一 API。
3. 直接引入外部服务数据库：可扩展性更强，但对当前单进程、固定数据库场景增加部署复杂度。

## 决策

采用选项 2：

- `SQLiteCatalog` 和 `SQLiteSemanticLayer` 是 SDK/MCP 主路径的运行时 metadata 适配器。
- `config/*.yaml` 只用于初次创建或显式更新 SQLite metadata。
- `SemanticQueryCompiler` 消费 SQLite 解析出的语义对象，生成确定性只读 SQL。
- 旧 YAML Catalog/SemanticLayer 保留给兼容入口，但不能被描述为 SQLite 主路径。

## 后果

正面影响：

- 语义查询、FTS、Join Graph 和扩展对象有统一存储。
- 同一 metadata DB 可被多个入口复用，迁移可在事务中重试。
- Compiler 能在 SQL 生成前检查未知对象、危险表达式和不安全 Join。

代价和边界：

- 需要维护 schema/migration 版本和 YAML/SQLite 差异发布流程。
- SQLite 解决的是 metadata 存储，不改变 DuckDB 作为业务查询库的角色。
- 现有 REST、Function Calling 和 LangChain 入口需要后续统一装配。
- 当前缓存和审计仍为进程内能力，不能视为完整多租户治理。

## 证据和链接

- `adapters/sqlite_schema.sql` 定义当前 metadata 表、索引和 FTS。
- `adapters/yaml_to_sqlite.py` 实现初始化和重复迁移。
- `integration/sdk.py` 将 SQLite Catalog、SemanticLayer 和 Compiler 注入 Workflow。
- Phase 0-2 测试基线：`venv/bin/python -m pytest -q`，85 passed。

后续若要改为外部 metadata 服务或改变 source of truth，必须新建 ADR 并在新决策中声明 `supersedes: ADR-0001`，不要改写本记录的决策历史。
