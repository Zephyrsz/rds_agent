"""
SQLite-based SemanticLayer Adapter for RDS Agent

This module provides a SQLite implementation of the SemanticLayer,
maintaining 100% API compatibility while using SQLite for storage.
"""

import sqlite3
import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

# Import the original classes for type compatibility
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.semantic import MetricDefinition, DimensionDefinition, ExampleSQL

logger = logging.getLogger(__name__)


class SQLiteSemanticLayer:
    """
    SQLite implementation of SemanticLayer.

    Provides the same API as SemanticLayer but reads from SQLite instead of YAML.
    All methods maintain 100% compatibility with the original implementation.

    Example:
        >>> semantic = SQLiteSemanticLayer("metadata.db")
        >>> metric = semantic.resolve_metric("sales_amount")
        >>> dimension = semantic.resolve_dimension("region")
    """

    def __init__(self, db_path: str, reference_date=None):
        """
        Initialize SQLite semantic layer.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.reference_date = reference_date
        self.connection = sqlite3.connect(db_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self._ensure_schema()

        # Cache for performance
        self._metrics_cache: Dict[str, MetricDefinition] = {}
        self._dimensions_cache: Dict[str, DimensionDefinition] = {}
        self._all_metrics_cache: Optional[List[MetricDefinition]] = None
        self._all_dimensions_cache: Optional[List[DimensionDefinition]] = None

        logger.info(f"SQLiteSemanticLayer initialized with database: {db_path}")

    def _ensure_schema(self):
        schema_file = Path(__file__).parent / "sqlite_schema.sql"
        if schema_file.exists():
            self.connection.executescript(schema_file.read_text(encoding="utf-8"))
            additions = {
                "tables": {"grain": "TEXT", "entities": "TEXT"},
                "joins": {"name": "TEXT", "auto_join": "BOOLEAN DEFAULT TRUE", "priority": "INTEGER DEFAULT 100", "fan_out_risk": "BOOLEAN DEFAULT FALSE", "temporal_validity": "TEXT"},
                "dimensions": {"dimension_type": "TEXT DEFAULT 'categorical'", "granularities": "TEXT", "filter_column": "TEXT"},
                "metrics": {"metric_type": "TEXT DEFAULT 'simple'", "numerator": "TEXT", "denominator": "TEXT", "base_measure": "TEXT", "comparison": "TEXT", "format": "TEXT", "certification": "TEXT DEFAULT 'draft'", "valid_dimensions": "TEXT"},
            }
            for table, columns in additions.items():
                existing = {row[1] for row in self.connection.execute(f"PRAGMA table_info({table})")}
                for name, definition in columns.items():
                    if name not in existing:
                        self.connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
            self.connection.commit()

    def resolve_metric(self, metric_name: str) -> Optional[MetricDefinition]:
        """
        Resolve metric by name.

        Args:
            metric_name: Metric name

        Returns:
            MetricDefinition object or None if not found
        """
        # Check cache first
        if metric_name in self._metrics_cache:
            return self._metrics_cache[metric_name]

        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT * FROM metrics
            WHERE name = ? AND active = TRUE
        """, (metric_name,))

        row = cursor.fetchone()
        if not row:
            canonical = self._canonical_name(metric_name, "metrics")
            if canonical:
                cursor.execute("SELECT * FROM metrics WHERE name = ? AND active = TRUE", (canonical,))
                row = cursor.fetchone()
        if not row:
            logger.warning(f"Metric not found: {metric_name}")
            return None

        metric_def = MetricDefinition(
            name=row["name"],
            display_name=row["display_name"],
            description=row["description"],
            expression=row["expression"],
            tables=json.loads(row["tables"]),
            filters=json.loads(row["filters"]) if row["filters"] else [],
            time_column=row["time_column"],
            unit=row["unit"],
            data_type=row["data_type"],
            min_value=row["min_value"],
            max_value=row["max_value"],
            metric_type=row["metric_type"] or "simple",
            numerator=row["numerator"],
            denominator=row["denominator"],
            base_measure=row["base_measure"],
            comparison=row["comparison"],
            format=row["format"],
            certification=row["certification"] or "draft",
            valid_dimensions=json.loads(row["valid_dimensions"] or "[]"),
        )

        # Cache it
        self._metrics_cache[metric_name] = metric_def

        logger.debug(f"Resolved metric: {metric_name}")
        return metric_def

    def resolve_dimension(self, dim_name: str) -> Optional[DimensionDefinition]:
        """
        Resolve dimension by name.

        Args:
            dim_name: Dimension name

        Returns:
            DimensionDefinition object or None if not found
        """
        # Check cache first
        if dim_name in self._dimensions_cache:
            return self._dimensions_cache[dim_name]

        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT * FROM dimensions
            WHERE name = ? AND active = TRUE
        """, (dim_name,))

        row = cursor.fetchone()
        if not row:
            canonical = self._canonical_name(dim_name, "dimensions")
            if canonical:
                cursor.execute("SELECT * FROM dimensions WHERE name = ? AND active = TRUE", (canonical,))
                row = cursor.fetchone()
        if not row:
            logger.warning(f"Dimension not found: {dim_name}")
            return None

        dim_def = DimensionDefinition(
            name=row["name"],
            display_name=row["display_name"],
            table=row["table_name"],
            column=row["column_name"],
            mappings=json.loads(row["mappings"]) if row["mappings"] else {},
            dimension_type=row["dimension_type"] or "categorical",
            granularities=json.loads(row["granularities"] or "[]"),
            filter_column=(row["filter_column"] or row["column_name"]),
        )

        # Cache it
        self._dimensions_cache[dim_name] = dim_def

        logger.debug(f"Resolved dimension: {dim_name}")
        return dim_def

    def resolve_dimension_value(self, dimension_name: str, value: str) -> Optional[str]:
        """Return a safe SQL predicate for a semantic dimension value."""
        dim = self.resolve_dimension(dimension_name)
        if dim is None:
            return None
        values = dim.mappings.get(value, [value])
        if not isinstance(values, (list, tuple)):
            values = [values]
        quote = lambda item: "'" + str(item).replace("'", "''") + "'"
        column = f"{dim.table}.{dim.filter_column}"
        if len(values) == 1:
            return f"{column} = {quote(values[0])}"
        return f"{column} IN ({', '.join(quote(item) for item in values)})"

    def resolve_business_term(self, term: str) -> List[str]:
        """
        Resolve business term to actual values.

        Args:
            term: Business term (e.g., "华东")

        Returns:
            List of actual values (e.g., ["上海", "江苏", "浙江"])
        """
        cursor = self.connection.cursor()

        # Try exact match in terms table
        cursor.execute("""
            SELECT synonyms FROM terms
            WHERE term = ? AND active = TRUE
        """, (term,))

        row = cursor.fetchone()
        if row:
            synonyms = json.loads(row["synonyms"] or "[]")
            logger.debug(f"Resolved term '{term}' to {len(synonyms)} values")
            return synonyms

        # Fallback: check dimension mappings
        cursor.execute("""
            SELECT mappings FROM dimensions
            WHERE active = TRUE
        """)

        for row in cursor.fetchall():
            if row["mappings"]:
                mappings = json.loads(row["mappings"]) or {}
                if term in mappings:
                    values = mappings[term]
                    logger.debug(f"Resolved term '{term}' via dimension mapping")
                    return values

        # No resolution found, return as-is
        logger.debug(f"Term '{term}' not found, returning as-is")
        return [term]

    def _canonical_name(self, name: str, target_table: str) -> Optional[str]:
        """Resolve a metric/dimension name through the normalized terms table."""
        needle = str(name).strip().lower()
        cursor = self.connection.cursor()
        cursor.execute("SELECT term, standard_name, synonyms FROM terms WHERE active = TRUE")
        for row in cursor.fetchall():
            candidates = [row["term"], row["standard_name"]]
            candidates.extend(json.loads(row["synonyms"] or "[]"))
            if any(str(candidate).strip().lower() == needle for candidate in candidates if candidate):
                canonical = row["term"]
                cursor.execute(f"SELECT name FROM {target_table} WHERE name = ? AND active = TRUE", (canonical,))
                match = cursor.fetchone()
                if match:
                    return match["name"]
        return None

    def resolve_filter(self, filter_name: str):
        from core.semantic import FilterDefinition

        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM filters WHERE name = ? AND active = TRUE", (filter_name,))
        row = cursor.fetchone()
        if not row:
            needle = str(filter_name).strip().lower()
            cursor.execute("SELECT * FROM filters WHERE active = TRUE")
            for candidate in cursor.fetchall():
                aliases = [candidate["name"], candidate["display_name"]]
                aliases.extend(json.loads(candidate["synonyms"] or "[]"))
                if needle in {str(alias).strip().lower() for alias in aliases if alias}:
                    row = candidate
                    break
        if not row:
            return None
        return FilterDefinition(
            name=row["name"], display_name=row["display_name"], expression=row["expression"],
            description=row["description"] or "", applies_to=json.loads(row["applies_to"] or "[]"),
            synonyms=json.loads(row["synonyms"] or "[]"),
        )

    def resolve_domain(self, domain_name: str):
        from core.semantic import DomainDefinition

        row = self.connection.execute(
            "SELECT * FROM domains WHERE name = ? AND active = TRUE", (domain_name,)
        ).fetchone()
        if not row:
            return None
        return DomainDefinition(
            name=row["name"], display_name=row["display_name"], description=row["description"] or "",
            allowed_tables=json.loads(row["allowed_tables"] or "[]"),
            allowed_metrics=json.loads(row["allowed_metrics"] or "[]"),
            default_timezone=row["default_timezone"] or "Asia/Shanghai",
            default_currency=row["default_currency"] or "CNY",
        )

    def resolve_measure(self, measure_name: str):
        from core.semantic import MeasureDefinition

        row = self.connection.execute(
            "SELECT * FROM measures WHERE name = ? AND active = TRUE", (measure_name,)
        ).fetchone()
        if not row:
            return None
        return MeasureDefinition(
            name=row["name"], display_name=row["display_name"], expression=row["expression"],
            table=row["table_name"], aggregation=row["aggregation"], data_type=row["data_type"] or "DECIMAL",
            unit=row["unit"] or "", additive=row["additive"], time_additive=row["time_additive"],
        )

    def resolve_time_range(self, expression: str) -> Dict[str, Any]:
        """
        Resolve time range expression.

        Args:
            expression: Time expression (e.g., "最近一个月", "本周", "今年")

        Returns:
            Dict with start_date, end_date, column
        """
        reference = self.reference_date or datetime.now().date()
        today = reference.date() if isinstance(reference, datetime) else reference

        def parse_count(text: str, default: int = 1) -> int:
            match = re.search(r"(\d+|[一二三四五六七八九十百]+)", text)
            if not match:
                return default
            token = match.group(1)
            if token.isdigit():
                return int(token)
            values = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
            if token == "十":
                return 10
            if "十" in token:
                parts = token.split("十")
                return (values.get(parts[0], 1) if parts[0] else 1) * 10 + (values.get(parts[1], 0) if len(parts) > 1 and parts[1] else 0)
            return values.get(token, default)

        expression_lower = expression.lower()
        if "最近" in expression or "近" in expression or "last" in expression_lower:
            if "天" in expression or "day" in expression_lower:
                start_date, end_date = today - timedelta(days=parse_count(expression)), today
            elif "周" in expression or "week" in expression_lower:
                start_date, end_date = today - timedelta(weeks=parse_count(expression)), today
            elif "年" in expression or "year" in expression_lower:
                start_date, end_date = today.replace(month=1, day=1), today
            else:
                months = parse_count(expression)
                month = today.month - months + 1
                year = today.year + (month - 1) // 12
                month = (month - 1) % 12 + 1
                start_date, end_date = today.replace(year=year, month=month, day=1), today
        elif "上月" in expression or "last month" in expression_lower:
            first = today.replace(day=1)
            end_date = first - timedelta(days=1)
            start_date = end_date.replace(day=1)
        elif "本周" in expression or "this week" in expression_lower:
            start_date, end_date = today - timedelta(days=today.weekday()), today
        elif "本月" in expression or "this month" in expression_lower:
            start_date, end_date = today.replace(day=1), today
        elif "今年" in expression or "this year" in expression_lower:
            start_date, end_date = today.replace(month=1, day=1), today
        elif "昨天" in expression or "昨日" in expression:
            start_date = end_date = today - timedelta(days=1)
        else:
            start_date, end_date = today - timedelta(days=30), today

        result = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "column": "order_date",  # Default time column
        }

        logger.debug(f"Resolved time range '{expression}': {result}")
        return result

    def get_all_metrics(self) -> List[MetricDefinition]:
        """
        Get all metrics.

        Returns:
            List of MetricDefinition objects
        """
        if self._all_metrics_cache is not None:
            return self._all_metrics_cache

        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT * FROM metrics
            WHERE active = TRUE
            ORDER BY name
        """)

        metrics = []
        for row in cursor.fetchall():
            metrics.append(MetricDefinition(
                name=row["name"],
                display_name=row["display_name"],
                description=row["description"],
                expression=row["expression"],
                tables=json.loads(row["tables"]),
                filters=json.loads(row["filters"]) if row["filters"] else [],
                time_column=row["time_column"],
                unit=row["unit"],
                data_type=row["data_type"],
                min_value=row["min_value"],
                max_value=row["max_value"],
                metric_type=row["metric_type"] or "simple",
                numerator=row["numerator"],
                denominator=row["denominator"],
                base_measure=row["base_measure"],
                comparison=row["comparison"],
                format=row["format"],
                certification=row["certification"] or "draft",
                valid_dimensions=json.loads(row["valid_dimensions"] or "[]"),
            ))

        self._all_metrics_cache = metrics
        logger.debug(f"Retrieved {len(metrics)} metrics")
        return metrics

    def get_all_dimensions(self) -> List[DimensionDefinition]:
        """
        Get all dimensions.

        Returns:
            List of DimensionDefinition objects
        """
        if self._all_dimensions_cache is not None:
            return self._all_dimensions_cache

        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT * FROM dimensions
            WHERE active = TRUE
            ORDER BY name
        """)

        dimensions = []
        for row in cursor.fetchall():
            dimensions.append(DimensionDefinition(
                name=row["name"],
                display_name=row["display_name"],
                table=row["table_name"],
                column=row["column_name"],
                mappings=json.loads(row["mappings"]) if row["mappings"] else {},
                dimension_type=row["dimension_type"] or "categorical",
                granularities=json.loads(row["granularities"] or "[]"),
                filter_column=(row["filter_column"] or row["column_name"]),
            ))

        self._all_dimensions_cache = dimensions
        logger.debug(f"Retrieved {len(dimensions)} dimensions")
        return dimensions

    def get_examples(
        self,
        question_type: str = None,
        limit: int = 3
    ) -> List[ExampleSQL]:
        """
        Get example SQL queries.

        Args:
            question_type: Filter by question type (optional)
            limit: Maximum number of examples to return

        Returns:
            List of ExampleSQL objects
        """
        cursor = self.connection.cursor()

        if question_type:
            cursor.execute("""
                SELECT * FROM examples
                WHERE question_type = ? AND active = TRUE
                LIMIT ?
            """, (question_type, limit))
        else:
            cursor.execute("""
                SELECT * FROM examples
                WHERE active = TRUE
                LIMIT ?
            """, (limit,))

        examples = []
        for row in cursor.fetchall():
            examples.append(ExampleSQL(
                question=row["question"],
                sql=row["sql"],
                question_type=row["question_type"] or "",
                tags=json.loads(row["tags"]) if row["tags"] else [],
            ))

        logger.debug(f"Retrieved {len(examples)} examples")
        return examples

    def search_examples(self, query: str, limit: int = 5) -> List[ExampleSQL]:
        """
        Search examples using full-text search.

        Args:
            query: Search query
            limit: Maximum number of results

        Returns:
            List of ExampleSQL objects
        """
        cursor = self.connection.cursor()

        # Use FTS5 for full-text search
        cursor.execute("""
            SELECT e.* FROM examples e
            JOIN examples_fts fts ON e.id = fts.rowid
            WHERE examples_fts MATCH ?
            AND e.active = TRUE
            ORDER BY rank
            LIMIT ?
        """, (query, limit))

        examples = []
        for row in cursor.fetchall():
            examples.append(ExampleSQL(
                question=row["question"],
                sql=row["sql"],
                question_type=row["question_type"] or "",
                tags=json.loads(row["tags"]) if row["tags"] else [],
            ))

        logger.debug(f"Found {len(examples)} examples matching '{query}'")
        return examples

    def get_metric(self, metric_name: str) -> Optional[MetricDefinition]:
        """
        Get metric definition (alias for resolve_metric).

        Args:
            metric_name: Metric name

        Returns:
            MetricDefinition object or None
        """
        return self.resolve_metric(metric_name)

    def get_dimension(self, dim_name: str) -> Optional[DimensionDefinition]:
        """
        Get dimension definition (alias for resolve_dimension).

        Args:
            dim_name: Dimension name

        Returns:
            DimensionDefinition object or None
        """
        return self.resolve_dimension(dim_name)

    def extract_intent(self, question: str) -> Dict[str, Any]:
        """
        Extract intent from natural language question.

        Note: This is a placeholder. In production, this would use an LLM
        or NLP model to extract structured intent.

        Args:
            question: Natural language question

        Returns:
            Dict with question_type, metrics, dimensions, time_range, filters
        """
        # Simple keyword-based extraction for now
        intent = {
            "question_type": "simple_query",
            "metrics": [],
            "dimensions": [],
            "time_range": None,
            "filters": {},
            "semantic_filters": [],
        }

        # Check for metrics
        all_metrics = self.get_all_metrics()
        for metric in all_metrics:
            aliases = [metric.name, metric.display_name]
            aliases.extend(self._term_aliases(metric.name))
            if any(alias and alias.lower() in question.lower() for alias in aliases):
                intent["metrics"].append(metric.name)

        # Check for dimensions
        all_dimensions = self.get_all_dimensions()
        for dim in all_dimensions:
            aliases = [dim.name, dim.display_name]
            aliases.extend(self._term_aliases(dim.name))
            if any(alias and alias.lower() in question.lower() for alias in aliases):
                intent["dimensions"].append(dim.name)
            for label in dim.mappings:
                if label in question:
                    intent["filters"][dim.name] = label

        for filter_name in ("valid_order",):
            definition = self.resolve_filter(filter_name)
            if definition and any(alias in question for alias in [definition.display_name, *definition.synonyms]):
                intent["semantic_filters"].append(filter_name)

        # Check for time expressions
        time_keywords = ["最近", "近", "本", "今", "昨"]
        for keyword in time_keywords:
            if keyword in question:
                # Extract the full time expression
                intent["time_range"] = "最近一个月"  # Simplified
                break

        logger.debug(f"Extracted intent: {intent}")
        return intent

    def _term_aliases(self, canonical: str) -> List[str]:
        row = self.connection.execute(
            "SELECT standard_name, synonyms FROM terms WHERE term = ? AND active = TRUE", (canonical,)
        ).fetchone()
        if not row:
            return []
        return [row["standard_name"], *json.loads(row["synonyms"] or "[]")]

    def clear_cache(self):
        """Clear all internal caches."""
        self._metrics_cache.clear()
        self._dimensions_cache.clear()
        self._all_metrics_cache = None
        self._all_dimensions_cache = None
        logger.debug("Cleared all caches")

    def close(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()
            logger.info("Database connection closed")


def create_semantic_layer_from_yaml(config_dir: Path, db_path: str) -> SQLiteSemanticLayer:
    """
    Create a SQLite semantic layer and populate it from YAML files.

    This is a convenience function for migrating from YAML to SQLite.

    Args:
        config_dir: Path to YAML config directory
        db_path: Path to SQLite database file

    Returns:
        Initialized SQLiteSemanticLayer
    """
    from .yaml_to_sqlite import migrate_yaml_to_sqlite

    # Perform migration
    migrate_yaml_to_sqlite(config_dir, db_path)

    # Return semantic layer
    return SQLiteSemanticLayer(db_path)
