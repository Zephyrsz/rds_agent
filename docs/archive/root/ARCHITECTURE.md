# RDS Agent 架构文档

## 1. 系统架构概览

RDS Agent 采用分层架构设计，从上到下分为：

```
┌─────────────────────────────────────────┐
│            应用层 (Application)          │
│  Interactive Demo, API Server, Web UI   │
├─────────────────────────────────────────┤
│         工作流层 (Workflow)              │
│      LangGraph 状态机与节点编排          │
├─────────────────────────────────────────┤
│          核心层 (Core)                   │
│   Catalog, Semantic, Planner, Generator │
│    Guard, Executor, Validator, Composer │
├─────────────────────────────────────────┤
│         适配层 (Adapters)                │
│        数据库适配器抽象与实现             │
├─────────────────────────────────────────┤
│         配置层 (Config)                  │
│    Schema, Metrics, Dimensions, Terms   │
└─────────────────────────────────────────┘
```

## 2. 核心设计原则

### 2.1 确定性与灵活性平衡

- **确定性流程**: 使用 LangGraph 定义固定的工作流节点和边
- **灵活决策**: 在节点内使用 LLM 进行意图理解和 SQL 生成
- **条件分支**: 根据验证结果动态选择重试或继续

### 2.2 安全第一

- **多层防护**: SQL 必须通过 AST 解析、白名单、敏感字段检查
- **只读约束**: 只允许 SELECT 查询，禁止所有写操作
- **成本控制**: EXPLAIN 分析 + 强制 LIMIT + 超时机制

### 2.3 业务语义显式化

- **不依赖模型**: 指标和维度定义在配置文件中明确声明
- **口径一致**: 相同指标名称对应唯一的计算逻辑
- **可追溯**: 每个指标都有文档说明和示例 SQL

## 3. 工作流详解

### 3.1 节点职责

#### classify_request
- **输入**: 用户问题
- **处理**: 提取结构化意图（问题类型、指标、维度、时间范围）
- **输出**: 意图对象

#### resolve_semantics
- **输入**: 结构化意图
- **处理**: 将业务术语解析为数据库实体
- **输出**: 解析后的指标、维度、过滤条件

#### select_schema
- **输入**: 用户问题
- **处理**: 检索相关表、字段、Join 关系
- **输出**: Schema 上下文

#### create_query_plan
- **输入**: 意图 + Schema 上下文
- **处理**: 根据问题类型生成查询计划（单步 or 多步）
- **输出**: 查询计划对象

#### generate_sql
- **输入**: 查询计划 + Schema 上下文
- **处理**: 使用 LLM 生成 SQL
- **输出**: SQL 字符串

#### validate_sql
- **输入**: SQL
- **处理**: AST 解析、权限检查、语法检查
- **输出**: 验证结果（通过/拒绝）

#### explain_sql
- **输入**: SQL
- **处理**: 执行 EXPLAIN，评估查询成本
- **输出**: 执行计划和成本估算

#### execute_sql
- **输入**: SQL
- **处理**: 执行查询，记录审计日志
- **输出**: 查询结果

#### validate_result
- **输入**: 查询结果 + 查询计划
- **处理**: 检查空结果、异常值、数据一致性
- **输出**: 验证问题列表

#### compose_answer
- **输入**: 问题 + 查询结果 + 验证问题
- **处理**: 组织结构化答案
- **输出**: 用户友好的答案对象

### 3.2 条件边

#### should_revise_sql
```python
if sql_validated:
    return "proceed"
elif retry_count >= max_retries:
    return "fail"
else:
    return "revise"
```

#### should_repair_sql
```python
if execution_error and retry_count < max_retries:
    return "repair"
elif execution_error:
    return "fail"
else:
    return "proceed"
```

## 4. 核心组件设计

### 4.1 DatabaseCatalog

**职责**: Schema 元数据管理

**核心方法**:
- `search_schema(question)`: 基于问题检索相关表
- `get_join_paths(tables)`: 获取表之间的 Join 路径
- `find_join_path(from_table, to_table)`: BFS 查找两表之间的最短路径

**数据结构**:
```python
{
    "tables": {
        "orders": TableDefinition(...),
        "customers": TableDefinition(...)
    },
    "joins": [JoinPath(...), ...],
    "join_graph": {"orders": [JoinPath, ...], ...}
}
```

### 4.2 SemanticLayer

**职责**: 业务语义解析

**核心方法**:
- `resolve_metric(name)`: 指标名 → 计算表达式
- `resolve_dimension(name)`: 维度名 → 表和字段
- `resolve_time_range(expression)`: 时间表达式 → 日期范围
- `resolve_business_term(text)`: 业务术语 → 标准名称

**配置驱动**:
```yaml
metrics:
  sales_amount:
    expression: SUM(order_items.net_amount)
    filters: ["orders.status IN ('paid', 'completed')"]
```

### 4.3 SQLGuard

**职责**: SQL 安全验证

**验证层次**:
1. **语法层**: 只允许 SELECT
2. **权限层**: 表/字段白名单
3. **风险层**: 笛卡尔积、无条件全表扫描
4. **成本层**: LIMIT、行数、超时

**实现方式**: AST 解析 (sqlparse)，而非正则表达式

### 4.4 QueryExecutor

**职责**: 安全执行查询

**保护机制**:
- 超时控制（30秒）
- 结果集限制（10,000行）
- 只读连接
- 审计日志

### 4.5 ResultValidator

**职责**: 结果合理性验证

**验证维度**:
- 空结果是否合理
- 数值是否在预期范围
- 时间范围是否正确
- 聚合粒度是否一致

## 5. 配置文件规范

### 5.1 schema.yaml

```yaml
tables:
  table_name:
    description: 表说明
    tags: [tag1, tag2]
    columns:
      column_name:
        type: INTEGER
        description: 字段说明
        primary_key: true
        foreign_key: other_table.id
        enum: [value1, value2]

joins:
  - left: table1.col
    right: table2.col
    cardinality: many_to_one
    description: Join 说明
```

### 5.2 metrics.yaml

```yaml
metrics:
  metric_name:
    name: 显示名称
    description: 详细说明
    expression: SQL 表达式
    tables: [table1, table2]
    filters: ["条件1", "条件2"]
    time_column: 时间字段
```

### 5.3 dimensions.yaml

```yaml
dimensions:
  dim_name:
    name: 显示名称
    table: 表名
    column: 字段名
    mappings:
      业务值: [数据库值1, 数据库值2]
```

## 6. 扩展点

### 6.1 新增数据库支持

1. 创建适配器类: `adapters/newdb.py`
2. 实现接口: `connect()`, `execute()`, `cursor()`
3. 更新 SQL 方言（如果需要）

### 6.2 新增节点

1. 在 `WorkflowNodes` 中添加方法
2. 在 `create_workflow_graph()` 中添加节点和边
3. 更新 `AgentState` 添加新状态字段

### 6.3 自定义验证规则

1. 继承 `SQLGuard` 或 `ResultValidator`
2. 重写验证方法
3. 在工作流初始化时传入自定义实例

## 7. 性能优化建议

### 7.1 Schema 检索

- 使用向量数据库缓存 Schema 嵌入
- 预计算常用表之间的 Join 路径
- 缓存热点问题的 Schema 上下文

### 7.2 SQL 生成

- 缓存问题-SQL 映射
- Few-shot 示例动态选择
- 使用更快的小模型初筛

### 7.3 查询执行

- 查询结果缓存（带 TTL）
- 预聚合常用指标
- 数据库索引优化

## 8. 监控指标

### 8.1 准确率指标

- Schema 选择准确率
- SQL 语法正确率
- SQL 执行成功率
- 业务口径正确率

### 8.2 性能指标

- 端到端响应时间
- SQL 生成时间
- 查询执行时间
- Token 消耗

### 8.3 安全指标

- 危险 SQL 拦截次数
- 权限违规次数
- 查询超时次数

## 9. 故障排查

### 9.1 SQL 生成失败

1. 检查 Schema 配置是否完整
2. 检查指标和维度定义
3. 检查 LLM 调用是否正常
4. 查看审计日志中的 prompt

### 9.2 SQL 验证失败

1. 查看具体的验证错误类型
2. 检查表/字段白名单配置
3. 检查是否触发了安全规则
4. 手动验证 SQL 语法

### 9.3 查询执行失败

1. 检查数据库连接状态
2. 查看数据库错误信息
3. 手动执行 SQL 排查
4. 检查是否超时

## 10. 最佳实践

### 10.1 配置管理

- 使用版本控制管理配置文件
- 配置变更需要经过 Review
- 重要指标定义需要文档化
- 定期审查和更新示例 SQL

### 10.2 测试策略

- 构建黄金测试集（100+ 问题）
- 覆盖各种问题类型和边界情况
- 回归测试确保变更不破坏现有功能
- 定期评估准确率指标

### 10.3 安全实践

- 最小权限原则（只开放必要的表和字段）
- 定期审计查询日志
- 监控异常查询模式
- 敏感字段脱敏处理

### 10.4 用户体验

- 提供查询进度反馈
- 解释为什么某些查询被拒绝
- 显示数据范围和口径说明
- 允许用户提供反馈
