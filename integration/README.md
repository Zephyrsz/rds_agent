# RDS Agent 集成方案

本目录包含将 RDS Agent 暴露给外部 Agent 调用的多种集成方案。

## 文件说明

| 文件 | 集成方式 | 适用场景 |
|------|---------|---------|
| `mcp_server.py` | MCP Server | DeepSeek Harness 等支持 MCP 的 Agent |
| `deepseek-harness.cordis.yml` | Harness 配置 | 以 stdio 子进程挂载 MCP Server |
| `rest_api.py` | RESTful API | 任何支持 HTTP 的 Agent |
| `langchain_tool.py` | LangChain Tool | 基于 LangChain 的 Agent |
| `function_calling.py` | Function Calling | OpenAI/Anthropic 原生 Agent |
| `sdk.py` | Python SDK | Python Agent 嵌入式集成 |

## 快速开始

### 1. MCP Server

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
export OPENAI_API_KEY=your_api_key
venv/bin/python -m integration.mcp_server
```

Server 只暴露 `query_data(question)`。该工具执行完整 RDS 工作流并返回 SQL、最多 20 行数据预览、行数、执行时间和警告。业务查询失败会返回 MCP tool error。

在 DeepSeek Harness 中启用：

```bash
export RDS_AGENT_ROOT=/Users/rgwei/pj/pj_data/rds_agent
export DEEPSEEK_API_KEY=your_api_key

cd /Users/rgwei/pj/pj_agent/deepseek-harness
pnpm dsh --profile web --patch "$RDS_AGENT_ROOT/integration/deepseek-harness.cordis.yml"
```

Harness 将工具注册为 `mcp__rds__query_data`。配置默认连接 DeepSeek API 并使用 `deepseek-chat`；可通过 `RDS_LLM_API_KEY`、`RDS_LLM_BASE_URL`、`RDS_LLM_MODEL` 和 `RDS_DB_PATH` 覆盖。省略 `RDS_DB_PATH` 时使用内存示例数据库。

### 2. RESTful API

```bash
# 安装依赖
pip install fastapi uvicorn

# 运行 API 服务器
python integration/rest_api.py
```

API 文档: http://localhost:8000/docs

### 3. LangChain Tool

```python
from integration.langchain_tool import RDSQueryTool
from langchain.agents import initialize_agent, AgentType
from langchain_openai import ChatOpenAI

# 创建工具
tools = [RDSQueryTool()]

# 创建 Agent
llm = ChatOpenAI(temperature=0, model="gpt-4")
agent = initialize_agent(
    tools,
    llm,
    agent=AgentType.OPENAI_FUNCTIONS,
    verbose=True
)

# 使用 Agent
agent.run("最近一个月的销售额是多少？")
```

### 4. Function Calling

```python
from integration.function_calling import RDSAgentFunctionCalling, FUNCTIONS
from openai import OpenAI

# 初始化
rds_agent = RDSAgentFunctionCalling(config_dir)
client = OpenAI()

# 调用
response = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "查询销售额"}],
    functions=FUNCTIONS,
    function_call="auto",
)
```

### 5. Python SDK

```python
from integration.sdk import RDSAgent

# 初始化
agent = RDSAgent()

# 查询
result = agent.query("最近一个月的销售额是多少？")

if result.success:
    print(f"数据: {result.data}")
else:
    print(f"错误: {result.error}")

# 关闭
agent.close()
```

## API 参考

### Python SDK

#### RDSAgent

```python
class RDSAgent:
    def __init__(
        self,
        config_dir: Optional[Path] = None,
        db_path: str = ":memory:",
        llm_model: str = "gpt-4",
        llm_temperature: float = 0.0,
    )

    def query(self, question: str, user_context: Optional[Dict] = None) -> QueryResult
    async def aquery(self, question: str, user_context: Optional[Dict] = None) -> QueryResult
    def get_schema(self, table_name: Optional[str] = None) -> Dict[str, Any]
    def get_metrics(self) -> List[Dict[str, Any]]
    def get_dimensions(self) -> List[Dict[str, Any]]
    def get_statistics(self) -> Dict[str, Any]
    def close(self)
```

#### QueryResult

```python
@dataclass
class QueryResult:
    success: bool
    question: str
    sql: Optional[str] = None
    data: Optional[List[Dict]] = None
    row_count: int = 0
    execution_time: float = 0.0
    error: Optional[str] = None
    warnings: Optional[List[str]] = None
```

### RESTful API

#### POST /api/v1/query

**请求**:
```json
{
    "question": "最近一个月的销售额是多少？",
    "user_id": "user123"
}
```

**响应**:
```json
{
    "query_id": "...",
    "question": "...",
    "sql": "SELECT ...",
    "result": {...},
    "row_count": 10,
    "execution_time": 1.23,
    "status": "success"
}
```

#### GET /api/v1/schema

获取数据库 Schema。

#### GET /api/v1/metrics

获取所有可用指标。

#### GET /api/v1/dimensions

获取所有可用维度。

## 性能对比

| 集成方式 | 延迟 | 吞吐量 | 复杂度 |
|---------|------|--------|--------|
| Python SDK | 最低 (~100ms) | 最高 | 最低 |
| LangChain Tool | 低 (~100ms) | 高 | 低 |
| MCP Server | 中 (~200ms) | 中 | 中 |
| Function Calling | 中 (~300ms) | 中 | 中 |
| RESTful API | 高 (~500ms) | 低-中 | 高 |

## 部署建议

### 开发环境
- 使用 Python SDK 或 LangChain Tool（最快速、易调试）

### 生产环境
- 同一进程：Python SDK
- 微服务架构：RESTful API
- LLM 原生集成：Function Calling 或 MCP Server

## 安全注意事项

1. **认证**: 所有对外暴露的接口都应添加认证
2. **授权**: 实现基于角色的访问控制
3. **限流**: 防止滥用
4. **审计**: 记录所有查询请求
5. **加密**: 使用 HTTPS/TLS

## 常见问题

### Q: 如何选择集成方式？

A: 
- Hermes Agent 支持 MCP → 使用 MCP Server
- 跨语言/平台 → 使用 RESTful API
- LangChain Agent → 使用 LangChain Tool
- Python 同进程 → 使用 Python SDK

### Q: 如何处理长时间查询？

A: 
- RESTful API: 使用异步任务 + 轮询
- Python SDK: 使用 `aquery` 异步方法
- MCP Server: 当前为一个同步的粗粒度工具调用

### Q: 如何提高性能？

A:
1. 使用查询结果缓存
2. 预热常用 Schema
3. 使用连接池
4. 异步处理

## 示例项目

查看 `examples/` 目录获取完整的集成示例：

- `examples/mcp_client.py` - MCP Client 示例
- `examples/api_client.py` - REST API Client 示例
- `examples/langchain_agent.py` - LangChain Agent 示例

## 技术支持

如有问题，请查看项目文档或提交 Issue。
