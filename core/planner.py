"""
QueryPlanner: 查询计划生成器

负责生成查询计划
"""

from typing import Dict, List, Optional, Any
from enum import Enum


class QueryType(Enum):
    """查询类型"""
    SIMPLE_QUERY = "simple_query"  # 简单统计查询
    COMPARISON = "comparison"  # 对比分析
    TREND = "trend"  # 趋势分析
    DIAGNOSTIC = "diagnostic"  # 诊断分析（需要多步骤）
    AGGREGATION = "aggregation"  # 聚合分析


class QueryStep:
    """查询步骤"""

    def __init__(
        self,
        step_id: str,
        purpose: str,
        query_type: str = "data",
        depends_on: Optional[List[str]] = None,
        metrics: Optional[List[str]] = None,
        dimensions: Optional[List[str]] = None,
        filters: Optional[Dict] = None,
    ):
        self.step_id = step_id
        self.purpose = purpose
        self.query_type = query_type  # data, comparison, calculation
        self.depends_on = depends_on or []
        self.metrics = metrics or []
        self.dimensions = dimensions or []
        self.filters = filters or {}
        self.sql = None
        self.result = None


class QueryPlan:
    """查询计划"""

    def __init__(
        self,
        question: str,
        question_type: QueryType,
        steps: List[QueryStep],
        complexity: str = "simple",
    ):
        self.question = question
        self.question_type = question_type
        self.steps = steps
        self.complexity = complexity  # simple, moderate, complex

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "question": self.question,
            "question_type": self.question_type.value,
            "complexity": self.complexity,
            "steps": [
                {
                    "step_id": step.step_id,
                    "purpose": step.purpose,
                    "query_type": step.query_type,
                    "depends_on": step.depends_on,
                    "metrics": step.metrics,
                    "dimensions": step.dimensions,
                }
                for step in self.steps
            ],
        }


class QueryPlanner:
    """
    查询计划生成器

    负责：
    1. 分析问题类型（简单统计 vs 复杂分析）
    2. 生成结构化查询意图
    3. 对于复杂问题，拆分为多个子查询
    4. 确定查询依赖关系
    """

    def __init__(self, semantic_layer, catalog):
        """
        初始化查询计划生成器

        Args:
            semantic_layer: SemanticLayer 实例
            catalog: DatabaseCatalog 实例
        """
        self.semantic_layer = semantic_layer
        self.catalog = catalog

    def create_plan(self, intent: Dict, context: Optional[Dict] = None) -> QueryPlan:
        """
        创建查询计划

        Args:
            intent: 结构化意图
                {
                    "question": str,
                    "question_type": str,
                    "metrics": List[str],
                    "dimensions": List[str],
                    "filters": Dict,
                    "time_range": str,
                }
            context: 上下文信息（对话历史等）

        Returns:
            QueryPlan 对象
        """
        question = intent.get("question", "")
        question_type_str = intent.get("question_type", "simple_query")

        # 转换为枚举
        try:
            question_type = QueryType(question_type_str)
        except ValueError:
            question_type = QueryType.SIMPLE_QUERY

        # 根据问题类型生成计划
        if question_type == QueryType.SIMPLE_QUERY:
            plan = self._create_simple_plan(intent)
        elif question_type == QueryType.COMPARISON:
            plan = self._create_comparison_plan(intent)
        elif question_type == QueryType.TREND:
            plan = self._create_trend_plan(intent)
        elif question_type == QueryType.DIAGNOSTIC:
            plan = self._create_diagnostic_plan(intent)
        else:
            plan = self._create_simple_plan(intent)

        return plan

    def _create_simple_plan(self, intent: Dict) -> QueryPlan:
        """创建简单查询计划（单步查询）"""
        step = QueryStep(
            step_id="query",
            purpose="执行查询并返回结果",
            query_type="data",
            metrics=intent.get("metrics", []),
            dimensions=intent.get("dimensions", []),
            filters=intent.get("filters", {}),
        )

        return QueryPlan(
            question=intent.get("question", ""),
            question_type=QueryType.SIMPLE_QUERY,
            steps=[step],
            complexity="simple",
        )

    def _create_comparison_plan(self, intent: Dict) -> QueryPlan:
        """创建对比分析计划（两步查询）"""
        steps = []

        # 步骤1：当前期间数据
        steps.append(
            QueryStep(
                step_id="current_period",
                purpose="获取当前期间数据",
                query_type="data",
                metrics=intent.get("metrics", []),
                dimensions=intent.get("dimensions", []),
                filters=intent.get("filters", {}),
            )
        )

        # 步骤2：对比期间数据
        steps.append(
            QueryStep(
                step_id="comparison_period",
                purpose="获取对比期间数据",
                query_type="data",
                metrics=intent.get("metrics", []),
                dimensions=intent.get("dimensions", []),
                filters=self._adjust_time_for_comparison(intent.get("filters", {})),
            )
        )

        # 步骤3：计算变化
        steps.append(
            QueryStep(
                step_id="calculate_change",
                purpose="计算变化和增长率",
                query_type="calculation",
                depends_on=["current_period", "comparison_period"],
            )
        )

        return QueryPlan(
            question=intent.get("question", ""),
            question_type=QueryType.COMPARISON,
            steps=steps,
            complexity="moderate",
        )

    def _create_trend_plan(self, intent: Dict) -> QueryPlan:
        """创建趋势分析计划"""
        steps = []

        # 步骤1：按时间维度聚合
        steps.append(
            QueryStep(
                step_id="trend_data",
                purpose="获取时间序列数据",
                query_type="data",
                metrics=intent.get("metrics", []),
                dimensions=["time_period"] + intent.get("dimensions", []),
                filters=intent.get("filters", {}),
            )
        )

        # 步骤2：计算趋势指标（增长率、移动平均等）
        steps.append(
            QueryStep(
                step_id="trend_metrics",
                purpose="计算趋势指标",
                query_type="calculation",
                depends_on=["trend_data"],
            )
        )

        return QueryPlan(
            question=intent.get("question", ""),
            question_type=QueryType.TREND,
            steps=steps,
            complexity="moderate",
        )

    def _create_diagnostic_plan(self, intent: Dict) -> QueryPlan:
        """创建诊断分析计划（多步骤深入分析）"""
        steps = []

        # 步骤1：基线数据
        steps.append(
            QueryStep(
                step_id="baseline",
                purpose="获取基线数据和整体趋势",
                query_type="data",
                metrics=intent.get("metrics", []),
                dimensions=["time_period"],
                filters=intent.get("filters", {}),
            )
        )

        # 步骤2：维度分解
        dimensions = intent.get("dimensions", [])
        if dimensions:
            for i, dim in enumerate(dimensions):
                steps.append(
                    QueryStep(
                        step_id=f"breakdown_{dim}",
                        purpose=f"按 {dim} 维度分解",
                        query_type="data",
                        metrics=intent.get("metrics", []),
                        dimensions=[dim, "time_period"],
                        filters=intent.get("filters", {}),
                    )
                )

        # 步骤3：识别异常贡献者
        steps.append(
            QueryStep(
                step_id="identify_contributors",
                purpose="识别主要贡献者和异常值",
                query_type="calculation",
                depends_on=[f"breakdown_{dim}" for dim in dimensions] if dimensions else ["baseline"],
            )
        )

        return QueryPlan(
            question=intent.get("question", ""),
            question_type=QueryType.DIAGNOSTIC,
            steps=steps,
            complexity="complex",
        )

    def _adjust_time_for_comparison(self, filters: Dict) -> Dict:
        """
        调整时间过滤器用于对比期间

        例如：当前月 -> 上月
        """
        # 简化实现：返回相同的过滤器
        # 实际生产环境需要根据时间范围自动调整
        adjusted_filters = filters.copy()

        # TODO: 实现时间范围的自动调整
        # 例如：如果当前是 "最近30天"，对比期间应该是 "前30天"

        return adjusted_filters

    def estimate_plan_complexity(self, plan: QueryPlan) -> Dict[str, Any]:
        """
        评估计划复杂度

        Returns:
            {
                "step_count": int,
                "complexity_score": int,
                "estimated_time": float,
                "requires_approval": bool
            }
        """
        step_count = len(plan.steps)
        complexity_score = step_count * 10

        # 评估是否需要审批
        requires_approval = step_count > 5 or plan.complexity == "complex"

        # 估算执行时间（秒）
        estimated_time = step_count * 2.0  # 假设每步2秒

        return {
            "step_count": step_count,
            "complexity_score": complexity_score,
            "estimated_time": estimated_time,
            "requires_approval": requires_approval,
        }
