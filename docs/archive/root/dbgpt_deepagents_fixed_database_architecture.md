# 基于 DB-GPT 思路与 LangChain Deep Agents 的固定数据库 Data Agent 方案

## 1. 方案概述

目标不是完整重写 DB-GPT，而是研究其数据 Agent 的核心流程，提炼对固定数据库场景真正有价值的能力，再使用 **LangChain Deep Agents + LangGraph** 实现一个轻量、可控、面向特定业务领域的 Data Agent Core。

整体路线如下：

```text
研究 DB-GPT 的数据 Agent 流程
        ↓
提取 Schema 理解、Text-to-SQL、执行反馈、结果解释等关键模式
        ↓
舍弃通用平台、Web UI、多模型托管及多数据库适配等外围能力
        ↓
针对固定数据库构建业务语义层和安全查询网关
        ↓
使用 LangGraph 实现确定性主流程
        ↓
使用 Deep Agents 实现复杂任务规划、上下文管理和子任务协作
```

该方案在技术上完全可行，而且在数据库类型固定、Schema 稳定、业务范围明确的情况下，通常比直接二次开发完整 DB-GPT 更容易控制、优化和产品化。

---

## 2. 核心判断

建议将系统定位为：

> 面向固定数据库的领域专用 Data Agent Runtime，而不是缩小版 DB-GPT。

设计原则如下：

- DB-GPT 作为数据 Agent 的参考实现。
- LangGraph 作为有状态、可恢复、可审计的确定性流程运行时。
- Deep Agents 负责任务规划、上下文管理、文件操作和复杂分析。
- 自定义 Data Core 负责数据库语义、SQL 安全、查询执行和结果验证。
- 所有数据库访问必须通过受控的只读查询网关。
- 模型负责提出分析意图，确定性代码负责执行安全规则。

最重要的原则是：

> Agent 决定分析什么，确定性 Core 决定允许如何查询、如何执行，以及结果是否可信。

---

## 3. 为什么不需要完整复刻 DB-GPT

DB-GPT 是一个相对完整的 AI 数据应用平台，通常包括：

- Agent 和 Multi-Agent
- AWEL 工作流编排
- 模型接入与管理
- 数据源连接器
- Text-to-SQL
- SQL 执行与分析
- RAG 和知识库
- 元数据存储
- 应用服务与 Web UI
- 沙箱和报告生成

但对于固定数据库项目，真正值得研究和复用的是以下核心问题：

1. 如何抽取和组织数据库 Schema。
2. 如何从大量表中选择相关表。
3. 如何把业务问题转换成结构化查询意图。
4. 如何生成符合业务口径的 SQL。
5. 如何校验、限制和安全执行 SQL。
6. 如何将执行异常反馈给模型并自动修复。
7. 如何验证查询结果是否符合问题和业务规则。
8. 如何解释结果并生成可信的业务结论。
9. 如何处理多轮对话中的时间、筛选条件和上下文继承。
10. 如何审计 Agent 的每次查询和工具调用。

以下模块可以暂不复刻：

- DB-GPT Web UI
- 通用多数据库连接器体系
- 完整 AWEL 编辑器
- 模型训练与推理服务管理
- 通用插件市场
- 完整知识库管理平台
- 通用向量数据库抽象
- 大规模 Multi-Agent 协作框架
- AI 应用发布和运营平台

---

## 4. 推荐的系统架构

```text
┌────────────────────────────────────────┐
│                API / UI                │
├────────────────────────────────────────┤
│         Deep Agents / LangGraph        │
│ Planning, State, Retry, HITL, Context  │
├────────────────────────────────────────┤
│             Data Agent Core            │
│ Intent, Plan, SQL, Verify, Answer      │
├────────────────────────────────────────┤
│        Database Semantic Layer         │
│ Metrics, Dimensions, Joins, Terms      │
├────────────────────────────────────────┤
│           Safe Query Gateway           │
│ AST, Permission, Cost, Limit, Audit    │
├────────────────────────────────────────┤
│             Fixed Database             │
└────────────────────────────────────────┘
```

### 4.1 Deep Agents / LangGraph 层

负责：

- 复杂任务规划
- 状态管理
- 条件分支
- 查询失败后的重试与恢复
- 子任务拆分
- 子 Agent 委派
- 上下文压缩
- 文件和分析制品管理
- 人工审批
- 流式事件输出

### 4.2 Data Agent Core 层

负责：

- 请求分类
- 结构化意图提取
- 查询计划生成
- SQL 生成与修复
- 结果验证
- 回答组织
- 分析过程审计

### 4.3 Database Semantic Layer 层

负责：

- 业务指标定义
- 维度定义
- 业务术语和同义词
- 固定 Join 关系
- 时间口径
- 枚举值说明
- 权限和敏感字段定义
- 高质量参考 SQL

### 4.4 Safe Query Gateway 层

负责：

- SQL AST 解析
- 只读约束
- 表和字段白名单
- 用户及租户权限检查
- 查询成本控制
- 超时和返回行数限制
- 敏感字段脱敏
- SQL 审计

---

## 5. 推荐的核心 Agent 流程

### 5.1 问题理解

用户问题：

```text
帮我分析华东地区最近三个月销售额下降的原因。
```

先生成结构化意图，而不是立即生成 SQL：

```json
{
  "task_type": "diagnostic_analysis",
  "metric": "sales_amount",
  "dimensions": ["region", "month", "product_category"],
  "filters": {
    "region": "华东"
  },
  "time_range": "last_3_months",
  "comparison": "previous_period"
}
```

### 5.2 业务语义解析

将用户语言映射为明确的数据库业务口径：

```text
“销售额”
→ SUM(order_items.net_amount)

“华东”
→ region.region_group = 'EAST_CHINA'

“有效订单”
→ orders.status IN ('paid', 'completed')

“最近三个月”
→ 使用 business_calendar 中定义的业务月份
```

语义层必须回答以下问题：

- GMV 是否包括退款？
- 销售额是否含税？
- 客户数按账号、企业还是自然人计算？
- 财务月是否等于自然月？
- 订单取消后是否参与统计？
- 收入使用下单时间、付款时间还是确认收入时间？

这通常是系统准确率最关键的部分。

### 5.3 相关 Schema 检索

不应每次将完整数据库 DDL 发送给模型，而应维护并检索：

- 表级说明
- 字段级说明
- 主外键关系
- 常用 Join 路径
- 指标和维度
- 枚举值
- 时间字段含义
- 业务同义词
- 示例 SQL
- 禁止访问字段

检索结果示例：

```json
{
  "tables": ["orders", "order_items", "customers", "regions"],
  "join_path": [
    "orders.id = order_items.order_id",
    "orders.customer_id = customers.id",
    "customers.region_id = regions.id"
  ],
  "metrics": ["sales_amount"],
  "dimensions": ["region", "order_month"]
}
```

### 5.4 查询计划生成

对于简单统计问题可以直接生成 SQL；对于诊断和分析问题，建议先生成分析计划：

```json
{
  "steps": [
    {
      "id": "baseline",
      "purpose": "计算最近三个月华东销售额趋势"
    },
    {
      "id": "comparison",
      "purpose": "与前三个月进行比较"
    },
    {
      "id": "category_breakdown",
      "purpose": "按产品类别计算销售额变化贡献"
    },
    {
      "id": "customer_breakdown",
      "purpose": "识别重点客户流失或购买下降"
    }
  ]
}
```

每个步骤独立完成 SQL 生成、校验、执行和结果验证。

### 5.5 SQL 生成与安全检查

生成 SQL 后必须经过确定性检查：

```text
语法检查
    ↓
只读检查
    ↓
表和字段白名单
    ↓
用户、角色与租户权限
    ↓
敏感字段检查
    ↓
全表扫描和笛卡尔积风险
    ↓
查询成本评估
    ↓
LIMIT、超时和资源限制
    ↓
执行
```

至少应禁止：

```sql
INSERT
UPDATE
DELETE
DROP
ALTER
TRUNCATE
CREATE
GRANT
REVOKE
COPY
CALL
```

同时防范：

- 多语句执行
- 注释和编码绕过
- 系统表访问
- 横向或跨租户越权
- 无约束笛卡尔积
- 超大结果集
- 超长查询
- 数据库危险函数
- 文件和网络访问函数

SQL 安全应使用 AST 解析器实现，不能仅依靠正则表达式或提示词。

### 5.6 执行反馈与自动修复

数据库执行错误应被转换成结构化反馈：

```json
{
  "error_type": "unknown_column",
  "database_message": "column orders.region does not exist",
  "available_columns": [
    "orders.customer_id",
    "customers.region_id",
    "regions.region_name"
  ],
  "retry_allowed": true
}
```

推荐修复循环：

```text
生成 SQL
  ↓
静态验证
  ↓
EXPLAIN
  ↓
执行
  ↓
错误分类
  ↓
局部修复或重新生成
  ↓
最多重试 2 至 3 次
```

必须设置重试上限，避免 Agent 无限循环。

### 5.7 结果验证与回答

SQL 执行成功并不代表答案正确。结果验证至少包括：

- 空结果是否合理
- 时间范围是否正确
- 指标是否出现异常负值
- 聚合粒度是否符合问题
- Join 是否造成重复计算
- 总计与明细合计是否一致
- 对比周期是否对齐
- 多个查询结果是否互相矛盾
- 结果是否足以支撑最终结论

最终回答建议包含：

1. 核心结论
2. 关键指标
3. 筛选条件
4. 指标和时间口径
5. 分析依据
6. 风险与限制
7. 查询 ID 或 SQL 审计信息

---

## 6. LangGraph 与 Deep Agents 的职责划分

### 6.1 LangGraph 适合承担的职责

- 固定状态机
- 确定性工作流
- 条件分支
- 最大重试次数
- 节点级审计
- 中断与恢复
- 检查点持久化
- 人工审批节点
- 安全边界控制

### 6.2 Deep Agents 适合承担的职责

- 长任务规划
- 多步骤分析
- 子任务拆分
- 子 Agent 委派
- 上下文压缩和卸载
- 文件读写
- Python 数据分析
- 报告生成
- 长周期任务执行
- 在受控工具集合中自主选择下一步操作

### 6.3 不应完全交给 Deep Agents 的职责

以下逻辑必须由确定性 Core 或安全网关实现：

- SQL 权限校验
- 业务指标定义
- Join 路径约束
- 租户隔离
- 敏感字段脱敏
- 最大扫描量和返回行数
- 查询超时
- 数据库凭据管理
- SQL 审计
- 高风险查询审批

因此推荐采用：

> LangGraph 确定性主流程 + Deep Agent 复杂分析器。

---

## 7. 推荐的 LangGraph 主流程

```text
START
  ↓
classify_request
  ↓
resolve_semantics
  ↓
select_schema
  ↓
create_query_plan
  ↓
generate_sql
  ↓
validate_sql
  ├─ rejected → revise_sql
  └─ passed
        ↓
      explain_sql
        ├─ too_expensive → revise_sql
        └─ accepted
              ↓
          execute_sql
              ├─ error → repair_sql
              └─ success
                    ↓
              validate_result
                    ↓
          need_deeper_analysis?
              ├─ yes → Deep Agent
              └─ no
                    ↓
              compose_answer
                    ↓
                   END
```

该设计的特点是：

- 安全检查位于确定性节点中。
- Deep Agent 不能绕过 SQL Gateway。
- 查询失败只允许有限次数修复。
- 复杂分析时才启动更自主的 Agent。
- 每一步都可以记录状态、输入、输出和耗时。

---

## 8. 最小工具集合

第一版无需实现大量工具，只需要覆盖核心闭环。

### 8.1 Schema 与语义工具

```python
get_relevant_schema(question: str)
get_table_definition(table_name: str)
get_metric_definition(metric_name: str)
get_join_path(tables: list[str])
search_business_terms(query: str)
```

### 8.2 SQL 工具

```python
validate_sql(sql: str)
explain_sql(sql: str)
execute_readonly_sql(sql: str)
```

### 8.3 分析工具

```python
profile_result(query_id: str)
compare_periods(query_id: str)
detect_anomalies(query_id: str)
create_chart(query_id: str)
```

### 8.4 审计与审批工具

```python
get_query_history(thread_id: str)
record_analysis_artifact(...)
request_query_approval(...)
```

不要向模型暴露没有安全边界的通用工具：

```python
run_any_sql(sql: str)
```

更安全的做法是将生成、校验、EXPLAIN 和执行分离，执行器只接受已经通过校验并带有授权信息的查询请求。

---

## 9. 建议实现的 Core 接口

```python
class DatabaseCatalog:
    def search_schema(self, question): ...
    def get_table(self, name): ...
    def get_column(self, table, column): ...
    def get_join_paths(self, tables): ...


class SemanticLayer:
    def resolve_metric(self, name): ...
    def resolve_dimension(self, name): ...
    def resolve_business_term(self, text): ...
    def resolve_time_range(self, expression): ...


class QueryPlanner:
    def create_plan(self, intent, context): ...


class SQLGenerator:
    def generate(self, plan, schema_context): ...
    def repair(self, sql, error_context): ...


class SQLGuard:
    def validate_ast(self, sql): ...
    def check_permissions(self, sql, user_context): ...
    def enforce_limits(self, sql): ...
    def estimate_cost(self, sql): ...


class QueryExecutor:
    def explain(self, checked_query): ...
    def execute(self, checked_query): ...


class ResultValidator:
    def validate(self, plan, result): ...


class AnswerComposer:
    def compose(self, question, plan, results): ...
```

Deep Agents 只调用这些受控能力，不负责替代其内部实现。

---

## 10. 固定数据库带来的优势

固定数据库不是限制，反而是实现高准确率的重要优势。

### 10.1 固定业务指标

```yaml
metrics:
  sales_amount:
    description: 有效订单的净销售额
    expression: SUM(order_items.net_amount)
    filters:
      - orders.status IN ('paid', 'completed')
    time_column: orders.paid_at
```

### 10.2 固定 Join 关系

```yaml
joins:
  - left: orders.customer_id
    right: customers.id
    cardinality: many_to_one
```

### 10.3 预置高质量示例

```yaml
examples:
  - question: 每月销售额趋势
    sql: |
      SELECT
        DATE_TRUNC('month', orders.paid_at) AS month,
        SUM(order_items.net_amount) AS sales_amount
      FROM orders
      JOIN order_items ON orders.id = order_items.order_id
      WHERE orders.status IN ('paid', 'completed')
      GROUP BY 1
      ORDER BY 1;
```

### 10.4 业务规则检查

可以将领域规则编码为确定性校验：

- 涉及销售额时必须排除取消订单。
- 涉及收入时必须使用确认收入日期。
- 涉及客户数时必须使用 `COUNT(DISTINCT customer_id)`。
- 涉及订单头和订单明细时必须检查重复聚合。
- 涉及同比时必须校验比较周期完整性。
- 涉及敏感客户信息时必须执行脱敏。

这类规则通常比简单扩大模型规模更能提高可靠性。

---

## 11. 是否需要 Multi-Agent

第一版不建议直接采用复杂 Multi-Agent 架构。

### 第一阶段：单 Agent + 确定性工作流

```text
Data Analyst Agent
  ├─ Schema Tool
  ├─ Semantic Tool
  ├─ SQL Planner
  ├─ SQL Guard
  └─ Query Executor
```

### 第二阶段：按需要引入专用子 Agent

```text
Coordinator
  ├─ Schema Analyst
  ├─ SQL Analyst
  ├─ Business Analyst
  └─ Report Writer
```

适合拆成子 Agent 的任务：

- 相互独立的分析维度
- 多数据集并行分析
- 报告写作和数据查询解耦
- 复杂根因分析
- 大规模文档或文件辅助分析

不适合拆成 LLM 子 Agent 的任务：

- SQL AST 校验
- 权限校验
- 查询成本检查
- 租户隔离
- 敏感字段控制

这些应始终由确定性代码完成。

---

## 12. 推荐研发路线

### 阶段一：研究 DB-GPT 核心调用链

选择一个完整的数据问答用例，通过日志、断点或调用追踪研究：

```text
用户请求
→ Agent 入口
→ Prompt 构造
→ Schema 检索
→ SQL 生成
→ 工具调用
→ SQL 执行
→ 异常处理
→ 结果解释
→ 最终回答
```

重点理解 DB-GPT 如何连接 Agent、模型、数据源和执行反馈，不必复制它的完整平台架构。

### 阶段二：建立固定数据库语义层

交付物建议包括：

- 表说明
- 字段说明
- 指标定义
- 维度定义
- Join 图
- 业务术语和同义词
- 时间口径
- 权限定义
- 敏感字段定义
- 50 至 200 个黄金问题及正确 SQL

### 阶段三：实现安全 Text-to-SQL 闭环

先实现最小流程：

```text
Question
→ Schema Selection
→ SQL Generation
→ Validation
→ Execution
→ Result Validation
→ Answer
```

此阶段可以先不引入 Deep Agents。

### 阶段四：迁入 LangGraph

增加：

- 状态持久化
- 条件分支
- SQL 自动修复
- 最大重试次数
- 人工审批
- 流式事件
- 中断恢复
- 节点级审计

### 阶段五：引入 Deep Agents

增加：

- 复杂分析规划
- 多查询联合分析
- 子 Agent
- Python 数据处理
- 文件和分析制品
- 自动化报告生成
- 长上下文管理

### 阶段六：评估与产品化

建立持续评测体系，至少跟踪：

- Schema 选择准确率
- SQL 语法正确率
- SQL 执行成功率
- 结果正确率
- 业务口径正确率
- 危险 SQL 拦截率
- 平均重试次数
- 查询时延
- Token 成本
- 用户满意度

---

## 13. 风险与控制措施

### 13.1 Agent 自主性过高

**风险：** Agent 绕过既定流程或发起高成本查询。

**措施：** 所有数据库访问只能经过 Query Gateway；高风险操作必须人工审批。

### 13.2 SQL 正确但业务口径错误

**风险：** 查询可执行，但指标、时间或过滤条件不符合业务定义。

**措施：** 建立显式语义层和业务规则校验，不依赖模型自行理解。

### 13.3 Join 导致重复聚合

**风险：** 一对多、多对多关系导致指标被放大。

**措施：** 维护 Join 基数，检测聚合粒度，必要时使用预聚合或子查询。

### 13.4 大结果集进入模型上下文

**风险：** Token 成本过高，并造成结果截断或错误总结。

**措施：** 在数据库侧聚合、分页、采样，只返回摘要、关键行和制品引用。

### 13.5 多 Agent 增加复杂度

**风险：** 调用链过长、成本升高、错误难以定位。

**措施：** 从单 Agent 起步，只有在任务可以独立拆分时才增加子 Agent。

---

## 14. 最终推荐技术组合

```text
LangChain Deep Agents
  + LangGraph
  + 自定义 Database Catalog
  + 自定义 Semantic Layer
  + SQL AST Guard
  + Read-only Query Gateway
  + 固定数据库适配器
  + 黄金测试集与持续评测
```

职责划分如下：

```text
Deep Agents
→ 复杂分析、任务规划、上下文管理、子任务委派、报告生成

LangGraph
→ 确定性流程、状态、重试、分支、审批、恢复和审计

Semantic Layer
→ 指标、维度、业务术语、Join、时间和口径

SQL Guard / Query Gateway
→ 权限、安全、成本、限制、执行和审计

Result Validator
→ 数据合理性、聚合粒度、口径和结论支撑检查
```

---

## 15. 结论

该方案技术上可行，并且符合固定数据库 Data Agent 的工程需求。建议借鉴 DB-GPT 的数据处理思想和完整调用链，但不复制其完整平台。

推荐以 LangGraph 构建可控主流程，以 Deep Agents 承载复杂、非确定性的分析任务，同时自行实现数据库目录、业务语义层、SQL 安全网关和结果验证体系。

最终系统应实现以下平衡：

- Agent 具有足够的分析灵活性。
- 数据库执行过程具有明确的安全边界。
- 业务指标和查询口径可以被验证。
- 每次查询和结论都可以追踪、审计和复现。
- 固定数据库的领域知识可以持续沉淀为语义规则和黄金测试集。

这条路线比直接修改完整 DB-GPT 更轻量，也更适合构建具有明确业务边界、较高准确率和生产可控性的企业级数据智能体。
