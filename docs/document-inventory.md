---
document_type: documentation-inventory
status: current
last_verified: 2026-09-04
source_revision: d612543 plus working-tree changes
---

# 文档资产清单

## 处理规则

本次清理以 `project-doc-versioning` 的文档分类为准：当前架构和项目介绍建立唯一 current 位置；架构决策进入 ADR；接口和运行说明跟随代码；旧分析、交付和实现总结移动到 archive；正式发布通过 releases 快照记录。没有发现既有 ADR、release tag、生成文档配置或合规政策。

## 当前权威文件

| 文件 | 分类 | source of truth / 维护规则 |
| --- | --- | --- |
| `README.md` | Project entrypoint | 当前项目介绍和最短上手路径 |
| `docs/project-overview.md` | Current overview | 代码、配置和测试共同校验 |
| `docs/architecture/current.md` | Current architecture | 当前组件、数据流、边界；不承载历史决策 |
| `docs/architecture/adr/0001-sqlite-metadata-runtime.md` | ADR | SQLite runtime 决策；未来只通过新 ADR supersede |
| `docs/reference/semantic-layer-api.md` | API/behavior reference | 与公开 API 和 Workflow 实现同步 |
| `docs/roadmap/phase-0-2.md` | Feature/roadmap | 当前 Phase 0-2 范围和验收状态 |
| `docs/guides/metadata-lifecycle.md` | Operations guide | 迁移、发布、回滚和缓存行为 |
| `docs/guides/integrations.md` | Integration guide | SDK、MCP 和兼容入口行为 |
| `docs/changelog.md` | Changelog | 用户/运维可见变化，每个 release 一节 |
| `docs/releases/2026-09-04-phase-0-2.md` | Working-tree snapshot | 形式化发布前的证据快照 |

## 逐文件归档分类

| 原文件 | 分类 | 处理 |
| --- | --- | --- |
| `ARCHITECTURE.md` | 旧 current architecture | 归档；由 `docs/architecture/current.md` 替代 |
| `BRANCH_SUMMARY.md` | 实现/交付总结 | 归档 |
| `COMMIT_INSTRUCTIONS.md` | 一次性操作说明 | 归档 |
| `DUCKDB_METADATA_GUIDE.md` | 旧 feature/operations guide | 归档；当前存储边界写入新指南 |
| `FILE_LIST.md` | 一次性交付清单 | 归档 |
| `FINAL_README.md` | 旧项目入口副本 | 归档 |
| `FINAL_SUMMARY.md` | 实现/交付总结 | 归档 |
| `IMPLEMENTATION_COMPLETE.md` | 实现状态快照 | 归档 |
| `IMPLEMENTATION_STATUS.md` | 实现状态快照 | 归档 |
| `INTEGRATION_GUIDE.md` | 旧 integration guide | 归档；由 `docs/guides/integrations.md` 替代 |
| `METADATA_API_FLOW.md` | 旧架构/API 分析 | 归档；当前接口合并至 reference/current |
| `PROJECT_SUMMARY.md` | 旧项目介绍副本 | 归档 |
| `QUICK_REFERENCE.md` | 旧 feature reference | 归档 |
| `README_IMPLEMENTATION.md` | 实现/交付总结 | 归档 |
| `SQLITE_MIGRATION_DESIGN.md` | 历史设计 | 归档；核心决策提炼为 ADR-0001 |
| `WORK_COMPLETED.md` | 实现/交付总结 | 归档 |
| `dbgpt_deepagents_fixed_database_architecture.md` | 外部/候选架构设计 | 归档 |
| `rds_agent_project_design.md` | 初始项目设计 | 归档 |
| `功能对比分析报告.md` | 历史功能比较 | 归档 |
| `docs/README_语义层演进分析.md` | 旧文档索引 | 归档；由 `docs/README.md` 替代 |
| `docs/SQLITE_USAGE.md` | 旧 feature/operations guide | 归档 |
| `docs/genie_semantic_layer_roadmap.md` | 历史产品路线图 | 归档 |
| `docs/交付总结.md` | 一次性交付总结 | 归档 |
| `docs/功能对比分析报告.md` | 历史功能比较 | 归档 |
| `docs/实施优先级矩阵.md` | 历史规划材料 | 归档 |
| `docs/执行摘要_一页纸.md` | 历史决策摘要 | 归档 |
| `docs/配置模板和示例.md` | 历史设计/模板 | 归档 |

上述 27 份文件保存在 `docs/archive/root/` 和 `docs/archive/docs/`，未删除内容。

## 保留并升级为 current 的文件

| 原文件 | 当前文件 | 分类 |
| --- | --- | --- |
| `docs/当前版本语义层实现与API调用指南.md` | `docs/reference/semantic-layer-api.md` | API/behavior reference |
| `docs/phase_0_2_implementation_roadmap.md` | `docs/roadmap/phase-0-2.md` | Feature/roadmap |

## 版本状态

- 当前代码没有 Git tag；基线提交为 `d612543`，工作树含 Phase 0-2 实现和本次文档整理。
- 当前文档使用 `last_verified: 2026-09-04`，并明确标注 `d612543 plus working-tree changes`。
- `docs/releases/2026-09-04-phase-0-2.md` 是工作树快照，不冒充正式产品版本。
- 未来正式发布需要新增带 tag 的 release manifest，记录不可变代码和文档 revision。
