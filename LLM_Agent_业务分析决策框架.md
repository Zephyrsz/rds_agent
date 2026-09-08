# LLM Agent 驱动的业务分析与决策框架

## 目录
1. [设计理念与架构](#1-设计理念与架构)
2. [业界最佳实践](#2-业界最佳实践)
3. [核心架构设计](#3-核心架构设计)
4. [LLM Agent 系统](#4-llm-agent-系统)
5. [业务分析 Agent](#5-业务分析-agent)
6. [业务决策 Agent](#6-业务决策-agent)
7. [与 DeepSeek Harness 集成](#7-与-deepseek-harness-集成)
8. [配置化 Skill 设计](#8-配置化-skill-设计)
9. [完整示例](#9-完整示例)
10. [生产级特性](#10-生产级特性)

---

## 1. 设计理念与架构

### 1.1 核心理念

```
传统方式（硬编码）:
数据 → 固定规则判断 → 固定动作

本方案（LLM Agent）:
数据 → LLM 分析推理 → LLM 决策 → 动态动作
      ↑               ↑
    工具调用        上下文学习
```

**核心优势：**
- ✅ **灵活性：** 无需为每个业务场景硬编码规则
- ✅ **智能性：** LLM 可以理解复杂的业务上下文
- ✅ **可扩展：** 通过配置添加新的分析和决策能力
- ✅ **自适应：** LLM 可以根据历史数据学习和改进

### 1.2 整体架构

```
┌────────────────────────────────────────────────────────────────────┐
│                      DeepSeek Harness                               │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │           Primary Agent (主 Agent)                            │  │
│  │  "检查销售是否异常，如有问题自动处理"                           │  │
│  └────────────────────────┬─────────────────────────────────────┘  │
│                           │ Tool Call                               │
└───────────────────────────┼─────────────────────────────────────────┘
                            │ MCP Protocol
┌───────────────────────────┴─────────────────────────────────────────┐
│              RDS Business Workflow MCP Server                        │
├──────────────────────────────────────────────────────────────────────┤
│  Exposed MCP Tools:                                                  │
│  ┌────────────────┐  ┌──────────────────┐  ┌───────────────────┐  │
│  │ rds_query      │  │ analyze_with_llm │  │ decide_with_llm   │  │
│  │ (查询数据)      │  │ (LLM分析)        │  │ (LLM决策)          │  │
│  └────────────────┘  └──────────────────┘  └───────────────────┘  │
├──────────────────────────────────────────────────────────────────────┤
│  Internal Agent System (内部 Agent 系统)                              │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Business Analysis Agent (业务分析 Agent)                     │  │
│  │  ┌─────────────────────────────────────────────────────────┐ │  │
│  │  │ LLM: DeepSeek/GPT-4                                      │ │  │
│  │  │ Prompt: 业务分析专家提示词                                 │ │  │
│  │  │ Tools: statistical_analysis, trend_detection,            │ │  │
│  │  │        anomaly_detection, correlation_analysis           │ │  │
│  │  └─────────────────────────────────────────────────────────┘ │  │
│  └──────────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Business Decision Agent (业务决策 Agent)                     │  │
│  │  ┌─────────────────────────────────────────────────────────┐ │  │
│  │  │ LLM: DeepSeek/GPT-4                                      │ │  │
│  │  │ Prompt: 业务决策专家提示词                                 │ │  │
│  │  │ Tools: rule_evaluation, impact_assessment,              │ │  │
│  │  │        action_recommendation, risk_calculation           │ │  │
│  │  └─────────────────────────────────────────────────────────┘ │  │
│  └──────────────────────────────────────────────────────────────┘  │
├──────────────────────────────────────────────────────────────────────┤
│  Tool Registry (工具注册中心)                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
│  │ RDS      │  │ Statistical│ │ ML       │  │ Business │          │
│  │ Query    │  │ Analysis  │  │ Models   │  │ Rules    │          │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘          │
├──────────────────────────────────────────────────────────────────────┤
│  Knowledge Base (知识库)                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
│  │ Business │  │ Historical│  │ Best     │  │ Domain   │          │
│  │ Context  │  │ Cases     │  │ Practices│  │ Knowledge│          │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘          │
└──────────────────────────────────────────────────────────────────────┘
```

### 1.3 三层 Agent 架构

```
Layer 1: Primary Agent (Harness 主 Agent)
  - 理解用户意图
  - 调度工作流
  - 整合最终结果

Layer 2: Specialized Agents (专业 Agent - 在 MCP Server 内部)
  - Business Analysis Agent (业务分析)
  - Business Decision Agent (业务决策)
  - 每个 Agent 有专门的提示词和工具

Layer 3: Tool Execution (工具执行)
  - RDS 数据查询
  - 统计分析
  - 规则引擎
  - 外部 API
```

---

## 2. 业界最佳实践

### 2.1 ReAct (Reasoning + Acting)

**论文：** [ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629)

**核心思想：**
```
Thought: 我需要分析销售数据的趋势
Action: statistical_analysis(data, method="trend")
Observation: 销售额呈现下降趋势，下降幅度为 15%
Thought: 下降幅度超过 10%，需要进一步分析原因
Action: correlation_analysis(sales, factors)
Observation: 与市场活动减少相关性高 (r=0.85)
Thought: 建议增加市场投入
```

### 2.2 Tool Use Pattern

**最佳实践：**
- Tools 应该是原子化的、单一职责的
- 每个 Tool 有清晰的输入输出 Schema
- Tool 返回结构化数据，而非自然语言

**示例：**
```python
# ✅ Good
@tool
def calculate_growth_rate(current: float, previous: float) -> dict:
    """计算增长率"""
    return {
        "growth_rate": (current - previous) / previous,
        "growth_amount": current - previous
    }

# ❌ Bad
@tool
def analyze_sales(data: list) -> str:
    """分析销售（职责不清晰，返回自然语言）"""
    return "销售额增长了 10%，表现不错"
```

### 2.3 Multi-Agent Collaboration

**模式 1: Sequential（顺序协作）**
```
Agent A (分析) → Agent B (决策) → Agent C (执行)
```

**模式 2: Hierarchical（层级协作）**
```
Supervisor Agent
    ├─ Worker Agent 1
    ├─ Worker Agent 2
    └─ Worker Agent 3
```

**模式 3: Debate（辩论协作）**
```
Agent A (乐观视角) ←→ Agent B (保守视角)
           ↓
    Aggregator Agent (综合决策)
```

### 2.4 Prompt Engineering

**System Prompt 结构：**
```markdown
# Role (角色)
你是一个资深的业务数据分析专家...

# Context (上下文)
当前分析的是零售行业的销售数据...

# Capabilities (能力)
你可以使用以下工具：
- statistical_analysis: 统计分析
- trend_detection: 趋势检测
...

# Guidelines (指导原则)
1. 先进行探索性分析
2. 使用多种方法交叉验证
3. 给出可解释的结论
...

# Output Format (输出格式)
请以 JSON 格式返回分析结果...
```

### 2.5 RAG (Retrieval-Augmented Generation)

**应用场景：**
```
用户问题 → 检索历史案例 → 注入上下文 → LLM 生成答案

示例：
"华东地区销售下降如何处理？"
    ↓ 检索
历史案例：2023年Q2华东销售下降，采取措施为...
    ↓ 注入
LLM: 基于历史经验，建议采取以下措施...
```

---

## 3. 核心架构设计

### 3.1 Agent 基础框架

```python
# agents/base.py
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from enum import Enum
import json

class AgentRole(Enum):
    """Agent 角色"""
    ANALYST = "analyst"          # 分析师
    DECISION_MAKER = "decision_maker"  # 决策者
    EXECUTOR = "executor"        # 执行者
    SUPERVISOR = "supervisor"    # 监督者

@dataclass
class Message:
    """消息"""
    role: str  # system, user, assistant, tool
    content: str
    name: Optional[str] = None
    tool_calls: Optional[List[Dict]] = None
    tool_call_id: Optional[str] = None

@dataclass
class AgentConfig:
    """Agent 配置"""
    name: str
    role: AgentRole
    model: str = "deepseek-chat"
    temperature: float = 0.0
    max_tokens: int = 4000
    system_prompt: str = ""
    tools: List[Callable] = field(default_factory=list)
    knowledge_base: Optional[str] = None
    examples: List[Dict] = field(default_factory=list)
    max_iterations: int = 10
    enable_reasoning: bool = True

@dataclass
class AgentResponse:
    """Agent 响应"""
    success: bool
    content: str
    reasoning_steps: List[str] = field(default_factory=list)
    tool_calls: List[Dict] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

class BaseAgent(ABC):
    """Agent 基类"""
    
    def __init__(self, config: AgentConfig):
        self.config = config
        self.messages: List[Message] = []
        self.tools_map: Dict[str, Callable] = {}
        
        # 注册工具
        for tool in config.tools:
            self.tools_map[tool.__name__] = tool
        
        # 初始化系统提示词
        self._init_system_prompt()
    
    def _init_system_prompt(self):
        """初始化系统提示词"""
        system_prompt = self.config.system_prompt
        
        # 添加工具描述
        if self.tools_map:
            tools_desc = self._generate_tools_description()
            system_prompt += f"\n\n## 可用工具\n{tools_desc}"
        
        # 添加示例
        if self.config.examples:
            examples_desc = self._generate_examples_description()
            system_prompt += f"\n\n## 示例\n{examples_desc}"
        
        self.messages.append(Message(
            role="system",
            content=system_prompt
        ))
    
    def _generate_tools_description(self) -> str:
        """生成工具描述"""
        lines = []
        for name, tool in self.tools_map.items():
            doc = tool.__doc__ or "无描述"
            lines.append(f"- **{name}**: {doc.strip()}")
        return "\n".join(lines)
    
    def _generate_examples_description(self) -> str:
        """生成示例描述"""
        lines = []
        for i, example in enumerate(self.config.examples, 1):
            lines.append(f"### 示例 {i}")
            lines.append(f"**输入：** {example.get('input', '')}")
            lines.append(f"**输出：** {example.get('output', '')}")
            lines.append("")
        return "\n".join(lines)
    
    @abstractmethod
    async def run(self, task: str, context: Dict[str, Any] = None) -> AgentResponse:
        """执行任务"""
        pass
    
    async def _call_llm(self, messages: List[Message]) -> Dict[str, Any]:
        """调用 LLM"""
        from langchain_openai import ChatOpenAI
        
        llm = ChatOpenAI(
            model=self.config.model,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens
        )
        
        # 转换消息格式
        lc_messages = []
        for msg in messages:
            if msg.role == "system":
                from langchain_core.messages import SystemMessage
                lc_messages.append(SystemMessage(content=msg.content))
            elif msg.role == "user":
                from langchain_core.messages import HumanMessage
                lc_messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                from langchain_core.messages import AIMessage
                lc_messages.append(AIMessage(content=msg.content))
        
        # 绑定工具
        if self.tools_map:
            from langchain_core.tools import tool as lc_tool
            tools = []
            for name, func in self.tools_map.items():
                tools.append(lc_tool(func))
            llm = llm.bind_tools(tools)
        
        # 调用
        response = await llm.ainvoke(lc_messages)
        
        return {
            "content": response.content,
            "tool_calls": getattr(response, "tool_calls", [])
        }
    
    async def _execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """执行工具"""
        if tool_name not in self.tools_map:
            raise ValueError(f"Tool '{tool_name}' not found")
        
        tool = self.tools_map[tool_name]
        
        # 执行
        import inspect
        if inspect.iscoroutinefunction(tool):
            result = await tool(**arguments)
        else:
            result = tool(**arguments)
        
        return result

class ReActAgent(BaseAgent):
    """ReAct Agent 实现"""
    
    async def run(self, task: str, context: Dict[str, Any] = None) -> AgentResponse:
        """执行任务（ReAct 模式）"""
        from monitoring.logger import get_logger
        logger = get_logger(__name__)
        
        # 添加任务消息
        self.messages.append(Message(
            role="user",
            content=self._format_task(task, context)
        ))
        
        reasoning_steps = []
        iterations = 0
        
        while iterations < self.config.max_iterations:
            iterations += 1
            
            # 调用 LLM
            response = await self._call_llm(self.messages)
            content = response["content"]
            tool_calls = response.get("tool_calls", [])
            
            # 记录推理步骤
            if self.config.enable_reasoning:
                reasoning_steps.append({
                    "iteration": iterations,
                    "thought": content,
                    "tool_calls": [tc["name"] for tc in tool_calls] if tool_calls else []
                })
            
            # 添加 assistant 消息
            self.messages.append(Message(
                role="assistant",
                content=content,
                tool_calls=tool_calls if tool_calls else None
            ))
            
            # 如果没有工具调用，说明已完成
            if not tool_calls:
                logger.info(
                    "agent_completed",
                    agent=self.config.name,
                    iterations=iterations
                )
                
                return AgentResponse(
                    success=True,
                    content=content,
                    reasoning_steps=reasoning_steps,
                    metadata={
                        "iterations": iterations,
                        "model": self.config.model
                    }
                )
            
            # 执行工具调用
            for tool_call in tool_calls:
                tool_name = tool_call["name"]
                arguments = tool_call["args"]
                
                logger.info(
                    "tool_call",
                    agent=self.config.name,
                    tool=tool_name,
                    arguments=arguments
                )
                
                try:
                    result = await self._execute_tool(tool_name, arguments)
                    
                    # 添加工具结果消息
                    self.messages.append(Message(
                        role="tool",
                        content=json.dumps(result, ensure_ascii=False),
                        tool_call_id=tool_call.get("id"),
                        name=tool_name
                    ))
                    
                    logger.info(
                        "tool_result",
                        agent=self.config.name,
                        tool=tool_name,
                        result=result
                    )
                
                except Exception as e:
                    logger.error(
                        "tool_error",
                        agent=self.config.name,
                        tool=tool_name,
                        error=str(e)
                    )
                    
                    # 添加错误消息
                    self.messages.append(Message(
                        role="tool",
                        content=f"Error: {str(e)}",
                        tool_call_id=tool_call.get("id"),
                        name=tool_name
                    ))
        
        # 达到最大迭代次数
        return AgentResponse(
            success=False,
            content="",
            reasoning_steps=reasoning_steps,
            error=f"达到最大迭代次数 {self.config.max_iterations}"
        )
    
    def _format_task(self, task: str, context: Dict[str, Any] = None) -> str:
        """格式化任务"""
        formatted = f"# 任务\n{task}"
        
        if context:
            formatted += f"\n\n# 上下文\n```json\n{json.dumps(context, ensure_ascii=False, indent=2)}\n```"
        
        return formatted
```

---

## 4. LLM Agent 系统

### 4.1 Agent 注册中心

```python
# agents/registry.py
from typing import Dict, Optional, List
from agents.base import BaseAgent, AgentConfig, AgentRole

class AgentRegistry:
    """Agent 注册中心"""
    
    def __init__(self):
        self._agents: Dict[str, BaseAgent] = {}
        self._configs: Dict[str, AgentConfig] = {}
    
    def register(self, agent: BaseAgent) -> None:
        """注册 Agent"""
        self._agents[agent.config.name] = agent
        self._configs[agent.config.name] = agent.config
        
        print(f"✓ Agent registered: {agent.config.name} ({agent.config.role.value})")
    
    def get(self, name: str) -> Optional[BaseAgent]:
        """获取 Agent"""
        return self._agents.get(name)
    
    def list(self, role: Optional[AgentRole] = None) -> List[AgentConfig]:
        """列出 Agent"""
        configs = list(self._configs.values())
        
        if role:
            configs = [c for c in configs if c.role == role]
        
        return configs

# 全局注册中心
agent_registry = AgentRegistry()
```

### 4.2 工具库

```python
# agents/tools.py
from typing import List, Dict, Any
import numpy as np
from scipy import stats

# ============ 统计分析工具 ============

def calculate_statistics(data: List[float]) -> Dict[str, float]:
    """计算描述性统计量
    
    Args:
        data: 数值列表
    
    Returns:
        统计量字典
    """
    arr = np.array(data)
    
    return {
        "mean": float(np.mean(arr)),
        "median": float(np.median(arr)),
        "std": float(np.std(arr)),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "q25": float(np.percentile(arr, 25)),
        "q75": float(np.percentile(arr, 75)),
        "count": len(data)
    }

def detect_trend(data: List[float], method: str = "linear") -> Dict[str, Any]:
    """检测趋势
    
    Args:
        data: 时间序列数据
        method: 方法 (linear, polynomial)
    
    Returns:
        趋势分析结果
    """
    x = np.arange(len(data))
    y = np.array(data)
    
    if method == "linear":
        # 线性回归
        slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
        
        return {
            "trend": "上升" if slope > 0 else "下降" if slope < 0 else "平稳",
            "slope": float(slope),
            "intercept": float(intercept),
            "r_squared": float(r_value ** 2),
            "p_value": float(p_value),
            "significant": p_value < 0.05
        }
    
    elif method == "polynomial":
        # 多项式拟合
        coeffs = np.polyfit(x, y, 2)
        
        return {
            "coefficients": [float(c) for c in coeffs],
            "curvature": "上凸" if coeffs[0] < 0 else "下凹" if coeffs[0] > 0 else "线性"
        }

def detect_anomalies(
    data: List[float],
    method: str = "zscore",
    threshold: float = 3.0
) -> Dict[str, Any]:
    """检测异常值
    
    Args:
        data: 数据列表
        method: 方法 (zscore, iqr, isolation_forest)
        threshold: 阈值
    
    Returns:
        异常检测结果
    """
    arr = np.array(data)
    
    if method == "zscore":
        mean = np.mean(arr)
        std = np.std(arr)
        z_scores = np.abs((arr - mean) / std)
        anomalies = np.where(z_scores > threshold)[0]
        
        return {
            "method": "zscore",
            "anomaly_indices": anomalies.tolist(),
            "anomaly_values": arr[anomalies].tolist(),
            "z_scores": z_scores[anomalies].tolist(),
            "threshold": threshold,
            "anomaly_count": len(anomalies)
        }
    
    elif method == "iqr":
        q1 = np.percentile(arr, 25)
        q3 = np.percentile(arr, 75)
        iqr = q3 - q1
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr
        
        anomalies = np.where((arr < lower_bound) | (arr > upper_bound))[0]
        
        return {
            "method": "iqr",
            "anomaly_indices": anomalies.tolist(),
            "anomaly_values": arr[anomalies].tolist(),
            "lower_bound": float(lower_bound),
            "upper_bound": float(upper_bound),
            "anomaly_count": len(anomalies)
        }

def calculate_correlation(
    x: List[float],
    y: List[float],
    method: str = "pearson"
) -> Dict[str, float]:
    """计算相关性
    
    Args:
        x: 变量 X
        y: 变量 Y
        method: 方法 (pearson, spearman, kendall)
    
    Returns:
        相关性结果
    """
    x_arr = np.array(x)
    y_arr = np.array(y)
    
    if method == "pearson":
        corr, p_value = stats.pearsonr(x_arr, y_arr)
    elif method == "spearman":
        corr, p_value = stats.spearmanr(x_arr, y_arr)
    elif method == "kendall":
        corr, p_value = stats.kendalltau(x_arr, y_arr)
    else:
        raise ValueError(f"Unknown method: {method}")
    
    return {
        "correlation": float(corr),
        "p_value": float(p_value),
        "significant": p_value < 0.05,
        "strength": "强" if abs(corr) > 0.7 else "中" if abs(corr) > 0.4 else "弱"
    }

def compare_groups(
    group1: List[float],
    group2: List[float],
    test: str = "ttest"
) -> Dict[str, Any]:
    """比较两组数据
    
    Args:
        group1: 组 1
        group2: 组 2
        test: 检验方法 (ttest, mannwhitney)
    
    Returns:
        比较结果
    """
    g1 = np.array(group1)
    g2 = np.array(group2)
    
    if test == "ttest":
        statistic, p_value = stats.ttest_ind(g1, g2)
        test_name = "t检验"
    elif test == "mannwhitney":
        statistic, p_value = stats.mannwhitneyu(g1, g2)
        test_name = "Mann-Whitney U检验"
    else:
        raise ValueError(f"Unknown test: {test}")
    
    return {
        "test": test_name,
        "statistic": float(statistic),
        "p_value": float(p_value),
        "significant": p_value < 0.05,
        "conclusion": "存在显著差异" if p_value < 0.05 else "无显著差异",
        "group1_mean": float(np.mean(g1)),
        "group2_mean": float(np.mean(g2)),
        "difference": float(np.mean(g1) - np.mean(g2))
    }

# ============ 业务规则工具 ============

def evaluate_threshold(
    value: float,
    threshold: float,
    operator: str = "gt"
) -> Dict[str, Any]:
    """评估阈值规则
    
    Args:
        value: 当前值
        threshold: 阈值
        operator: 操作符 (gt, lt, gte, lte, eq)
    
    Returns:
        评估结果
    """
    operators = {
        "gt": lambda v, t: v > t,
        "lt": lambda v, t: v < t,
        "gte": lambda v, t: v >= t,
        "lte": lambda v, t: v <= t,
        "eq": lambda v, t: v == t
    }
    
    if operator not in operators:
        raise ValueError(f"Unknown operator: {operator}")
    
    result = operators[operator](value, threshold)
    
    return {
        "triggered": result,
        "value": value,
        "threshold": threshold,
        "operator": operator,
        "difference": value - threshold,
        "difference_pct": (value - threshold) / threshold * 100 if threshold != 0 else 0
    }

def assess_impact(
    metric: str,
    current_value: float,
    baseline_value: float,
    importance: str = "medium"
) -> Dict[str, Any]:
    """评估影响
    
    Args:
        metric: 指标名称
        current_value: 当前值
        baseline_value: 基准值
        importance: 重要性 (low, medium, high, critical)
    
    Returns:
        影响评估结果
    """
    change = current_value - baseline_value
    change_pct = (change / baseline_value * 100) if baseline_value != 0 else 0
    
    # 重要性权重
    importance_weights = {
        "low": 0.25,
        "medium": 0.5,
        "high": 0.75,
        "critical": 1.0
    }
    
    weight = importance_weights.get(importance, 0.5)
    
    # 计算影响分数 (0-100)
    impact_score = min(abs(change_pct) * weight, 100)
    
    # 影响等级
    if impact_score > 75:
        impact_level = "严重"
    elif impact_score > 50:
        impact_level = "较大"
    elif impact_score > 25:
        impact_level = "中等"
    else:
        impact_level = "较小"
    
    return {
        "metric": metric,
        "current_value": current_value,
        "baseline_value": baseline_value,
        "change": change,
        "change_pct": change_pct,
        "direction": "上升" if change > 0 else "下降" if change < 0 else "持平",
        "importance": importance,
        "impact_score": impact_score,
        "impact_level": impact_level,
        "requires_action": impact_score > 50
    }

def calculate_risk_score(
    factors: Dict[str, float],
    weights: Dict[str, float] = None
) -> Dict[str, Any]:
    """计算风险分数
    
    Args:
        factors: 风险因素及其值 (0-1)
        weights: 权重（可选，默认均等）
    
    Returns:
        风险评分结果
    """
    if weights is None:
        weights = {k: 1.0 / len(factors) for k in factors.keys()}
    
    # 归一化权重
    total_weight = sum(weights.values())
    normalized_weights = {k: v / total_weight for k, v in weights.items()}
    
    # 计算加权分数
    risk_score = sum(factors[k] * normalized_weights.get(k, 0) for k in factors.keys())
    risk_score = max(0, min(100, risk_score * 100))
    
    # 风险等级
    if risk_score > 80:
        risk_level = "极高"
        color = "red"
    elif risk_score > 60:
        risk_level = "高"
        color = "orange"
    elif risk_score > 40:
        risk_level = "中"
        color = "yellow"
    elif risk_score > 20:
        risk_level = "低"
        color = "blue"
    else:
        risk_level = "极低"
        color = "green"
    
    return {
        "risk_score": risk_score,
        "risk_level": risk_level,
        "color": color,
        "factors": factors,
        "weights": normalized_weights,
        "top_factors": sorted(
            [(k, v * normalized_weights.get(k, 0) * 100) for k, v in factors.items()],
            key=lambda x: x[1],
            reverse=True
        )[:3]
    }

# ============ 决策推荐工具 ============

def recommend_actions(
    situation: str,
    available_actions: List[str],
    constraints: Dict[str, Any] = None
) -> List[Dict[str, Any]]:
    """推荐行动方案
    
    Args:
        situation: 当前情况描述
        available_actions: 可用动作列表
        constraints: 约束条件
    
    Returns:
        推荐的动作列表（按优先级排序）
    """
    # 这里可以集成更复杂的决策逻辑
    # 简化实现：基于规则
    
    recommendations = []
    
    for action in available_actions:
        # 基本适用性检查
        applicable = True
        priority = 50  # 默认优先级
        
        # 可以根据 situation 和 constraints 调整
        if constraints:
            budget = constraints.get("budget", float('inf'))
            if "high_cost" in action and budget < 10000:
                applicable = False
        
        if applicable:
            recommendations.append({
                "action": action,
                "priority": priority,
                "reason": f"基于当前情况，该动作适用"
            })
    
    # 按优先级排序
    recommendations.sort(key=lambda x: x["priority"], reverse=True)
    
    return recommendations
```

---

## 5. 业务分析 Agent

### 5.1 Analyst Agent 实现

```python
# agents/analyst_agent.py
from agents.base import ReActAgent, AgentConfig, AgentRole
from agents.tools import (
    calculate_statistics,
    detect_trend,
    detect_anomalies,
    calculate_correlation,
    compare_groups
)

# System Prompt for Business Analyst
ANALYST_SYSTEM_PROMPT = """# 角色
你是一位资深的业务数据分析专家，擅长从数据中发现洞察、识别趋势和异常。

# 能力
你可以使用以下分析工具：
- calculate_statistics: 计算描述性统计量（均值、中位数、标准差等）
- detect_trend: 检测时间序列趋势（上升/下降/平稳）
- detect_anomalies: 检测异常值（Z-score、IQR 方法）
- calculate_correlation: 计算变量间相关性
- compare_groups: 比较两组数据的差异

# 分析流程
1. **探索性分析**：先用 calculate_statistics 了解数据的基本特征
2. **趋势分析**：如果是时间序列数据，使用 detect_trend 分析趋势
3. **异常检测**：使用 detect_anomalies 识别异常点
4. **相关性分析**：如果涉及多个变量，使用 calculate_correlation 分析关系
5. **对比分析**：如果需要比较不同组，使用 compare_groups

# 指导原则
1. 使用多种方法交叉验证结论
2. 给出数据支撑的可解释结论
3. 识别需要进一步调查的问题
4. 量化分析结果（使用具体数字和百分比）
5. 区分相关性和因果性

# 输出格式
请以结构化的方式输出分析结果，包括：
- **关键发现**：最重要的洞察（3-5条）
- **数据证据**：支撑发现的具体数据
- **风险提示**：潜在的问题或风险
- **建议**：后续可以采取的行动

# 示例
输入：分析最近7天各地区的销售数据
输出：
**关键发现**：
1. 整体销售额呈下降趋势，下降幅度为 15%
2. 华东地区异常下降 30%，远超其他地区
3. 销售额与市场活动投入呈强正相关 (r=0.85)

**数据证据**：
- 7天销售额: [1000, 980, 950, 920, 900, 880, 850]
- 线性回归斜率: -21.43 (p<0.001，显著)
- 华东地区Z-score: -2.5 (异常)

**风险提示**：
- 如果趋势持续，预计本月销售额将低于目标 20%
- 华东地区可能存在特殊问题，需要深入调查

**建议**：
1. 立即调查华东地区销售下降的原因
2. 增加市场活动投入
3. 监控其他地区是否出现类似趋势
"""

def create_analyst_agent(
    name: str = "business_analyst",
    model: str = "deepseek-chat"
) -> ReActAgent:
    """创建业务分析 Agent"""
    
    config = AgentConfig(
        name=name,
        role=AgentRole.ANALYST,
        model=model,
        temperature=0.0,
        system_prompt=ANALYST_SYSTEM_PROMPT,
        tools=[
            calculate_statistics,
            detect_trend,
            detect_anomalies,
            calculate_correlation,
            compare_groups
        ],
        enable_reasoning=True,
        max_iterations=10
    )
    
    return ReActAgent(config)

# 注册
from agents.registry import agent_registry
agent_registry.register(create_analyst_agent())
```

### 5.2 配置化 Analyst Skill

```python
# skills/analyst_skill.py
from skills.base import Skill, SkillMetadata, SkillType, SkillResult, SkillContext
from agents.registry import agent_registry
from typing import Dict, Any
import json

class AnalystSkill(Skill):
    """业务分析 Skill（基于 LLM Agent）"""
    
    def _register_metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name="analyze_with_llm",
            display_name="LLM 业务分析",
            description="使用 LLM Agent 进行智能业务分析，支持趋势检测、异常识别、相关性分析等",
            skill_type=SkillType.ANALYSIS,
            version="1.0.0",
            author="System",
            input_schema={
                "data": {
                    "type": "object",
                    "required": True,
                    "description": "待分析的数据"
                },
                "analysis_task": {
                    "type": "string",
                    "required": True,
                    "description": "分析任务描述"
                },
                "agent_config": {
                    "type": "object",
                    "required": False,
                    "description": "Agent 配置（可选）"
                }
            },
            output_schema={
                "findings": {"type": "array", "description": "关键发现"},
                "evidence": {"type": "object", "description": "数据证据"},
                "risks": {"type": "array", "description": "风险提示"},
                "recommendations": {"type": "array", "description": "建议"}
            },
            tags=["llm", "analysis", "intelligent"]
        )
    
    async def execute(
        self,
        inputs: Dict[str, Any],
        context: SkillContext
    ) -> SkillResult:
        """执行分析"""
        from monitoring.logger import get_logger
        from monitoring.metrics import track_skill
        
        logger = get_logger(__name__)
        
        data = inputs["data"]
        analysis_task = inputs["analysis_task"]
        agent_config = inputs.get("agent_config", {})
        
        # 获取 Analyst Agent
        agent_name = agent_config.get("name", "business_analyst")
        agent = agent_registry.get(agent_name)
        
        if not agent:
            return SkillResult(
                success=False,
                data=None,
                error=f"Analyst Agent '{agent_name}' not found"
            )
        
        # 准备上下文
        agent_context = {
            "data": data,
            "user_id": context.user_id,
            "session_id": context.session_id
        }
        
        # 执行分析
        logger.info(
            "analyst_agent_start",
            agent=agent_name,
            task=analysis_task
        )
        
        try:
            response = await agent.run(analysis_task, agent_context)
            
            if not response.success:
                return SkillResult(
                    success=False,
                    data=None,
                    error=response.error
                )
            
            # 解析结果
            result_data = self._parse_analysis_result(response.content)
            
            logger.info(
                "analyst_agent_complete",
                agent=agent_name,
                iterations=len(response.reasoning_steps)
            )
            
            return SkillResult(
                success=True,
                data=result_data,
                metadata={
                    "agent": agent_name,
                    "reasoning_steps": response.reasoning_steps,
                    "tool_calls": response.tool_calls
                }
            )
        
        except Exception as e:
            logger.error(
                "analyst_agent_error",
                agent=agent_name,
                error=str(e)
            )
            
            return SkillResult(
                success=False,
                data=None,
                error=f"分析失败: {str(e)}"
            )
    
    def _parse_analysis_result(self, content: str) -> Dict[str, Any]:
        """解析分析结果"""
        # 尝试从 LLM 输出中提取结构化信息
        # 简化实现：假设 LLM 输出了 JSON
        
        try:
            # 如果 LLM 输出了 JSON
            if content.strip().startswith("{"):
                return json.loads(content)
            
            # 否则，尝试从文本中提取关键信息
            result = {
                "findings": [],
                "evidence": {},
                "risks": [],
                "recommendations": [],
                "raw_analysis": content
            }
            
            # 简单的文本解析
            lines = content.split("\n")
            current_section = None
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                if "关键发现" in line or "Key Findings" in line:
                    current_section = "findings"
                elif "数据证据" in line or "Evidence" in line:
                    current_section = "evidence"
                elif "风险" in line or "Risks" in line:
                    current_section = "risks"
                elif "建议" in line or "Recommendations" in line:
                    current_section = "recommendations"
                elif current_section and line.startswith(("-", "*", "•")):
                    item = line.lstrip("-*• ").strip()
                    if current_section != "evidence":
                        result[current_section].append(item)
            
            return result
        
        except Exception:
            # 解析失败，返回原始内容
            return {
                "raw_analysis": content,
                "findings": [],
                "evidence": {},
                "risks": [],
                "recommendations": []
            }

# 注册
from skills.registry import skill_registry
skill_registry.register(AnalystSkill)
```

---

## 6. 业务决策 Agent

### 6.1 Decision Maker Agent 实现

```python
# agents/decision_agent.py
from agents.base import ReActAgent, AgentConfig, AgentRole
from agents.tools import (
    evaluate_threshold,
    assess_impact,
    calculate_risk_score,
    recommend_actions
)

# System Prompt for Decision Maker
DECISION_MAKER_SYSTEM_PROMPT = """# 角色
你是一位经验丰富的业务决策专家，擅长基于数据分析结果做出明智的业务决策。

# 能力
你可以使用以下决策工具：
- evaluate_threshold: 评估指标是否触发阈值规则
- assess_impact: 评估某个变化的业务影响
- calculate_risk_score: 计算综合风险分数
- recommend_actions: 推荐可行的行动方案

# 决策框架
1. **情况评估**：
   - 使用 evaluate_threshold 检查是否触发告警规则
   - 使用 assess_impact 量化业务影响

2. **风险分析**：
   - 使用 calculate_risk_score 综合评估风险
   - 考虑多个维度：财务风险、运营风险、声誉风险

3. **方案生成**：
   - 使用 recommend_actions 生成可行方案
   - 考虑成本、收益、可行性、时间窗口

4. **决策输出**：
   - 给出明确的决策建议（做/不做）
   - 说明决策理由和支撑数据
   - 列出执行步骤和预期结果

# 决策原则
1. **数据驱动**：决策必须有数据支撑
2. **风险可控**：优先选择风险可控的方案
3. **收益最大化**：在风险可控前提下追求收益最大
4. **可执行性**：方案必须可行且有明确的执行路径
5. **时效性**：考虑决策的时间敏感性

# 输出格式
请以结构化的方式输出决策结果：
- **决策建议**：明确的建议（采取行动/继续观察/无需行动）
- **决策理由**：为什么做出这个决策
- **风险评估**：潜在风险及应对措施
- **执行计划**：具体的执行步骤
- **预期结果**：执行后的预期效果

# 示例
输入：华东地区销售下降 30%，需要决定是否采取行动
输出：
**决策建议**：立即采取行动

**决策理由**：
1. 下降幅度 30% 超过阈值（10%），触发高风险告警
2. 业务影响评估显示：预计本月损失 50万元营收
3. 风险分数 85/100，属于"极高"风险等级
4. 历史数据显示，类似情况如不干预将持续恶化

**风险评估**：
- 不采取行动：营收持续下降，可能影响全年目标
- 采取行动：需要投入营销费用约 10万元，ROI 预期为 5:1

**执行计划**：
1. 立即启动华东地区市场活动（预算 10万）
2. 安排区域经理走访TOP 10客户了解情况
3. 3天内完成竞品分析，识别市场变化
4. 1周内调整销售策略并执行

**预期结果**：
- 2周内销售额止跌回升
- 1个月内恢复至正常水平
- 投资回报率预期 5:1
"""

def create_decision_maker_agent(
    name: str = "business_decision_maker",
    model: str = "deepseek-chat"
) -> ReActAgent:
    """创建业务决策 Agent"""
    
    config = AgentConfig(
        name=name,
        role=AgentRole.DECISION_MAKER,
        model=model,
        temperature=0.0,
        system_prompt=DECISION_MAKER_SYSTEM_PROMPT,
        tools=[
            evaluate_threshold,
            assess_impact,
            calculate_risk_score,
            recommend_actions
        ],
        enable_reasoning=True,
        max_iterations=10
    )
    
    return ReActAgent(config)

# 注册
agent_registry.register(create_decision_maker_agent())
```

### 6.2 配置化 Decision Skill

```python
# skills/decision_skill.py
from skills.base import Skill, SkillMetadata, SkillType, SkillResult, SkillContext
from agents.registry import agent_registry
from typing import Dict, Any
import json

class DecisionSkill(Skill):
    """业务决策 Skill（基于 LLM Agent）"""
    
    def _register_metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name="decide_with_llm",
            display_name="LLM 业务决策",
            description="使用 LLM Agent 进行智能业务决策，基于分析结果给出可执行的行动建议",
            skill_type=SkillType.DECISION,
            version="1.0.0",
            author="System",
            dependencies=["analyze_with_llm"],
            input_schema={
                "analysis_result": {
                    "type": "object",
                    "required": True,
                    "description": "分析结果"
                },
                "decision_task": {
                    "type": "string",
                    "required": True,
                    "description": "决策任务描述"
                },
                "business_rules": {
                    "type": "object",
                    "required": False,
                    "description": "业务规则配置"
                },
                "agent_config": {
                    "type": "object",
                    "required": False,
                    "description": "Agent 配置"
                }
            },
            output_schema={
                "decision": {"type": "string", "description": "决策建议"},
                "reasoning": {"type": "string", "description": "决策理由"},
                "risk_assessment": {"type": "object", "description": "风险评估"},
                "execution_plan": {"type": "array", "description": "执行计划"},
                "expected_outcome": {"type": "string", "description": "预期结果"}
            },
            tags=["llm", "decision", "intelligent"]
        )
    
    async def execute(
        self,
        inputs: Dict[str, Any],
        context: SkillContext
    ) -> SkillResult:
        """执行决策"""
        from monitoring.logger import get_logger
        
        logger = get_logger(__name__)
        
        analysis_result = inputs["analysis_result"]
        decision_task = inputs["decision_task"]
        business_rules = inputs.get("business_rules", {})
        agent_config = inputs.get("agent_config", {})
        
        # 获取 Decision Agent
        agent_name = agent_config.get("name", "business_decision_maker")
        agent = agent_registry.get(agent_name)
        
        if not agent:
            return SkillResult(
                success=False,
                data=None,
                error=f"Decision Agent '{agent_name}' not found"
            )
        
        # 准备上下文
        agent_context = {
            "analysis_result": analysis_result,
            "business_rules": business_rules,
            "user_id": context.user_id,
            "session_id": context.session_id
        }
        
        # 执行决策
        logger.info(
            "decision_agent_start",
            agent=agent_name,
            task=decision_task
        )
        
        try:
            response = await agent.run(decision_task, agent_context)
            
            if not response.success:
                return SkillResult(
                    success=False,
                    data=None,
                    error=response.error
                )
            
            # 解析结果
            result_data = self._parse_decision_result(response.content)
            
            logger.info(
                "decision_agent_complete",
                agent=agent_name,
                decision=result_data.get("decision"),
                iterations=len(response.reasoning_steps)
            )
            
            return SkillResult(
                success=True,
                data=result_data,
                metadata={
                    "agent": agent_name,
                    "reasoning_steps": response.reasoning_steps,
                    "tool_calls": response.tool_calls
                },
                next_actions=result_data.get("execution_plan", [])
            )
        
        except Exception as e:
            logger.error(
                "decision_agent_error",
                agent=agent_name,
                error=str(e)
            )
            
            return SkillResult(
                success=False,
                data=None,
                error=f"决策失败: {str(e)}"
            )
    
    def _parse_decision_result(self, content: str) -> Dict[str, Any]:
        """解析决策结果"""
        try:
            if content.strip().startswith("{"):
                return json.loads(content)
            
            result = {
                "decision": "",
                "reasoning": "",
                "risk_assessment": {},
                "execution_plan": [],
                "expected_outcome": "",
                "raw_decision": content
            }
            
            lines = content.split("\n")
            current_section = None
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                if "决策建议" in line or "Decision" in line:
                    current_section = "decision"
                elif "决策理由" in line or "Reasoning" in line:
                    current_section = "reasoning"
                elif "风险" in line or "Risk" in line:
                    current_section = "risk"
                elif "执行计划" in line or "Execution" in line:
                    current_section = "execution"
                elif "预期结果" in line or "Expected" in line:
                    current_section = "expected"
                elif current_section == "execution" and line.startswith(("-", "*", "•", "1", "2", "3")):
                    item = line.lstrip("-*•0123456789. ").strip()
                    result["execution_plan"].append(item)
            
            return result
        
        except Exception:
            return {
                "raw_decision": content,
                "decision": "",
                "reasoning": "",
                "risk_assessment": {},
                "execution_plan": [],
                "expected_outcome": ""
            }

# 注册
skill_registry.register(DecisionSkill)
```

---

## 7. 与 DeepSeek Harness 集成

### 7.1 完整的 MCP Server

```python
# mcp_server/llm_agent_server.py
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
import json
import asyncio
from typing import Dict, Any

from agents.registry import agent_registry
from skills.registry import skill_registry
from integration.sdk import RDSAgent
from monitoring.logger import get_logger

logger = get_logger(__name__)
mcp = FastMCP("rds-llm-agent")

# 全局组件
rds_agent: RDSAgent = None

def _init():
    global rds_agent
    if rds_agent is None:
        rds_agent = RDSAgent(
            metadata_db_path="var/metadata.db"
        )

@mcp.tool()
async def rds_query(question: str, reference_date: str = None) -> str:
    """查询业务数据（保持原有功能）"""
    _init()
    
    try:
        user_context = {}
        if reference_date:
            user_context["reference_date"] = reference_date
        
        result = rds_agent.query(question, user_context=user_context)
        
        if not result.success:
            raise ToolError(f"查询失败: {result.error}")
        
        response = {
            "success": True,
            "sql": result.sql,
            "data": result.data[:20],
            "row_count": result.row_count
        }
        
        return json.dumps(response, ensure_ascii=False, indent=2)
    
    except Exception as e:
        raise ToolError(f"查询失败: {str(e)}")

@mcp.tool()
async def analyze_with_llm(
    data: str,  # JSON string
    analysis_task: str,
    agent_name: str = "business_analyst"
) -> str:
    """使用 LLM Agent 进行业务分析
    
    基于 LLM 的智能分析，能够理解复杂的业务上下文，
    自动选择合适的分析方法，给出可解释的洞察。
    
    Args:
        data: JSON 格式的数据
        analysis_task: 分析任务描述，如"分析销售趋势并识别异常"
        agent_name: Agent 名称（可选，默认 business_analyst）
    
    Returns:
        JSON 格式的分析结果
    
    Examples:
        data: {"sales": [100, 95, 90, 85, 80, 75, 70]}
        analysis_task: "分析销售趋势，识别异常，并给出业务建议"
    """
    _init()
    
    try:
        # 解析数据
        try:
            data_obj = json.loads(data)
        except json.JSONDecodeError:
            raise ToolError("数据格式错误，必须是 JSON 格式")
        
        # 获取 Agent
        agent = agent_registry.get(agent_name)
        if not agent:
            available = [a.name for a in agent_registry.list()]
            raise ToolError(
                f"Agent '{agent_name}' 不存在。"
                f"可用: {', '.join(available)}"
            )
        
        # 执行分析
        logger.info(
            "llm_analysis_start",
            agent=agent_name,
            task=analysis_task
        )
        
        response = await agent.run(analysis_task, {"data": data_obj})
        
        if not response.success:
            raise ToolError(f"分析失败: {response.error}")
        
        result = {
            "success": True,
            "analysis": response.content,
            "reasoning_steps": response.reasoning_steps,
            "metadata": response.metadata
        }
        
        logger.info(
            "llm_analysis_complete",
            agent=agent_name,
            iterations=len(response.reasoning_steps)
        )
        
        return json.dumps(result, ensure_ascii=False, indent=2)
    
    except Exception as e:
        logger.error("llm_analysis_error", error=str(e))
        raise ToolError(f"分析失败: {str(e)}")

@mcp.tool()
async def decide_with_llm(
    analysis_result: str,  # JSON string
    decision_task: str,
    business_rules: str = "{}",  # JSON string
    agent_name: str = "business_decision_maker"
) -> str:
    """使用 LLM Agent 进行业务决策
    
    基于分析结果和业务规则，使用 LLM 进行智能决策，
    给出可执行的行动建议和风险评估。
    
    Args:
        analysis_result: JSON 格式的分析结果
        decision_task: 决策任务描述
        business_rules: JSON 格式的业务规则（可选）
        agent_name: Agent 名称（可选）
    
    Returns:
        JSON 格式的决策结果
    
    Examples:
        analysis_result: {"findings": ["销售下降30%"], "risks": ["营收风险"]}
        decision_task: "决定是否立即采取行动"
        business_rules: {"revenue_drop_threshold": 0.1, "max_budget": 100000}
    """
    _init()
    
    try:
        # 解析输入
        try:
            analysis_obj = json.loads(analysis_result)
            rules_obj = json.loads(business_rules)
        except json.JSONDecodeError as e:
            raise ToolError(f"JSON 格式错误: {str(e)}")
        
        # 获取 Agent
        agent = agent_registry.get(agent_name)
        if not agent:
            available = [a.name for a in agent_registry.list()]
            raise ToolError(
                f"Agent '{agent_name}' 不存在。"
                f"可用: {', '.join(available)}"
            )
        
        # 执行决策
        logger.info(
            "llm_decision_start",
            agent=agent_name,
            task=decision_task
        )
        
        response = await agent.run(decision_task, {
            "analysis_result": analysis_obj,
            "business_rules": rules_obj
        })
        
        if not response.success:
            raise ToolError(f"决策失败: {response.error}")
        
        result = {
            "success": True,
            "decision": response.content,
            "reasoning_steps": response.reasoning_steps,
            "metadata": response.metadata
        }
        
        logger.info(
            "llm_decision_complete",
            agent=agent_name,
            iterations=len(response.reasoning_steps)
        )
        
        return json.dumps(result, ensure_ascii=False, indent=2)
    
    except Exception as e:
        logger.error("llm_decision_error", error=str(e))
        raise ToolError(f"决策失败: {str(e)}")

@mcp.tool()
async def list_agents(role: str = None) -> str:
    """列出所有可用的 LLM Agent
    
    Args:
        role: Agent 角色过滤（可选）: analyst, decision_maker, executor
    """
    try:
        from agents.base import AgentRole
        
        role_enum = None
        if role:
            try:
                role_enum = AgentRole(role)
            except ValueError:
                valid_roles = [r.value for r in AgentRole]
                raise ToolError(
                    f"无效的角色: {role}。"
                    f"有效角色: {', '.join(valid_roles)}"
                )
        
        agents = agent_registry.list(role=role_enum)
        
        result = {
            "total": len(agents),
            "agents": [
                {
                    "name": a.name,
                    "role": a.role.value,
                    "model": a.model,
                    "tools_count": len(a.tools),
                    "max_iterations": a.max_iterations
                }
                for a in agents
            ]
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
    
    except Exception as e:
        raise ToolError(f"获取 Agent 列表失败: {str(e)}")

if __name__ == "__main__":
    # 初始化 Agents
    from agents.analyst_agent import create_analyst_agent
    from agents.decision_agent import create_decision_maker_agent
    
    create_analyst_agent()
    create_decision_maker_agent()
    
    logger.info("MCP Server starting with LLM Agents")
    mcp.run(transport="stdio")
```

### 7.2 DeepSeek Harness 配置

```yaml
# config/deepseek-harness.llm-agent.yml
- insert:
    - id: rds-llm-agent
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: rds-llm-agent
        transport: stdio
        command: ./venv/bin/python
        args:
          - -m
          - mcp_server.llm_agent_server
        cwd: !!js process.env.RDS_AGENT_ROOT
        env:
          # RDS 配置
          RDS_METADATA_DB_PATH: !!js process.env.RDS_METADATA_DB_PATH
          
          # LLM 配置（内部 Agent 使用）
          OPENAI_API_KEY: !!js process.env.LLM_API_KEY
          OPENAI_API_BASE: !!js process.env.LLM_BASE_URL || 'https://api.deepseek.com'
          
          # 日志
          LOG_LEVEL: !!js process.env.LOG_LEVEL || 'INFO'
        
        toolCallTimeoutMs: 300000
        failOnStartupError: true
```

---

## 8. 配置化 Skill 设计

### 8.1 YAML 配置文件

```yaml
# config/agent_skills.yaml
# LLM Agent Skills 配置

agents:
  # 业务分析 Agent
  - name: business_analyst
    role: analyst
    model: deepseek-chat
    temperature: 0.0
    system_prompt_template: analyst_expert
    tools:
      - calculate_statistics
      - detect_trend
      - detect_anomalies
      - calculate_correlation
      - compare_groups
    enable_reasoning: true
    max_iterations: 10
  
  # 业务决策 Agent
  - name: business_decision_maker
    role: decision_maker
    model: deepseek-chat
    temperature: 0.0
    system_prompt_template: decision_expert
    tools:
      - evaluate_threshold
      - assess_impact
      - calculate_risk_score
      - recommend_actions
    enable_reasoning: true
    max_iterations: 10
  
  # 自定义：销售分析专家
  - name: sales_analyst
    role: analyst
    model: gpt-4
    temperature: 0.0
    system_prompt: |
      你是销售数据分析专家，专注于：
      - 销售趋势分析
      - 客户行为分析
      - 销售预测
    tools:
      - calculate_statistics
      - detect_trend
      - calculate_correlation
    knowledge_base: sales_kb
    examples:
      - input: "分析本月销售趋势"
        output: "销售额呈上升趋势，增长率15%..."

skills:
  # 分析 Skill
  - name: analyze_sales
    type: analysis
    agent: sales_analyst
    description: "使用专业销售分析 Agent 分析销售数据"
  
  # 决策 Skill
  - name: decide_sales_action
    type: decision
    agent: business_decision_maker
    description: "基于销售分析结果做出业务决策"
    dependencies:
      - analyze_sales

workflows:
  # 销售异常处理工作流
  - name: sales_anomaly_handling
    description: "销售异常检测、分析、决策、执行完整流程"
    nodes:
      - id: query_data
        type: skill
        skill_name: rds_query
        inputs:
          question: "{{workflow.inputs.question}}"
      
      - id: analyze
        type: skill
        skill_name: analyze_sales
        inputs:
          data: "{{nodes.query_data.output.data}}"
          analysis_task: "分析销售数据，识别异常和趋势"
      
      - id: decide
        type: skill
        skill_name: decide_sales_action
        inputs:
          analysis_result: "{{nodes.analyze.output}}"
          decision_task: "基于分析结果决定是否采取行动"
      
      - id: execute
        type: skill
        skill_name: execute_business_action
        inputs:
          decision: "{{nodes.decide.output}}"
```

### 8.2 配置加载器

```python
# config/agent_loader.py
import yaml
from pathlib import Path
from typing import Dict, Any, List
from agents.base import AgentConfig, AgentRole, ReActAgent
from agents.registry import agent_registry

class AgentConfigLoader:
    """Agent 配置加载器"""
    
    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        with open(self.config_path) as f:
            return yaml.safe_load(f)
    
    def load_agents(self):
        """加载并注册所有 Agents"""
        for agent_config in self.config.get("agents", []):
            agent = self._create_agent(agent_config)
            agent_registry.register(agent)
    
    def _create_agent(self, config: Dict[str, Any]) -> ReActAgent:
        """创建 Agent"""
        # 解析角色
        role = AgentRole(config["role"])
        
        # 加载系统提示词
        system_prompt = self._load_system_prompt(config)
        
        # 加载工具
        tools = self._load_tools(config.get("tools", []))
        
        # 创建配置
        agent_config = AgentConfig(
            name=config["name"],
            role=role,
            model=config.get("model", "deepseek-chat"),
            temperature=config.get("temperature", 0.0),
            system_prompt=system_prompt,
            tools=tools,
            enable_reasoning=config.get("enable_reasoning", True),
            max_iterations=config.get("max_iterations", 10)
        )
        
        return ReActAgent(agent_config)
    
    def _load_system_prompt(self, config: Dict[str, Any]) -> str:
        """加载系统提示词"""
        if "system_prompt" in config:
            return config["system_prompt"]
        
        if "system_prompt_template" in config:
            template_name = config["system_prompt_template"]
            # 从模板库加载
            return self._load_prompt_template(template_name)
        
        return ""
    
    def _load_prompt_template(self, template_name: str) -> str:
        """从模板库加载提示词"""
        templates = {
            "analyst_expert": ANALYST_SYSTEM_PROMPT,
            "decision_expert": DECISION_MAKER_SYSTEM_PROMPT
        }
        
        return templates.get(template_name, "")
    
    def _load_tools(self, tool_names: List[str]) -> List:
        """加载工具"""
        from agents import tools as tools_module
        
        loaded_tools = []
        for name in tool_names:
            tool = getattr(tools_module, name, None)
            if tool:
                loaded_tools.append(tool)
        
        return loaded_tools

# 使用
def init_agents_from_config(config_path: str = "config/agent_skills.yaml"):
    """从配置文件初始化 Agents"""
    loader = AgentConfigLoader(Path(config_path))
    loader.load_agents()
    
    print(f"✓ Loaded {len(agent_registry.list())} agents from config")
```

---

## 9. 完整示例

### 9.1 场景：销售异常智能处理

```
用户（在 Harness 中）: 检查最近7天销售是否异常，如有问题自动处理

Harness Primary Agent:
  → 理解意图：需要查询数据 + 分析 + 决策 + 执行
  
  Step 1: 查询数据
    Tool Call: rds_query(
      question="最近7天各地区销售额"
    )
    Result: {
      "data": [
        {"date": "2024-09-24", "region": "华东", "revenue": 1000},
        {"date": "2024-09-25", "region": "华东", "revenue": 950},
        ...
        {"date": "2024-09-30", "region": "华东", "revenue": 700}
      ]
    }
  
  Step 2: LLM 分析
    Tool Call: analyze_with_llm(
      data=<上述数据>,
      analysis_task="分析销售趋势，识别异常，评估业务影响"
    )
    
    [MCP Server 内部]
    Business Analyst Agent:
      Thought: 需要先了解数据的基本特征
      Action: calculate_statistics([1000, 950, 920, 880, 850, 780, 700])
      Observation: {"mean": 868.57, "std": 107.14, ...}
      
      Thought: 检测趋势
      Action: detect_trend([1000, 950, 920, 880, 850, 780, 700])
      Observation: {"trend": "下降", "slope": -50, "r_squared": 0.98, ...}
      
      Thought: 检测异常
      Action: detect_anomalies([1000, 950, 920, 880, 850, 780, 700])
      Observation: {"anomaly_indices": [6], "anomaly_values": [700], ...}
      
      Final Output: {
        "findings": [
          "销售额呈显著下降趋势，下降率 30%",
          "最后一天(700)为异常值，偏离均值 2.5 个标准差",
          "趋势拟合度高(R²=0.98)，预计将持续下降"
        ],
        "evidence": {
          "slope": -50,
          "total_drop": 300,
          "drop_rate": 0.30
        },
        "risks": [
          "如不干预，预计本月营收损失 50 万",
          "可能影响 Q4 目标达成"
        ],
        "recommendations": [
          "立即调查华东地区原因",
          "启动应急营销方案"
        ]
      }
    
    Result: <Analyst Agent 的输出>
  
  Step 3: LLM 决策
    Tool Call: decide_with_llm(
      analysis_result=<上述分析结果>,
      decision_task="决定是否立即采取行动，给出具体执行计划",
      business_rules={"revenue_drop_threshold": 0.1, "max_marketing_budget": 100000}
    )
    
    [MCP Server 内部]
    Business Decision Maker Agent:
      Thought: 先评估是否触发阈值
      Action: evaluate_threshold(value=0.30, threshold=0.1, operator="gt")
      Observation: {"triggered": true, "difference_pct": 200}
      
      Thought: 评估业务影响
      Action: assess_impact(
        metric="revenue",
        current_value=700,
        baseline_value=1000,
        importance="critical"
      )
      Observation: {"impact_score": 90, "impact_level": "严重", ...}
      
      Thought: 计算风险分数
      Action: calculate_risk_score(
        factors={"revenue_risk": 0.9, "trend_risk": 0.85, "anomaly_risk": 0.8}
      )
      Observation: {"risk_score": 85, "risk_level": "极高"}
      
      Thought: 推荐行动方案
      Action: recommend_actions(
        situation="销售下降30%，风险极高",
        available_actions=["紧急营销活动", "客户走访", "竞品分析", "价格调整"]
      )
      Observation: [
        {"action": "紧急营销活动", "priority": 90},
        {"action": "客户走访", "priority": 85},
        ...
      ]
      
      Final Output: {
        "decision": "立即采取行动",
        "reasoning": "下降幅度30%超过阈值3倍，风险极高...",
        "risk_assessment": {
          "risk_score": 85,
          "risk_level": "极高",
          "financial_impact": "预计损失50万"
        },
        "execution_plan": [
          "立即启动华东地区营销活动（预算10万）",
          "安排区域经理走访TOP10客户",
          "3天内完成竞品分析",
          "1周内调整销售策略"
        ],
        "expected_outcome": "2周内销售止跌，1月内恢复正常"
      }
    
    Result: <Decision Agent 的输出>
  
  Step 4: 执行行动（如配置了自动执行）
    Tool Call: send_notification(...)
    Tool Call: api_call(api="crm.create_task", ...)
    
  Final Response to User:
    已完成销售异常分析和决策：
    
    **分析结果**：
    - 销售额下降 30%，呈显著下降趋势
    - 最后一天出现异常值，偏离均值 2.5σ
    - 预计不干预将损失 50 万营收
    
    **决策建议**：立即采取行动
    - 风险等级：极高 (85/100)
    - 预计损失：50 万元
    
    **执行计划**：
    1. 已启动华东地区营销活动（预算10万）
    2. 已创建客户走访任务（TOP10客户）
    3. 已安排竞品分析任务（3天内完成）
    4. 已通知销售团队调整策略
    
    **预期结果**：2周内止跌，1月内恢复
```

---

## 10. 生产级特性

### 10.1 Agent 性能监控

```python
# monitoring/agent_metrics.py
from prometheus_client import Counter, Histogram, Gauge

# Agent 执行指标
agent_executions_total = Counter(
    'agent_executions_total',
    'Total agent executions',
    ['agent_name', 'status']
)

agent_duration_seconds = Histogram(
    'agent_duration_seconds',
    'Agent execution duration',
    ['agent_name']
)

agent_iterations = Histogram(
    'agent_iterations',
    'Number of iterations per agent execution',
    ['agent_name']
)

agent_tool_calls_total = Counter(
    'agent_tool_calls_total',
    'Total agent tool calls',
    ['agent_name', 'tool_name', 'status']
)

llm_tokens_total = Counter(
    'llm_tokens_total',
    'Total LLM tokens consumed',
    ['agent_name', 'token_type']  # prompt, completion
)

llm_cost_dollars = Counter(
    'llm_cost_dollars',
    'Estimated LLM cost in dollars',
    ['agent_name', 'model']
)
```

### 10.2 Agent 缓存

```python
# agents/cache.py
from typing import Optional, Dict, Any
import hashlib
import json
import redis

class AgentCache:
    """Agent 响应缓存"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis = redis.from_url(redis_url)
        self.ttl = 3600  # 1小时
    
    def _generate_key(
        self,
        agent_name: str,
        task: str,
        context: Dict[str, Any]
    ) -> str:
        """生成缓存键"""
        content = f"{agent_name}:{task}:{json.dumps(context, sort_keys=True)}"
        return f"agent_cache:{hashlib.md5(content.encode()).hexdigest()}"
    
    def get(
        self,
        agent_name: str,
        task: str,
        context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """获取缓存"""
        key = self._generate_key(agent_name, task, context)
        cached = self.redis.get(key)
        
        if cached:
            return json.loads(cached)
        
        return None
    
    def set(
        self,
        agent_name: str,
        task: str,
        context: Dict[str, Any],
        response: Dict[str, Any]
    ):
        """设置缓存"""
        key = self._generate_key(agent_name, task, context)
        self.redis.setex(
            key,
            self.ttl,
            json.dumps(response, ensure_ascii=False)
        )
```

### 10.3 成本控制

```python
# agents/cost_control.py
from typing import Dict
import time

class CostController:
    """成本控制器"""
    
    def __init__(self):
        self.cost_limits = {
            "per_request": 1.0,   # 单次请求最大成本 $1
            "per_hour": 100.0,    # 每小时最大成本 $100
            "per_day": 1000.0     # 每天最大成本 $1000
        }
        
        self.costs: Dict[str, float] = {}
        self.timestamps: Dict[str, float] = {}
    
    def check_limit(self, estimated_cost: float) -> bool:
        """检查是否超限"""
        now = time.time()
        
        # 检查单次请求
        if estimated_cost > self.cost_limits["per_request"]:
            return False
        
        # 检查每小时
        hour_key = f"hour_{int(now // 3600)}"
        hour_cost = self.costs.get(hour_key, 0)
        if hour_cost + estimated_cost > self.cost_limits["per_hour"]:
            return False
        
        # 检查每天
        day_key = f"day_{int(now // 86400)}"
        day_cost = self.costs.get(day_key, 0)
        if day_cost + estimated_cost > self.cost_limits["per_day"]:
            return False
        
        return True
    
    def record_cost(self, actual_cost: float):
        """记录实际成本"""
        now = time.time()
        
        hour_key = f"hour_{int(now // 3600)}"
        day_key = f"day_{int(now // 86400)}"
        
        self.costs[hour_key] = self.costs.get(hour_key, 0) + actual_cost
        self.costs[day_key] = self.costs.get(day_key, 0) + actual_cost
```

---

## 总结

### 核心创新点

1. **三层 Agent 架构**：
   - Layer 1: Harness Primary Agent（理解意图、调度）
   - Layer 2: Specialized Agents（分析、决策）
   - Layer 3: Tool Execution（执行）

2. **LLM-Powered 分析与决策**：
   - 不再依赖硬编码规则
   - LLM 自主推理和工具调用
   - 可解释的决策过程

3. **完全配置化**：
   - YAML 配置 Agent 和 Skill
   - 无需修改代码即可扩展
   - 支持自定义提示词和工具

4. **生产级特性**：
   - 监控、缓存、成本控制
   - 错误处理和重试
   - 分布式追踪

### 与传统方案对比

| 特性 | 传统硬编码 | 本方案（LLM Agent） |
|------|-----------|------------------|
| **灵活性** | 每个场景需要编码 | 配置即可扩展 |
| **智能性** | 固定规则 | LLM 推理 |
| **可解释性** | 规则明确但死板 | LLM 推理步骤可追踪 |
| **维护成本** | 高（需改代码） | 低（改配置） |
| **适应性** | 差 | 好（可处理新场景） |

---

**文档版本：** v1.0  
**最后更新：** 2026-09-07  
**参考论文：**
- ReAct: Reasoning and Acting in Language Models
- Tool Learning with Foundation Models
- Multi-Agent Collaboration Patterns
