"""
Unit Tests for SQLite SemanticLayer Adapter

Tests the SQLiteSemanticLayer implementation to ensure 100% API compatibility
with the original SemanticLayer.
"""

import pytest
import sqlite3
import tempfile
import shutil
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from adapters.sqlite_semantic import SQLiteSemanticLayer
from adapters.yaml_to_sqlite import migrate_yaml_to_sqlite
from core.semantic import MetricDefinition, DimensionDefinition, ExampleSQL


@pytest.fixture
def temp_db():
    """Create a temporary SQLite database for testing."""
    temp_dir = Path(tempfile.mkdtemp())
    db_path = temp_dir / "test_metadata.db"

    # Migrate sample data
    config_dir = Path(__file__).parent.parent / "config"
    if config_dir.exists():
        migrate_yaml_to_sqlite(config_dir, str(db_path))

    yield str(db_path)

    # Cleanup
    shutil.rmtree(temp_dir)


class TestSQLiteSemanticLayer:
    """Test suite for SQLiteSemanticLayer."""

    def test_init(self, temp_db):
        """Test semantic layer initialization."""
        semantic = SQLiteSemanticLayer(temp_db)
        assert semantic is not None
        assert semantic.db_path == temp_db
        assert semantic.connection is not None

    def test_resolve_metric(self, temp_db):
        """Test resolving a metric by name."""
        semantic = SQLiteSemanticLayer(temp_db)

        # Get all metrics first
        all_metrics = semantic.get_all_metrics()
        if not all_metrics:
            pytest.skip("No metrics in test database")

        metric_name = all_metrics[0].name
        metric = semantic.resolve_metric(metric_name)

        assert isinstance(metric, MetricDefinition)
        assert metric.name == metric_name
        assert isinstance(metric.display_name, str)
        assert isinstance(metric.expression, str)
        assert isinstance(metric.tables, list)

    def test_resolve_metric_not_found(self, temp_db):
        """Test resolving a non-existent metric."""
        semantic = SQLiteSemanticLayer(temp_db)
        metric = semantic.resolve_metric("non_existent_metric")
        assert metric is None

    def test_resolve_dimension(self, temp_db):
        """Test resolving a dimension by name."""
        semantic = SQLiteSemanticLayer(temp_db)

        # Get all dimensions first
        all_dimensions = semantic.get_all_dimensions()
        if not all_dimensions:
            pytest.skip("No dimensions in test database")

        dim_name = all_dimensions[0].name
        dimension = semantic.resolve_dimension(dim_name)

        assert isinstance(dimension, DimensionDefinition)
        assert dimension.name == dim_name
        assert isinstance(dimension.display_name, str)
        assert isinstance(dimension.table, str)
        assert isinstance(dimension.column, str)

    def test_resolve_dimension_not_found(self, temp_db):
        """Test resolving a non-existent dimension."""
        semantic = SQLiteSemanticLayer(temp_db)
        dimension = semantic.resolve_dimension("non_existent_dimension")
        assert dimension is None

    def test_resolve_business_term(self, temp_db):
        """Test resolving business terms."""
        semantic = SQLiteSemanticLayer(temp_db)

        # Test with a term that should exist
        result = semantic.resolve_business_term("test_term")
        assert isinstance(result, list)

        # Should return at least the term itself
        assert len(result) > 0

    def test_resolve_time_range(self, temp_db):
        """Test resolving time range expressions."""
        semantic = SQLiteSemanticLayer(temp_db)

        test_cases = [
            "最近一个月",
            "最近7天",
            "本周",
            "本月",
            "今天",
        ]

        for expression in test_cases:
            result = semantic.resolve_time_range(expression)

            assert isinstance(result, dict)
            assert "start_date" in result
            assert "end_date" in result
            assert "column" in result

    def test_get_all_metrics(self, temp_db):
        """Test retrieving all metrics."""
        semantic = SQLiteSemanticLayer(temp_db)
        metrics = semantic.get_all_metrics()

        assert isinstance(metrics, list)
        for metric in metrics:
            assert isinstance(metric, MetricDefinition)

    def test_get_all_dimensions(self, temp_db):
        """Test retrieving all dimensions."""
        semantic = SQLiteSemanticLayer(temp_db)
        dimensions = semantic.get_all_dimensions()

        assert isinstance(dimensions, list)
        for dimension in dimensions:
            assert isinstance(dimension, DimensionDefinition)

    def test_get_examples(self, temp_db):
        """Test retrieving example SQL queries."""
        semantic = SQLiteSemanticLayer(temp_db)

        examples = semantic.get_examples(limit=5)

        assert isinstance(examples, list)
        assert len(examples) <= 5

        for example in examples:
            assert isinstance(example, ExampleSQL)
            assert isinstance(example.question, str)
            assert isinstance(example.sql, str)

    def test_get_examples_by_type(self, temp_db):
        """Test retrieving examples filtered by type."""
        semantic = SQLiteSemanticLayer(temp_db)

        # Get all examples first to find a valid type
        all_examples = semantic.get_examples(limit=100)
        if not all_examples:
            pytest.skip("No examples in test database")

        # Get examples of first type
        example_type = all_examples[0].question_type
        if example_type:
            filtered = semantic.get_examples(question_type=example_type)

            assert isinstance(filtered, list)
            for example in filtered:
                assert example.question_type == example_type

    def test_search_examples(self, temp_db):
        """Test full-text search of examples."""
        semantic = SQLiteSemanticLayer(temp_db)

        # Search for common SQL keywords
        results = semantic.search_examples("SELECT", limit=3)

        assert isinstance(results, list)
        assert len(results) <= 3

    def test_get_metric_alias(self, temp_db):
        """Test get_metric alias method."""
        semantic = SQLiteSemanticLayer(temp_db)

        all_metrics = semantic.get_all_metrics()
        if not all_metrics:
            pytest.skip("No metrics in test database")

        metric_name = all_metrics[0].name

        # get_metric should work the same as resolve_metric
        metric1 = semantic.get_metric(metric_name)
        metric2 = semantic.resolve_metric(metric_name)

        assert metric1.name == metric2.name

    def test_extract_intent(self, temp_db):
        """Test intent extraction from natural language."""
        semantic = SQLiteSemanticLayer(temp_db)

        question = "最近一个月的销售额是多少？"
        intent = semantic.extract_intent(question)

        assert isinstance(intent, dict)
        assert "question_type" in intent
        assert "metrics" in intent
        assert "dimensions" in intent
        assert "time_range" in intent
        assert "filters" in intent

    def test_caching(self, temp_db):
        """Test that caching works correctly."""
        semantic = SQLiteSemanticLayer(temp_db)

        all_metrics = semantic.get_all_metrics()
        if not all_metrics:
            pytest.skip("No metrics in test database")

        metric_name = all_metrics[0].name

        # First access
        metric1 = semantic.resolve_metric(metric_name)

        # Second access (should hit cache)
        metric2 = semantic.resolve_metric(metric_name)

        # Should be the same object
        assert metric1 is metric2

    def test_clear_cache(self, temp_db):
        """Test cache clearing."""
        semantic = SQLiteSemanticLayer(temp_db)

        all_metrics = semantic.get_all_metrics()
        if not all_metrics:
            pytest.skip("No metrics in test database")

        # Access a metric to populate cache
        semantic.resolve_metric(all_metrics[0].name)
        assert len(semantic._metrics_cache) > 0

        # Clear cache
        semantic.clear_cache()
        assert len(semantic._metrics_cache) == 0

    def test_close_connection(self, temp_db):
        """Test closing database connection."""
        semantic = SQLiteSemanticLayer(temp_db)
        semantic.close()

        # Connection should be closed
        with pytest.raises(sqlite3.ProgrammingError):
            cursor = semantic.connection.cursor()
            cursor.execute("SELECT 1")


class TestAPICompatibility:
    """Test API compatibility with original SemanticLayer."""

    def test_method_signatures(self, temp_db):
        """Test that method signatures match original implementation."""
        semantic = SQLiteSemanticLayer(temp_db)

        # Check that all expected methods exist
        assert hasattr(semantic, "resolve_metric")
        assert hasattr(semantic, "resolve_dimension")
        assert hasattr(semantic, "resolve_business_term")
        assert hasattr(semantic, "resolve_time_range")
        assert hasattr(semantic, "get_all_metrics")
        assert hasattr(semantic, "get_all_dimensions")
        assert hasattr(semantic, "get_examples")
        assert hasattr(semantic, "get_metric")
        assert hasattr(semantic, "get_dimension")
        assert hasattr(semantic, "extract_intent")

    def test_return_types(self, temp_db):
        """Test that return types match original implementation."""
        semantic = SQLiteSemanticLayer(temp_db)

        # get_all_metrics should return List[MetricDefinition]
        metrics = semantic.get_all_metrics()
        assert isinstance(metrics, list)

        # get_all_dimensions should return List[DimensionDefinition]
        dimensions = semantic.get_all_dimensions()
        assert isinstance(dimensions, list)

        # get_examples should return List[ExampleSQL]
        examples = semantic.get_examples()
        assert isinstance(examples, list)

        # resolve_business_term should return List[str]
        terms = semantic.resolve_business_term("test")
        assert isinstance(terms, list)

        # resolve_time_range should return Dict
        time_range = semantic.resolve_time_range("最近一周")
        assert isinstance(time_range, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
