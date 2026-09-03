"""
YAML to SQLite Migration Tool

This module provides functionality to migrate RDS Agent metadata
from YAML files to SQLite database.
"""

import sqlite3
import yaml
import json
from pathlib import Path
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


def migrate_yaml_to_sqlite(config_dir: Path, db_path: str):
    """
    Migrate all YAML configuration to SQLite database.

    Args:
        config_dir: Path to directory containing YAML files
        db_path: Path to SQLite database file (will be created if doesn't exist)
    """
    config_dir = Path(config_dir)

    logger.info(f"Starting migration from {config_dir} to {db_path}")

    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 1. Initialize schema
        _init_schema(cursor)

        # 2. Migrate schema.yaml (tables, columns, joins)
        schema_file = config_dir / "schema.yaml"
        if schema_file.exists():
            logger.info("Migrating schema.yaml...")
            _migrate_schema(cursor, schema_file)

        # 3. Migrate metrics.yaml
        metrics_file = config_dir / "metrics.yaml"
        if metrics_file.exists():
            logger.info("Migrating metrics.yaml...")
            _migrate_metrics(cursor, metrics_file)

        # 4. Migrate dimensions.yaml
        dimensions_file = config_dir / "dimensions.yaml"
        if dimensions_file.exists():
            logger.info("Migrating dimensions.yaml...")
            _migrate_dimensions(cursor, dimensions_file)

        # 5. Migrate terms.yaml
        terms_file = config_dir / "terms.yaml"
        if terms_file.exists():
            logger.info("Migrating terms.yaml...")
            _migrate_terms(cursor, terms_file)

        # 6. Migrate examples.yaml
        examples_file = config_dir / "examples.yaml"
        if examples_file.exists():
            logger.info("Migrating examples.yaml...")
            _migrate_examples(cursor, examples_file)

        # Commit all changes
        conn.commit()
        logger.info(f"✓ Migration completed successfully: {db_path}")

    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed: {e}")
        raise
    finally:
        conn.close()


def _init_schema(cursor: sqlite3.Cursor):
    """Initialize database schema."""
    schema_sql_path = Path(__file__).parent / "sqlite_schema.sql"

    if schema_sql_path.exists():
        with open(schema_sql_path) as f:
            cursor.executescript(f.read())
        logger.debug("Database schema initialized")
    else:
        logger.warning(f"Schema file not found: {schema_sql_path}")


def _migrate_schema(cursor: sqlite3.Cursor, schema_file: Path):
    """Migrate schema.yaml to SQLite."""
    with open(schema_file) as f:
        schema_data = yaml.safe_load(f)

    if not schema_data:
        logger.warning("Empty schema.yaml")
        return

    # Migrate tables and columns
    tables_data = schema_data.get("tables", {})
    for table_name, table_config in tables_data.items():
        # Insert table
        cursor.execute("""
            INSERT OR REPLACE INTO tables (name, description, tags)
            VALUES (?, ?, ?)
        """, (
            table_name,
            table_config.get("description", ""),
            json.dumps(table_config.get("tags", []))
        ))

        table_id = cursor.lastrowid

        # Insert columns
        columns = table_config.get("columns", {})
        for col_name, col_config in columns.items():
            foreign_key = col_config.get("foreign_key", "")
            fk_table = foreign_key.split(".")[0] if "." in foreign_key else None
            fk_column = foreign_key.split(".")[1] if "." in foreign_key else None

            cursor.execute("""
                INSERT OR REPLACE INTO columns (
                    table_id, name, type, description,
                    is_primary_key, is_foreign_key,
                    foreign_key_table, foreign_key_column,
                    enum_values
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                table_id,
                col_name,
                col_config.get("type", "TEXT"),
                col_config.get("description", ""),
                col_config.get("primary_key", False),
                bool(foreign_key),
                fk_table,
                fk_column,
                json.dumps(col_config.get("enum", [])) if "enum" in col_config else None
            ))

        logger.debug(f"  Migrated table: {table_name} ({len(columns)} columns)")

    # Migrate joins
    joins_data = schema_data.get("joins", [])
    for join in joins_data:
        left_parts = join["left"].split(".")
        right_parts = join["right"].split(".")

        cursor.execute("""
            INSERT OR REPLACE INTO joins (
                left_table, left_column,
                right_table, right_column,
                join_type, cardinality, description
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            left_parts[0],
            left_parts[1],
            right_parts[0],
            right_parts[1],
            "INNER",
            join.get("cardinality", ""),
            join.get("description", "")
        ))

    logger.debug(f"  Migrated {len(joins_data)} joins")


def _migrate_metrics(cursor: sqlite3.Cursor, metrics_file: Path):
    """Migrate metrics.yaml to SQLite."""
    with open(metrics_file) as f:
        metrics_data = yaml.safe_load(f)

    if not metrics_data:
        logger.warning("Empty metrics.yaml")
        return

    metrics = metrics_data.get("metrics", {})
    for metric_name, metric_config in metrics.items():
        cursor.execute("""
            INSERT OR REPLACE INTO metrics (
                name, display_name, description,
                expression, tables, filters,
                time_column, unit, data_type,
                min_value, max_value, category
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            metric_name,
            metric_config.get("name", metric_name),
            metric_config.get("description", ""),
            metric_config.get("expression", ""),
            json.dumps(metric_config.get("tables", [])),
            json.dumps(metric_config.get("filters", [])),
            metric_config.get("time_column"),
            metric_config.get("unit", ""),
            metric_config.get("data_type", "DECIMAL"),
            metric_config.get("min_value"),
            metric_config.get("max_value"),
            metric_config.get("category", "")
        ))

    logger.debug(f"  Migrated {len(metrics)} metrics")


def _migrate_dimensions(cursor: sqlite3.Cursor, dimensions_file: Path):
    """Migrate dimensions.yaml to SQLite."""
    with open(dimensions_file) as f:
        dimensions_data = yaml.safe_load(f)

    if not dimensions_data:
        logger.warning("Empty dimensions.yaml")
        return

    dimensions = dimensions_data.get("dimensions", {})
    for dim_name, dim_config in dimensions.items():
        cursor.execute("""
            INSERT OR REPLACE INTO dimensions (
                name, display_name,
                table_name, column_name,
                mappings, category
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            dim_name,
            dim_config.get("name", dim_name),
            dim_config.get("table", ""),
            dim_config.get("column", ""),
            json.dumps(dim_config.get("mappings", {})),
            dim_config.get("category", "")
        ))

    logger.debug(f"  Migrated {len(dimensions)} dimensions")


def _migrate_terms(cursor: sqlite3.Cursor, terms_file: Path):
    """Migrate terms.yaml to SQLite."""
    with open(terms_file) as f:
        terms_data = yaml.safe_load(f)

    if not terms_data:
        logger.warning("Empty terms.yaml")
        return

    terms = terms_data.get("terms", {})
    for term, synonyms in terms.items():
        if isinstance(synonyms, list):
            cursor.execute("""
                INSERT OR REPLACE INTO terms (
                    term, synonyms, category, description
                )
                VALUES (?, ?, ?, ?)
            """, (
                term,
                json.dumps(synonyms),
                "",
                ""
            ))

    logger.debug(f"  Migrated {len(terms)} terms")


def _migrate_examples(cursor: sqlite3.Cursor, examples_file: Path):
    """Migrate examples.yaml to SQLite."""
    with open(examples_file) as f:
        examples_data = yaml.safe_load(f)

    if not examples_data:
        logger.warning("Empty examples.yaml")
        return

    examples = examples_data.get("examples", [])
    for example in examples:
        cursor.execute("""
            INSERT OR REPLACE INTO examples (
                question, sql, question_type, tags, description
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            example.get("question", ""),
            example.get("sql", ""),
            example.get("type", ""),
            json.dumps(example.get("tags", [])),
            example.get("description", "")
        ))

    logger.debug(f"  Migrated {len(examples)} examples")


def export_sqlite_to_yaml(db_path: str, output_dir: Path):
    """
    Export SQLite database back to YAML files.

    This is useful for version control and manual editing.

    Args:
        db_path: Path to SQLite database
        output_dir: Directory to write YAML files
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    logger.info(f"Exporting SQLite to YAML in {output_dir}")

    try:
        # Export schema
        _export_schema(cursor, output_dir / "schema.yaml")

        # Export metrics
        _export_metrics(cursor, output_dir / "metrics.yaml")

        # Export dimensions
        _export_dimensions(cursor, output_dir / "dimensions.yaml")

        # Export terms
        _export_terms(cursor, output_dir / "terms.yaml")

        # Export examples
        _export_examples(cursor, output_dir / "examples.yaml")

        logger.info("✓ Export completed successfully")

    finally:
        conn.close()


def _export_schema(cursor: sqlite3.Cursor, output_file: Path):
    """Export tables, columns, and joins to schema.yaml."""
    schema_data = {"tables": {}, "joins": []}

    # Export tables and columns
    cursor.execute("SELECT * FROM tables WHERE active = TRUE")
    for table_row in cursor.fetchall():
        table_name = table_row["name"]

        # Get columns
        cursor.execute("SELECT * FROM columns WHERE table_id = ?", (table_row["id"],))
        columns = {}
        for col_row in cursor.fetchall():
            col_data = {
                "type": col_row["type"],
                "description": col_row["description"]
            }

            if col_row["is_primary_key"]:
                col_data["primary_key"] = True

            if col_row["is_foreign_key"]:
                col_data["foreign_key"] = f"{col_row['foreign_key_table']}.{col_row['foreign_key_column']}"

            if col_row["enum_values"]:
                col_data["enum"] = json.loads(col_row["enum_values"])

            columns[col_row["name"]] = col_data

        schema_data["tables"][table_name] = {
            "description": table_row["description"],
            "columns": columns,
            "tags": json.loads(table_row["tags"]) if table_row["tags"] else []
        }

    # Export joins
    cursor.execute("SELECT * FROM joins")
    for join_row in cursor.fetchall():
        schema_data["joins"].append({
            "left": f"{join_row['left_table']}.{join_row['left_column']}",
            "right": f"{join_row['right_table']}.{join_row['right_column']}",
            "cardinality": join_row["cardinality"],
            "description": join_row["description"]
        })

    with open(output_file, 'w') as f:
        yaml.dump(schema_data, f, default_flow_style=False, allow_unicode=True)

    logger.debug(f"Exported schema to {output_file}")


def _export_metrics(cursor: sqlite3.Cursor, output_file: Path):
    """Export metrics to metrics.yaml."""
    metrics_data = {"metrics": {}}

    cursor.execute("SELECT * FROM metrics WHERE active = TRUE")
    for row in cursor.fetchall():
        metrics_data["metrics"][row["name"]] = {
            "name": row["display_name"],
            "description": row["description"],
            "expression": row["expression"],
            "tables": json.loads(row["tables"]),
            "filters": json.loads(row["filters"]) if row["filters"] else [],
            "time_column": row["time_column"],
            "unit": row["unit"],
            "data_type": row["data_type"],
            "min_value": row["min_value"],
            "max_value": row["max_value"],
            "category": row["category"]
        }

    with open(output_file, 'w') as f:
        yaml.dump(metrics_data, f, default_flow_style=False, allow_unicode=True)

    logger.debug(f"Exported metrics to {output_file}")


def _export_dimensions(cursor: sqlite3.Cursor, output_file: Path):
    """Export dimensions to dimensions.yaml."""
    dimensions_data = {"dimensions": {}}

    cursor.execute("SELECT * FROM dimensions WHERE active = TRUE")
    for row in cursor.fetchall():
        dimensions_data["dimensions"][row["name"]] = {
            "name": row["display_name"],
            "table": row["table_name"],
            "column": row["column_name"],
            "mappings": json.loads(row["mappings"]) if row["mappings"] else {},
            "category": row["category"]
        }

    with open(output_file, 'w') as f:
        yaml.dump(dimensions_data, f, default_flow_style=False, allow_unicode=True)

    logger.debug(f"Exported dimensions to {output_file}")


def _export_terms(cursor: sqlite3.Cursor, output_file: Path):
    """Export terms to terms.yaml."""
    terms_data = {"terms": {}}

    cursor.execute("SELECT * FROM terms WHERE active = TRUE")
    for row in cursor.fetchall():
        terms_data["terms"][row["term"]] = json.loads(row["synonyms"])

    with open(output_file, 'w') as f:
        yaml.dump(terms_data, f, default_flow_style=False, allow_unicode=True)

    logger.debug(f"Exported terms to {output_file}")


def _export_examples(cursor: sqlite3.Cursor, output_file: Path):
    """Export examples to examples.yaml."""
    examples_data = {"examples": []}

    cursor.execute("SELECT * FROM examples WHERE active = TRUE")
    for row in cursor.fetchall():
        examples_data["examples"].append({
            "question": row["question"],
            "sql": row["sql"],
            "type": row["question_type"],
            "tags": json.loads(row["tags"]) if row["tags"] else [],
            "description": row["description"]
        })

    with open(output_file, 'w') as f:
        yaml.dump(examples_data, f, default_flow_style=False, allow_unicode=True)

    logger.debug(f"Exported examples to {output_file}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python yaml_to_sqlite.py <config_dir> <db_path>")
        sys.exit(1)

    config_dir = Path(sys.argv[1])
    db_path = sys.argv[2]

    logging.basicConfig(level=logging.INFO)
    migrate_yaml_to_sqlite(config_dir, db_path)
