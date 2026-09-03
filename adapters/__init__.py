"""
SQLite Adapter Package for RDS Agent

This package provides SQLite-based implementations of Catalog and SemanticLayer,
maintaining 100% API compatibility with the YAML-based versions.
"""

from .sqlite_catalog import SQLiteCatalog
from .sqlite_semantic import SQLiteSemanticLayer
from .yaml_to_sqlite import migrate_yaml_to_sqlite, export_sqlite_to_yaml
from .factory import (
    create_catalog,
    create_semantic_layer,
    migrate_to_sqlite,
    get_config_mode,
)

__all__ = [
    # Main classes
    "SQLiteCatalog",
    "SQLiteSemanticLayer",

    # Migration functions
    "migrate_yaml_to_sqlite",
    "export_sqlite_to_yaml",

    # Factory functions
    "create_catalog",
    "create_semantic_layer",
    "migrate_to_sqlite",
    "get_config_mode",
]
