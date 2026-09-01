# RDS Agent

基于 DB-GPT 思路与 LangGraph 实现的轻量级数据分析 Agent，专注于固定数据库场景。

## 项目概述

RDS Agent 是一个面向固定数据库的领域专用 Data Agent Runtime，它结合了 DB-GPT 的数据分析思路和 LangGraph 的确定性工作流，为特定业务领域提供安全、可控、高准确率的自然语言数据查询能力。

### 核心特性

- **确定性工作流**: 使用 LangGraph 实现可审计、可恢复的状态机
- **业务语义层**: 显式定义指标、维度和业务术语，确保口径准确
- **SQL 安全网关**: 多层安全验证，防止 SQL 注入和危险操作
- **自动修复机制**: SQL 验证失败或执行错误时自动重试和修复
- **结果验证**: 对查询结果进行合理性检查，提高答案可信度
- **完整审计**: 记录每个节点的输入输出，便于追踪和调试

### 技术栈

- **流程编排**: LangGraph
- **Agent 框架**: LangChain
- **数据库**: DuckDB (首期，可扩展)
- **SQL 解析**: sqlparse
- **LLM**: OpenAI GPT-4 / Anthropic Claude

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 配置环境变量

```bash
export OPENAI_API_KEY=your_api_key
```

### 运行示例

#### 1. 基本查询示例

```bash
python examples/basic_query.py
```

这个示例会：
1. 创建一个包含示例数据的 DuckDB 数据库
2. 初始化所有核心组件
3. 执行几个预定义的查询
4. 显示查询结果和统计信息

#### 2. 交互式演示

```bash
python examples/interactive_demo.py
```

这是一个交互式程序，您可以：
- 输入自然语言问题
- 实时查看 Agent 生成的 SQL
- 查看查询结果
- 输入 `stats` 查看统计信息
- 输入 `quit` 退出

### 示例问题

```
最近一个月的总销售额是多少？
华东地区的订单数有多少？
各个地区的销售额分别是多少？
TOP 5 销售额最高的客户
最近三个月每个月的销售额趋势
```

## 项目结构

```
rds_agent/
├── core/                   # 核心组件
│   ├── catalog.py         # 数据库 Schema 目录
│   ├── semantic.py        # 业务语义层
│   ├── planner.py         # 查询计划生成器
│   ├── generator.py       # SQL 生成器
│   ├── guard.py           # SQL 安全网关
│   ├── executor.py        # 查询执行器
│   ├── validator.py       # 结果验证器
│   └── composer.py        # 答案组织器
│
├── workflow/              # LangGraph 工作流
│   ├── states.py         # 状态定义
│   ├── nodes.py          # 节点实现
│   └── graph.py          # 工作流图
│
├── adapters/             # 数据库适配器
│   └── duckdb.py        # DuckDB 适配器
│
├── config/               # 配置文件
│   ├── schema.yaml      # Schema 定义
│   ├── metrics.yaml     # 指标定义
│   ├── dimensions.yaml  # 维度定义
│   ├── terms.yaml       # 业务术语
│   └── examples.yaml    # 示例 SQL
│
├── examples/            # 使用示例
│   ├── basic_query.py
│   └── interactive_demo.py
│
└── tests/              # 测试
    └── fixtures/
```

## 系统架构

```
┌────────────────────────────────────────┐
│              API / UI                  │
├────────────────────────────────────────┤
│        LangGraph Workflow              │
│ (确定性状态机，条件分支，重试逻辑)       │
├────────────────────────────────────────┤
│          Data Agent Core               │
│ Intent → Plan → SQL → Verify → Answer │
├────────────────────────────────────────┤
│       Database Semantic Layer          │
│ Metrics, Dimensions, Joins, Terms     │
├────────────────────────────────────────┤
│         Safe Query Gateway             │
│ AST, Permission, Cost, Limit, Audit   │
├────────────────────────────────────────┤
│           Fixed Database               │
│            (DuckDB)                    │
└────────────────────────────────────────┘
```

## 工作流程

```
START
  ↓
classify_request (分类请求)
  ↓
resolve_semantics (解析语义)
  ↓
select_schema (选择 Schema)
  ↓
create_query_plan (创建查询计划)
  ↓
generate_sql (生成 SQL)
  ↓
validate_sql (验证 SQL)
  ├─ rejected → revise_sql (最多重试3次)
  └─ passed
        ↓
      explain_sql (分析执行计划)
        ├─ too_expensive → revise_sql
        └─ accepted
              ↓
          execute_sql (执行查询)
              ├─ error → repair_sql (最多重试2次)
              └─ success
                    ↓
              validate_result (验证结果)
                    ↓
              compose_answer (组织答案)
                    ↓
                   END
```

## 核心组件说明

### 1. DatabaseCatalog

管理数据库 Schema 信息，包括表结构、字段说明、主外键关系等。支持基于问题的相关 Schema 检索。

### 2. SemanticLayer

业务语义层，负责将用户的业务语言映射到数据库查询语言：
- 指标定义（如"销售额" → `SUM(net_amount)`）
- 维度定义（如"华东" → `region_code = 'EAST_CHINA'`）
- 时间范围解析（如"最近三个月"）
- 业务术语和同义词

### 3. QueryPlanner

查询计划生成器，根据问题类型生成不同的查询计划：
- 简单查询：单步查询
- 对比分析：多期间对比
- 趋势分析：时间序列分析
- 诊断分析：多维度深入分析

### 4. SQLGenerator

SQL 生成器，使用 LLM 生成 SQL 并支持错误修复：
- 根据查询计划和 Schema 上下文生成 SQL
- 基于错误反馈自动修复 SQL
- 支持重试机制

### 5. SQLGuard

SQL 安全网关，多层安全验证：
- AST 解析，禁止 DML/DDL 操作
- 表和字段白名单检查
- 检测笛卡尔积风险
- 强制 LIMIT 限制
- 敏感字段检查

### 6. QueryExecutor

查询执行器，安全执行只读查询：
- EXPLAIN 分析
- 超时控制
- 结果集大小限制
- 查询审计日志

### 7. ResultValidator

结果验证器，验证查询结果的合理性：
- 空结果检查
- 异常值检测
- 数据类型一致性
- 时间范围验证

### 8. AnswerComposer

答案组织器，将查询结果组织成用户友好的答案：
- 生成核心结论
- 提取关键指标
- 说明数据范围和口径
- 附带警告和审计信息

## 配置说明

### schema.yaml

定义数据库表结构、字段说明、主外键关系。

### metrics.yaml

定义业务指标的计算方式、涉及的表、默认过滤条件等。

### dimensions.yaml

定义业务维度及其映射关系（如地区代码映射到地区名称）。

### terms.yaml

定义业务术语和同义词，帮助系统理解用户的各种表达方式。

### examples.yaml

提供高质量的示例问题和 SQL，帮助 LLM 生成更准确的查询。

## 安全策略

### SQL 黑名单

- 禁止所有 DML 操作（INSERT, UPDATE, DELETE）
- 禁止所有 DDL 操作（DROP, ALTER, CREATE）
- 禁止危险函数（系统函数、文件操作等）
- 禁止访问系统表

### 查询限制

- 最大返回行数：10,000
- 查询超时：30 秒
- 强制添加 LIMIT（默认 1000）
- 检测笛卡尔积风险

### 审计日志

每个节点都会记录审计日志，包括：
- 节点名称和时间戳
- 输入和输出
- 执行时间
- 错误信息

## 扩展数据库支持

目前支持 DuckDB，扩展其他数据库只需：

1. 在 `adapters/` 下创建新的适配器类
2. 实现标准接口（connect, execute, cursor 等）
3. 更新配置文件以匹配新数据库的 Schema

示例：

```python
# adapters/postgresql.py
class PostgreSQLAdapter:
    def __init__(self, connection_string):
        self.connection_string = connection_string
        self.connection = None

    def connect(self):
        import psycopg2
        self.connection = psycopg2.connect(self.connection_string)
        return self.connection

    # ... 实现其他方法
```

## 开发路线

### ✅ Phase 1: 核心基础设施
- [x] DatabaseCatalog
- [x] SemanticLayer
- [x] SQLGuard
- [x] QueryExecutor
- [x] DuckDB 示例数据

### ✅ Phase 2: SQL 生成和修复
- [x] QueryPlanner
- [x] SQLGenerator
- [x] 错误反馈机制
- [x] LLM 集成

### ✅ Phase 3: LangGraph 工作流
- [x] 状态和节点定义
- [x] 工作流图
- [x] 重试和恢复逻辑
- [x] 审计日志

### ✅ Phase 4: 结果验证和答案生成
- [x] ResultValidator
- [x] AnswerComposer
- [x] 错误处理

### 🔄 Phase 5: 测试和优化
- [ ] 单元测试
- [ ] 黄金测试集
- [ ] 性能优化
- [ ] 文档完善

### 📋 Phase 6: 高级功能
- [ ] 多轮对话支持
- [ ] 查询结果缓存
- [ ] 图表生成
- [ ] 报告生成

## 贡献指南

欢迎贡献代码、报告问题或提出建议！

## 许可证

MIT License

## 致谢

本项目的设计思路参考了 DB-GPT 项目，感谢 DB-GPT 团队的开创性工作。
