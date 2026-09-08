---
document_type: documentation-archive-index
status: historical
last_verified: 2026-09-04
---

# 历史文档归档

这里保存 2026-09-04 之前或本次整理前生成的根目录和 `docs/` 文档。文件只做了目录移动，没有删除原始内容；它们用于追溯设计过程、交付记录和比较分析，不是当前实现的权威说明。

## 目录

- `root/`：原根目录的架构、设计、实现总结、迁移方案和操作说明。
- `docs/`：原 `docs/` 目录中的路线图、功能比较、优先级矩阵、配置模板和交付总结。

## 使用规则

1. 判断当前行为时，优先查看代码、`docs/architecture/current.md` 和 `docs/reference/semantic-layer-api.md`。
2. 判断历史意图或旧版本背景时，使用归档文件，并注明归档路径和日期。
3. 不在归档文件中追加当前实现说明；新变化应更新 current 文档、ADR、指南和 changelog。
4. 若未来有正式 Git tag，应在 `docs/releases/<tag>.md` 保存对应不可变快照，而不是修改本目录文件。

原始文件清单见 [`../document-inventory.md`](../document-inventory.md)。
