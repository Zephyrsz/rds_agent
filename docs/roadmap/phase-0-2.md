---
document_type: feature-roadmap
status: completed
last_verified: 2026-09-04
source_revision: d612543 plus working-tree changes
scope: phase-0-2
---

# RDS Agent Phase 0-2 实施路线图

## 目标

在保留现有 SDK、MCP、REST 和 YAML 兼容能力的前提下，完成 RDS Agent 的 Phase 0-2：

```text
YAML 种子配置
    -> SQLite metadata store
    -> 结构化 Semantic Query
    -> 语义图与 Join 安全校验
    -> 确定性 SQL 编译
    -> SQLGuard / DuckDB 执行
```

本阶段不实现 Policy Engine、Trusted Assets、向量检索、完整 Ontology 和 Web 配置编辑器。

## 架构约束

1. SQLite 是运行时 metadata 的唯一存储；Agent 查询、Catalog、SemanticLayer 均从 SQLite 读取。
2. 当前 `config/*.yaml` 只作为可版本控制的种子输入和迁移来源，不作为运行时查询源。
3. 初始 5 个 YAML seed 文件和现有 API 保持向后兼容；新增 Domain/Measure/Filter 等 seed 采用可选字段和兼容迁移。
4. LLM（如启用）只负责自然语言理解；最终 SQL 由确定性编译器生成。
5. 所有最终 SQL 仍必须经过 SQLGuard 和 DuckDB 只读执行链路。
6. 相对时间测试固定使用示例数据的业务日期 `2024-09-30`，生产环境由 Domain 或请求上下文提供时区和参考时间。

## Phase 0：恢复运行基线（1 周）

### 工作项

- 修复 `SQLiteCatalog` 与 `core.catalog` 的数据模型兼容性（`ColumnInfo`、`JoinPath`）。
- 补齐 SQLite SemanticLayer 所需的 `ExampleSQL` 和扩展指标字段。
- 修复 YAML -> SQLite 迁移：术语对象、example 的 `question_type`、新字段和重复迁移行为。
- 增加 SDK 的 SQLite metadata source 选择；默认示例运行也使用 SQLite metadata。
- 建立端到端 smoke test：SQLite metadata -> SemanticLayer -> Compiler -> DuckDB。
- 运行完整测试集，消除 collection error。

### 验收标准

- `venv/bin/python -m pytest -q` 无 collection error。
- 5 张示例业务表、4 条 Join、6 个指标、5 个维度、11 个术语和 7 条 examples 可从 SQLite 读取。
- 现有 YAML/SQLite adapter API 测试保持通过。

## Phase 1：语义契约落地（2 周）

### Metadata 对象

- `domains`：首个 Domain 为 `retail_sales`，包含允许表、指标、默认时区和币种。
- `semantic_models`/表扩展：为核心表增加 `grain` 和主实体信息。
- `entities`：表达 `order`、`order_line`、`customer`、`product`、`region`。
- `measures`：从原子聚合中抽取 `net_revenue`、`order_count`、`customer_count`、`quantity`。
- `metrics`：保留旧指标别名，同时支持 `simple`、`ratio`、`period_over_period` 引用式定义。
- `filters`：抽取 `valid_order` 等可复用业务过滤器。
- `dimensions`：增加维度类型、时间粒度和 Domain 关联。
- `terms`：增加语义对象映射、排除词、上下文和优先级。

### 关键口径修正

- `avg_order_amount` 改为 `net_revenue / order_count`，避免把订单行平均误当成订单平均。
- 明确 `sales_amount` 与 `gmv` 的状态、时间字段和退款口径差异。
- 明确 `customer_count` 是否只统计有效订单客户；默认采用经过 `valid_order` 过滤的客户口径。

### 验收标准

- 所有运行时语义对象可通过 SQLite API 按唯一名称解析。
- 每个核心 measure 都有聚合函数、粒度、可加性和数据类型。
- 重复的有效订单条件只在 `filters` 中维护，指标通过引用使用。
- 术语“营收/收入/销售额”能够解析到确定的指标或返回歧义信息。

## Phase 2：语义查询与确定性编译（3 周）

### SemanticQuery DSL

定义稳定的结构化查询对象：

```yaml
metrics: [sales_amount]
dimensions: [region]
filters:
  region: 华东
  semantic_filters: [valid_order]
time_range: 最近一个月
order_by:
  field: sales_amount
  direction: desc
limit: 1000
```

### 编译流程

```text
SemanticQuery
    -> 指标/维度/过滤器解析
    -> 需要的事实表与维度表
    -> Join Graph 路径选择
    -> 基数与 Fan-out 检查
    -> 时间边界展开
    -> SELECT / GROUP BY / ORDER BY / LIMIT
    -> SQLGuard
```

### 编译器首版支持

- 单事实表和多个维度表。
- `SUM`、`COUNT`、`COUNT DISTINCT`、`AVG`。
- 基础 categorical dimension 和时间范围。
- Many-to-one Join；未知或 many-to-many 路径默认拒绝。
- 标准 Filter 和维度值映射。
- 参数化的时间边界和固定 LIMIT。

### 工作流接入

- `extract_intent` 输出可转换为 `SemanticQuery`。
- `QueryPlanner` 保留现有步骤模型，但数据步骤携带 SemanticQuery。
- `SQLGenerator` 在有编译器时调用确定性编译器；旧模式继续支持 LLM fallback。
- `select_schema` 根据已解析指标和维度补齐所需表，不依赖纯关键词命中。
- 结果验证节点调用真实 `ResultValidator`，保留警告和审计信息。

### 验收标准

- 同一 SemanticQuery 在相同 metadata 下生成稳定 SQL，不依赖 LLM 输出。
- “最近一个月华东地区的营收”可在示例 DuckDB 上执行并返回结果。
- 生成 SQL 必须包含正确事实表、维度 Join、过滤条件、时间边界、GROUP BY 和 LIMIT。
- 未知指标/维度、缺少 Join、many-to-many 或聚合粒度不安全时明确失败。
- 7 条现有 examples 至少完成结构化意图和 SQL 执行 smoke test；comparison/trend 对比逻辑的完整扩展留给后续时间智能阶段。

## 测试策略

### 单元测试

- Core semantic model 和 SQLite metadata API。
- YAML -> SQLite migration。
- 中文/英文同义词、维度值和日历时间解析。
- Join path、基数和编译器拒绝条件。
- SQLGuard 兼容性和只读限制。

### 集成测试

固定使用 `adapters.duckdb.create_sample_database()`：

1. 迁移 `config/` 到临时 SQLite metadata DB。
2. 从 SQLite 创建 Catalog 与 SemanticLayer。
3. 从自然语言得到 SemanticQuery。
4. 编译 SQL。
5. 通过 SQLGuard。
6. 在示例 DuckDB 执行。
7. 校验列、行数、关键数值和审计字段。

### 完成条件

- 全量测试通过。
- 新增集成测试至少覆盖总销售额、地区销售额、产品类别销售额、订单数和时间范围。
- 不以“代码已添加”替代验收；最终报告必须列出实际测试命令和结果。

## 暂不纳入本次范围

- `policies.yaml` 的行级权限、列脱敏和最小分组人数。
- `trusted_assets.yaml` 和审批生命周期。
- Benchmark Runner、CI 评测报告和用户反馈闭环。
- 同比/环比/YTD/MTD 的完整窗口 SQL。
- 向量数据库、自动 Join 推断、多 Domain 路由和双层语义覆盖。

## 实施状态（2026-09-04）

Phase 0-2 已完成并以 SQLite metadata 作为运行时唯一来源：

- YAML -> SQLite 迁移支持旧 schema 升级、Domain/Entity/Measure/Filter 和幂等重复迁移。
- SQLite Catalog/SemanticLayer 支持 grain、Join 安全属性、指标/维度扩展字段、同义词、维度值和固定参考日期解析。
- 新增 `SemanticQueryCompiler`，确定性生成安全 SQL，支持 SUM、COUNT、COUNT DISTINCT、AVG/Ratio、维度映射、时间半开区间、GROUP BY、ORDER BY、LIMIT 和危险 Join 拒绝。
- Workflow 的解析、Schema 选择、SQL 生成和结果验证已接入结构化 SemanticQuery；无 compiler 的旧 LLM 模式保持兼容。
- SDK 默认创建临时 SQLite metadata；示例 DuckDB 默认使用 `2024-09-30` 作为参考日期，也可通过 `reference_date` 或请求上下文覆盖。

验证结果：`venv/bin/python -m pytest -q` -> **85 passed**。使用示例 DuckDB 的 SDK smoke test 已验证“最近一个月华东地区的营收”返回 `3891.00`，“华东地区的订单数”返回 `6`。
