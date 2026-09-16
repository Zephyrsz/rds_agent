---
document_type: changelog
status: current
last_verified: 2026-09-04
source_revision: d612543 plus working-tree changes
---

# 变更记录

本文件只记录用户或运维可见的变化。实现过程、旧方案和完整分析保留在 `docs/archive/`，不在此重复。

## Unreleased - 2026-09-16

### Added

- 新增 AWS Oregon 远程部署架构文档和 `/app/rds_agent/start.sh` 统一服务入口。

## Unreleased - 2026-09-04

### Added

- 新增 SQLite metadata schema、YAML -> SQLite 迁移和 Catalog/SemanticLayer 兼容适配器。
- 新增 Domain、Entity、Measure、Filter 等 Phase 1 语义对象。
- 新增 `SemanticQuery` 和确定性 `SemanticQueryCompiler`，支持基础聚合、维度、过滤、时间范围、Join 安全和 LIMIT。
- SDK 与 MCP 查询主路径改为 SQLite metadata；内置 DuckDB 样例可在无 LLM key 时完成 smoke test。
- 新增当前架构、项目介绍、API 参考、集成指南、metadata 生命周期和 Phase 0-2 发布快照。

### Changed

- Workflow 的语义解析、Schema 选择、SQL 生成和结果验证节点接入结构化语义查询。
- SQLite metadata DB 已包含 5 张表、22 列、4 条 Join、6 个指标、5 个维度、11 个术语和 7 条 examples 的样例数据。

### Known limitations

- REST、Function Calling 和 LangChain Tool 尚未统一到 SDK/SQLite 主路径。
- Policy Engine、Trusted Assets、完整同比环比、多租户治理和持久化审计尚未实现。

验证：`venv/bin/python -m pytest -q` -> `85 passed`。
