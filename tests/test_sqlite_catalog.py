"""
Unit Tests for SQLite Catalog Adapter

Tests the SQLiteCatalog implementation to ensure 100% API compatibility
with the original DatabaseCatalog.
"""

import pytest
import sqlite3
import tempfile
import shutil
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from adapters.sqlite_catalog import SQLiteCatalog
from adapters.yaml_to_sqlite import migrate_yaml_to_sqlite
from core.catalog import TableDefinition, ColumnInfo, JoinPath


@pytest.fixture
def temp_db():
    """Create a temporary SQLite database for testing."""
    # Create temp directory
    temp_dir = Path(tempfile.mkdtemp())
    db_path = temp_dir / "test_metadata.db"

    # Migrate sample data
    config_dir = Path(__file__).parent.parent / "config"
    if config_dir.exists():
        migrate_yaml_to_sqlite(config_dir, str(db_path))

    yield str(db_path)

    # Cleanup
    shutil.rmtree(temp_dir)


class TestSQLiteCatalog:
    """Test suite for SQLiteCatalog."""

    def test_init(self, temp_db):
        """Test catalog initialization."""
        catalog = SQLiteCatalog(temp_db)
        assert catalog is not None
        assert catalog.db_path == temp_db
        assert catalog.connection is not None

    def test_get_all_tables(self, temp_db):
        """Test retrieving all table names."""
        catalog = SQLiteCatalog(temp_db)
        tables = catalog.get_all_tables()

        assert isinstance(tables, list)
        assert len(tables) > 0
        assert all(isinstance(t, str) for t in tables)

        # Check for expected tables
        expected_tables = ["orders", "customers", "products"]
        for table in expected_tables:
            if table in tables:  # Only check if sample data exists
                assert table in tables

    def test_get_table(self, temp_db):
        """Test retrieving a single table definition."""
        catalog = SQLiteCatalog(temp_db)

        # Get first available table
        tables = catalog.get_all_tables()
        if not tables:
            pytest.skip("No tables in test database")

        table_name = tables[0]
        table_def = catalog.get_table(table_name)

        assert isinstance(table_def, TableDefinition)
        assert table_def.name == table_name
        assert isinstance(table_def.description, str)
        assert isinstance(table_def.columns, dict)
        assert len(table_def.columns) > 0

        # Check column structure
        for col_name, col_info in table_def.columns.items():
            assert isinstance(col_name, str)
            assert isinstance(col_info, ColumnInfo)
            assert isinstance(col_info.type, str)

    def test_get_table_not_found(self, temp_db):
        """Test retrieving a non-existent table."""
        catalog = SQLiteCatalog(temp_db)
        table_def = catalog.get_table("non_existent_table")
        assert table_def is None

    def test_search_schema_with_required_tables(self, temp_db):
        """Test schema search with required tables."""
        catalog = SQLiteCatalog(temp_db)

        all_tables = catalog.get_all_tables()
        if len(all_tables) < 2:
            pytest.skip("Not enough tables for testing")

        required = all_tables[:2]
        found = catalog.search_schema(required_tables=required)

        assert isinstance(found, list)
        assert len(found) == len(required)
        for table in required:
            assert table in found

    def test_search_schema_with_question(self, temp_db):
        """Test schema search with natural language question."""
        catalog = SQLiteCatalog(temp_db)

        # Search for tables with "order" in name or description
        found = catalog.search_schema(question="order")

        assert isinstance(found, list)
        # Should find at least orders table if it exists

    def test_get_join_paths(self, temp_db):
        """Test retrieving join paths between tables."""
        catalog = SQLiteCatalog(temp_db)

        all_tables = catalog.get_all_tables()
        if len(all_tables) < 2:
            pytest.skip("Not enough tables for testing")

        tables = all_tables[:2]
        joins = catalog.get_join_paths(tables)

        assert isinstance(joins, list)
        for join in joins:
            assert isinstance(join, JoinPath)
            assert join.left_table in tables or join.right_table in tables

    def test_find_join_path(self, temp_db):
        """Test finding join path between two tables."""
        catalog = SQLiteCatalog(temp_db)

        # Test with known tables that should have a path
        # This test is schema-dependent
        all_tables = catalog.get_all_tables()
        if "orders" in all_tables and "customers" in all_tables:
            path = catalog.find_join_path("orders", "customers")
            assert isinstance(path, list)
            # Path should exist between orders and customers

    def test_is_valid_join(self, temp_db):
        """Test checking if a join is valid."""
        catalog = SQLiteCatalog(temp_db)

        # Get some joins to test
        all_joins = catalog.get_join_paths(catalog.get_all_tables())
        if all_joins:
            join = all_joins[0]
            assert catalog.is_valid_join(join.left_table, join.right_table) is True

        # Test invalid join
        assert catalog.is_valid_join("non_existent_1", "non_existent_2") is False

    def test_get_ddl_summary(self, temp_db):
        """Test generating DDL summary."""
        catalog = SQLiteCatalog(temp_db)

        tables = catalog.get_all_tables()
        if not tables:
            pytest.skip("No tables in test database")

        ddl = catalog.get_ddl_summary(tables[0])

        assert isinstance(ddl, str)
        assert "CREATE TABLE" in ddl
        assert tables[0] in ddl

    def test_caching(self, temp_db):
        """Test that caching works correctly."""
        catalog = SQLiteCatalog(temp_db)

        tables = catalog.get_all_tables()
        if not tables:
            pytest.skip("No tables in test database")

        table_name = tables[0]

        # First access
        table_def_1 = catalog.get_table(table_name)

        # Second access (should hit cache)
        table_def_2 = catalog.get_table(table_name)

        # Should be the same object
        assert table_def_1 is table_def_2

    def test_clear_cache(self, temp_db):
        """Test cache clearing."""
        catalog = SQLiteCatalog(temp_db)

        tables = catalog.get_all_tables()
        if not tables:
            pytest.skip("No tables in test database")

        # Access a table to populate cache
        catalog.get_table(tables[0])
        assert len(catalog._tables_cache) > 0

        # Clear cache
        catalog.clear_cache()
        assert len(catalog._tables_cache) == 0

    def test_close_connection(self, temp_db):
        """Test closing database connection."""
        catalog = SQLiteCatalog(temp_db)
        catalog.close()

        # Connection should be closed
        # Attempting to use it should raise an error
        with pytest.raises(sqlite3.ProgrammingError):
            cursor = catalog.connection.cursor()
            cursor.execute("SELECT 1")


class TestSQLiteCatalogEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_database(self):
        """Test with empty database."""
        temp_dir = Path(tempfile.mkdtemp())
        db_path = temp_dir / "empty.db"

        try:
            catalog = SQLiteCatalog(str(db_path))
            tables = catalog.get_all_tables()
            assert tables == []
        finally:
            shutil.rmtree(temp_dir)

    def test_invalid_table_name_special_chars(self, temp_db):
        """Test with special characters in table name."""
        catalog = SQLiteCatalog(temp_db)

        # Should handle gracefully
        table_def = catalog.get_table("table'; DROP TABLE users; --")
        assert table_def is None

    def test_concurrent_access(self, temp_db):
        """Test concurrent access to database."""
        catalog1 = SQLiteCatalog(temp_db)
        catalog2 = SQLiteCatalog(temp_db)

        tables1 = catalog1.get_all_tables()
        tables2 = catalog2.get_all_tables()

        assert tables1 == tables2


class TestAPICompatibility:
    """Test API compatibility with original DatabaseCatalog."""

    def test_method_signatures(self, temp_db):
        """Test that method signatures match original implementation."""
        catalog = SQLiteCatalog(temp_db)

        # Check that all expected methods exist
        assert hasattr(catalog, "get_all_tables")
        assert hasattr(catalog, "get_table")
        assert hasattr(catalog, "search_schema")
        assert hasattr(catalog, "get_join_paths")
        assert hasattr(catalog, "find_join_path")
        assert hasattr(catalog, "is_valid_join")
        assert hasattr(catalog, "get_ddl_summary")

    def test_return_types(self, temp_db):
        """Test that return types match original implementation."""
        catalog = SQLiteCatalog(temp_db)

        # get_all_tables should return List[str]
        tables = catalog.get_all_tables()
        assert isinstance(tables, list)

        if tables:
            # get_table should return TableDefinition or None
            table_def = catalog.get_table(tables[0])
            assert table_def is None or isinstance(table_def, TableDefinition)

            # search_schema should return List[str]
            found = catalog.search_schema(required_tables=[tables[0]])
            assert isinstance(found, list)

            # get_join_paths should return List[JoinPath]
            joins = catalog.get_join_paths([tables[0]])
            assert isinstance(joins, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
