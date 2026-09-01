"""
SQLGenerator: SQL 生成器

负责生成和修复 SQL
"""

from typing import Dict, List, Optional, Any
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.language_models import BaseChatModel


class SQLGenerator:
    """
    SQL 生成器

    负责：
    1. 根据查询计划生成 SQL
    2. 基于错误反馈修复 SQL
    3. 使用 Schema 上下文和示例
    4. 支持重试机制
    """

    def __init__(
        self,
        llm: BaseChatModel,
        catalog,
        semantic_layer,
        examples: Optional[List[Dict]] = None,
    ):
        """
        初始化 SQL 生成器

        Args:
            llm: 语言模型
            catalog: DatabaseCatalog 实例
            semantic_layer: SemanticLayer 实例
            examples: 示例 SQL 列表
        """
        self.llm = llm
        self.catalog = catalog
        self.semantic_layer = semantic_layer
        self.examples = examples or []

    def generate(self, plan_step: Any, schema_context: Dict) -> str:
        """
        生成 SQL

        Args:
            plan_step: QueryStep 对象
            schema_context: Schema 上下文信息

        Returns:
            SQL 字符串
        """
        # 构建提示词
        prompt = self._build_generation_prompt(plan_step, schema_context)

        # 调用 LLM 生成 SQL
        response = self.llm.invoke(prompt)

        # 提取 SQL（去除 markdown 代码块标记）
        sql = self._extract_sql(response.content)

        return sql

    def repair(self, sql: str, error_context: Dict) -> str:
        """
        修复 SQL

        Args:
            sql: 原始 SQL
            error_context: 错误上下文
                {
                    "error_type": str,
                    "error_message": str,
                    "database_message": str,
                    "available_columns": List[str],
                    "schema_context": Dict
                }

        Returns:
            修复后的 SQL
        """
        # 构建修复提示词
        prompt = self._build_repair_prompt(sql, error_context)

        # 调用 LLM 修复 SQL
        response = self.llm.invoke(prompt)

        # 提取 SQL
        repaired_sql = self._extract_sql(response.content)

        return repaired_sql

    def _build_generation_prompt(self, plan_step: Any, schema_context: Dict) -> str:
        """构建 SQL 生成提示词"""
        # 获取相关的示例 SQL
        relevant_examples = self._get_relevant_examples(plan_step.purpose)

        # 构建 Schema 描述
        schema_desc = self._format_schema_context(schema_context)

        # 构建指标和维度说明
        metrics_desc = self._format_metrics(plan_step.metrics)
        dimensions_desc = self._format_dimensions(plan_step.dimensions)

        prompt = f"""你是一个专业的 SQL 生成专家。请根据以下信息生成 SQL 查询。

## 任务目标
{plan_step.purpose}

## 数据库 Schema
{schema_desc}

## 业务指标
{metrics_desc}

## 维度
{dimensions_desc}

## 过滤条件
{plan_step.filters}

## 参考示例
{relevant_examples}

## 要求
1. 只生成 SELECT 查询
2. 必须包含 LIMIT 子句（建议 LIMIT 1000）
3. 使用表的完整名称（table.column）
4. 确保 JOIN 条件正确
5. 聚合查询必须有 GROUP BY
6. 返回纯 SQL，不要包含解释

请生成 SQL：
"""
        return prompt

    def _build_repair_prompt(self, sql: str, error_context: Dict) -> str:
        """构建 SQL 修复提示词"""
        error_type = error_context.get("error_type", "unknown")
        error_message = error_context.get("error_message", "")
        database_message = error_context.get("database_message", "")
        available_columns = error_context.get("available_columns", [])
        schema_context = error_context.get("schema_context", {})

        schema_desc = self._format_schema_context(schema_context)

        prompt = f"""请修复以下 SQL 查询中的错误。

## 原始 SQL
```sql
{sql}
```

## 错误信息
错误类型: {error_type}
错误描述: {error_message}
数据库消息: {database_message}

## 可用的列
{', '.join(available_columns) if available_columns else '请参考 Schema'}

## 数据库 Schema
{schema_desc}

## 要求
1. 只修复错误，保持原有查询逻辑
2. 确保列名和表名正确
3. 确保 JOIN 条件正确
4. 返回修复后的 SQL，不要包含解释

请生成修复后的 SQL：
"""
        return prompt

    def _format_schema_context(self, schema_context: Dict) -> str:
        """格式化 Schema 上下文"""
        lines = []

        # 表定义
        tables = schema_context.get("tables", {})
        for table_name, table_desc in tables.items():
            lines.append(table_desc)
            lines.append("")

        # Join 关系
        joins = schema_context.get("joins", [])
        if joins:
            lines.append("## Join 关系")
            for join in joins:
                lines.append(f"- {join}")
            lines.append("")

        return "\n".join(lines)

    def _format_metrics(self, metrics: List[str]) -> str:
        """格式化指标说明"""
        if not metrics:
            return "无特定指标"

        lines = []
        for metric_name in metrics:
            metric = self.semantic_layer.resolve_metric(metric_name)
            if metric:
                lines.append(f"- {metric.display_name}: {metric.expression}")
                lines.append(f"  说明: {metric.description}")
                if metric.filters:
                    lines.append(f"  过滤条件: {', '.join(metric.filters)}")

        return "\n".join(lines) if lines else "无特定指标"

    def _format_dimensions(self, dimensions: List[str]) -> str:
        """格式化维度说明"""
        if not dimensions:
            return "无特定维度"

        lines = []
        for dim_name in dimensions:
            dim = self.semantic_layer.resolve_dimension(dim_name)
            if dim:
                lines.append(f"- {dim.display_name}: {dim.table}.{dim.column}")

        return "\n".join(lines) if lines else "无特定维度"

    def _get_relevant_examples(self, purpose: str, max_examples: int = 3) -> str:
        """获取相关的示例 SQL"""
        if not self.examples:
            return "无示例"

        # 简单实现：返回前几个示例
        # 生产环境应该使用语义搜索找到最相关的示例
        relevant = self.examples[:max_examples]

        lines = []
        for example in relevant:
            question = example.get("question", "")
            sql = example.get("sql", "")
            lines.append(f"问题: {question}")
            lines.append(f"```sql\n{sql}\n```")
            lines.append("")

        return "\n".join(lines) if lines else "无示例"

    def _extract_sql(self, text: str) -> str:
        """从 LLM 响应中提取 SQL"""
        import re

        # 尝试提取 markdown 代码块中的 SQL
        match = re.search(r'```sql\s*\n(.*?)\n```', text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()

        # 尝试提取普通代码块
        match = re.search(r'```\s*\n(.*?)\n```', text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # 如果没有代码块，尝试提取 SELECT 语句
        match = re.search(r'(SELECT\s+.*?;?)\s*$', text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip().rstrip(';')

        # 返回整个文本（去除首尾空白）
        return text.strip()

    def generate_with_retry(
        self,
        plan_step: Any,
        schema_context: Dict,
        max_retries: int = 3,
        validator=None,
    ) -> tuple[str, List[str]]:
        """
        生成 SQL 并在验证失败时重试

        Args:
            plan_step: QueryStep 对象
            schema_context: Schema 上下文
            max_retries: 最大重试次数
            validator: SQL 验证器（SQLGuard 实例）

        Returns:
            (sql, errors) - SQL 和错误列表
        """
        errors = []

        for attempt in range(max_retries):
            try:
                # 生成 SQL
                sql = self.generate(plan_step, schema_context)

                # 如果提供了验证器，进行验证
                if validator:
                    is_valid, error_msg = validator.validate_sql(sql)
                    if not is_valid:
                        errors.append(f"Attempt {attempt + 1}: {error_msg}")

                        # 如果不是最后一次尝试，尝试修复
                        if attempt < max_retries - 1:
                            error_context = {
                                "error_type": "validation_failed",
                                "error_message": error_msg,
                                "database_message": error_msg,
                                "schema_context": schema_context,
                            }
                            sql = self.repair(sql, error_context)
                        continue

                # 验证通过，返回
                return sql, errors

            except Exception as e:
                errors.append(f"Attempt {attempt + 1}: {str(e)}")

        # 所有尝试都失败
        return "", errors
