# 项目文件清单

```
rds_agent/
│
├── ARCHITECTURE.md                    # 架构设计文档
├── PROJECT_SUMMARY.md                 # 项目总结文档
├── README.md                          # 项目说明文档
├── rds_agent_project_design.md       # 详细设计文档
├── dbgpt_deepagents_fixed_database_architecture.md  # 原始需求文档
│
├── requirements.txt                   # Python 依赖包
├── start.sh                          # 快速启动脚本
│
├── adapters/                         # 数据库适配器
│   ├── __init__.py
│   └── duckdb.py                     # DuckDB 适配器和示例数据
│
├── config/                           # 配置文件
│   ├── dimensions.yaml               # 维度定义
│   ├── examples.yaml                 # 示例 SQL
│   ├── metrics.yaml                  # 指标定义
│   ├── schema.yaml                   # Schema 定义
│   └── terms.yaml                    # 业务术语
│
├── core/                             # 核心组件
│   ├── __init__.py
│   ├── catalog.py                    # 数据库目录
│   ├── composer.py                   # 答案组织器
│   ├── executor.py                   # 查询执行器
│   ├── generator.py                  # SQL 生成器
│   ├── guard.py                      # SQL 安全网关
│   ├── planner.py                    # 查询计划器
│   ├── semantic.py                   # 语义层
│   └── validator.py                  # 结果验证器
│
├── examples/                         # 使用示例
│   ├── basic_query.py                # 基本查询示例
│   └── interactive_demo.py           # 交互式演示
│
├── tests/                            # 测试
│   ├── test_guard.py                 # SQL 安全测试
│   ├── test_semantic.py              # 语义层测试
│   └── test_workflow.py              # 工作流测试
│
└── workflow/                         # LangGraph 工作流
    ├── __init__.py
    ├── graph.py                      # 工作流图
    ├── nodes.py                      # 工作流节点
    └── states.py                     # 状态定义

总计:
- Python 文件: 20
- YAML 配置: 5
- Markdown 文档: 4
- Shell 脚本: 1
```
