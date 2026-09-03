"""
Factory methods for creating Catalog and SemanticLayer instances.

This module provides factory methods that support both YAML and SQLite modes,
allowing seamless switching between the two implementations.
"""

from pathlib import Path
from typing import Union

import logging

logger = logging.getLogger(__name__)


def create_catalog(config_source: Union[Path, str]):
    """
    Factory method to create a Catalog instance.

    Automatically detects the configuration source type and returns
    the appropriate implementation (YAML or SQLite).

    Args:
        config_source: Either:
            - Path object pointing to YAML config directory
            - String path to YAML config directory (ending with /)
            - String path to SQLite database file (ending with .db)

    Returns:
        DatabaseCatalog or SQLiteCatalog instance

    Examples:
        >>> # YAML mode
        >>> catalog = create_catalog(Path("config"))
        >>> catalog = create_catalog("config/")

        >>> # SQLite mode
        >>> catalog = create_catalog("metadata.db")

    Raises:
        ValueError: If config_source format is invalid
        FileNotFoundError: If the specified path doesn't exist
    """
    # Convert to string for easier checking
    source_str = str(config_source)

    if isinstance(config_source, Path) or source_str.endswith("/"):
        # YAML mode
        config_dir = Path(config_source)
        if not config_dir.exists():
            raise FileNotFoundError(f"Config directory not found: {config_dir}")

        logger.info(f"Creating YAML-based catalog from: {config_dir}")
        from core.catalog import DatabaseCatalog
        return DatabaseCatalog(config_dir)

    elif source_str.endswith(".db") or source_str.endswith(".sqlite"):
        # SQLite mode
        db_path = Path(source_str)
        if not db_path.exists():
            logger.warning(f"SQLite database not found, will be created: {db_path}")

        logger.info(f"Creating SQLite-based catalog from: {db_path}")
        from adapters.sqlite_catalog import SQLiteCatalog
        return SQLiteCatalog(str(db_path))

    else:
        raise ValueError(
            f"Invalid config source: {config_source}\n"
            "Expected either:\n"
            "  - Path to YAML directory (Path object or string ending with /)\n"
            "  - Path to SQLite database (string ending with .db or .sqlite)"
        )


def create_semantic_layer(config_source: Union[Path, str]):
    """
    Factory method to create a SemanticLayer instance.

    Automatically detects the configuration source type and returns
    the appropriate implementation (YAML or SQLite).

    Args:
        config_source: Either:
            - Path object pointing to YAML config directory
            - String path to YAML config directory (ending with /)
            - String path to SQLite database file (ending with .db)

    Returns:
        SemanticLayer or SQLiteSemanticLayer instance

    Examples:
        >>> # YAML mode
        >>> semantic = create_semantic_layer(Path("config"))
        >>> semantic = create_semantic_layer("config/")

        >>> # SQLite mode
        >>> semantic = create_semantic_layer("metadata.db")

    Raises:
        ValueError: If config_source format is invalid
        FileNotFoundError: If the specified path doesn't exist
    """
    # Convert to string for easier checking
    source_str = str(config_source)

    if isinstance(config_source, Path) or source_str.endswith("/"):
        # YAML mode
        config_dir = Path(config_source)
        if not config_dir.exists():
            raise FileNotFoundError(f"Config directory not found: {config_dir}")

        logger.info(f"Creating YAML-based semantic layer from: {config_dir}")
        from core.semantic import SemanticLayer
        return SemanticLayer(config_dir)

    elif source_str.endswith(".db") or source_str.endswith(".sqlite"):
        # SQLite mode
        db_path = Path(source_str)
        if not db_path.exists():
            logger.warning(f"SQLite database not found, will be created: {db_path}")

        logger.info(f"Creating SQLite-based semantic layer from: {db_path}")
        from adapters.sqlite_semantic import SQLiteSemanticLayer
        return SQLiteSemanticLayer(str(db_path))

    else:
        raise ValueError(
            f"Invalid config source: {config_source}\n"
            "Expected either:\n"
            "  - Path to YAML directory (Path object or string ending with /)\n"
            "  - Path to SQLite database (string ending with .db or .sqlite)"
        )


def migrate_to_sqlite(
    yaml_config_dir: Union[Path, str],
    sqlite_db_path: str,
    export_back: bool = False
) -> tuple:
    """
    Migrate YAML configuration to SQLite and return both instances.

    This is a convenience function for performing migration and getting
    ready-to-use catalog and semantic layer instances.

    Args:
        yaml_config_dir: Path to YAML configuration directory
        sqlite_db_path: Path to SQLite database file (will be created)
        export_back: If True, export SQLite back to YAML for verification

    Returns:
        Tuple of (SQLiteCatalog, SQLiteSemanticLayer)

    Example:
        >>> catalog, semantic = migrate_to_sqlite("config/", "metadata.db")
        >>> # Now you can use catalog and semantic with SQLite backend
    """
    from adapters.yaml_to_sqlite import migrate_yaml_to_sqlite, export_sqlite_to_yaml

    yaml_dir = Path(yaml_config_dir)

    logger.info(f"Migrating YAML config to SQLite: {yaml_dir} -> {sqlite_db_path}")

    # Perform migration
    migrate_yaml_to_sqlite(yaml_dir, sqlite_db_path)

    # Optionally export back for verification
    if export_back:
        verify_dir = yaml_dir.parent / "config_exported"
        logger.info(f"Exporting SQLite back to YAML for verification: {verify_dir}")
        export_sqlite_to_yaml(sqlite_db_path, verify_dir)

    # Create and return instances
    catalog = create_catalog(sqlite_db_path)
    semantic = create_semantic_layer(sqlite_db_path)

    logger.info("Migration completed successfully")
    return catalog, semantic


def get_config_mode(config_source: Union[Path, str]) -> str:
    """
    Detect the configuration mode from config_source.

    Args:
        config_source: Configuration source (Path or string)

    Returns:
        Either "yaml" or "sqlite"

    Example:
        >>> get_config_mode("config/")
        'yaml'
        >>> get_config_mode("metadata.db")
        'sqlite'
    """
    source_str = str(config_source)

    if isinstance(config_source, Path) or source_str.endswith("/"):
        return "yaml"
    elif source_str.endswith(".db") or source_str.endswith(".sqlite"):
        return "sqlite"
    else:
        raise ValueError(f"Cannot determine config mode from: {config_source}")


# Convenience aliases
create_db_catalog = create_catalog
create_db_semantic = create_semantic_layer
