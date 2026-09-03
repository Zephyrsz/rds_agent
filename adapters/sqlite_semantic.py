"""
SQLite-based SemanticLayer Adapter for RDS Agent

This module provides a SQLite implementation of the SemanticLayer,
maintaining 100% API compatibility while using SQLite for storage.
"""

import sqlite3
import json
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

    def __init__(self, db_path: str):
        """
        Initialize SQLite semantic layer.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.connection = sqlite3.connect(db_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row

        # Cache for performance
        self._metrics_cache: Dict[str, MetricDefinition] = {}
        self._dimensions_cache: Dict[str, DimensionDefinition] = {}
        self._all_metrics_cache: Optional[List[MetricDefinition]] = None
        self._all_dimensions_cache: Optional[List[DimensionDefinition]] = None

        logger.info(f"SQLiteSemanticLayer initialized with database: {db_path}")

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
            logger.warning(f"Dimension not found: {dim_name}")
            return None

        dim_def = DimensionDefinition(
            name=row["name"],
            display_name=row["display_name"],
            table=row["table_name"],
            column=row["column_name"],
            mappings=json.loads(row["mappings"]) if row["mappings"] else {},
        )

        # Cache it
        self._dimensions_cache[dim_name] = dim_def

        logger.debug(f"Resolved dimension: {dim_name}")
        return dim_def

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
            synonyms = json.loads(row["synonyms"])
            logger.debug(f"Resolved term '{term}' to {len(synonyms)} values")
            return synonyms

        # Fallback: check dimension mappings
        cursor.execute("""
            SELECT mappings FROM dimensions
            WHERE active = TRUE
        """)

        for row in cursor.fetchall():
            if row["mappings"]:
                mappings = json.loads(row["mappings"])
                if term in mappings:
                    values = mappings[term]
                    logger.debug(f"Resolved term '{term}' via dimension mapping")
                    return values

        # No resolution found, return as-is
        logger.debug(f"Term '{term}' not found, returning as-is")
        return [term]

    def resolve_time_range(self, expression: str) -> Dict[str, Any]:
        """
        Resolve time range expression.

        Args:
            expression: Time expression (e.g., "最近一个月", "本周", "今年")

        Returns:
            Dict with start_date, end_date, column
        """
        today = datetime.now().date()

        # Parse common expressions
        if "最近" in expression or "近" in expression:
            if "天" in expression:
                # Extract number of days
                import re
                match = re.search(r'(\d+)天', expression)
                if match:
                    days = int(match.group(1))
                    start_date = today - timedelta(days=days)
                    end_date = today
            elif "周" in expression:
                match = re.search(r'(\d+)周', expression)
                if match:
                    weeks = int(match.group(1))
                    start_date = today - timedelta(weeks=weeks)
                    end_date = today
                else:
                    start_date = today - timedelta(weeks=1)
                    end_date = today
            elif "月" in expression or "个月" in expression:
                match = re.search(r'(\d+)个?月', expression)
                if match:
                    months = int(match.group(1))
                    # Approximate: 30 days per month
                    start_date = today - timedelta(days=30 * months)
                    end_date = today
                else:
                    start_date = today - timedelta(days=30)
                    end_date = today
            elif "年" in expression:
                start_date = today.replace(month=1, day=1)
                end_date = today
            else:
                # Default to last 7 days
                start_date = today - timedelta(days=7)
                end_date = today

        elif "本" in expression:
            if "周" in expression:
                # Start of this week (Monday)
                start_date = today - timedelta(days=today.weekday())
                end_date = today
            elif "月" in expression:
                start_date = today.replace(day=1)
                end_date = today
            elif "年" in expression:
                start_date = today.replace(month=1, day=1)
                end_date = today
            else:
                start_date = today
                end_date = today

        elif "今天" in expression or "今日" in expression:
            start_date = today
            end_date = today

        elif "昨天" in expression or "昨日" in expression:
            start_date = today - timedelta(days=1)
            end_date = today - timedelta(days=1)

        else:
            # Default: last 30 days
            start_date = today - timedelta(days=30)
            end_date = today

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
            "filters": []
        }

        # Check for metrics
        all_metrics = self.get_all_metrics()
        for metric in all_metrics:
            if metric.display_name in question or metric.name in question:
                intent["metrics"].append(metric.name)

        # Check for dimensions
        all_dimensions = self.get_all_dimensions()
        for dim in all_dimensions:
            if dim.display_name in question or dim.name in question:
                intent["dimensions"].append(dim.name)

        # Check for time expressions
        time_keywords = ["最近", "近", "本", "今", "昨"]
        for keyword in time_keywords:
            if keyword in question:
                # Extract the full time expression
                intent["time_range"] = "最近一个月"  # Simplified
                break

        logger.debug(f"Extracted intent: {intent}")
        return intent

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
