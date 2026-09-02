# RDS Agent

RDS Agent 是一个面向固定数据库场景的数据分析 Agent。它使用 LangGraph 编排确定性查询流程，用业务语义配置约束指标、维度和术语，并通过 SQL 安全网关执行只读查询。

本文档以 DeepSeek Harness 为宿主，介绍从安装到验证、再到创建 Git 分支并推送远程仓库的完整流程。当前 PoC 采用 MCP stdio，只向 Harness 暴露一个粗粒度工具：query_data(question)。

## 集成后的调用链

~~~text
DeepSeek Harness Web / Headless
          |
          | @deepseek-ai/dsh-mcp-client
          | MCP over stdio
          v
RDS Agent integration/mcp_server.py
          |
          | query_data(question)
          v
RDS Agent SDK -> LangGraph workflow -> SQLGuard -> DuckDB
          |
          v
SQL、结果预览、行数、执行时间、警告
~~~

Harness 启动 RDS Agent 的 Python 子进程，并将其注册为 rds MCP server。Harness 内部看到的工具名是 mcp__rds__query_data。MCP stdout 只传输 JSON-RPC，诊断日志写入 stderr。

## 目录和环境变量

本文档使用以下目录变量。请替换为实际路径；不要把 API key 写进 YAML、README 或 Git。

~~~bash
export RDS_AGENT_ROOT=/Users/rgwei/pj/pj_data/rds_agent
export HARNESS_ROOT=/Users/rgwei/pj/pj_agent/deepseek-harness
~~~

后续所有命令都假定使用 macOS/Linux 的 bash 或 zsh。Windows 用户需要把 source、路径分隔符和 Python 可执行文件路径替换为对应写法。

## 1. 准备环境

需要：

- Python 3.11 或更高版本
- Node.js ^22.19.0 或 >=24.0.0
- pnpm（源码运行 DeepSeek Harness 时使用）
- Git
- 一个可调用 DeepSeek API 的 key

检查版本：

~~~bash
python3 --version
node --version
pnpm --version
git --version
~~~

配置本次 shell 会话使用的 key 和模型。下面只使用占位符：

~~~bash
export DEEPSEEK_API_KEY='<your-deepseek-api-key>'
export RDS_LLM_API_KEY="$DEEPSEEK_API_KEY"
export RDS_LLM_BASE_URL='https://api.deepseek.com'
export RDS_LLM_MODEL='deepseek-chat'
export RDS_CONFIG_DIR="$RDS_AGENT_ROOT/config"
~~~

RDS_LLM_API_KEY、RDS_LLM_BASE_URL 和 RDS_LLM_MODEL 会由 Harness patch 映射到 RDS Agent 子进程使用的 OPENAI_API_KEY、OPENAI_API_BASE 和模型配置。key 只应存在于当前进程环境、个人凭据管理器或未提交的 .env 文件中。

## 2. 安装 RDS Agent

创建隔离的 Python 虚拟环境并安装依赖：

~~~bash
cd "$RDS_AGENT_ROOT"
python3 -m venv venv
venv/bin/python -m pip install --upgrade pip
venv/bin/python -m pip install -r requirements.txt
~~~

MCP patch 使用的命令是 ./venv/bin/python -m integration.mcp_server，因此不要只在系统 Python 中安装依赖。安装后可先检查模块和 MCP 参数：

~~~bash
venv/bin/python -m integration.mcp_server --help
~~~

该命令只检查启动入口，不会执行真实查询，也不会要求 API key。

## 3. 安装官方 DeepSeek Harness

有两种官方运行方式。只做一次性体验可以使用 npm 包；需要反复修改 patch、调试集成或运行 pnpm dsh 时，建议使用源码 checkout。

### 3.1 npm 包方式

~~~bash
npx @deepseek-ai/dsh web
~~~

将 RDS patch 加载到 Web profile：

~~~bash
npx @deepseek-ai/dsh web \
  --patch "$RDS_AGENT_ROOT/integration/deepseek-harness.cordis.yml"
~~~

### 3.2 源码方式（开发集成推荐）

如果还没有 Harness checkout：

~~~bash
git clone https://github.com/deepseek-ai/deepseek-harness.git "$HARNESS_ROOT"
~~~

安装 workspace 依赖并构建产物：

~~~bash
cd "$HARNESS_ROOT"
pnpm install
pnpm run build
~~~

pnpm dsh 使用源码入口，但生产 profile 仍需要先生成构建产物。构建后可用 pnpm dsh --help 检查启动器。

## 4. 检查 MCP patch

集成配置位于 integration/deepseek-harness.cordis.yml。其关键配置如下：

~~~yaml
- insert:
    - id: rds-agent-mcp
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: rds
        transport: stdio
        command: ./venv/bin/python
        args: [-m, integration.mcp_server]
        cwd: !!js process.env.RDS_AGENT_ROOT
        env:
          OPENAI_API_KEY: !!js process.env.RDS_LLM_API_KEY || process.env.DEEPSEEK_API_KEY
          OPENAI_API_BASE: !!js process.env.RDS_LLM_BASE_URL || process.env.DEEPSEEK_BASE_URL || 'https://api.deepseek.com'
          RDS_LLM_MODEL: !!js process.env.RDS_LLM_MODEL || 'deepseek-chat'
          RDS_DB_PATH: !!js process.env.RDS_DB_PATH || ':memory:'
        toolCallTimeoutMs: 120000
        failOnStartupError: true
~~~

字段含义：

- serverName: rds：决定 Harness 工具名前缀 mcp__rds__。
- transport: stdio：Harness 通过子进程 stdin/stdout 使用 MCP，不需要额外 HTTP 端口。
- cwd：RDS Agent 项目根目录，必须指向包含 venv/、integration/ 和 config/ 的目录。
- command 与 args：使用项目虚拟环境启动 integration.mcp_server。
- env：把 DeepSeek 和数据库配置传给子进程。
- toolCallTimeoutMs：单次 MCP 调用最多等待 120 秒。
- failOnStartupError：MCP 子进程启动失败时让 Harness 尽早报告错误。

!!js 是 Harness 配置支持的环境表达式，必须保留两个感叹号。不要把 $RDS_AGENT_ROOT 展开后的绝对路径或真实 key 直接写到 YAML 中。

## 5. 启动 Web profile

### 5.1 源码 Harness 的标准命令

~~~bash
cd "$HARNESS_ROOT"
pnpm dsh --profile web \
  --patch "$RDS_AGENT_ROOT/integration/deepseek-harness.cordis.yml"
~~~

不希望自动打开浏览器或需要固定端口时：

~~~bash
pnpm dsh --profile web \
  --patch "$RDS_AGENT_ROOT/integration/deepseek-harness.cordis.yml" \
  --no-open \
  --port 3081
~~~

也可以使用 Web 别名：

~~~bash
pnpm dsh web \
  --patch "$RDS_AGENT_ROOT/integration/deepseek-harness.cordis.yml"
~~~

启动器参数和 Web 应用参数有边界：--profile、--patch 必须放在前面；遇到第一个 Web 应用参数后，后续内容会交给 Web profile。下面的顺序是错误的：

~~~bash
pnpm dsh --profile web --no-open --patch "$RDS_AGENT_ROOT/integration/deepseek-harness.cordis.yml"
~~~

此时 --no-open 已经开始作为 Web 参数传递，后面的 --patch 可能被 Web 应用报为 unknown option。把 --patch 放在 --no-open 前面即可。

默认地址是 http://127.0.0.1:3080；上例指定端口后访问 http://127.0.0.1:3081。

### 5.2 启动前检查组合配置

无需启动 Web 服务即可查看 patch 是否被加载：

~~~bash
cd "$HARNESS_ROOT"
pnpm dsh web \
  --patch "$RDS_AGENT_ROOT/integration/deepseek-harness.cordis.yml" \
  --dump-config
~~~

输出中应能看到 rds-agent-mcp、@deepseek-ai/dsh-mcp-client 和 stdio 配置。--dump-config 不会运行真实查询；!!js 表达式会按原样显示。

## 6. 验证 MCP 工具调用

### 6.1 Web UI 验证

启动 Web 后，在对话中提出一个需要数据库回答的问题，例如：

~~~text
请使用 RDS 数据工具查询最近一个月的总销售额，并说明生成的 SQL。
~~~

验证以下现象：

1. Harness 发现的工具名为 mcp__rds__query_data。
2. 工具参数只有 question，例如 {"question":"最近一个月的总销售额是多少？"}。
3. RDS 返回 SQL、行数、执行时间和最多 20 行数据预览。
4. SQL 不通过只读安全检查或数据库执行失败时，工具调用显示错误，而不是伪造成功结果。

### 6.2 Headless 验证

Headless 适合脚本和 CI 冒烟测试：

~~~bash
cd "$HARNESS_ROOT"
pnpm dsh --profile headless \
  --patch "$RDS_AGENT_ROOT/integration/deepseek-harness.cordis.yml" \
  '请查询最近一个月的总销售额，并返回结果。'
~~~

任务文本必须放在所有 launcher 参数之后。成功时命令输出最终回答并以退出码 0 结束；配置、MCP 启动或模型调用失败时以非零状态退出。

### 6.3 RDS Agent 单元测试

测试不依赖真实模型 key：

~~~bash
cd "$RDS_AGENT_ROOT"
venv/bin/python -m pytest -q
~~~

重点测试包括 SQLGuard、SDK 结果处理、MCP 工具发现与失败响应。真实 API 验证只在明确需要时执行，并应使用临时环境变量。

## 7. 配置真实数据库和业务语义

默认 RDS_DB_PATH 是 :memory:，每次启动 MCP 子进程都会创建示例 DuckDB 数据库。要连接真实 DuckDB 文件：

~~~bash
export RDS_DB_PATH="$RDS_AGENT_ROOT/data/business.duckdb"
~~~

当前 SDK 的行为是：

- :memory:：创建内存示例数据库。
- 指向已存在的 DuckDB 文件：打开该文件。
- 指向不存在的路径：创建示例数据库；生产环境应先确认路径和文件确实正确，避免误把拼写错误当成新库。

业务配置位于 config/：

| 文件 | 作用 |
|---|---|
| schema.yaml | 表、字段、主外键和允许访问的 Schema |
| metrics.yaml | 指标表达式、默认过滤条件和涉及的表 |
| dimensions.yaml | 维度字段及业务名称映射 |
| terms.yaml | 业务术语、同义词和自然语言映射 |
| examples.yaml | 示例问题、意图和高质量 SQL |

接入真实库时，应同时检查数据库表结构与这些配置。SQLGuard 会根据 schema.yaml 的允许表集合拒绝未声明的表；仅修改提示词而不更新 Schema 不会完成接入。修改指标、维度或术语后，先运行单元测试，再使用一个已知答案的问题做回归查询。

如果配置不在项目默认目录，可以设置：

~~~bash
export RDS_CONFIG_DIR=/absolute/path/to/rds-agent-config
~~~

## 8. 安全和运维边界

- MCP server 只暴露 query_data(question)，不暴露任意 SQL 执行工具、文件系统工具或数据库管理工具。
- SQLGuard 拒绝 DML/DDL、危险函数、未授权表和高风险查询，并限制结果集规模。
- 数据库凭据、API key 和生产库文件不应进入 Git。
- 生产环境应在 Harness 进程外配置凭据，并根据部署环境增加认证、审计、限流和网络隔离。
- stdio 通道的 stdout 是协议通道；不要在 integration/mcp_server.py 或其依赖中向 stdout 打印启动日志。调试信息应写 stderr。
- :memory: 适合 PoC，不适合需要跨重启保留数据的场景。

## 9. 常见问题排查

### unknown option --patch

通常是 launcher 参数顺序错误。使用：

~~~bash
pnpm dsh --profile web \
  --patch "$RDS_AGENT_ROOT/integration/deepseek-harness.cordis.yml" \
  --no-open
~~~

不要把 --no-open、--port 等 Web 参数放到 --patch 前面。

### MCP 工具没有出现

按顺序检查：

~~~bash
test -x "$RDS_AGENT_ROOT/venv/bin/python"
test -f "$RDS_AGENT_ROOT/integration/mcp_server.py"
cd "$HARNESS_ROOT"
pnpm dsh web \
  --patch "$RDS_AGENT_ROOT/integration/deepseek-harness.cordis.yml" \
  --dump-config
~~~

确认环境变量已在启动 Harness 的同一个 shell 中导出，并确认 cwd 是 RDS Agent 根目录。若 MCP 子进程启动失败，failOnStartupError: true 会让 Harness 在启动阶段报告原因。

### 401、模型不存在或 API base 错误

确认 key 已设置且模型配置正确：

~~~bash
if [ -n "$DEEPSEEK_API_KEY" ]; then echo "DEEPSEEK_API_KEY is set"; else echo "DEEPSEEK_API_KEY is empty"; fi
printf '%s\n' "$RDS_LLM_BASE_URL"
printf '%s\n' "$RDS_LLM_MODEL"
~~~

不要通过 echo "$DEEPSEEK_API_KEY" 打印 key。DeepSeek API 通常使用 https://api.deepseek.com 和 deepseek-chat；如果使用兼容网关，请同时修改 RDS_LLM_BASE_URL 和可用模型名。

### MCP JSON-RPC 解析失败

不要直接向 stdout 写日志或诊断文本。当前 server 已将 structlog 和示例数据库诊断输出到 stderr；如果自行增加日志，也必须沿用该约定。

### 查询返回示例数据或数据为空

检查 RDS_DB_PATH 是否为空、是否为 :memory:，以及指定文件是否真的存在。检查 schema.yaml、metrics.yaml 与实际表名和字段名是否一致。

### 查询超时

PoC 的 MCP 调用超时是 120 秒，RDS Agent 内部执行器还有查询时间和结果行数限制。先缩小时间范围、维度和结果集，再评估是否需要调整配置和数据库索引。

## 10. 开发检查清单

在提交前运行与本次改动相关的检查：

~~~bash
cd "$RDS_AGENT_ROOT"
venv/bin/python -m pytest -q
git diff --check
~~~

扫描工作区中是否误包含 key（只检查形如 sk- 的字符串，不会打印 key 内容）：

~~~bash
rg -n 'sk-[A-Za-z0-9]+' . \
  --glob '!venv/**' \
  --glob '!**/__pycache__/**' \
  --glob '!*.pyc' || true
~~~

提交前还应确认：

- venv/、缓存、日志和本地数据库被 .gitignore 忽略。
- README 和 patch 中只有占位符，没有真实凭据。
- integration/deepseek-harness.cordis.yml 使用绝对路径变量，不依赖调用者当前目录。
- Harness launcher 参数顺序在文档命令中保持正确。

## 11. 创建新 branch、提交并推送远程仓库

以下流程只操作 rds_agent 仓库，不会修改 DeepSeek Harness 仓库。

### 11.1 创建分支并检查工作区

~~~bash
cd "$RDS_AGENT_ROOT"
git status --short
git branch --show-current
git switch -c codex/deepseek-harness-integration
~~~

如果该分支已经存在，使用 git switch codex/deepseek-harness-integration，不要重复创建。创建分支后再次检查变更：

~~~bash
git status --short
git diff --stat
~~~

### 11.2 暂存和提交

确认 diff 中没有 key、虚拟环境、缓存或不应提交的本地数据库后执行：

~~~bash
git add -A
git diff --cached --stat
git diff --cached --check
git commit -m "docs: document DeepSeek Harness integration"
git show --stat --oneline HEAD
~~~

如果提交前发现错误，使用 git restore --staged <path> 取消某个文件的暂存，修正后再提交。不要使用 git reset --hard 覆盖未确认的工作区改动。

### 11.3 配置远程并推送

先确认当前仓库是否已经有远程地址：

~~~bash
git remote -v
~~~

如果没有 origin，需要使用实际仓库地址显式添加；不要猜测 owner 或仓库名，也不要在没有确认的情况下创建新的 GitHub 仓库：

~~~bash
git remote add origin https://github.com/<owner>/<rds-agent-repository>.git
git push -u origin codex/deepseek-harness-integration
~~~

如果 origin 已存在，先核对它是否指向目标仓库：

~~~bash
git remote get-url origin
git push -u origin codex/deepseek-harness-integration
~~~

推送成功后，可以在远程仓库创建 Pull Request，目标分支通常是 master 或团队指定的默认分支。推送失败时先检查远程 URL、登录身份和仓库权限，不要通过提交 key 或关闭安全检查来绕过问题。

## 12. 文件索引

- [integration/mcp_server.py](integration/mcp_server.py)：MCP stdio server，只暴露 query_data。
- [integration/sdk.py](integration/sdk.py)：Python SDK 和 RDSAgent.query()。
- [integration/deepseek-harness.cordis.yml](integration/deepseek-harness.cordis.yml)：DeepSeek Harness MCP overlay。
- [integration/README.md](integration/README.md)：MCP、REST、LangChain、Function Calling 和 SDK 的集成参考。
- [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md)：各集成方式的架构和选型说明。
- [ARCHITECTURE.md](ARCHITECTURE.md)：RDS Agent 分层架构和工作流设计。
- [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md)：当前功能、示例数据和实现摘要。
- config/：Schema、指标、维度、术语和 SQL 示例配置。
- tests/：核心组件和 MCP 集成测试。

## 许可证

MIT License。
