"""
Unit Tests for Factory Methods

Tests the factory functions that support both YAML and SQLite modes.
"""

import pytest
import tempfile
import shutil
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from adapters.factory import (
    create_catalog,
    create_semantic_layer,
    migrate_to_sqlite,
    get_config_mode,
)
from adapters.sqlite_catalog import SQLiteCatalog
from adapters.sqlite_semantic import SQLiteSemanticLayer
from core.catalog import DatabaseCatalog
from core.semantic import SemanticLayer


@pytest.fixture
def temp_yaml_config():
    """Create temporary YAML config directory."""
    temp_dir = Path(tempfile.mkdtemp())

    # Copy sample config if exists
    source_config = Path(__file__).parent.parent / "config"
    if source_config.exists():
        dest_config = temp_dir / "config"
        shutil.copytree(source_config, dest_config)
        yield dest_config
    else:
        # Create minimal config
        config_dir = temp_dir / "config"
        config_dir.mkdir()
        yield config_dir

    # Cleanup
    shutil.rmtree(temp_dir)


@pytest.fixture
def temp_sqlite_db():
    """Create temporary SQLite database."""
    temp_dir = Path(tempfile.mkdtemp())
    db_path = temp_dir / "test.db"

    yield str(db_path)

    # Cleanup
    shutil.rmtree(temp_dir)


class TestCreateCatalog:
    """Test create_catalog factory method."""

    def test_create_yaml_catalog_with_path(self, temp_yaml_config):
        """Test creating YAML catalog with Path object."""
        catalog = create_catalog(temp_yaml_config)
        assert isinstance(catalog, DatabaseCatalog)

    def test_create_yaml_catalog_with_string(self, temp_yaml_config):
        """Test creating YAML catalog with string path."""
        catalog = create_catalog(str(temp_yaml_config) + "/")
        assert isinstance(catalog, DatabaseCatalog)

    def test_create_sqlite_catalog(self, temp_sqlite_db):
        """Test creating SQLite catalog."""
        catalog = create_catalog(temp_sqlite_db)
        assert isinstance(catalog, SQLiteCatalog)

    def test_invalid_source(self):
        """Test with invalid source format."""
        with pytest.raises(ValueError):
            create_catalog("invalid_format")

    def test_nonexistent_yaml_dir(self):
        """Test with non-existent YAML directory."""
        with pytest.raises(FileNotFoundError):
            create_catalog(Path("/nonexistent/dir"))


class TestCreateSemanticLayer:
    """Test create_semantic_layer factory method."""

    def test_create_yaml_semantic(self, temp_yaml_config):
        """Test creating YAML semantic layer."""
        semantic = create_semantic_layer(temp_yaml_config)
        assert isinstance(semantic, SemanticLayer)

    def test_create_sqlite_semantic(self, temp_sqlite_db):
        """Test creating SQLite semantic layer."""
        semantic = create_semantic_layer(temp_sqlite_db)
        assert isinstance(semantic, SQLiteSemanticLayer)


class TestMigrateToSQLite:
    """Test migrate_to_sqlite convenience function."""

    def test_migrate_basic(self, temp_yaml_config, temp_sqlite_db):
        """Test basic migration."""
        catalog, semantic = migrate_to_sqlite(temp_yaml_config, temp_sqlite_db)

        assert isinstance(catalog, SQLiteCatalog)
        assert isinstance(semantic, SQLiteSemanticLayer)
        assert Path(temp_sqlite_db).exists()

    def test_migrate_with_export(self, temp_yaml_config):
        """Test migration with export back to YAML."""
        temp_dir = Path(tempfile.mkdtemp())
        db_path = temp_dir / "metadata.db"

        try:
            catalog, semantic = migrate_to_sqlite(
                temp_yaml_config,
                str(db_path),
                export_back=True
            )

            # Check exported directory was created
            export_dir = temp_yaml_config.parent / "config_exported"
            assert export_dir.exists()
        finally:
            shutil.rmtree(temp_dir)


class TestGetConfigMode:
    """Test get_config_mode helper function."""

    def test_yaml_mode_with_path(self):
        """Test detecting YAML mode with Path object."""
        mode = get_config_mode(Path("config"))
        assert mode == "yaml"

    def test_yaml_mode_with_string(self):
        """Test detecting YAML mode with string."""
        mode = get_config_mode("config/")
        assert mode == "yaml"

    def test_sqlite_mode_db(self):
        """Test detecting SQLite mode with .db extension."""
        mode = get_config_mode("metadata.db")
        assert mode == "sqlite"

    def test_sqlite_mode_sqlite(self):
        """Test detecting SQLite mode with .sqlite extension."""
        mode = get_config_mode("metadata.sqlite")
        assert mode == "sqlite"

    def test_invalid_mode(self):
        """Test with invalid source."""
        with pytest.raises(ValueError):
            get_config_mode("invalid")


class TestDualMode:
    """Test that both modes produce compatible results."""

    def test_catalog_compatibility(self, temp_yaml_config, temp_sqlite_db):
        """Test that YAML and SQLite catalogs produce same results."""
        # Migrate first
        migrate_to_sqlite(temp_yaml_config, temp_sqlite_db)

        # Create both catalogs
        yaml_catalog = create_catalog(temp_yaml_config)
        sqlite_catalog = create_catalog(temp_sqlite_db)

        # Compare results
        yaml_tables = set(yaml_catalog.get_all_tables())
        sqlite_tables = set(sqlite_catalog.get_all_tables())

        assert yaml_tables == sqlite_tables

    def test_semantic_compatibility(self, temp_yaml_config, temp_sqlite_db):
        """Test that YAML and SQLite semantic layers produce same results."""
        # Migrate first
        migrate_to_sqlite(temp_yaml_config, temp_sqlite_db)

        # Create both semantic layers
        yaml_semantic = create_semantic_layer(temp_yaml_config)
        sqlite_semantic = create_semantic_layer(temp_sqlite_db)

        # Compare metrics
        yaml_metrics = {m.name for m in yaml_semantic.get_all_metrics()}
        sqlite_metrics = {m.name for m in sqlite_semantic.get_all_metrics()}

        assert yaml_metrics == sqlite_metrics


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
