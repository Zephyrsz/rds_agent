# DeepSeek Harness 生产级业务流程集成框架

## 目录
1. [整体架构设计](#1-整体架构设计)
2. [DeepSeek Harness 插件机制](#2-deepseek-harness-插件机制)
3. [核心组件设计](#3-核心组件设计)
4. [MCP Server 实现](#4-mcp-server-实现)
5. [业务流程编排](#5-业务流程编排)
6. [生产级特性](#6-生产级特性)
7. [部署方案](#7-部署方案)
8. [完整示例](#8-完整示例)

---

## 1. 整体架构设计

### 1.1 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                     DeepSeek Harness                             │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   Agent Runtime                           │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐ │   │
│  │  │  Model   │  │  Tool    │  │  Memory  │  │ Session │ │   │
│  │  │ Adapter  │  │ Registry │  │ Manager  │  │  Store  │ │   │
│  │  └──────────┘  └──────────┘  └──────────┘  └─────────┘ │   │
│  └──────────────────────────────────────────────────────────┘   │
└───────────────────────────┬─────────────────────────────────────┘
                            │ MCP Protocol (stdio/HTTP)
                            │
┌───────────────────────────┴─────────────────────────────────────┐
│              RDS Business Workflow MCP Server                    │
├──────────────────────────────────────────────────────────────────┤
│  MCP Tools (Harness 可见的工具)                                   │
│  ┌──────────────────┐  ┌──────────────────┐  ┌───────────────┐ │
│  │ rds_query        │  │ execute_workflow │  │ list_skills   │ │
│  │ (单次查询)        │  │ (编排执行)        │  │ (技能发现)     │ │
│  └──────────────────┘  └──────────────────┘  └───────────────┘ │
├──────────────────────────────────────────────────────────────────┤
│  Workflow Orchestrator (编排引擎)                                │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  State Machine │ Condition Router │ Parallel Executor   │   │
│  └─────────────────────────────────────────────────────────┘   │
├──────────────────────────────────────────────────────────────────┤
│  Skill Registry (技能注册中心)                                    │
│  ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌────────────┐   │
│  │ Data     │  │ Analysis  │  │Business  │  │Integration │   │
│  │ Skills   │  │ Skills    │  │ Skills   │  │ Skills     │   │
│  └──────────┘  └───────────┘  └──────────┘  └────────────┘   │
├──────────────────────────────────────────────────────────────────┤
│  Execution Layer (执行层)                                         │
│  ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌────────────┐   │
│  │ RDS      │  │ Analysis  │  │ Business │  │ API        │   │
│  │ Agent    │  │ Engine    │  │ Logic    │  │ Clients    │   │
│  └──────────┘  └───────────┘  └──────────┘  └────────────┘   │
├──────────────────────────────────────────────────────────────────┤
│  Infrastructure (基础设施)                                        │
│  ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌────────────┐   │
│  │ Config   │  │ Logger    │  │ Monitor  │  │ Secret     │   │
│  │ Manager  │  │           │  │          │  │ Manager    │   │
│  └──────────┘  └───────────┘  └──────────┘  └────────────┘   │
└──────────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
┌───────▼────────┐  ┌──────▼──────┐  ┌────────▼────────┐
│ DuckDB/SQLite  │  │ External    │  │ Notification    │
│ (Business Data)│  │ APIs        │  │ Services        │
│                │  │ (CRM/ERP)   │  │ (钉钉/企微)      │
└────────────────┘  └─────────────┘  └─────────────────┘
```

### 1.2 核心设计原则

1. **插件化：** 所有功能以 Skill 形式插件化，热加载和热更新
2. **编排优先：** 通过工作流编排而非硬编码实现业务逻辑
3. **MCP 原生：** 完全基于 MCP 协议，与 Harness 深度集成
4. **生产就绪：** 完整的错误处理、监控、日志、配置管理
5. **可扩展：** 易于添加新的 Skills 和 Workflows

---

## 2. DeepSeek Harness 插件机制

### 2.1 Harness 插件类型

DeepSeek Harness 支持多种插件机制：

| 插件类型 | 通信方式 | 特点 | 适用场景 |
|---------|---------|------|---------|
| **MCP stdio** | 子进程 stdio | 标准协议，语言无关 | 外部工具集成（推荐）|
| **MCP HTTP** | HTTP/SSE | 支持远程调用 | 分布式部署 |
| **Native Plugin** | JavaScript | 性能最优 | 内置功能 |
| **Cordis Plugin** | 事件总线 | 可拦截 Harness 内部事件 | 高级扩展 |

**本方案选择：MCP stdio + 可选 MCP HTTP**

### 2.2 MCP Tools 设计原则

#### 原则 1：粗粒度工具
```
❌ 不推荐：暴露过多细粒度工具
- get_sales_data
- calculate_anomaly
- send_notification
- create_order
（Harness 需要多次调用，增加延迟和复杂度）

✅ 推荐：暴露粗粒度业务工具
- execute_business_workflow (一次调用完成整个流程)
- rds_query (单次数据查询)
- list_available_workflows (发现能力)
```

#### 原则 2：自包含工具
每个工具应该：
- 输入明确，输出完整
- 包含足够的上下文信息
- 错误信息清晰可操作

#### 原则 3：可组合性
- 简单场景：直接调用 `rds_query`
- 复杂场景：调用 `execute_workflow` 编排多个步骤
- Harness 的 LLM 自主决策何时用哪个工具

---

## 3. 核心组件设计

### 3.1 配置管理系统

```python
# config/config.py
from typing import Dict, Any, Optional
from pathlib import Path
import yaml
import os
from dataclasses import dataclass, field

@dataclass
class DatabaseConfig:
    """数据库配置"""
    metadata_db_path: str = "var/metadata.db"
    business_db_path: str = ":memory:"
    connection_pool_size: int = 5
    query_timeout: int = 30

@dataclass
class WorkflowConfig:
    """工作流配置"""
    max_execution_time: int = 300
    max_retry_count: int = 3
    enable_parallel: bool = True
    enable_human_approval: bool = False

@dataclass
class IntegrationConfig:
    """外部集成配置"""
    api_registry: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    notification_channels: Dict[str, Dict[str, Any]] = field(default_factory=dict)

@dataclass
class MonitoringConfig:
    """监控配置"""
    enable_metrics: bool = True
    enable_tracing: bool = True
    log_level: str = "INFO"
    metrics_port: int = 9090

@dataclass
class AppConfig:
    """应用配置"""
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    workflow: WorkflowConfig = field(default_factory=WorkflowConfig)
    integration: IntegrationConfig = field(default_factory=IntegrationConfig)
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    
    @classmethod
    def load_from_file(cls, config_path: Path) -> "AppConfig":
        """从配置文件加载"""
        with open(config_path) as f:
            data = yaml.safe_load(f)
        
        return cls(
            database=DatabaseConfig(**data.get("database", {})),
            workflow=WorkflowConfig(**data.get("workflow", {})),
            integration=IntegrationConfig(**data.get("integration", {})),
            monitoring=MonitoringConfig(**data.get("monitoring", {}))
        )
    
    @classmethod
    def load_from_env(cls) -> "AppConfig":
        """从环境变量加载"""
        return cls(
            database=DatabaseConfig(
                metadata_db_path=os.getenv("RDS_METADATA_DB_PATH", "var/metadata.db"),
                business_db_path=os.getenv("RDS_BUSINESS_DB_PATH", ":memory:"),
            ),
            workflow=WorkflowConfig(
                max_execution_time=int(os.getenv("WORKFLOW_MAX_TIME", "300")),
                enable_human_approval=os.getenv("ENABLE_APPROVAL", "false").lower() == "true"
            )
        )

# 全局配置实例
config: Optional[AppConfig] = None

def init_config(config_path: Optional[Path] = None) -> AppConfig:
    """初始化配置"""
    global config
    if config_path and config_path.exists():
        config = AppConfig.load_from_file(config_path)
    else:
        config = AppConfig.load_from_env()
    return config

def get_config() -> AppConfig:
    """获取配置"""
    if config is None:
        return init_config()
    return config
```

### 3.2 日志和监控系统

```python
# monitoring/logger.py
import structlog
import sys
from typing import Any, Dict
import time
from contextlib import contextmanager

# 配置结构化日志
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

def get_logger(name: str) -> structlog.BoundLogger:
    """获取日志记录器"""
    return structlog.get_logger(name)

# monitoring/metrics.py
from prometheus_client import Counter, Histogram, Gauge
import functools
import time

# 定义指标
workflow_executions_total = Counter(
    'workflow_executions_total',
    'Total workflow executions',
    ['workflow_id', 'status']
)

workflow_duration_seconds = Histogram(
    'workflow_duration_seconds',
    'Workflow execution duration',
    ['workflow_id']
)

skill_executions_total = Counter(
    'skill_executions_total',
    'Total skill executions',
    ['skill_name', 'status']
)

skill_duration_seconds = Histogram(
    'skill_duration_seconds',
    'Skill execution duration',
    ['skill_name']
)

active_workflows = Gauge(
    'active_workflows',
    'Number of active workflows'
)

def track_workflow(workflow_id: str):
    """装饰器：跟踪工作流执行"""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            active_workflows.inc()
            start_time = time.time()
            status = "success"
            
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                status = "error"
                raise
            finally:
                duration = time.time() - start_time
                workflow_executions_total.labels(
                    workflow_id=workflow_id,
                    status=status
                ).inc()
                workflow_duration_seconds.labels(
                    workflow_id=workflow_id
                ).observe(duration)
                active_workflows.dec()
        
        return wrapper
    return decorator

def track_skill(skill_name: str):
    """装饰器：跟踪技能执行"""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            status = "success"
            
            try:
                result = await func(*args, **kwargs)
                if hasattr(result, 'success') and not result.success:
                    status = "failure"
                return result
            except Exception as e:
                status = "error"
                raise
            finally:
                duration = time.time() - start_time
                skill_executions_total.labels(
                    skill_name=skill_name,
                    status=status
                ).inc()
                skill_duration_seconds.labels(
                    skill_name=skill_name
                ).observe(duration)
        
        return wrapper
    return decorator

# monitoring/tracing.py
from typing import Optional, Dict, Any
import uuid
from contextvars import ContextVar

# 追踪上下文
trace_context: ContextVar[Optional[Dict[str, Any]]] = ContextVar('trace_context', default=None)

class TraceContext:
    """追踪上下文"""
    def __init__(
        self,
        trace_id: Optional[str] = None,
        parent_span_id: Optional[str] = None
    ):
        self.trace_id = trace_id or str(uuid.uuid4())
        self.span_id = str(uuid.uuid4())
        self.parent_span_id = parent_span_id
        self.metadata: Dict[str, Any] = {}
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "metadata": self.metadata
        }

@contextmanager
def trace_span(operation: str, **metadata):
    """创建追踪 span"""
    parent_ctx = trace_context.get()
    
    ctx = TraceContext(
        trace_id=parent_ctx.trace_id if parent_ctx else None,
        parent_span_id=parent_ctx.span_id if parent_ctx else None
    )
    ctx.metadata = {"operation": operation, **metadata}
    
    token = trace_context.set(ctx)
    logger = get_logger(__name__)
    
    logger.info(f"span_start", **ctx.to_dict())
    start_time = time.time()
    
    try:
        yield ctx
    finally:
        duration = time.time() - start_time
        logger.info(
            f"span_end",
            duration_seconds=duration,
            **ctx.to_dict()
        )
        trace_context.reset(token)
```

### 3.3 密钥管理系统

```python
# security/secrets.py
import os
from typing import Optional, Dict
from cryptography.fernet import Fernet
import json
from pathlib import Path

class SecretManager:
    """密钥管理器"""
    
    def __init__(self, encryption_key: Optional[str] = None):
        """初始化
        
        Args:
            encryption_key: 加密密钥（用于加密存储的密钥）
        """
        if encryption_key:
            self.cipher = Fernet(encryption_key.encode())
        else:
            self.cipher = None
        
        self._secrets: Dict[str, str] = {}
    
    def load_from_env(self, prefix: str = "SECRET_") -> None:
        """从环境变量加载密钥"""
        for key, value in os.environ.items():
            if key.startswith(prefix):
                secret_name = key[len(prefix):].lower()
                self._secrets[secret_name] = value
    
    def load_from_file(self, file_path: Path, encrypted: bool = False) -> None:
        """从文件加载密钥
        
        Args:
            file_path: 密钥文件路径
            encrypted: 是否加密存储
        """
        with open(file_path, 'rb') as f:
            data = f.read()
        
        if encrypted and self.cipher:
            data = self.cipher.decrypt(data)
        
        secrets = json.loads(data)
        self._secrets.update(secrets)
    
    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """获取密钥"""
        return self._secrets.get(key, default)
    
    def set(self, key: str, value: str) -> None:
        """设置密钥"""
        self._secrets[key] = value
    
    def save_to_file(self, file_path: Path, encrypted: bool = True) -> None:
        """保存到文件
        
        Args:
            file_path: 目标文件路径
            encrypted: 是否加密存储
        """
        data = json.dumps(self._secrets).encode()
        
        if encrypted and self.cipher:
            data = self.cipher.encrypt(data)
        
        with open(file_path, 'wb') as f:
            f.write(data)

# 全局密钥管理器
secret_manager = SecretManager()
secret_manager.load_from_env()
```

---

## 4. MCP Server 实现

### 4.1 主 MCP Server

```python
# mcp_server/main.py
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
import json
import asyncio
from typing import Dict, Any, Optional
from pathlib import Path
import sys

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.config import init_config, get_config
from monitoring.logger import get_logger
from monitoring.metrics import track_workflow
from monitoring.tracing import trace_span
from security.secrets import secret_manager
from workflow.orchestrator import WorkflowOrchestrator
from workflow.registry import workflow_registry
from skills.registry import skill_registry
from integration.sdk import RDSAgent

# 初始化
logger = get_logger(__name__)
config = init_config()

# 创建 MCP 服务器
mcp = FastMCP("rds-business-workflow")

# 全局组件
rds_agent: Optional[RDSAgent] = None
orchestrator: Optional[WorkflowOrchestrator] = None

def _init_components():
    """初始化组件"""
    global rds_agent, orchestrator
    
    if rds_agent is None:
        rds_agent = RDSAgent(
            metadata_db_path=config.database.metadata_db_path,
            db_path=config.database.business_db_path
        )
        logger.info("RDS Agent initialized")
    
    if orchestrator is None:
        orchestrator = WorkflowOrchestrator(skill_registry, config)
        logger.info("Workflow Orchestrator initialized")

@mcp.tool()
async def rds_query(question: str, reference_date: str = None) -> str:
    """查询业务数据
    
    直接使用 RDS Agent 查询业务数据库，返回 SQL 和数据结果。
    适用于简单的单次数据查询场景。
    
    Args:
        question: 自然语言问题，如"最近7天各地区销售额"
        reference_date: 参考日期（可选），格式 YYYY-MM-DD
    
    Returns:
        JSON 格式的查询结果，包含 SQL、数据、行数等
    
    Examples:
        - "最近一个月华东地区的营收"
        - "TOP 10 销售额最高的客户"
        - "昨天的订单数"
    """
    _init_components()
    
    with trace_span("rds_query", question=question):
        try:
            user_context = {}
            if reference_date:
                user_context["reference_date"] = reference_date
            
            result = rds_agent.query(question, user_context=user_context)
            
            if not result.success:
                raise ToolError(f"查询失败: {result.error}")
            
            response = {
                "success": True,
                "question": question,
                "sql": result.sql,
                "data": result.data[:20],  # 限制返回前20行
                "row_count": result.row_count,
                "execution_time": result.execution_time,
                "warnings": result.warnings or []
            }
            
            if result.row_count > 20:
                response["warnings"].append(
                    f"结果已截断，仅显示前 20 行（总共 {result.row_count} 行）"
                )
            
            logger.info(
                "rds_query_success",
                question=question,
                row_count=result.row_count,
                execution_time=result.execution_time
            )
            
            return json.dumps(response, ensure_ascii=False, indent=2)
        
        except Exception as e:
            logger.error("rds_query_error", error=str(e), question=question)
            raise ToolError(f"查询执行失败: {str(e)}")

@mcp.tool()
async def execute_workflow(
    workflow_name: str,
    inputs: str,
    enable_approval: bool = False
) -> str:
    """执行业务工作流
    
    执行预定义的业务工作流，可以串联多个步骤：数据查询 → 业务分析 → 业务操作 → API调用。
    适用于复杂的多步骤业务流程。
    
    Args:
        workflow_name: 工作流名称，使用 list_workflows 查看可用工作流
        inputs: JSON 格式的输入参数
        enable_approval: 是否启用人工审批（默认 False）
    
    Returns:
        JSON 格式的执行结果，包含每个步骤的输出
    
    Available Workflows:
        - sales_anomaly_detection: 销售异常检测与通知
        - inventory_replenishment: 库存预警与自动补货
        - customer_churn_prevention: 客户流失预警与挽回
    
    Example:
        workflow_name: "sales_anomaly_detection"
        inputs: {
            "question": "最近7天各地区销售额",
            "metric_column": "revenue",
            "threshold_std": 2.0,
            "notification_channel": "dingtalk",
            "recipients": ["18812345678"]
        }
    """
    _init_components()
    
    with trace_span("execute_workflow", workflow_name=workflow_name):
        try:
            # 解析输入
            try:
                initial_inputs = json.loads(inputs)
            except json.JSONDecodeError as e:
                raise ToolError(f"输入参数格式错误: {str(e)}")
            
            # 获取工作流
            workflow = workflow_registry.get(workflow_name)
            if not workflow:
                available = workflow_registry.list()
                raise ToolError(
                    f"工作流 '{workflow_name}' 不存在。"
                    f"可用工作流: {', '.join([w.name for w in available])}"
                )
            
            # 覆盖审批配置
            if enable_approval:
                workflow.config.enable_human_approval = True
            
            logger.info(
                "workflow_start",
                workflow_name=workflow_name,
                inputs=initial_inputs
            )
            
            # 执行工作流
            result = await orchestrator.execute(
                workflow,
                initial_inputs
            )
            
            # 格式化结果
            response = {
                "success": True,
                "workflow_id": workflow.id,
                "workflow_name": workflow.name,
                "execution_id": result.get("execution_id"),
                "status": result.get("status", "completed"),
                "steps": result.get("steps", {}),
                "final_output": result.get("final_output"),
                "execution_time": result.get("execution_time"),
                "warnings": result.get("warnings", [])
            }
            
            logger.info(
                "workflow_complete",
                workflow_name=workflow_name,
                status=response["status"],
                execution_time=response["execution_time"]
            )
            
            return json.dumps(response, ensure_ascii=False, indent=2)
        
        except Exception as e:
            logger.error(
                "workflow_error",
                workflow_name=workflow_name,
                error=str(e)
            )
            raise ToolError(f"工作流执行失败: {str(e)}")

@mcp.tool()
async def list_workflows(category: str = None) -> str:
    """列出所有可用的业务工作流
    
    查看系统中注册的所有业务工作流及其说明。
    
    Args:
        category: 工作流分类（可选），如 "sales", "inventory", "customer"
    
    Returns:
        JSON 格式的工作流列表
    """
    try:
        workflows = workflow_registry.list()
        
        # 按分类过滤
        if category:
            workflows = [
                w for w in workflows
                if category.lower() in (w.tags or [])
            ]
        
        result = {
            "total": len(workflows),
            "workflows": [
                {
                    "id": w.id,
                    "name": w.name,
                    "description": w.description,
                    "tags": w.tags or [],
                    "required_inputs": w.required_inputs or [],
                    "steps_count": len(w.nodes)
                }
                for w in workflows
            ]
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
    
    except Exception as e:
        logger.error("list_workflows_error", error=str(e))
        raise ToolError(f"获取工作流列表失败: {str(e)}")

@mcp.tool()
async def list_skills(skill_type: str = None) -> str:
    """列出所有可用的业务技能
    
    查看系统中注册的所有技能及其功能说明。
    
    Args:
        skill_type: 技能类型（可选），如 "data_query", "analysis", "operation"
    
    Returns:
        JSON 格式的技能列表
    """
    try:
        from skills.base import SkillType
        
        skill_type_enum = None
        if skill_type:
            try:
                skill_type_enum = SkillType(skill_type)
            except ValueError:
                valid_types = [t.value for t in SkillType]
                raise ToolError(
                    f"无效的技能类型: {skill_type}。"
                    f"有效类型: {', '.join(valid_types)}"
                )
        
        skills = skill_registry.list(skill_type=skill_type_enum)
        
        result = {
            "total": len(skills),
            "skills": [
                {
                    "name": s.name,
                    "display_name": s.display_name,
                    "description": s.description,
                    "type": s.skill_type.value,
                    "version": s.version,
                    "tags": s.tags or []
                }
                for s in skills
            ]
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
    
    except Exception as e:
        logger.error("list_skills_error", error=str(e))
        raise ToolError(f"获取技能列表失败: {str(e)}")

@mcp.tool()
async def get_workflow_status(execution_id: str) -> str:
    """获取工作流执行状态
    
    查询正在执行或已完成的工作流状态。
    
    Args:
        execution_id: 工作流执行 ID
    
    Returns:
        JSON 格式的执行状态
    """
    _init_components()
    
    try:
        status = await orchestrator.get_execution_status(execution_id)
        
        if not status:
            raise ToolError(f"执行记录不存在: {execution_id}")
        
        return json.dumps(status, ensure_ascii=False, indent=2)
    
    except Exception as e:
        logger.error("get_workflow_status_error", error=str(e))
        raise ToolError(f"获取执行状态失败: {str(e)}")

# 健康检查
@mcp.tool()
async def health_check() -> str:
    """系统健康检查
    
    检查系统各组件状态。
    """
    try:
        _init_components()
        
        health = {
            "status": "healthy",
            "components": {
                "rds_agent": "ok" if rds_agent else "not_initialized",
                "orchestrator": "ok" if orchestrator else "not_initialized",
                "skill_registry": f"{len(skill_registry.list())} skills loaded",
                "workflow_registry": f"{len(workflow_registry.list())} workflows loaded"
            },
            "config": {
                "metadata_db": config.database.metadata_db_path,
                "business_db": config.database.business_db_path
            }
        }
        
        return json.dumps(health, ensure_ascii=False, indent=2)
    
    except Exception as e:
        return json.dumps({
            "status": "unhealthy",
            "error": str(e)
        }, ensure_ascii=False)

def main():
    """启动 MCP 服务器"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="RDS Business Workflow MCP Server"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="配置文件路径"
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="传输方式"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="HTTP 端口（仅 http 模式）"
    )
    
    args = parser.parse_args()
    
    # 初始化配置
    if args.config:
        init_config(args.config)
    else:
        init_config()
    
    logger.info(
        "mcp_server_starting",
        transport=args.transport,
        config_file=str(args.config) if args.config else "env"
    )
    
    # 启动服务器
    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="http", port=args.port)

if __name__ == "__main__":
    main()
```

### 4.2 DeepSeek Harness 配置

```yaml
# config/deepseek-harness.production.yml
# 生产级 DeepSeek Harness 配置

- insert:
    # RDS Business Workflow MCP Server
    - id: rds-business-workflow
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: rds-workflow
        transport: stdio
        command: ./venv/bin/python
        args:
          - -m
          - mcp_server.main
          - --config
          - config/production.yaml
        cwd: !!js process.env.RDS_AGENT_ROOT || '/opt/rds-agent'
        env:
          # 数据库配置
          RDS_METADATA_DB_PATH: !!js process.env.RDS_METADATA_DB_PATH || '/data/metadata.db'
          RDS_BUSINESS_DB_PATH: !!js process.env.RDS_BUSINESS_DB_PATH || '/data/business.duckdb'
          
          # LLM 配置（RDS 内部使用）
          OPENAI_API_KEY: !!js process.env.RDS_LLM_API_KEY
          OPENAI_API_BASE: !!js process.env.RDS_LLM_BASE_URL || 'https://api.deepseek.com'
          RDS_LLM_MODEL: !!js process.env.RDS_LLM_MODEL || 'deepseek-chat'
          
          # 密钥配置
          SECRET_DINGTALK_WEBHOOK: !!js process.env.DINGTALK_WEBHOOK
          SECRET_WECOM_WEBHOOK: !!js process.env.WECOM_WEBHOOK
          SECRET_ERP_API_TOKEN: !!js process.env.ERP_API_TOKEN
          SECRET_CRM_API_TOKEN: !!js process.env.CRM_API_TOKEN
          
          # 监控配置
          LOG_LEVEL: !!js process.env.LOG_LEVEL || 'INFO'
          ENABLE_METRICS: !!js process.env.ENABLE_METRICS || 'true'
          METRICS_PORT: !!js process.env.METRICS_PORT || '9090'
          
          # 工作流配置
          WORKFLOW_MAX_TIME: !!js process.env.WORKFLOW_MAX_TIME || '300'
          ENABLE_APPROVAL: !!js process.env.ENABLE_APPROVAL || 'false'
        
        # 超时配置
        toolCallTimeoutMs: 300000  # 5分钟
        startupTimeoutMs: 30000    # 30秒
        
        # 错误处理
        failOnStartupError: true
        retryOnError: true
        maxRetries: 3
        
        # 资源限制
        maxConcurrentCalls: 10
```

---

## 5. 业务流程编排

### 5.1 工作流定义

```python
# workflow/definitions.py
from workflow.models import Workflow, WorkflowNode, WorkflowEdge, NodeType
from skills.registry import skill_registry

def define_sales_anomaly_workflow() -> Workflow:
    """销售异常检测与通知工作流"""
    return Workflow(
        id="sales_anomaly_detection",
        name="销售异常检测与通知",
        description="检测销售数据异常并自动通知团队",
        tags=["sales", "monitoring", "alert"],
        required_inputs=["question", "metric_column", "notification_channel", "recipients"],
        nodes=[
            WorkflowNode(
                id="query_sales",
                name="查询销售数据",
                node_type=NodeType.SKILL,
                skill_name="rds_query",
                inputs_mapping={
                    "question": "$.inputs.question",
                    "reference_date": "$.inputs.reference_date"
                },
                timeout_seconds=30
            ),
            WorkflowNode(
                id="detect_anomaly",
                name="检测异常",
                node_type=NodeType.SKILL,
                skill_name="anomaly_detection",
                inputs_mapping={
                    "data": "$.steps.query_sales.output.data",
                    "metric_column": "$.inputs.metric_column",
                    "threshold_std": "$.inputs.threshold_std"
                },
                timeout_seconds=60
            ),
            WorkflowNode(
                id="check_anomaly",
                name="检查是否有异常",
                node_type=NodeType.CONDITION,
                condition="$.steps.detect_anomaly.output.has_anomaly == true"
            ),
            WorkflowNode(
                id="format_alert",
                name="格式化告警内容",
                node_type=NodeType.SKILL,
                skill_name="format_notification",
                inputs_mapping={
                    "template": "sales_anomaly_alert",
                    "data": {
                        "question": "$.inputs.question",
                        "anomalies": "$.steps.detect_anomaly.output.anomalies",
                        "analysis": "$.steps.detect_anomaly.output.analysis",
                        "statistics": "$.steps.detect_anomaly.output.statistics"
                    }
                }
            ),
            WorkflowNode(
                id="send_alert",
                name="发送告警",
                node_type=NodeType.SKILL,
                skill_name="send_notification",
                inputs_mapping={
                    "channel": "$.inputs.notification_channel",
                    "recipients": "$.inputs.recipients",
                    "title": "$.steps.format_alert.output.title",
                    "content": "$.steps.format_alert.output.content"
                },
                timeout_seconds=30
            )
        ],
        edges=[
            WorkflowEdge(from_node="query_sales", to_node="detect_anomaly"),
            WorkflowEdge(from_node="detect_anomaly", to_node="check_anomaly"),
            WorkflowEdge(
                from_node="check_anomaly",
                to_node="format_alert",
                condition="$.steps.check_anomaly.output.result == true"
            ),
            WorkflowEdge(from_node="format_alert", to_node="send_alert")
        ],
        entry_node="query_sales"
    )

def define_inventory_replenishment_workflow() -> Workflow:
    """库存预警与自动补货工作流"""
    return Workflow(
        id="inventory_replenishment",
        name="库存预警与自动补货",
        description="检查库存状态，自动发起补货流程",
        tags=["inventory", "supply_chain", "automation"],
        required_inputs=["safety_stock_days", "approval_required"],
        nodes=[
            WorkflowNode(
                id="query_inventory",
                name="查询库存数据",
                node_type=NodeType.SKILL,
                skill_name="rds_query",
                inputs_mapping={
                    "question": "当前库存和最近30天销售速率"
                }
            ),
            WorkflowNode(
                id="calculate_replenishment",
                name="计算补货需求",
                node_type=NodeType.SKILL,
                skill_name="inventory_calculator",
                inputs_mapping={
                    "inventory_data": "$.steps.query_inventory.output.data",
                    "safety_stock_days": "$.inputs.safety_stock_days"
                }
            ),
            WorkflowNode(
                id="check_approval_required",
                name="检查是否需要审批",
                node_type=NodeType.CONDITION,
                condition="$.inputs.approval_required == true"
            ),
            WorkflowNode(
                id="human_approval",
                name="人工审批",
                node_type=NodeType.HUMAN_APPROVAL,
                approval_config={
                    "approvers": ["purchasing_manager"],
                    "timeout_seconds": 3600,
                    "notification_channel": "dingtalk"
                }
            ),
            WorkflowNode(
                id="create_purchase_order",
                name="创建采购订单",
                node_type=NodeType.SKILL,
                skill_name="api_call",
                inputs_mapping={
                    "api_name": "erp.purchase_order.create",
                    "method": "POST",
                    "body": "$.steps.calculate_replenishment.output.orders"
                }
            ),
            WorkflowNode(
                id="notify_team",
                name="通知采购团队",
                node_type=NodeType.SKILL,
                skill_name="send_notification",
                inputs_mapping={
                    "channel": "dingtalk",
                    "recipients": "$.inputs.recipients",
                    "title": "采购订单已创建",
                    "content": "$.steps.create_purchase_order.output"
                }
            )
        ],
        edges=[
            WorkflowEdge(from_node="query_inventory", to_node="calculate_replenishment"),
            WorkflowEdge(from_node="calculate_replenishment", to_node="check_approval_required"),
            WorkflowEdge(
                from_node="check_approval_required",
                to_node="human_approval",
                condition="$.steps.check_approval_required.output.result == true"
            ),
            WorkflowEdge(
                from_node="check_approval_required",
                to_node="create_purchase_order",
                condition="$.steps.check_approval_required.output.result == false"
            ),
            WorkflowEdge(from_node="human_approval", to_node="create_purchase_order"),
            WorkflowEdge(from_node="create_purchase_order", to_node="notify_team")
        ],
        entry_node="query_inventory"
    )

# 注册工作流
from workflow.registry import workflow_registry

workflow_registry.register(define_sales_anomaly_workflow())
workflow_registry.register(define_inventory_replenishment_workflow())
```

---

## 6. 生产级特性

### 6.1 错误处理和重试

```python
# workflow/error_handling.py
from typing import Callable, Any, TypeVar, Optional
import asyncio
from functools import wraps
from monitoring.logger import get_logger

logger = get_logger(__name__)
T = TypeVar('T')

class RetryPolicy:
    """重试策略"""
    def __init__(
        self,
        max_attempts: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True
    ):
        self.max_attempts = max_attempts
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
    
    def get_delay(self, attempt: int) -> float:
        """计算延迟时间"""
        import random
        
        delay = self.initial_delay * (self.exponential_base ** attempt)
        delay = min(delay, self.max_delay)
        
        if self.jitter:
            delay *= (0.5 + random.random())
        
        return delay

def with_retry(
    policy: Optional[RetryPolicy] = None,
    retryable_exceptions: tuple = (Exception,)
):
    """重试装饰器"""
    if policy is None:
        policy = RetryPolicy()
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            
            for attempt in range(policy.max_attempts):
                try:
                    return await func(*args, **kwargs)
                
                except retryable_exceptions as e:
                    last_exception = e
                    
                    if attempt < policy.max_attempts - 1:
                        delay = policy.get_delay(attempt)
                        logger.warning(
                            "retry_attempt",
                            function=func.__name__,
                            attempt=attempt + 1,
                            max_attempts=policy.max_attempts,
                            delay=delay,
                            error=str(e)
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            "retry_exhausted",
                            function=func.__name__,
                            attempts=policy.max_attempts,
                            error=str(e)
                        )
            
            raise last_exception
        
        return wrapper
    return decorator

class CircuitBreaker:
    """断路器"""
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exception: type = Exception
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._state = "closed"  # closed, open, half_open
    
    def __call__(self, func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            import time
            
            # 检查断路器状态
            if self._state == "open":
                if (time.time() - self._last_failure_time) > self.recovery_timeout:
                    self._state = "half_open"
                    logger.info("circuit_breaker_half_open", function=func.__name__)
                else:
                    raise Exception(f"Circuit breaker is open for {func.__name__}")
            
            try:
                result = await func(*args, **kwargs)
                
                # 成功，重置计数
                if self._state == "half_open":
                    self._state = "closed"
                    logger.info("circuit_breaker_closed", function=func.__name__)
                
                self._failure_count = 0
                return result
            
            except self.expected_exception as e:
                self._failure_count += 1
                self._last_failure_time = time.time()
                
                if self._failure_count >= self.failure_threshold:
                    self._state = "open"
                    logger.error(
                        "circuit_breaker_opened",
                        function=func.__name__,
                        failure_count=self._failure_count
                    )
                
                raise
        
        return wrapper
```

### 6.2 人工审批

```python
# workflow/approval.py
import asyncio
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import uuid
import time

@dataclass
class ApprovalRequest:
    """审批请求"""
    id: str
    workflow_id: str
    node_id: str
    title: str
    content: Dict[str, Any]
    approvers: List[str]
    created_at: float
    timeout_seconds: int
    status: str = "pending"  # pending, approved, rejected, timeout

class ApprovalManager:
    """审批管理器"""
    
    def __init__(self):
        self._pending_approvals: Dict[str, ApprovalRequest] = {}
        self._approval_results: Dict[str, bool] = {}
    
    async def request_approval(
        self,
        workflow_id: str,
        node_id: str,
        title: str,
        content: Dict[str, Any],
        approvers: List[str],
        timeout_seconds: int = 3600
    ) -> bool:
        """请求审批
        
        Args:
            workflow_id: 工作流 ID
            node_id: 节点 ID
            title: 审批标题
            content: 审批内容
            approvers: 审批人列表
            timeout_seconds: 超时时间（秒）
        
        Returns:
            是否批准
        """
        request_id = str(uuid.uuid4())
        
        request = ApprovalRequest(
            id=request_id,
            workflow_id=workflow_id,
            node_id=node_id,
            title=title,
            content=content,
            approvers=approvers,
            created_at=time.time(),
            timeout_seconds=timeout_seconds
        )
        
        self._pending_approvals[request_id] = request
        
        # 发送通知（通过配置的通知渠道）
        await self._send_approval_notification(request)
        
        # 等待审批结果
        start_time = time.time()
        while True:
            # 检查是否有结果
            if request_id in self._approval_results:
                approved = self._approval_results.pop(request_id)
                del self._pending_approvals[request_id]
                request.status = "approved" if approved else "rejected"
                return approved
            
            # 检查超时
            if (time.time() - start_time) > timeout_seconds:
                del self._pending_approvals[request_id]
                request.status = "timeout"
                raise TimeoutError(f"Approval timeout for {request_id}")
            
            await asyncio.sleep(1)
    
    async def _send_approval_notification(self, request: ApprovalRequest):
        """发送审批通知"""
        # TODO: 集成通知系统
        logger.info(
            "approval_notification_sent",
            request_id=request.id,
            approvers=request.approvers,
            title=request.title
        )
    
    def submit_approval(self, request_id: str, approved: bool, approver: str):
        """提交审批结果"""
        if request_id not in self._pending_approvals:
            raise ValueError(f"Approval request not found: {request_id}")
        
        request = self._pending_approvals[request_id]
        
        if approver not in request.approvers:
            raise ValueError(f"Approver {approver} not in approvers list")
        
        self._approval_results[request_id] = approved
        
        logger.info(
            "approval_submitted",
            request_id=request_id,
            approved=approved,
            approver=approver
        )
    
    def list_pending_approvals(self, approver: Optional[str] = None) -> List[ApprovalRequest]:
        """列出待审批请求"""
        approvals = list(self._pending_approvals.values())
        
        if approver:
            approvals = [a for a in approvals if approver in a.approvers]
        
        return approvals

# 全局审批管理器
approval_manager = ApprovalManager()
```

---

## 7. 部署方案

### 7.1 Docker 容器化部署

```dockerfile
# Dockerfile
FROM python:3.11-slim

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 创建数据目录
RUN mkdir -p /data /app/var

# 暴露 Prometheus metrics 端口
EXPOSE 9090

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.path.insert(0, '/app'); from mcp_server.main import _init_components; _init_components(); print('healthy')"

# 启动命令
CMD ["python", "-m", "mcp_server.main", "--config", "/app/config/production.yaml"]
```

```yaml
# docker-compose.yml
version: '3.8'

services:
  rds-workflow:
    build: .
    image: rds-workflow:latest
    container_name: rds-workflow
    restart: unless-stopped
    
    volumes:
      # 持久化数据
      - ./data:/data
      # 配置文件
      - ./config:/app/config:ro
      # 日志
      - ./logs:/app/logs
    
    environment:
      # 数据库
      - RDS_METADATA_DB_PATH=/data/metadata.db
      - RDS_BUSINESS_DB_PATH=/data/business.duckdb
      
      # LLM
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - OPENAI_API_BASE=${OPENAI_API_BASE:-https://api.deepseek.com}
      - RDS_LLM_MODEL=${RDS_LLM_MODEL:-deepseek-chat}
      
      # 密钥
      - SECRET_DINGTALK_WEBHOOK=${DINGTALK_WEBHOOK}
      - SECRET_ERP_API_TOKEN=${ERP_API_TOKEN}
      
      # 监控
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - ENABLE_METRICS=true
      - METRICS_PORT=9090
    
    ports:
      - "9090:9090"  # Prometheus metrics
    
    # 资源限制
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G
    
    # 健康检查
    healthcheck:
      test: ["CMD", "python", "-c", "from mcp_server.main import health_check; import asyncio; print(asyncio.run(health_check()))"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
  
  # Prometheus 监控
  prometheus:
    image: prom/prometheus:latest
    container_name: prometheus
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus-data:/prometheus
    ports:
      - "9091:9090"
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
    depends_on:
      - rds-workflow
  
  # Grafana 可视化
  grafana:
    image: grafana/grafana:latest
    container_name: grafana
    volumes:
      - grafana-data:/var/lib/grafana
      - ./monitoring/grafana/dashboards:/etc/grafana/provisioning/dashboards:ro
      - ./monitoring/grafana/datasources:/etc/grafana/provisioning/datasources:ro
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD:-admin}
    depends_on:
      - prometheus

volumes:
  prometheus-data:
  grafana-data:
```

### 7.2 Kubernetes 部署

```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: rds-workflow
  labels:
    app: rds-workflow
spec:
  replicas: 3
  selector:
    matchLabels:
      app: rds-workflow
  template:
    metadata:
      labels:
        app: rds-workflow
    spec:
      containers:
      - name: rds-workflow
        image: rds-workflow:latest
        ports:
        - containerPort: 9090
          name: metrics
        
        env:
        - name: RDS_METADATA_DB_PATH
          value: "/data/metadata.db"
        - name: RDS_BUSINESS_DB_PATH
          value: "/data/business.duckdb"
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: rds-secrets
              key: openai-api-key
        
        resources:
          limits:
            cpu: "2"
            memory: "2Gi"
          requests:
            cpu: "1"
            memory: "1Gi"
        
        volumeMounts:
        - name: data
          mountPath: /data
        - name: config
          mountPath: /app/config
          readOnly: true
        
        livenessProbe:
          exec:
            command:
            - python
            - -c
            - "from mcp_server.main import health_check; import asyncio; asyncio.run(health_check())"
          initialDelaySeconds: 30
          periodSeconds: 30
        
        readinessProbe:
          exec:
            command:
            - python
            - -c
            - "from mcp_server.main import _init_components; _init_components()"
          initialDelaySeconds: 10
          periodSeconds: 10
      
      volumes:
      - name: data
        persistentVolumeClaim:
          claimName: rds-data-pvc
      - name: config
        configMap:
          name: rds-config

---
apiVersion: v1
kind: Service
metadata:
  name: rds-workflow-metrics
spec:
  selector:
    app: rds-workflow
  ports:
  - port: 9090
    targetPort: 9090
    name: metrics

---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: rds-data-pvc
spec:
  accessModes:
  - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
```

---

## 8. 完整示例

### 8.1 启动服务

```bash
# 方式 1: Docker Compose
cd /opt/rds-agent
docker-compose up -d

# 方式 2: 直接运行
python -m mcp_server.main --config config/production.yaml

# 方式 3: Kubernetes
kubectl apply -f k8s/
```

### 8.2 配置 DeepSeek Harness

```bash
# 1. 设置环境变量
export RDS_AGENT_ROOT=/opt/rds-agent
export RDS_METADATA_DB_PATH=/data/metadata.db
export RDS_BUSINESS_DB_PATH=/data/business.duckdb
export RDS_LLM_API_KEY=your_key
export DINGTALK_WEBHOOK=your_webhook
export ERP_API_TOKEN=your_token

# 2. 启动 Harness
cd /path/to/deepseek-harness
pnpm dsh --profile web \
  --patch $RDS_AGENT_ROOT/config/deepseek-harness.production.yml
```

### 8.3 使用示例

#### 场景 1: 简单数据查询

```
User: 最近7天各地区的销售额

Harness LLM: [自动选择 rds_query 工具]
  Tool Call: rds_query(
    question="最近7天各地区的销售额"
  )

Response: {
  "success": true,
  "sql": "SELECT region, SUM(amount) as revenue ...",
  "data": [...],
  "row_count": 5
}
```

#### 场景 2: 复杂业务流程

```
User: 检查销售数据是否有异常，如果有问题自动通知团队

Harness LLM: [自动选择 execute_workflow 工具]
  Tool Call: execute_workflow(
    workflow_name="sales_anomaly_detection",
    inputs={
      "question": "最近7天各地区销售额",
      "metric_column": "revenue",
      "threshold_std": 2.0,
      "notification_channel": "dingtalk",
      "recipients": ["18812345678"]
    }
  )

Response: {
  "success": true,
  "workflow_id": "sales_anomaly_detection",
  "status": "completed",
  "steps": {
    "query_sales": {"status": "success", "row_count": 7},
    "detect_anomaly": {"status": "success", "has_anomaly": true, "anomalies": [...]},
    "send_alert": {"status": "success", "message_id": "xxx"}
  },
  "execution_time": 12.5
}
```

#### 场景 3: 查看可用能力

```
User: 你能帮我做什么？

Harness LLM: [调用 list_workflows 和 list_skills]
  Tool Call: list_workflows()
  Tool Call: list_skills()

Response: 我可以帮你执行以下业务流程：
1. sales_anomaly_detection - 销售异常检测与通知
2. inventory_replenishment - 库存预警与自动补货
3. customer_churn_prevention - 客户流失预警与挽回

支持的技能包括：数据查询、异常检测、通知发送、API调用等...
```

---

## 9. 总结

### 9.1 核心优势

✅ **统一入口：** 通过 DeepSeek Harness 统一管理所有业务流程
✅ **智能编排：** LLM 自动决策使用哪个工具或工作流
✅ **生产就绪：** 完整的错误处理、监控、日志、配置管理
✅ **高度可扩展：** 易于添加新 Skills 和 Workflows
✅ **容器化部署：** 支持 Docker 和 Kubernetes
✅ **可观测性：** Prometheus + Grafana 监控

### 9.2 与现有系统对比

| 特性 | 传统方式 | 本方案 |
|------|---------|--------|
| **流程串联** | 硬编码 | 工作流编排 |
| **工具发现** | 文档查找 | LLM 自动选择 |
| **错误处理** | 手动捕获 | 自动重试+断路器 |
| **监控** | 缺失或分散 | 统一 Metrics |
| **部署** | 手动配置 | 容器化+K8s |
| **扩展性** | 修改代码 | 添加插件 |

### 9.3 实施建议

**Phase 1（1周）：** 搭建基础框架
- MCP Server 框架
- 配置管理系统
- 监控和日志

**Phase 2（1周）：** 核心 Skills 实现
- RDS Query Skill
- Anomaly Detection Skill
- Notification Skill
- API Call Skill

**Phase 3（1周）：** 工作流编排
- Workflow Orchestrator
- 2-3 个典型业务工作流
- 审批流程

**Phase 4（1周）：** 生产化
- 容器化部署
- Harness 集成测试
- 文档和培训

**总计：约 4 周完成生产级框架**

---

**文档版本：** v1.0  
**最后更新：** 2026-09-07  
**适用场景：** 基于 DeepSeek Harness 的企业级业务流程自动化
