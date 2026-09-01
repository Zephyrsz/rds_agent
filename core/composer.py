"""
AnswerComposer: 答案组织器

负责将查询结果组织成用户友好的答案
"""

from typing import Dict, List, Optional, Any
from datetime import datetime


class AnswerComposer:
    """
    答案组织器

    负责：
    1. 生成核心结论
    2. 包含关键指标
    3. 说明筛选条件和口径
    4. 附带风险提示
    5. 提供审计信息
    """

    def __init__(self, llm=None):
        """
        初始化答案组织器

        Args:
            llm: 语言模型（可选，用于生成自然语言总结）
        """
        self.llm = llm

    def compose(
        self,
        question: str,
        plan: Any,
        results: List[tuple[Any, Any]],  # List of (plan_step, query_result)
        validation_results: Optional[List[Any]] = None,
    ) -> Dict[str, Any]:
        """
        组织答案

        Args:
            question: 用户问题
            plan: QueryPlan 对象
            results: 查询结果列表 [(plan_step, query_result), ...]
            validation_results: 验证结果列表

        Returns:
            结构化答案字典
        """
        answer = {
            "question": question,
            "summary": "",
            "key_metrics": [],
            "details": [],
            "filters": {},
            "data_scope": "",
            "warnings": [],
            "audit_info": {},
            "timestamp": datetime.now().isoformat(),
        }

        # 1. 提取关键指标
        answer["key_metrics"] = self._extract_key_metrics(results)

        # 2. 生成详细数据
        answer["details"] = self._format_details(results)

        # 3. 提取过滤条件
        answer["filters"] = self._extract_filters(plan)

        # 4. 生成数据范围说明
        answer["data_scope"] = self._generate_data_scope(plan, results)

        # 5. 收集警告信息
        if validation_results:
            answer["warnings"] = self._collect_warnings(validation_results)

        # 6. 生成审计信息
        answer["audit_info"] = self._generate_audit_info(results)

        # 7. 生成总结（如果有 LLM）
        if self.llm:
            answer["summary"] = self._generate_summary(question, answer)
        else:
            answer["summary"] = self._generate_simple_summary(question, answer)

        return answer

    def _extract_key_metrics(self, results: List[tuple[Any, Any]]) -> List[Dict]:
        """提取关键指标"""
        key_metrics = []

        for plan_step, query_result in results:
            if not query_result.success or query_result.row_count == 0:
                continue

            # 查找数值列
            first_row = query_result.rows[0] if query_result.rows else {}

            for col_name, value in first_row.items():
                if isinstance(value, (int, float)):
                    # 判断是否为聚合指标（包含 sum, avg, count 等）
                    is_metric = any(
                        keyword in col_name.lower()
                        for keyword in ['sum', 'avg', 'count', 'total', 'amount', 'sales', '总', '平均', '数量']
                    )

                    if is_metric:
                        key_metrics.append({
                            "name": col_name,
                            "value": value,
                            "formatted": self._format_number(value),
                        })

        return key_metrics

    def _format_details(self, results: List[tuple[Any, Any]]) -> List[Dict]:
        """格式化详细数据"""
        details = []

        for plan_step, query_result in results:
            detail = {
                "step": plan_step.step_id if hasattr(plan_step, 'step_id') else "unknown",
                "purpose": plan_step.purpose if hasattr(plan_step, 'purpose') else "",
                "row_count": query_result.row_count,
                "success": query_result.success,
                "data": query_result.rows[:100],  # 最多返回前100行
                "truncated": query_result.row_count > 100,
            }

            if not query_result.success:
                detail["error"] = query_result.error

            details.append(detail)

        return details

    def _extract_filters(self, plan: Any) -> Dict:
        """提取过滤条件"""
        filters = {}

        if hasattr(plan, 'steps') and plan.steps:
            # 从第一个步骤提取过滤条件
            first_step = plan.steps[0]
            if hasattr(first_step, 'filters'):
                filters = first_step.filters

        return filters

    def _generate_data_scope(self, plan: Any, results: List[tuple[Any, Any]]) -> str:
        """生成数据范围说明"""
        scope_parts = []

        # 时间范围
        filters = self._extract_filters(plan)
        if 'time_range' in filters:
            scope_parts.append(f"时间范围: {filters['time_range']}")

        # 数据量
        total_rows = sum(qr.row_count for _, qr in results if qr.success)
        scope_parts.append(f"数据行数: {total_rows}")

        return " | ".join(scope_parts)

    def _collect_warnings(self, validation_results: List[Any]) -> List[str]:
        """收集警告信息"""
        warnings = []

        for validation_result in validation_results:
            if hasattr(validation_result, 'issues'):
                for issue in validation_result.issues:
                    if issue.severity in ['warning', 'error']:
                        warnings.append(f"[{issue.severity.upper()}] {issue.message}")

        return warnings

    def _generate_audit_info(self, results: List[tuple[Any, Any]]) -> Dict:
        """生成审计信息"""
        query_ids = []
        total_execution_time = 0.0

        for _, query_result in results:
            if hasattr(query_result, 'query_id'):
                query_ids.append(query_result.query_id)
            if hasattr(query_result, 'execution_time'):
                total_execution_time += query_result.execution_time

        return {
            "query_ids": query_ids,
            "total_execution_time": round(total_execution_time, 3),
            "query_count": len(results),
        }

    def _generate_summary(self, question: str, answer: Dict) -> str:
        """使用 LLM 生成自然语言总结"""
        # 构建提示词
        prompt = f"""请根据以下信息，用自然语言回答用户的问题。

## 用户问题
{question}

## 关键指标
{self._format_metrics_for_summary(answer['key_metrics'])}

## 数据范围
{answer['data_scope']}

## 警告
{chr(10).join(answer['warnings']) if answer['warnings'] else '无'}

请生成简洁、准确的回答，包括：
1. 直接回答问题
2. 列出关键数字
3. 如果有警告，简要说明

回答：
"""

        response = self.llm.invoke(prompt)
        return response.content.strip()

    def _generate_simple_summary(self, question: str, answer: Dict) -> str:
        """生成简单总结（不使用 LLM）"""
        summary_parts = []

        # 关键指标
        if answer['key_metrics']:
            metrics_str = ", ".join(
                f"{m['name']}: {m['formatted']}"
                for m in answer['key_metrics'][:3]  # 最多显示3个
            )
            summary_parts.append(f"关键指标: {metrics_str}")

        # 数据范围
        if answer['data_scope']:
            summary_parts.append(answer['data_scope'])

        # 警告
        if answer['warnings']:
            summary_parts.append(f"注意: {len(answer['warnings'])} 个警告")

        return " | ".join(summary_parts)

    def _format_metrics_for_summary(self, metrics: List[Dict]) -> str:
        """格式化指标用于总结"""
        if not metrics:
            return "无"

        return "\n".join(
            f"- {m['name']}: {m['formatted']}"
            for m in metrics
        )

    def _format_number(self, value: float) -> str:
        """格式化数字"""
        if abs(value) >= 1e9:
            return f"{value / 1e9:.2f}B"
        elif abs(value) >= 1e6:
            return f"{value / 1e6:.2f}M"
        elif abs(value) >= 1e3:
            return f"{value / 1e3:.2f}K"
        else:
            return f"{value:.2f}"

    def format_answer_for_display(self, answer: Dict) -> str:
        """格式化答案用于展示"""
        lines = []

        # 标题
        lines.append("=" * 60)
        lines.append(f"问题: {answer['question']}")
        lines.append("=" * 60)
        lines.append("")

        # 总结
        lines.append("## 总结")
        lines.append(answer['summary'])
        lines.append("")

        # 关键指标
        if answer['key_metrics']:
            lines.append("## 关键指标")
            for metric in answer['key_metrics']:
                lines.append(f"- {metric['name']}: {metric['formatted']}")
            lines.append("")

        # 数据范围
        if answer['data_scope']:
            lines.append("## 数据范围")
            lines.append(answer['data_scope'])
            lines.append("")

        # 警告
        if answer['warnings']:
            lines.append("## 注意事项")
            for warning in answer['warnings']:
                lines.append(f"⚠️  {warning}")
            lines.append("")

        # 审计信息
        lines.append("## 审计信息")
        audit = answer['audit_info']
        lines.append(f"- 查询数量: {audit.get('query_count', 0)}")
        lines.append(f"- 执行时间: {audit.get('total_execution_time', 0)}秒")
        lines.append(f"- 查询ID: {', '.join(audit.get('query_ids', [])[:2])}")
        lines.append("")

        return "\n".join(lines)
