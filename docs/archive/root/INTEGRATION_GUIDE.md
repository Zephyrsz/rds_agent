# RDS Agent 外部集成方案

## 概述

本文档介绍如何将 RDS Agent 暴露给外部 Agent（如 Hermes Agent）调用的多种集成方式。

## 方案对比

| 集成方式 | 适用场景 | 优势 | 劣势 | 复杂度 |
|---------|---------|------|------|--------|
| RESTful API | 通用、跨语言 | 标准化、易集成 | 需要网络通信 | ⭐⭐⭐ |
| MCP Server | Claude/LLM Agent | 官方标准、丰富上下文 | 仅限 MCP 生态 | ⭐⭐ |
| LangChain Tool | LangChain Agent | 原生集成 | 限 LangChain | ⭐ |
| Function Calling | OpenAI/Anthropic | 原生支持 | 需要精心设计 schema | ⭐⭐ |
| Python SDK | Python Agent | 直接调用、性能好 | 语言限制 | ⭐ |
| gRPC | 高性能场景 | 高效、强类型 | 实现复杂 | ⭐⭐⭐⭐ |

## 推荐方案

### 方案 1: MCP Server（最推荐）⭐⭐⭐⭐⭐

**适用场景**: DeepSeek Harness 等支持 MCP 的 Agent

**优势**:
- 官方标准协议，生态支持好
- 可以传递丰富的上下文信息
- 只暴露一个粗粒度查询工具
- 支持工具发现和动态调用

**实现步骤**:
1. 创建 MCP Server 实现
2. 定义工具 schema
3. 处理工具调用请求
4. 返回有上限的文本结果

详见: `integration/mcp_server.py`

---

### 方案 2: RESTful API（通用）⭐⭐⭐⭐

**适用场景**: 任何支持 HTTP 的 Agent

**优势**:
- 标准化、跨语言
- 易于部署和扩展
- 支持负载均衡

**实现步骤**:
1. 创建 FastAPI/Flask 应用
2. 定义 API endpoints
3. 添加认证和限流
4. 部署到服务器

详见: `integration/rest_api.py`

---

### 方案 3: LangChain Tool（LangChain Agent）⭐⭐⭐⭐

**适用场景**: 基于 LangChain 的 Agent

**优势**:
- 原生集成，无需额外服务
- 可以访问 Agent 的完整上下文
- 支持流式输出

**实现步骤**:
1. 继承 BaseTool
2. 实现 _run 和 _arun 方法
3. 注册到 Agent

详见: `integration/langchain_tool.py`

---

### 方案 4: Function Calling（OpenAI/Anthropic）⭐⭐⭐

**适用场景**: 使用 OpenAI/Anthropic API 的 Agent

**优势**:
- 原生支持，无需额外框架
- LLM 自动决策何时调用
- 支持并行调用

**实现步骤**:
1. 定义 function schema
2. 处理 function call 请求
3. 返回 function 结果

详见: `integration/function_calling.py`

---

### 方案 5: Python SDK（嵌入式）⭐⭐⭐

**适用场景**: Python Agent 直接集成

**优势**:
- 性能最好（无网络开销）
- 可以共享上下文
- 易于调试

**实现步骤**:
1. 封装简化的 API
2. 提供同步/异步接口
3. 文档化

详见: `integration/sdk.py`

---

## 集成架构图

### MCP Server 架构
```
┌─────────────────┐
│  Hermes Agent   │
│  (MCP Client)   │
└────────┬────────┘
         │ MCP Protocol
         │ (stdio/HTTP)
         ↓
┌─────────────────┐
│   MCP Server    │
│  (本项目封装)    │
├─────────────────┤
│ - query_data    │
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│   RDS Agent     │
│   Core Logic    │
└─────────────────┘
```

### RESTful API 架构
```
┌─────────────────┐
│  Hermes Agent   │
└────────┬────────┘
         │ HTTP/REST
         ↓
┌─────────────────┐
│   API Gateway   │
│  (FastAPI)      │
├─────────────────┤
│ POST /query     │
│ GET  /schema    │
│ GET  /metrics   │
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│   RDS Agent     │
│   Workflow      │
└─────────────────┘
```

### LangChain Tool 架构
```
┌────────────────────────┐
│   Hermes Agent         │
│   (LangChain Based)    │
├────────────────────────┤
│  Tools:                │
│  - RDSQueryTool ←──┐   │
│  - Other Tools     │   │
└────────────────────┼───┘
                     │
              直接调用（同进程）
                     │
┌────────────────────↓───┐
│   RDS Agent Core       │
└────────────────────────┘
```

## 数据流示例

### 1. 查询流程（MCP）
```
Hermes Agent 
    → MCP Request: tools/call
    → Tool: query_data
    → Args: {"question": "最近一个月的销售额"}
    ↓
MCP Server
    → 解析请求
    → 调用 workflow.run()
    → 等待结果
    ↓
RDS Agent
    → 执行完整工作流
    → 生成 SQL
    → 执行查询
    → 验证结果
    ↓
MCP Server
    → 格式化响应
    → 返回文本结果
    ↓
Hermes Agent
    → 接收结果
    → 继续对话
```

### 2. 查询流程（REST API）
```
Hermes Agent
    → POST /api/v1/query
    → Body: {"question": "..."}
    ↓
API Server
    → 认证和限流
    → 调用 workflow.run()
    ↓
RDS Agent
    → 执行工作流
    ↓
API Server
    → JSON 响应
    ↓
Hermes Agent
    → 解析 JSON
```

## 安全考虑

### 1. 认证
- API Key 认证
- JWT Token
- OAuth 2.0

### 2. 授权
- 基于角色的访问控制（RBAC）
- 数据行级权限
- 查询成本限制

### 3. 限流
- 用户级别限流
- IP 限流
- 查询复杂度限流

### 4. 审计
- 记录所有 API 调用
- 记录调用者身份
- 记录查询内容和结果

## 性能优化

### 1. 缓存
- 查询结果缓存（Redis）
- Schema 缓存
- 指标定义缓存

### 2. 异步处理
- 长查询异步执行
- Webhook 通知结果
- 轮询状态接口

### 3. 负载均衡
- 多实例部署
- 数据库连接池
- 请求队列

## 监控指标

### 1. 业务指标
- 查询成功率
- 平均响应时间
- SQL 生成准确率

### 2. 技术指标
- API 调用量
- 错误率
- 并发数

### 3. 资源指标
- CPU 使用率
- 内存使用率
- 数据库连接数

## 部署方案

### 1. Docker 部署
```bash
docker build -t rds-agent .
docker run -p 8000:8000 rds-agent
```

### 2. Kubernetes 部署
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: rds-agent
spec:
  replicas: 3
  ...
```

### 3. Serverless 部署
- AWS Lambda
- Google Cloud Functions
- Azure Functions

## 选择建议

根据你的场景选择：

1. **如果 Hermes Agent 支持 MCP**: 
   → 使用 MCP Server（方案 1）

2. **如果需要跨语言/跨平台**: 
   → 使用 RESTful API（方案 2）

3. **如果 Hermes Agent 基于 LangChain**: 
   → 使用 LangChain Tool（方案 3）

4. **如果希望最简单集成**: 
   → 使用 Function Calling（方案 4）

5. **如果都是 Python 且在同一进程**: 
   → 使用 Python SDK（方案 5）

## 下一步

查看具体实现代码：
- `integration/mcp_server.py` - MCP Server 完整实现
- `integration/rest_api.py` - RESTful API 完整实现
- `integration/langchain_tool.py` - LangChain Tool 实现
- `integration/function_calling.py` - Function Calling 示例
- `integration/sdk.py` - Python SDK 封装
