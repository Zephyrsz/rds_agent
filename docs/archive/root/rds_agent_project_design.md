# RDS Agent 项目设计文档

## 项目概述

基于 DB-GPT 思路，使用 LangGraph + LangChain 实现面向固定数据库的轻量级 Data Agent，首期以 DuckDB 为例。

## 核心设计原则

1. **Agent 决定分析什么，确定性 Core 决定如何安全执行**
2. **所有数据库访问必须通过受控的只读查询网关**
3. **业务语义由显式配置定义，不依赖模型自行理解**
4. **LangGraph 负责确定性流程，Deep Agents 负责复杂分析**
5. **每次查询可审计、可追踪、可复现**

## 技术栈

- **流程编排**: LangGraph (确定性状态机)
- **Agent 框架**: LangChain
- **数据库**: DuckDB (首期，可扩展)
- **SQL 解析**: sqlparse / sqlglot
- **LLM**: OpenAI / Anthropic Claude
- **配置管理**: YAML
- **类型检查**: Pydantic

## 项目结构

```
rds_agent/
├── core/
│   ├── __init__.py
│   ├── catalog.py          # 数据库 Schema 目录
│   ├── semantic.py         # 业务语义层
│   ├── planner.py          # 查询计划生成器
│   ├── generator.py        # SQL 生成器
│   ├── guard.py            # SQL 安全网关
│   ├── executor.py         # 查询执行器
│   ├── validator.py        # 结果验证器
│   └── composer.py         # 答案组织器
│
├── workflow/
│   ├── __init__.py
│   ├── graph.py            # LangGraph 主流程
│   ├── nodes.py            # 工作流节点
│   └── states.py           # 状态定义
│
├── adapters/
│   ├── __init__.py
│   ├── base.py             # 数据库适配器基类
│   └── duckdb.py           # DuckDB 适配器
│
├── config/
│   ├── schema.yaml         # Schema 定义
│   ├── metrics.yaml        # 指标定义
│   ├── dimensions.yaml     # 维度定义
│   ├── terms.yaml          # 业务术语
│   └── examples.yaml       # 示例问题和 SQL
│
├── tools/
│   ├── __init__.py
│   └── schema_tools.py     # Schema 检索工具
│
├── tests/
│   ├── test_semantic.py
│   ├── test_guard.py
│   ├── test_workflow.py
│   └── fixtures/
│       └── sample_data.sql
│
├── examples/
│   ├── basic_query.py
│   ├── complex_analysis.py
│   └── interactive_demo.py
│
├── requirements.txt
├── setup.py
└── README.md
```

## 核心模块设计

### 1. DatabaseCatalog (catalog.py)

负责管理和检索数据库 Schema 信息。

**核心功能**：
- 加载 Schema 配置
- 根据问题检索相关表和字段
- 提供 Join 路径
- 返回字段说明和示例值

### 2. SemanticLayer (semantic.py)

负责业务语义解析和映射。

**核心功能**：
- 解析业务指标（如"销售额"→ SUM(net_amount)）
- 解析维度（如"华东"→ region='EAST_CHINA'）
- 解析时间范围（如"最近三个月"）
- 解析业务术语和同义词

### 3. QueryPlanner (planner.py)

负责生成查询计划。

**核心功能**：
- 分析问题类型（简单统计 vs 复杂分析）
- 生成结构化查询意图
- 对于复杂问题，拆分为多个子查询
- 确定查询依赖关系

### 4. SQLGenerator (generator.py)

负责生成和修复 SQL。

**核心功能**：
- 根据查询计划生成 SQL
- 基于错误反馈修复 SQL
- 使用 Schema 上下文和示例
- 支持重试机制

### 5. SQLGuard (guard.py)

负责 SQL 安全检查。

**核心功能**：
- AST 解析（禁止 DML/DDL）
- 表和字段白名单检查
- 检测笛卡尔积风险
- 评估查询成本
- 强制 LIMIT 限制
- 敏感字段检查

### 6. QueryExecutor (executor.py)

负责安全执行查询。

**核心功能**：
- EXPLAIN 分析
- 执行只读查询
- 超时控制
- 结果集大小限制
- 查询审计日志

### 7. ResultValidator (validator.py)

负责结果验证。

**核心功能**：
- 空结果合理性检查
- 时间范围验证
- 异常值检测
- 聚合粒度验证
- Join 重复检查

### 8. AnswerComposer (composer.py)

负责组织最终答案。

**核心功能**：
- 生成核心结论
- 包含关键指标
- 说明筛选条件和口径
- 附带风险提示
- 提供审计信息

## LangGraph 工作流设计

### 状态定义

```python
class AgentState(TypedDict):
    question: str
    question_type: str
    intent: Dict
    schema_context: Dict
    query_plan: Dict
    sql: str
    sql_validated: bool
    explain_result: Dict
    query_result: Dict
    result_validated: bool
    answer: str
    error: Optional[str]
    retry_count: int
    audit_trail: List[Dict]
```

### 节点定义

1. **classify_request**: 分类请求类型
2. **resolve_semantics**: 解析业务语义
3. **select_schema**: 选择相关 Schema
4. **create_query_plan**: 创建查询计划
5. **generate_sql**: 生成 SQL
6. **validate_sql**: 验证 SQL 安全性
7. **explain_sql**: 分析执行计划
8. **execute_sql**: 执行查询
9. **validate_result**: 验证结果
10. **compose_answer**: 组织答案

### 边和条件

- validate_sql → passed → explain_sql
- validate_sql → rejected → revise_sql (最多重试 3 次)
- explain_sql → too_expensive → revise_sql
- execute_sql → error → repair_sql (最多重试 2 次)
- validate_result → need_deeper_analysis → Deep Agent

## 配置文件设计

### metrics.yaml 示例

```yaml
metrics:
  sales_amount:
    name: 销售额
    description: 有效订单的净销售额（不含退款）
    expression: SUM(order_items.net_amount)
    tables:
      - orders
      - order_items
    filters:
      - orders.status IN ('paid', 'completed')
    time_column: orders.paid_at
    
  order_count:
    name: 订单数
    description: 有效订单数量
    expression: COUNT(DISTINCT orders.id)
    tables:
      - orders
    filters:
      - orders.status IN ('paid', 'completed')
```

### dimensions.yaml 示例

```yaml
dimensions:
  region:
    name: 地区
    table: regions
    column: region_name
    mappings:
      华东: ['Shanghai', 'Jiangsu', 'Zhejiang']
      华北: ['Beijing', 'Tianjin', 'Hebei']
      
  product_category:
    name: 产品类别
    table: products
    column: category
```

### schema.yaml 示例

```yaml
tables:
  orders:
    description: 订单主表
    columns:
      id:
        type: INTEGER
        description: 订单ID
        primary_key: true
      customer_id:
        type: INTEGER
        description: 客户ID
        foreign_key: customers.id
      status:
        type: VARCHAR
        description: 订单状态
        enum: ['pending', 'paid', 'completed', 'cancelled']
      paid_at:
        type: TIMESTAMP
        description: 支付时间
        
joins:
  - left: orders.customer_id
    right: customers.id
    cardinality: many_to_one
    description: 订单关联客户
```

## 安全策略

### SQL 黑名单（AST 级别）

- INSERT, UPDATE, DELETE
- DROP, TRUNCATE, ALTER
- CREATE (TABLE, INDEX, VIEW)
- GRANT, REVOKE
- COPY, CALL
- 系统表访问
- 文件操作函数

### 查询限制

- 最大返回行数: 10,000
- 查询超时: 30 秒
- 最大扫描数据量: 100MB
- 必须显式 LIMIT（默认添加 LIMIT 1000）
- 禁止无条件全表扫描（某些情况除外）

### 权限模型

```yaml
permissions:
  tables:
    allowed: ['orders', 'customers', 'products', 'regions']
    denied: ['users', 'credentials', 'audit_log']
  columns:
    sensitive: ['customers.id_card', 'customers.phone']
    action: mask  # mask | deny | require_approval
```

## 开发路线

### Phase 1: 核心基础设施 (Week 1-2)

- [ ] 实现 DatabaseCatalog
- [ ] 实现 SemanticLayer
- [ ] 实现 SQLGuard
- [ ] 实现 QueryExecutor
- [ ] 创建 DuckDB 示例数据

### Phase 2: SQL 生成和修复 (Week 2-3)

- [ ] 实现 QueryPlanner
- [ ] 实现 SQLGenerator
- [ ] 实现错误反馈机制
- [ ] 集成 LLM

### Phase 3: LangGraph 工作流 (Week 3-4)

- [ ] 定义状态和节点
- [ ] 实现工作流图
- [ ] 添加重试和恢复逻辑
- [ ] 实现审计日志

### Phase 4: 结果验证和答案生成 (Week 4-5)

- [ ] 实现 ResultValidator
- [ ] 实现 AnswerComposer
- [ ] 完善错误处理

### Phase 5: 测试和优化 (Week 5-6)

- [ ] 编写单元测试
- [ ] 构建黄金测试集
- [ ] 性能优化
- [ ] 文档完善

## 评估指标

### 准确率指标

- Schema 选择准确率 (目标 > 95%)
- SQL 语法正确率 (目标 > 90%)
- SQL 执行成功率 (目标 > 85%)
- 业务口径正确率 (目标 > 90%)
- 结果正确率 (目标 > 85%)

### 安全指标

- 危险 SQL 拦截率 (目标 = 100%)
- 权限违规拦截率 (目标 = 100%)
- 敏感字段保护率 (目标 = 100%)

### 性能指标

- 平均查询时延 (目标 < 5s)
- 平均重试次数 (目标 < 0.3)
- Token 成本 (目标 < 5000 tokens/query)

### 用户体验指标

- 用户满意度 (目标 > 4.0/5.0)
- 首次成功率 (目标 > 70%)
- 需要人工干预率 (目标 < 10%)

## 扩展计划

### 数据库支持

- Phase 1: DuckDB
- Phase 2: PostgreSQL
- Phase 3: MySQL
- Phase 4: ClickHouse

### 高级功能

- 多轮对话上下文管理
- 查询结果缓存
- 自动图表生成
- 报告生成
- 异常检测和归因分析
- 与 BI 工具集成

## 风险和缓解措施

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| SQL 注入 | 高 | 中 | AST 解析 + 参数化查询 |
| 业务口径错误 | 高 | 高 | 显式语义层 + 人工审核 |
| 性能问题 | 中 | 中 | EXPLAIN 分析 + 查询限制 |
| 模型幻觉 | 中 | 高 | 结果验证 + 审计日志 |
| 成本失控 | 中 | 中 | Token 预算 + 缓存策略 |

## 总结

本设计采用 LangGraph 确定性流程 + 业务语义层 + SQL 安全网关的架构，既保持了 Agent 的灵活性，又确保了数据访问的安全性和业务口径的准确性。

核心优势：
1. 轻量级：专注核心流程，不包含平台化功能
2. 可控：确定性流程，明确的安全边界
3. 可扩展：模块化设计，易于添加新数据库支持
4. 可审计：每步操作都有日志和追踪
5. 高准确率：显式语义层 + 结果验证
