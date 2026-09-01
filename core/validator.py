"""
ResultValidator: 结果验证器

负责验证查询结果的合理性
"""

from typing import Dict, List, Optional, Any
from datetime import datetime


class ValidationIssue:
    """验证问题"""

    def __init__(self, severity: str, message: str, details: Optional[Dict] = None):
        """
        Args:
            severity: 严重程度 (info, warning, error)
            message: 问题描述
            details: 详细信息
        """
        self.severity = severity
        self.message = message
        self.details = details or {}


class ValidationResult:
    """验证结果"""

    def __init__(self, is_valid: bool, issues: List[ValidationIssue]):
        self.is_valid = is_valid
        self.issues = issues

    def has_errors(self) -> bool:
        """是否有错误"""
        return any(issue.severity == "error" for issue in self.issues)

    def has_warnings(self) -> bool:
        """是否有警告"""
        return any(issue.severity == "warning" for issue in self.issues)

    def get_errors(self) -> List[ValidationIssue]:
        """获取所有错误"""
        return [issue for issue in self.issues if issue.severity == "error"]

    def get_warnings(self) -> List[ValidationIssue]:
        """获取所有警告"""
        return [issue for issue in self.issues if issue.severity == "warning"]


class ResultValidator:
    """
    结果验证器

    负责：
    1. 空结果合理性检查
    2. 时间范围验证
    3. 异常值检测
    4. 聚合粒度验证
    5. Join 重复检查
    """

    def __init__(self, semantic_layer=None):
        """
        初始化结果验证器

        Args:
            semantic_layer: SemanticLayer 实例（用于业务规则验证）
        """
        self.semantic_layer = semantic_layer

    def validate(self, plan_step: Any, query_result: Any) -> ValidationResult:
        """
        验证查询结果

        Args:
            plan_step: QueryStep 对象
            query_result: QueryResult 对象

        Returns:
            ValidationResult 对象
        """
        issues = []

        # 1. 检查查询是否成功
        if not query_result.success:
            issues.append(
                ValidationIssue(
                    severity="error",
                    message=f"查询执行失败: {query_result.error}",
                )
            )
            return ValidationResult(is_valid=False, issues=issues)

        # 2. 检查空结果
        self._check_empty_result(plan_step, query_result, issues)

        # 3. 检查异常值
        self._check_anomalies(query_result, issues)

        # 4. 检查数据类型
        self._check_data_types(query_result, issues)

        # 5. 检查聚合一致性
        self._check_aggregation_consistency(query_result, issues)

        # 6. 检查时间范围
        self._check_time_range(plan_step, query_result, issues)

        # 判断是否有错误
        is_valid = not any(issue.severity == "error" for issue in issues)

        return ValidationResult(is_valid=is_valid, issues=issues)

    def _check_empty_result(self, plan_step: Any, query_result: Any, issues: List[ValidationIssue]):
        """检查空结果是否合理"""
        if query_result.row_count == 0:
            # 空结果可能是正常的，但需要提醒
            issues.append(
                ValidationIssue(
                    severity="warning",
                    message="查询返回空结果，请确认过滤条件是否正确",
                    details={"filters": plan_step.filters if hasattr(plan_step, 'filters') else {}},
                )
            )

    def _check_anomalies(self, query_result: Any, issues: List[ValidationIssue]):
        """检查异常值"""
        if not query_result.rows:
            return

        # 检查数值列中的异常
        for row in query_result.rows:
            for col_name, value in row.items():
                # 检查负值（某些指标不应该为负）
                if isinstance(value, (int, float)):
                    if value < 0:
                        # 某些指标（如销售额、数量）不应该为负
                        if any(keyword in col_name.lower() for keyword in ['amount', 'count', 'quantity', '数量', '金额']):
                            issues.append(
                                ValidationIssue(
                                    severity="warning",
                                    message=f"检测到负值: {col_name} = {value}",
                                    details={"column": col_name, "value": value},
                                )
                            )

                    # 检查异常大的值
                    if abs(value) > 1e12:
                        issues.append(
                            ValidationIssue(
                                severity="warning",
                                message=f"检测到异常大的值: {col_name} = {value}",
                                details={"column": col_name, "value": value},
                            )
                        )

    def _check_data_types(self, query_result: Any, issues: List[ValidationIssue]):
        """检查数据类型一致性"""
        if not query_result.rows or len(query_result.rows) < 2:
            return

        # 检查每列的数据类型是否一致
        column_types = {}

        for row in query_result.rows:
            for col_name, value in row.items():
                value_type = type(value).__name__ if value is not None else "None"

                if col_name not in column_types:
                    column_types[col_name] = set()

                column_types[col_name].add(value_type)

        # 检查类型不一致的列
        for col_name, types in column_types.items():
            if len(types) > 2:  # 允许 None + 一种类型
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        message=f"列 {col_name} 的数据类型不一致: {types}",
                        details={"column": col_name, "types": list(types)},
                    )
                )

    def _check_aggregation_consistency(self, query_result: Any, issues: List[ValidationIssue]):
        """
        检查聚合一致性

        例如：如果有 SUM 和 COUNT，检查平均值是否合理
        """
        if not query_result.rows:
            return

        # 简化实现：检查总计是否等于明细之和
        # 这需要根据具体的查询结构来判断

        # TODO: 实现更复杂的聚合一致性检查
        pass

    def _check_time_range(self, plan_step: Any, query_result: Any, issues: List[ValidationIssue]):
        """检查时间范围是否正确"""
        if not query_result.rows:
            return

        # 查找时间列
        time_columns = []
        for col_name in query_result.columns:
            if any(keyword in col_name.lower() for keyword in ['date', 'time', 'day', 'month', 'year', '日期', '时间']):
                time_columns.append(col_name)

        if not time_columns:
            return

        # 检查时间范围
        for time_col in time_columns:
            time_values = []
            for row in query_result.rows:
                value = row.get(time_col)
                if value is not None:
                    # 尝试解析为日期
                    try:
                        if isinstance(value, str):
                            # 简单的日期解析
                            date_value = datetime.fromisoformat(value.replace('Z', '+00:00'))
                            time_values.append(date_value)
                        elif isinstance(value, datetime):
                            time_values.append(value)
                    except:
                        pass

            if time_values:
                min_date = min(time_values)
                max_date = max(time_values)
                date_range = (max_date - min_date).days

                # 检查是否有未来日期
                now = datetime.now()
                if max_date > now:
                    issues.append(
                        ValidationIssue(
                            severity="warning",
                            message=f"检测到未来日期: {max_date}",
                            details={"column": time_col, "max_date": max_date.isoformat()},
                        )
                    )

    def validate_multiple_results(
        self,
        results: List[tuple[Any, Any]],  # List of (plan_step, query_result)
    ) -> ValidationResult:
        """
        验证多个查询结果的一致性

        用于对比分析等需要多个查询的场景
        """
        issues = []

        # 验证每个结果
        for plan_step, query_result in results:
            result = self.validate(plan_step, query_result)
            issues.extend(result.issues)

        # 检查结果之间的一致性
        if len(results) >= 2:
            self._check_cross_result_consistency(results, issues)

        is_valid = not any(issue.severity == "error" for issue in issues)
        return ValidationResult(is_valid=is_valid, issues=issues)

    def _check_cross_result_consistency(
        self,
        results: List[tuple[Any, Any]],
        issues: List[ValidationIssue],
    ):
        """检查多个结果之间的一致性"""
        # 例如：对比查询的两个期间数据量应该相近
        # 这里只做简单的行数检查

        row_counts = [qr.row_count for _, qr in results]

        if len(row_counts) >= 2:
            max_count = max(row_counts)
            min_count = min(row_counts)

            # 如果差异过大，发出警告
            if max_count > 0 and min_count / max_count < 0.1:
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        message=f"多个查询结果的数据量差异较大: {row_counts}",
                        details={"row_counts": row_counts},
                    )
                )
