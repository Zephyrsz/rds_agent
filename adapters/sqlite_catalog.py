"""
SQLite-based Catalog Adapter for RDS Agent

This module provides a SQLite implementation of the DatabaseCatalog,
maintaining 100% API compatibility while using SQLite for storage.
"""

import sqlite3
import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass
import logging

# Import the original classes for type compatibility
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.catalog import TableDefinition, ColumnInfo, JoinPath

logger = logging.getLogger(__name__)


class SQLiteCatalog:
    """
    SQLite implementation of DatabaseCatalog.

    Provides the same API as DatabaseCatalog but reads from SQLite instead of YAML.
    All methods maintain 100% compatibility with the original implementation.

    Example:
        >>> catalog = SQLiteCatalog("metadata.db")
        >>> tables = catalog.get_all_tables()
        >>> table_def = catalog.get_table("orders")
    """

    def __init__(self, db_path: str):
        """
        Initialize SQLite catalog.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.connection = sqlite3.connect(db_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row

        # Cache for performance
        self._tables_cache: Dict[str, TableDefinition] = {}
        self._joins_cache: Optional[List[JoinPath]] = None
        self._all_tables_cache: Optional[List[str]] = None

        # Initialize schema if needed
        self._ensure_schema()

        logger.info(f"SQLiteCatalog initialized with database: {db_path}")

    def _ensure_schema(self):
        """Ensure the database schema exists."""
        schema_file = Path(__file__).parent / "sqlite_schema.sql"
        if schema_file.exists():
            with open(schema_file) as f:
                self.connection.executescript(f.read())
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

    def get_all_tables(self) -> List[str]:
        """
        Get all table names.

        Returns:
            List of table names
        """
        if self._all_tables_cache is not None:
            return self._all_tables_cache

        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT name FROM tables
            WHERE active = TRUE
            ORDER BY name
        """)

        tables = [row["name"] for row in cursor.fetchall()]
        self._all_tables_cache = tables

        logger.debug(f"Retrieved {len(tables)} tables from database")
        return tables

    def get_table(self, table_name: str) -> Optional[TableDefinition]:
        """
        Get table definition by name.

        Args:
            table_name: Name of the table

        Returns:
            TableDefinition object or None if not found
        """
        # Check cache first
        if table_name in self._tables_cache:
            return self._tables_cache[table_name]

        cursor = self.connection.cursor()

        # Query table info
        cursor.execute("""
            SELECT * FROM tables
            WHERE name = ? AND active = TRUE
        """, (table_name,))

        table_row = cursor.fetchone()
        if not table_row:
            logger.warning(f"Table not found: {table_name}")
            return None

        # Query column info
        cursor.execute("""
            SELECT * FROM columns
            WHERE table_id = ?
            ORDER BY name
        """, (table_row["id"],))

        columns = {}
        for col_row in cursor.fetchall():
            columns[col_row["name"]] = ColumnInfo(
                type=col_row["type"],
                description=col_row["description"] or "",
                primary_key=bool(col_row["is_primary_key"]),
                foreign_key=(
                    f"{col_row['foreign_key_table']}.{col_row['foreign_key_column']}"
                    if col_row["is_foreign_key"] else None
                ),
                enum=(
                    json.loads(col_row["enum_values"])
                    if col_row["enum_values"] else None
                ),
            )

        # Build TableDefinition
        table_def = TableDefinition(
            name=table_row["name"],
            description=table_row["description"],
            columns=columns,
            tags=json.loads(table_row["tags"]) if table_row["tags"] else [],
            grain=table_row["grain"] if "grain" in table_row.keys() else None,
            entities=json.loads(table_row["entities"] or "[]") if "entities" in table_row.keys() else [],
        )

        # Cache it
        self._tables_cache[table_name] = table_def

        logger.debug(f"Loaded table definition: {table_name} ({len(columns)} columns)")
        return table_def

    def search_schema(
        self,
        question: str = None,
        required_tables: List[str] = None
    ) -> List[str]:
        """
        Search for relevant tables.

        Args:
            question: Natural language question (optional)
            required_tables: List of required table names (optional)

        Returns:
            List of relevant table names
        """
        cursor = self.connection.cursor()

        if required_tables:
            # Validate that tables exist
            placeholders = ','.join('?' * len(required_tables))
            cursor.execute(f"""
                SELECT name FROM tables
                WHERE name IN ({placeholders}) AND active = TRUE
            """, required_tables)

            found_tables = [row["name"] for row in cursor.fetchall()]
            logger.debug(f"Found {len(found_tables)}/{len(required_tables)} required tables")
            return found_tables

        if question:
            # Keyword-based search (simple implementation)
            # Could be enhanced with embeddings/semantic search
            cursor.execute("""
                SELECT name FROM tables
                WHERE active = TRUE
                    AND (description LIKE ? OR name LIKE ?)
                ORDER BY name
            """, (f"%{question}%", f"%{question}%"))

            found_tables = [row["name"] for row in cursor.fetchall()]
            logger.debug(f"Found {len(found_tables)} tables matching question")
            return found_tables

        # Return all tables if no criteria
        return self.get_all_tables()

    def get_join_paths(self, tables: List[str]) -> List[JoinPath]:
        """
        Get join paths between tables.

        Args:
            tables: List of table names

        Returns:
            List of JoinPath objects
        """
        if not tables:
            return []

        cursor = self.connection.cursor()

        # Query joins involving these tables
        placeholders = ','.join('?' * len(tables))
        cursor.execute(f"""
            SELECT * FROM joins
            WHERE (left_table IN ({placeholders})
                OR right_table IN ({placeholders}))
        """, tables + tables)

        join_paths = []
        for row in cursor.fetchall():
            join_paths.append(JoinPath(
                left_table=row["left_table"],
                left_column=row["left_column"],
                right_table=row["right_table"],
                right_column=row["right_column"],
                join_type=row["join_type"] or "INNER",
                cardinality=row["cardinality"] or "",
                description=row["description"] or "",
                name=row["name"] if "name" in row.keys() else None,
                auto_join=bool(row["auto_join"]) if "auto_join" in row.keys() else True,
                priority=row["priority"] if "priority" in row.keys() and row["priority"] is not None else 100,
                fan_out_risk=bool(row["fan_out_risk"]) if "fan_out_risk" in row.keys() else False,
                temporal_validity=row["temporal_validity"] if "temporal_validity" in row.keys() else None,
            ))

        logger.debug(f"Found {len(join_paths)} join paths for {len(tables)} tables")
        return join_paths

    def find_join_path(
        self,
        from_table: str,
        to_table: str
    ) -> List[JoinPath]:
        """
        Find the shortest join path between two tables using BFS.

        Args:
            from_table: Starting table name
            to_table: Target table name

        Returns:
            List of JoinPath objects representing the path
        """
        if from_table == to_table:
            return []

        # Load all joins if not cached
        if self._joins_cache is None:
            cursor = self.connection.cursor()
            cursor.execute("SELECT * FROM joins")

            self._joins_cache = [
                JoinPath(
                    left_table=row["left_table"],
                    left_column=row["left_column"],
                    right_table=row["right_table"],
                    right_column=row["right_column"],
                    join_type=row["join_type"] or "INNER",
                    cardinality=row["cardinality"] or "",
                    description=row["description"] or "",
                    name=row["name"] if "name" in row.keys() else None,
                    auto_join=bool(row["auto_join"]) if "auto_join" in row.keys() else True,
                    priority=row["priority"] if "priority" in row.keys() and row["priority"] is not None else 100,
                    fan_out_risk=bool(row["fan_out_risk"]) if "fan_out_risk" in row.keys() else False,
                    temporal_validity=row["temporal_validity"] if "temporal_validity" in row.keys() else None,
                )
                for row in cursor.fetchall()
            ]

        # BFS to find shortest path
        path = self._bfs_join_path(from_table, to_table, self._joins_cache)

        if path:
            logger.debug(f"Found join path: {from_table} -> {to_table} ({len(path)} hops)")
        else:
            logger.warning(f"No join path found: {from_table} -> {to_table}")

        return path

    def _bfs_join_path(
        self,
        from_table: str,
        to_table: str,
        all_joins: List[JoinPath]
    ) -> List[JoinPath]:
        """
        BFS algorithm to find shortest join path.

        Args:
            from_table: Starting table
            to_table: Target table
            all_joins: All available joins

        Returns:
            List of JoinPath objects or empty list if no path found
        """
        from collections import deque

        # Build adjacency graph
        graph: Dict[str, List[tuple]] = {}
        for join in all_joins:
            if join.left_table not in graph:
                graph[join.left_table] = []
            if join.right_table not in graph:
                graph[join.right_table] = []

            graph[join.left_table].append((join.right_table, join))
            graph[join.right_table].append((join.left_table, join))

        if from_table not in graph or to_table not in graph:
            return []

        # BFS
        queue = deque([(from_table, [])])
        visited = {from_table}

        while queue:
            current_table, path = queue.popleft()

            if current_table == to_table:
                return path

            for next_table, join in graph.get(current_table, []):
                if next_table not in visited:
                    visited.add(next_table)
                    queue.append((next_table, path + [join]))

        return []

    def is_valid_join(self, left_table: str, right_table: str) -> bool:
        """
        Check if a join between two tables is valid.

        Args:
            left_table: Left table name
            right_table: Right table name

        Returns:
            True if join exists, False otherwise
        """
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT COUNT(*) as count FROM joins
            WHERE (left_table = ? AND right_table = ?)
                OR (left_table = ? AND right_table = ?)
        """, (left_table, right_table, right_table, left_table))

        count = cursor.fetchone()["count"]
        return count > 0

    def get_ddl_summary(self, table_name: str) -> str:
        """
        Get DDL summary for a table.

        Args:
            table_name: Table name

        Returns:
            DDL-like string representation
        """
        table = self.get_table(table_name)
        if not table:
            return ""

        lines = [f"CREATE TABLE {table.name} ("]

        for col_name, col_info in table.columns.items():
            col_line = f"  {col_name} {col_info.type}"

            if col_info.primary_key:
                col_line += " PRIMARY KEY"
            if col_info.foreign_key:
                col_line += f" REFERENCES {col_info.foreign_key}"
            if col_info.description:
                col_line += f" -- {col_info.description}"

            lines.append(col_line + ",")

        lines[-1] = lines[-1].rstrip(",")
        lines.append(");")

        return "\n".join(lines)

    def clear_cache(self):
        """Clear all internal caches."""
        self._tables_cache.clear()
        self._joins_cache = None
        self._all_tables_cache = None
        logger.debug("Cleared all caches")

    def close(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()
            logger.info("Database connection closed")


def create_catalog_from_yaml(config_dir: Path, db_path: str) -> SQLiteCatalog:
    """
    Create a SQLite catalog and populate it from YAML files.

    This is a convenience function for migrating from YAML to SQLite.

    Args:
        config_dir: Path to YAML config directory
        db_path: Path to SQLite database file

    Returns:
        Initialized SQLiteCatalog
    """
    from .yaml_to_sqlite import migrate_yaml_to_sqlite

    # Perform migration
    migrate_yaml_to_sqlite(config_dir, db_path)

    # Return catalog
    return SQLiteCatalog(db_path)
