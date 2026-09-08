# RDS Agent 语义层功能演进路线图
## 基于 Databricks Genie 设计的综合分析与实施方案

---

## 执行摘要

本文档对比 Databricks Genie 的语义层产品设计与 RDS Agent 当前的元数据和语义功能，识别适合添加和优化的功能点，并制定分阶段的实施路线图。

### 当前状态评估

**RDS Agent 已具备的核心能力：**
- ✅ 基础语义层（Schema、Metrics、Dimensions、Terms）
- ✅ SQL 安全网关（AST 解析、白名单、成本控制）
- ✅ 确定性工作流（LangGraph 状态机）
- ✅ 结果验证与答案组织
- ✅ 审计日志与可追溯性

**与 Genie 设计的主要差距：**
- ❌ 缺少 Domain（业务领域）概念
- ❌ 缺少 Entity（业务实体）和语义图
- ❌ 缺少 Relationship 的基数和路径控制
- ❌ 缺少 Trusted Assets（认证资产）
- ❌ 缺少双层语义（企业级 + Agent 局部）
- ❌ 缺少权限治理引擎
- ❌ 缺少 Benchmark 和持续评价体系
- ❌ 缺少语义对象生命周期管理

---

## 第一部分：功能对比矩阵

| Genie 核心功能 | RDS Agent 现状 | 优先级 | 实施难度 | 价值评估 |
|---------------|---------------|-------|---------|---------|
| **Domain（业务领域）** | ❌ 无 | 🔴 高 | 中 | ⭐⭐⭐⭐⭐ |
| **Entity（业务实体）** | ⚠️ 部分（隐式在 Join 中） | 🔴 高 | 高 | ⭐⭐⭐⭐⭐ |
| **Semantic Model（语义模型）** | ✅ 有（schema.yaml） | 🟡 中 | 中 | ⭐⭐⭐⭐ |
| **Dimension（维度）** | ✅ 有 | 🟢 低 | 低 | ⭐⭐⭐⭐ |
| **Measure（原子度量）** | ✅ 有（metrics.yaml） | 🟡 中 | 低 | ⭐⭐⭐⭐ |
| **Metric（业务指标）** | ⚠️ 部分（未区分 Measure/Metric） | 🔴 高 | 中 | ⭐⭐⭐⭐⭐ |
| **Relationship（关联关系）** | ⚠️ 基础（joins 配置） | 🔴 高 | 高 | ⭐⭐⭐⭐⭐ |
| **Business Term（业务术语）** | ✅ 有（terms.yaml） | 🟢 低 | 低 | ⭐⭐⭐ |
| **Filter（标准过滤器）** | ⚠️ 部分（在 metrics 中） | 🟡 中 | 低 | ⭐⭐⭐⭐ |
| **Trusted Asset（认证资产）** | ❌ 无 | 🟡 中 | 高 | ⭐⭐⭐⭐⭐ |
| **权限治理引擎** | ⚠️ 基础（表白名单） | 🔴 高 | 高 | ⭐⭐⭐⭐⭐ |
| **查询编译器** | ✅ 有（SQL Generator） | 🟡 中 | 中 | ⭐⭐⭐⭐ |
| **Benchmark & 评价体系** | ⚠️ 基础（examples.yaml） | 🔴 高 | 中 | ⭐⭐⭐⭐⭐ |
| **语义检索服务** | ⚠️ 简单（关键词匹配） | 🟡 中 | 高 | ⭐⭐⭐⭐ |
| **双层语义（企业+局部）** | ❌ 无 | 🟡 中 | 高 | ⭐⭐⭐ |
| **时间智能** | ⚠️ 基础 | 🟡 中 | 中 | ⭐⭐⭐⭐ |
| **多币种/财年支持** | ❌ 无 | 🟢 低 | 低 | ⭐⭐⭐ |
| **版本管理和发布** | ❌ 无 | 🟡 中 | 中 | ⭐⭐⭐⭐ |

**优先级说明：**
- 🔴 高：核心功能，显著影响产品能力
- 🟡 中：重要增强，提升用户体验
- 🟢 低：锦上添花，可后续迭代

---

## 第二部分：核心功能差距分析

### 1. Domain（业务领域）⭐⭐⭐⭐⭐

**当前状态：** 无
**Genie 设计：** 用于限制语义和权限边界，一个 Agent 对应一个清晰的 Domain

**差距分析：**
- RDS Agent 当前是全局配置，无法支持多业务场景隔离
- 无法实现"销售领域的收入"和"财务领域的收入"使用不同指标定义

**实施建议：**
```yaml
# 新增 config/domains.yaml
domains:
  retail_sales:
    name: 零售销售
    description: 中国区线上及线下零售销售分析
    owner: sales_analytics_team
    default_timezone: Asia/Shanghai
    default_currency: CNY
    fiscal_year_start: 1  # 1月开始
    allowed_tables: [orders, order_items, customers, regions, products]
    allowed_metrics: [sales_amount, order_count, customer_count]
    
  finance:
    name: 财务分析
    description: 财务报表和核算分析
    owner: finance_team
    default_timezone: Asia/Shanghai
    default_currency: CNY
    fiscal_year_start: 4  # 4月开始
    allowed_tables: [accounts, transactions]
    allowed_metrics: [recognized_revenue, gross_margin]
```

**实施难度：** 中（需要重构配置加载和权限检查逻辑）

---

### 2. Entity（业务实体）和语义图 ⭐⭐⭐⭐⭐

**当前状态：** 隐式存在于 Join 配置中，未显式建模
**Genie 设计：** 显式的业务实体定义，支持主实体、外键实体、语义图构建

**差距分析：**
- 无法明确表达"每一行代表什么"（数据粒度）
- 无法判断 Join 是否会造成重复聚合
- 无法构建跨模型的语义关系图

**实施建议：**
```yaml
# 增强 config/schema.yaml
tables:
  order_items:
    description: 订单明细表，存储订单商品明细
    grain: "每行代表一个订单中的一个商品"  # 新增
    entities:  # 新增
      - name: order_line
        type: primary
        keys: [order_id, id]
      - name: order
        type: foreign
        expr: order_id
        references: orders.id
      - name: product
        type: foreign
        expr: product_id
        references: products.id
    columns:
      # ...
```

**实施难度：** 高（需要新增 Entity 管理模块和语义图构建逻辑）

---

### 3. Relationship 增强（基数和路径控制）⭐⭐⭐⭐⭐

**当前状态：** 基础 Join 配置，缺少基数、优先级、Fan-out 风险控制
**Genie 设计：** 完整的关联关系管理，包含基数、路径优先级、替代路径

**差距分析：**
- 无法防止 many-to-many Join 造成的数据膨胀
- 无法处理多条 Join 路径的歧义
- 无法标记慢变维（SCD Type 2）的时间有效性

**实施建议：**
```yaml
# 增强 config/schema.yaml 的 joins
joins:
  - name: order_to_customer  # 新增 name
    left: orders.customer_id
    right: customers.id
    cardinality: many_to_one  # 已有
    join_type: left  # 新增
    description: 订单关联客户
    auto_join: true  # 新增：是否允许查询规划器自动采用
    priority: 1  # 新增：多条路径时的优先级
    fan_out_risk: false  # 新增：是否有数据膨胀风险
    temporal_validity: null  # 新增：慢变维时间条件（如 AND order_date BETWEEN customer.valid_from AND customer.valid_to）
```

**实施难度：** 高（需要在 SQL 生成时增加 Join 路径规划和膨胀检测）

---

### 4. Measure 与 Metric 分离 ⭐⭐⭐⭐⭐

**当前状态：** metrics.yaml 混合了原子度量和复合指标
**Genie 设计：** 严格区分 Measure（底层聚合）和 Metric（业务指标）

**差距分析：**
```text
当前混淆：
  sales_amount: SUM(order_items.net_amount)  # 这是 Measure
  avg_order_amount: AVG(order_items.net_amount)  # 这也是 Measure
  
应该区分：
  Measure:
    net_revenue: SUM(order_items.net_amount)
    order_count: COUNT(DISTINCT orders.id)
  
  Metric:
    avg_order_value:
      type: ratio
      numerator: net_revenue
      denominator: order_count
```

**实施建议：**
```yaml
# config/measures.yaml（新文件）
measures:
  net_revenue:
    name: 净销售收入
    expr: SUM(order_items.net_amount)
    table: order_items
    additive: true  # 可按维度相加
    format: currency
    currency: CNY
    
  order_count:
    name: 有效订单数
    expr: COUNT(DISTINCT orders.id)
    table: orders
    additive: false  # 不能跨时间简单相加
    
# config/metrics.yaml（重构）
metrics:
  avg_order_value:
    name: 平均订单价值
    type: ratio
    numerator: net_revenue
    denominator: order_count
    format: currency
    
  revenue_yoy_growth:
    name: 收入同比增长率
    type: period_over_period
    base_measure: net_revenue
    comparison: year_over_year
    format: percentage
```

**实施难度：** 中（需要重构 Metric 解析逻辑，增加 Ratio/YoY 计算）

---

### 5. Filter 对象化 ⭐⭐⭐⭐

**当前状态：** 过滤条件分散在 metrics 的 filters 数组中
**Genie 设计：** 标准过滤器作为可复用对象

**差距分析：**
- "有效订单" 条件在多个指标中重复定义
- 无法统一修改常用过滤条件
- 无法在自然语言中识别 "大客户"、"有效订单" 等业务概念

**实施建议：**
```yaml
# config/filters.yaml（新文件）
filters:
  valid_order:
    name: 有效订单
    description: 已支付或已完成的订单
    expr: "orders.status IN ('paid', 'completed')"
    applies_to: [orders]
    
  key_account:
    name: 大客户
    description: KA 级别客户
    expr: "customers.tier IN ('KA', 'STRATEGIC')"
    applies_to: [customers]
    synonyms: [重点客户, 战略客户, KA]
    
  current_year:
    name: 本年
    description: 当前自然年
    expr: "YEAR({time_column}) = YEAR(CURRENT_DATE)"
    type: temporal
```

**实施难度：** 低（配置文件扩展 + 语义解析增强）

---

### 6. Trusted Assets（认证资产）⭐⭐⭐⭐⭐

**当前状态：** 无
**Genie 设计：** 高风险指标使用认证查询或认证函数锁定逻辑

**差距分析：**
- 财务收入、毛利率等关键指标每次都由 LLM 生成，可能不一致
- 无法保证关键指标的计算口径统一
- 无法进行审批和认证流程

**实施建议：**
```yaml
# config/trusted_assets.yaml（新文件）
trusted_assets:
  monthly_revenue:
    id: finance_monthly_revenue
    name: 月度财务收入
    description: 财务部门认证的月度收入统计
    owner: finance_controller
    certification: certified
    approved_by: CFO
    approved_at: 2026-08-15
    
    # 匹配模式
    question_patterns:
      - "本月公司收入"
      - "月度收入"
      - "月营收"
    
    # 参数定义
    parameters:
      - name: month
        type: date
        required: true
        default: current_month
    
    # 锁定的查询逻辑
    implementation:
      type: sql_template
      sql: |
        SELECT 
          DATE_TRUNC('month', orders.paid_at) AS month,
          SUM(order_items.net_amount) AS revenue
        FROM orders
        INNER JOIN order_items ON orders.id = order_items.order_id
        WHERE orders.status IN ('paid', 'completed')
          AND DATE_TRUNC('month', orders.paid_at) = :month
        GROUP BY DATE_TRUNC('month', orders.paid_at)
    
    # 测试用例
    test_cases:
      - input: {month: '2026-08-01'}
        expected_columns: [month, revenue]
        expected_rows: 1
```

**实施难度：** 高（需要新增资产匹配、参数绑定、模板渲染模块）

---

### 7. 权限治理引擎 ⭐⭐⭐⭐⭐

**当前状态：** 仅有表白名单，缺少行级、列级权限控制
**Genie 设计：** 完整的权限治理，包含发现权限、查询权限、行过滤、列掩码

**差距分析：**
- 无法实现"销售只能看自己区域的数据"
- 无法实现"客户手机号脱敏"
- 无法实现"金额只允许聚合不允许明细"

**实施建议：**
```yaml
# config/policies.yaml（新文件）
policies:
  - name: regional_sales_isolation
    description: 销售人员只能查看所属区域数据
    applies_to: [orders, customers]
    type: row_level
    condition: |
      regions.region_code = :user_region
    user_attribute: region_code
    
  - name: customer_pii_masking
    description: 客户敏感信息脱敏
    applies_to: [customers]
    type: column_level
    columns:
      phone:
        mask_type: partial
        mask_pattern: "***-****-{last_4}"
      email:
        mask_type: hash
    
  - name: finance_aggregation_only
    description: 财务数据只允许聚合查询
    applies_to: [order_items]
    type: query_constraint
    allowed_operations: [SUM, COUNT, AVG]
    deny_operations: [SELECT_STAR, LIMIT_WITHOUT_AGGREGATE]
```

**实施难度：** 高（需要新增 Policy Engine 模块，在 SQL 编译时注入权限条件）

---

### 8. Benchmark 和持续评价体系 ⭐⭐⭐⭐⭐

**当前状态：** examples.yaml 仅作为 Few-shot 示例，无评价机制
**Genie 设计：** 完整的测试集、自动回归、分层验证（语义解析、SQL、结果）

**差距分析：**
- 无法量化系统准确率
- 配置变更后无法快速回归
- 无法跟踪模型能力退化

**实施建议：**
```yaml
# config/benchmarks.yaml（新文件）
benchmarks:
  - id: basic_001
    category: simple_aggregation
    question: 最近一个月的总销售额是多少？
    
    # 期望的语义解析
    expected_intent:
      metric: sales_amount
      time_range: last_1_month
      filters: []
    
    # 期望的 SQL 要素
    expected_sql:
      tables: [orders, order_items]
      joins: [orders.id = order_items.order_id]
      aggregates: [SUM]
      filters: [orders.status, orders.paid_at]
      
    # 期望的结果
    expected_result:
      columns: [sales_amount]
      rows: 1
      value_range:
        sales_amount: {min: 0, max: 1000000}
    
    # 元数据
    priority: high
    tags: [sales, time_range, aggregation]
    created_at: 2026-08-20
    last_passed: 2026-09-01
```

**实施难度：** 中（需要新增 Benchmark Runner 和评价指标计算）

---

### 9. 时间智能增强 ⭐⭐⭐⭐

**当前状态：** 基础时间解析，缺少同比环比、滚动窗口、累计指标
**Genie 设计：** 完整的时间维度定义、财务日历、窗口函数

**差距分析：**
- 无法正确处理"今年同比去年"
- 无法处理"最近 7 天滚动平均"
- 无法处理"年初至今累计"

**实施建议：**
```yaml
# 增强 config/dimensions.yaml
dimensions:
  order_date:
    name: 订单日期
    type: time
    table: orders
    column: order_date
    
    # 时间粒度
    granularities:
      - day
      - week
      - month
      - quarter
      - year
    
    # 时间偏移（同比环比）
    time_shifts:
      year_over_year:
        offset: -1 year
        label: 同比
      month_over_month:
        offset: -1 month
        label: 环比
    
    # 累计窗口
    cumulative_windows:
      year_to_date:
        start: fiscal_year_start
        label: 年初至今
      month_to_date:
        start: month_start
        label: 月初至今
    
    # 滚动窗口
    rolling_windows:
      - name: last_7_days
        size: 7
        unit: day
      - name: last_4_weeks
        size: 4
        unit: week
```

**实施难度：** 中（需要增强时间解析和 SQL 生成逻辑）

---

### 10. 语义检索服务增强 ⭐⭐⭐⭐

**当前状态：** 简单的关键词匹配
**Genie 设计：** 分层检索（Domain → Entity/Metric → Dimension/Filter）+ 向量相似度

**差距分析：**
- 当语义对象数量增加时，检索效率低
- 无法处理语义相似的模糊匹配
- 无法根据用户历史优化检索排序

**实施建议：**
```python
# 新增 core/retrieval.py
class SemanticRetrieval:
    """分层语义检索服务"""
    
    def retrieve_domain(self, question: str) -> Domain:
        """第一层：Domain 选择"""
        pass
    
    def retrieve_metrics(self, question: str, domain: Domain) -> List[Metric]:
        """第二层：Metric 检索"""
        # 1. 关键词匹配
        # 2. 向量相似度（使用 embedding）
        # 3. 历史成功率加权
        pass
    
    def retrieve_dimensions(self, question: str, metrics: List[Metric]) -> List[Dimension]:
        """第三层：Dimension 检索"""
        pass
    
    def retrieve_filters(self, question: str) -> List[Filter]:
        """第三层：Filter 检索"""
        pass
```

**实施难度：** 高（需要集成向量数据库或 Embedding 服务）

---

## 第三部分：分阶段实施路线图

### 🎯 Phase 1: 核心语义层增强（2-3 周）

**目标：** 补齐 Genie 核心语义对象，建立企业级语义基础

**里程碑 1.1: Domain 和配置重构**（Week 1）
- [ ] 新增 `config/domains.yaml`
- [ ] 重构配置加载逻辑，支持按 Domain 过滤
- [ ] 更新 Catalog 支持 Domain 边界
- [ ] 添加 Domain 单元测试

**里程碑 1.2: Entity 和语义图**（Week 1-2）
- [ ] 增强 `schema.yaml`，添加 `entities` 和 `grain` 字段
- [ ] 新增 `core/entity.py` 模块
- [ ] 构建语义图（Entity Relationship Graph）
- [ ] 实现基于语义图的 Join 路径规划

**里程碑 1.3: Measure/Metric 分离**（Week 2）
- [ ] 新增 `config/measures.yaml`
- [ ] 重构 `config/metrics.yaml`，支持 Ratio/YoY/Derived Metric
- [ ] 更新 SemanticLayer 解析逻辑
- [ ] 增加 Metric 依赖分析

**里程碑 1.4: Relationship 增强**（Week 2-3）
- [ ] 增强 `schema.yaml` 的 `joins` 配置
- [ ] 新增基数验证（防止 many-to-many）
- [ ] 新增 Join 路径优先级和 Fan-out 检测
- [ ] 更新 SQL Generator 使用增强的 Join 配置

**里程碑 1.5: Filter 对象化**（Week 3）
- [ ] 新增 `config/filters.yaml`
- [ ] 更新 SemanticLayer 支持 Filter 解析
- [ ] 在自然语言理解中识别 Filter 术语
- [ ] 更新示例和文档

**验收标准：**
- ✅ 支持多 Domain 配置
- ✅ 显式的 Entity 定义和语义图可视化
- ✅ Measure 和 Metric 明确区分
- ✅ Join 路径规划考虑基数和优先级
- ✅ Filter 作为独立对象可复用
- ✅ 通过所有单元测试和回归测试

---

### 🎯 Phase 2: 安全和治理（2-3 周）

**目标：** 建立企业级权限治理和认证资产体系

**里程碑 2.1: Policy Engine 基础**（Week 4）
- [ ] 新增 `config/policies.yaml`
- [ ] 新增 `core/policy.py` 模块
- [ ] 实现表级权限（白名单增强）
- [ ] 实现字段级权限（黑名单）

**里程碑 2.2: 行级权限**（Week 4-5）
- [ ] 实现 Row-Level Security (RLS) 条件注入
- [ ] 支持用户属性绑定（如 region_code）
- [ ] 在 SQL 编译时自动注入 RLS 条件
- [ ] 添加 RLS 测试用例

**里程碑 2.3: 列级脱敏**（Week 5）
- [ ] 实现列掩码（Partial、Hash、Null）
- [ ] 在 SQL 生成时替换敏感字段为脱敏表达式
- [ ] 支持聚合查询绕过脱敏（SUM/COUNT）

**里程碑 2.4: Trusted Assets**（Week 5-6）
- [ ] 新增 `config/trusted_assets.yaml`
- [ ] 新增 `core/trusted_assets.py` 模块
- [ ] 实现问题模式匹配
- [ ] 实现 SQL 模板渲染和参数绑定
- [ ] 添加认证状态和审批流程

**里程碑 2.5: 查询约束**（Week 6）
- [ ] 实现聚合约束（只允许聚合，禁止明细）
- [ ] 实现最小分组人数约束（防止反推个人数据）
- [ ] 更新 SQLGuard 整合 Policy 检查

**验收标准：**
- ✅ 支持按角色配置表/字段权限
- ✅ 行级过滤自动注入到 SQL
- ✅ 敏感字段自动脱敏
- ✅ 关键指标使用 Trusted Assets 锁定口径
- ✅ 通过安全测试（越权、注入、泄露）

---

### 🎯 Phase 3: 评价和运营（2 周）

**目标：** 建立持续评价体系和语义对象生命周期管理

**里程碑 3.1: Benchmark 体系**（Week 7）
- [ ] 新增 `config/benchmarks.yaml`
- [ ] 新增 `tests/benchmark_runner.py`
- [ ] 实现语义解析测试（Intent 比对）
- [ ] 实现 SQL 结构测试（AST 比对）
- [ ] 实现结果测试（值范围、行数、列数）

**里程碑 3.2: 评价指标**（Week 7-8）
- [ ] 计算准确率（语义解析、SQL 生成、执行成功率）
- [ ] 计算性能指标（响应时间、Token 消耗）
- [ ] 生成评价报告（Markdown + HTML）
- [ ] 集成到 CI/CD（Pull Request 自动运行）

**里程碑 3.3: 语义对象生命周期**（Week 8）
- [ ] 为所有配置文件添加 `status` 字段（draft/approved/certified/deprecated）
- [ ] 为所有配置文件添加 `version` 和 `owner` 字段
- [ ] 实现配置变更影响分析（依赖图）
- [ ] 添加配置审批工作流（可选）

**里程碑 3.4: 反馈闭环**（Week 8）
- [ ] 新增用户反馈收集接口（正确/错误标记）
- [ ] 分析错误模式（Schema 选择、SQL 语法、结果验证）
- [ ] 自动生成修复建议（新增同义词、Filter、示例）
- [ ] 人工审核后更新配置和 Benchmark

**验收标准：**
- ✅ 50+ Benchmark 用例覆盖主要场景
- ✅ 自动计算并展示准确率和性能指标
- ✅ 配置变更自动触发回归测试
- ✅ 用户反馈能够驱动配置优化

---

### 🎯 Phase 4: 高级功能（2-3 周）

**目标：** 时间智能、语义检索、多层语义

**里程碑 4.1: 时间智能**（Week 9）
- [ ] 增强 Dimension 配置支持时间粒度、偏移、窗口
- [ ] 实现同比环比计算（YoY、MoM）
- [ ] 实现累计指标（YTD、MTD）
- [ ] 实现滚动窗口（Last 7 days、Last 4 weeks）

**里程碑 4.2: 高级 Metric**（Week 9-10）
- [ ] 实现 Conversion Metric（漏斗转化）
- [ ] 实现 Retention Metric（留存率）
- [ ] 实现 Window Metric（移动平均、累计求和）
- [ ] 更新 SQL Generator 支持窗口函数

**里程碑 4.3: 语义检索增强**（Week 10）
- [ ] 集成向量数据库（Chroma/FAISS）或 Embedding API
- [ ] 为所有语义对象生成 Embedding
- [ ] 实现分层检索（Domain → Metric → Dimension）
- [ ] 实现排序信号（相似度、频率、权限、历史成功率）

**里程碑 4.4: 双层语义**（Week 10-11）
- [ ] 设计企业级共享语义层（global）
- [ ] 设计 Agent 局部语义层（local override）
- [ ] 实现语义继承和覆盖规则
- [ ] 支持不同 Agent 使用不同业务术语

**里程碑 4.5: 多币种和财年**（Week 11）
- [ ] 在 Domain 中配置默认币种和财年规则
- [ ] 在 Measure 中添加币种字段
- [ ] 实现币种转换（如果需要跨币种聚合）
- [ ] 实现财年时间计算（FY2026 Q1）

**验收标准：**
- ✅ 支持同比环比、累计、滚动窗口查询
- ✅ 支持漏斗、留存等高级分析
- ✅ 语义检索准确率 > 90%
- ✅ 支持多 Agent 使用不同术语体系

---

### 🎯 Phase 5: 产品化和扩展（持续）

**目标：** 完善用户体验、多数据库支持、性能优化

**长期路线：**
- [ ] Web UI（语义层配置界面、Benchmark 面板）
- [ ] 多数据库支持（PostgreSQL、MySQL、ClickHouse）
- [ ] 查询结果缓存和预聚合
- [ ] 自动同义词建议（基于失败查询）
- [ ] 自动 Join 推断（基于外键和命名约定）
- [ ] 多轮对话（上下文继承）
- [ ] 图表自动生成（基于查询结果类型）
- [ ] API 和 MCP 增强（更多工具）
- [ ] Git 集成（配置版本控制）
- [ ] 多环境发布（Dev/Staging/Prod）

---

## 第四部分：实施优先级建议

### ⚡ 立即实施（Phase 1 + 部分 Phase 2）

**理由：** 这些功能构成 Genie 语义层的核心能力，对产品竞争力影响最大

1. **Domain**（1 周）- 多场景隔离的基础
2. **Entity 和语义图**（1 周）- 防止错误聚合的关键
3. **Measure/Metric 分离**（3 天）- 指标口径统一的前提
4. **Relationship 增强**（1 周）- Join 路径控制
5. **Filter 对象化**（3 天）- 业务规则复用
6. **Benchmark 体系**（1 周）- 质量保障

### 🔥 短期实施（Phase 2 + Phase 3）

**理由：** 安全治理和评价体系是企业级部署的必备条件

7. **Policy Engine**（1 周）- 权限治理基础
8. **Trusted Assets**（1 周）- 关键指标锁定
9. **评价指标和反馈闭环**（1 周）- 持续改进

### 🌟 中期实施（Phase 4）

**理由：** 提升用户体验和高级分析能力

10. **时间智能**（1 周）- 同比环比等常见需求
11. **语义检索增强**（1 周）- 提升匹配准确率
12. **高级 Metric**（1 周）- 漏斗、留存等分析

### 🎨 长期演进（Phase 5）

**理由：** 锦上添花，持续优化

13. **多数据库支持** - 扩大适用范围
14. **Web UI** - 降低配置门槛
15. **性能优化** - 缓存、预聚合

---

## 第五部分：风险和挑战

### 技术风险

1. **复杂度急剧增加**
   - 从 2000 行轻量框架演进为 10000+ 行企业平台
   - 缓解：渐进式重构，保持向后兼容

2. **LLM 能力边界**
   - 复杂语义可能超出模型理解能力
   - 缓解：Trusted Assets 锁定关键逻辑，降低对 LLM 依赖

3. **性能瓶颈**
   - 语义检索、权限注入可能增加延迟
   - 缓解：缓存、索引、异步执行

### 团队挑战

1. **需要数据架构师**
   - Entity、Relationship、Domain 设计需要专业能力
   - 建议：引入有数仓/语义层经验的架构师

2. **配置管理复杂度**
   - 从 5 个 YAML 增加到 10+ 个
   - 缓解：提供配置校验工具、Web UI

3. **持续运营**
   - Benchmark 维护、配置审批、反馈处理需要持续投入
   - 建议：建立专职的语义层运营角色

### 迁移风险

1. **现有配置重构**
   - metrics.yaml 需要拆分为 measures.yaml + metrics.yaml
   - 缓解：编写迁移脚本，保持兼容层

2. **API 兼容性**
   - 外部集成（MCP Server）可能需要调整
   - 缓解：保持 query_data(question) 接口不变

---

## 第六部分：成功指标

### 准确率指标

- **语义解析准确率** > 90%（Intent 正确识别）
- **SQL 生成准确率** > 85%（首次生成可执行）
- **业务口径正确率** > 95%（使用 Trusted Assets 的查询）

### 性能指标

- **端到端响应时间** < 5 秒（P95）
- **SQL 生成时间** < 2 秒（P95）
- **查询执行时间** < 3 秒（P95）

### 安全指标

- **危险 SQL 拦截率** = 100%（DROP/DELETE/UPDATE）
- **权限违规次数** = 0（行级、列级）

### 运营指标

- **Benchmark 覆盖率** > 80%（高频场景）
- **配置变更回归通过率** > 95%
- **用户反馈采纳率** > 50%（有效反馈）

---

## 附录 A：配置文件结构对比

### 当前（RDS Agent）
```
config/
├── schema.yaml       (表、字段、Join)
├── metrics.yaml      (混合 Measure 和 Metric)
├── dimensions.yaml   (维度)
├── terms.yaml        (术语)
└── examples.yaml     (示例)
```

### 目标（Genie-like）
```
config/
├── domains.yaml           (业务领域)
├── schema.yaml           (表、字段，增强 Entity 和 Relationship)
├── measures.yaml         (原子度量，新增)
├── metrics.yaml          (业务指标，重构)
├── dimensions.yaml       (维度，增强时间智能)
├── terms.yaml            (术语)
├── filters.yaml          (标准过滤器，新增)
├── policies.yaml         (权限策略，新增)
├── trusted_assets.yaml   (认证资产，新增)
├── benchmarks.yaml       (测试集，新增)
└── examples.yaml         (示例)
```

---

## 附录 B：核心模块扩展

### 当前（RDS Agent）
```
core/
├── catalog.py      (Schema 管理)
├── semantic.py     (语义解析)
├── planner.py      (查询计划)
├── generator.py    (SQL 生成)
├── guard.py        (SQL 安全)
├── executor.py     (查询执行)
├── validator.py    (结果验证)
└── composer.py     (答案组织)
```

### 目标（Genie-like）
```
core/
├── domain.py           (Domain 管理，新增)
├── entity.py           (Entity 和语义图，新增)
├── catalog.py          (Schema 管理，增强)
├── semantic.py         (语义解析，增强)
├── measure.py          (Measure 管理，新增)
├── metric.py           (Metric 计算，新增)
├── filter.py           (Filter 管理，新增)
├── policy.py           (Policy Engine，新增)
├── trusted_assets.py   (认证资产，新增)
├── planner.py          (查询计划，增强)
├── generator.py        (SQL 生成，增强)
├── guard.py            (SQL 安全，增强)
├── executor.py         (查询执行)
├── validator.py        (结果验证)
├── composer.py         (答案组织)
├── retrieval.py        (语义检索，新增)
└── benchmark.py        (Benchmark 运行器，新增)
```

---

## 附录 C：参考资源

### Genie 相关
- 上传的设计文档：`genie_semantic_layer_product_design.md`
- Databricks Genie 官方文档
- Semantic Layer 最佳实践

### 开源参考
- **Cube.js**：语义层框架
- **dbt Metrics**：Metric 定义规范
- **Malloy**：Google 的语义建模语言
- **LookML**：Looker 的语义层 DSL

### 学术论文
- *Towards a Semantic Layer for Enterprise Data*
- *Knowledge Graphs for Data Integration*
- *Ontology-based Data Access*

---

## 结论

RDS Agent 已经具备了扎实的基础架构和核心能力，通过 3-4 个月的分阶段实施，可以演进为一个具备 Genie 级别语义层能力的企业级数据分析平台。

**核心建议：**
1. **优先实施 Phase 1**（Domain、Entity、Measure/Metric 分离）- 这是语义层的基石
2. **快速迭代 Phase 2**（Policy、Trusted Assets）- 企业部署的必要条件
3. **持续改进 Phase 3**（Benchmark、反馈闭环）- 长期质量保障
4. **灵活选择 Phase 4**（根据业务需求选择高级功能）

**关键成功因素：**
- 引入数据架构师参与语义建模
- 建立配置审批和版本管理流程
- 持续运营 Benchmark 和用户反馈
- 保持轻量灵活，避免过度工程化

---

**文档版本：** v1.0
**创建日期：** 2026-09-04
**作者：** RDS Agent Team
**审批状态：** Draft
