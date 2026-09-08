"""Deterministic compilation of a semantic query into read-only SQL."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Sequence, Set

from .semantic import SemanticQuery


_REFERENCE_RE = re.compile(r"\b([A-Za-z_][\w]*)\.([A-Za-z_][\w]*)\b")
_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class SemanticQueryCompiler:
    """Compile the supported Phase 2 query DSL without an LLM."""

    def __init__(self, semantic_layer: Any, catalog: Any, default_limit: int = 1000):
        self.semantic_layer = semantic_layer
        self.catalog = catalog
        self.default_limit = default_limit

    def compile(self, query: SemanticQuery) -> str:
        if not isinstance(query, SemanticQuery):
            query = SemanticQuery.from_intent(query)
        if not query.metrics:
            raise ValueError("at least one metric is required")

        dimensions = self._resolve_dimensions(query.dimensions)
        metrics = self._resolve_metrics(query.metrics)
        base_table = self._choose_base_table(metrics)
        required_tables = self._required_tables(metrics, dimensions, base_table, query.filters)
        joins = self._join_closure(base_table, required_tables)

        select_parts = [f"{dim.table}.{dim.column} AS {dim.name}" for dim in dimensions]
        for metric in metrics:
            expression = self._compile_metric_expression(metric)
            select_parts.append(f"{expression} AS {metric.name}")

        sql = ["SELECT " + ", ".join(select_parts), f"FROM {base_table}"]
        for join, current_table, next_table in joins:
            if current_table == join.left_table:
                on_clause = f"{join.left} = {join.right}"
            else:
                on_clause = f"{join.right} = {join.left}"
            sql.append(
                f"{join.join_type} JOIN {next_table} ON "
                f"{on_clause}"
            )

        where = self._where_clauses(query, metrics, dimensions)
        if where:
            sql.append("WHERE " + " AND ".join(where))

        if dimensions:
            sql.append("GROUP BY " + ", ".join(f"{d.table}.{d.column}" for d in dimensions))

        if query.order_by:
            field = query.order_by.get("field", "")
            direction = str(query.order_by.get("direction", "desc")).upper()
            if field not in {m.name for m in metrics} | {d.name for d in dimensions}:
                raise ValueError(f"unknown order_by field: {field}")
            if direction not in {"ASC", "DESC"}:
                raise ValueError("order_by direction must be ASC or DESC")
            sql.append(f"ORDER BY {field} {direction}")

        limit = self._normalize_limit(query.limit)
        sql.append(f"LIMIT {limit}")
        return "\n".join(sql)

    def _resolve_metrics(self, names: Sequence[str]) -> List[Any]:
        resolved = []
        for name in names:
            resolver = getattr(self.semantic_layer, "resolve_metric", None)
            metric = resolver(name) if resolver else None
            if metric is None:
                raise ValueError(f"unknown metric: {name}")
            resolved.append(metric)
        return resolved

    def _resolve_dimensions(self, names: Sequence[str]) -> List[Any]:
        resolved = []
        for name in names:
            resolver = getattr(self.semantic_layer, "resolve_dimension", None)
            dimension = resolver(name) if resolver else None
            if dimension is None:
                raise ValueError(f"unknown dimension: {name}")
            resolved.append(dimension)
        return resolved

    def _choose_base_table(self, metrics: Sequence[Any]) -> str:
        references = []
        for metric in metrics:
            references.extend(_REFERENCE_RE.findall(metric.expression or ""))
        referenced_tables = [table for table, _ in references]
        for metric in metrics:
            for table in metric.tables:
                if table in referenced_tables:
                    return table
        for metric in metrics:
            if metric.tables:
                return metric.tables[0]
        raise ValueError("metric has no source table")

    def _required_tables(self, metrics: Sequence[Any], dimensions: Sequence[Any], base: str, filters: Dict[str, Any] | None = None) -> Set[str]:
        tables = {base}
        for metric in metrics:
            tables.update(metric.tables or [])
            tables.update(table for table, _ in _REFERENCE_RE.findall(metric.expression or ""))
        tables.update(dim.table for dim in dimensions)
        for name in (filters or {}):
            dimension = getattr(self.semantic_layer, "resolve_dimension", lambda _: None)(name)
            if dimension is None:
                raise ValueError(f"unknown filter dimension: {name}")
            tables.add(dimension.table)
        return tables

    def _join_closure(self, base: str, required_tables: Set[str]):
        joins = []
        joined = {base}
        pending = sorted(required_tables - joined)
        while pending:
            target = pending.pop(0)
            path = self.catalog.find_join_path(base, target)
            if not path:
                raise ValueError(f"no join path from {base} to {target}")
            current = base
            for edge in path:
                if edge.cardinality in {"many_to_many", "one_to_many"} or edge.fan_out_risk:
                    raise ValueError(f"unsafe join path includes {edge.name}")
                if not edge.auto_join:
                    raise ValueError(f"join is not approved for automatic use: {edge.name}")
                next_table = edge.right_table if current == edge.left_table else edge.left_table
                if next_table not in joined:
                    joins.append((edge, current, next_table))
                    joined.add(next_table)
                current = next_table
            pending = sorted(required_tables - joined)
        return joins

    def _compile_metric_expression(self, metric: Any) -> str:
        expression = (metric.expression or "").strip()
        if not expression:
            raise ValueError(f"metric has no expression: {metric.name}")
        metric_type = getattr(metric, "metric_type", "simple")
        if metric_type not in {None, "", "simple", "ratio"}:
            raise ValueError(f"unsupported metric type: {metric_type}")
        if ";" in expression or "--" in expression or "/*" in expression:
            raise ValueError(f"unsafe metric expression: {metric.name}")
        return expression

    def _where_clauses(self, query: SemanticQuery, metrics: Sequence[Any], dimensions: Sequence[Any]) -> List[str]:
        clauses: List[str] = []
        for metric in metrics:
            for expression in getattr(metric, "filters", []) or []:
                if expression and expression not in clauses:
                    clauses.append(expression)

        for filter_name in query.semantic_filters:
            definition = self.semantic_layer.resolve_filter(filter_name)
            if definition is None:
                raise ValueError(f"unknown semantic filter: {filter_name}")
            if definition.expression not in clauses:
                clauses.append(definition.expression)

        for name, value in (query.filters or {}).items():
            dimension = self.semantic_layer.resolve_dimension(name)
            if dimension is None:
                raise ValueError(f"unknown filter dimension: {name}")
            column = f"{dimension.table}.{dimension.filter_column}"
            values = dimension.mappings.get(value, [value]) if isinstance(value, str) else value
            if not isinstance(values, (list, tuple, set)):
                values = [values]
            quoted = ", ".join(self._quote_literal(item) for item in values)
            clauses.append(f"{column} = {quoted}" if len(values) == 1 else f"{column} IN ({quoted})")

        if query.time_range:
            parsed = self.semantic_layer.resolve_time_range(query.time_range)
            start = self._date_value(parsed["start_date"])
            end = self._date_value(parsed["end_date"]) + timedelta(days=1)
            time_columns = [getattr(m, "time_column", None) for m in metrics if getattr(m, "time_column", None)]
            if time_columns:
                column = time_columns[0]
                if any(item != column for item in time_columns):
                    raise ValueError("metrics use different time columns")
                clauses.extend([f"{column} >= {self._quote_literal(start.isoformat())}",
                                f"{column} < {self._quote_literal(end.isoformat())}"])
        return clauses

    @staticmethod
    def _date_value(value: Any) -> date:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        return date.fromisoformat(str(value)[:10])

    @staticmethod
    def _quote_literal(value: Any) -> str:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return str(value)
        escaped = str(value).replace("'", "''")
        return f"'{escaped}'"

    def _normalize_limit(self, limit: Any) -> int:
        try:
            value = int(limit or self.default_limit)
        except (TypeError, ValueError):
            value = self.default_limit
        return max(1, min(value, 10000))
