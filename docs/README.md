---
document_type: documentation-index
status: current
last_verified: 2026-09-04
source_revision: d612543 plus working-tree changes
---

# RDS Agent 文档

这里是 RDS Agent 的唯一技术文档入口。当前文档描述代码和配置在 `2026-09-04` 的实际状态；历史分析、旧设计和交付总结位于 [`archive/`](archive/README.md)，不作为当前行为依据。

## 当前文档

| 文档 | 类型 | 用途 |
| --- | --- | --- |
| [项目介绍](project-overview.md) | Current overview | 产品范围、能力边界和快速上手 |
| [当前架构](architecture/current.md) | Current architecture | 组件、数据流、部署边界和约束 |
| [ADR-0001 SQLite metadata runtime](architecture/adr/0001-sqlite-metadata-runtime.md) | ADR | SQLite 作为运行时 metadata source of truth 的决策 |
| [语义层与 API 参考](reference/semantic-layer-api.md) | API/behavior reference | 当前语义对象、SDK、Compiler 和 Agent 调用链 |
| [Phase 0-2 路线图](roadmap/phase-0-2.md) | Feature/roadmap | 当前阶段的实施范围、验收标准和状态 |
| [Metadata 生命周期](guides/metadata-lifecycle.md) | Operations guide | YAML seed、SQLite 迁移、持久化和发布注意事项 |
| [外部集成指南](guides/integrations.md) | Integration guide | SDK、MCP、REST、Function Calling、LangChain 和 Harness |
| [AWS Oregon 远程部署](remote-deployment.md) | Operations guide | 三个服务的架构、启动顺序、配置和统一运维入口 |
| [变更记录](changelog.md) | Changelog | 用户和运维可见的版本变化 |
| [Phase 0-2 快照](releases/2026-09-04-phase-0-2.md) | Release snapshot | 当前工作树对应的可审查交付快照 |

## 文档规则

- `architecture/current.md` 是当前架构唯一权威位置；架构决策放入 `architecture/adr/`，不在 current 文档中维护历史叙事。
- API 和行为参考必须与代码一起更新。当前 API 文档是手工维护的行为参考，不宣称由 OpenAPI 或 docstring 自动生成。
- `changelog.md` 只记录面向用户或运维的变化，不作为实现日志。
- `releases/` 保存不可变快照；历史快照不得反向引用会改变含义的 `current` 内容作为唯一证据。
- `archive/` 中的文件仅供追溯，若内容与当前代码冲突，以代码和当前文档为准。
- 当前没有生效的合规政策文件，因此没有建立 `compliance/` 目录。

## 阅读顺序

新成员：项目介绍 -> 当前架构 -> Metadata 生命周期 -> API 参考。

集成开发：API 参考 -> 外部集成指南 -> Phase 0-2 路线图。

维护者：当前架构 -> ADR -> 变更记录 -> 发布快照 -> 文档清单。

完整资产处理记录见 [文档清单](document-inventory.md)。
