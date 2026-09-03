"""
Example: Using SQLite Adapter in RDS Agent Workflow

This example demonstrates how to use the SQLite adapter in a complete
RDS Agent workflow, showing migration and usage.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from adapters.factory import create_catalog, create_semantic_layer, migrate_to_sqlite
from core import QueryPlanner, SQLGenerator, SQLGuard, QueryExecutor
from langchain_openai import ChatOpenAI
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def example_1_migration():
    """Example 1: Migrate from YAML to SQLite."""
    print("=" * 80)
    print("Example 1: Migration from YAML to SQLite")
    print("=" * 80)
    print()

    config_dir = Path(__file__).parent.parent / "config"
    db_path = "metadata.db"

    if not config_dir.exists():
        print(f"⚠️  Config directory not found: {config_dir}")
        print("This example requires config/ directory with YAML files")
        return

    print(f"Migrating from {config_dir} to {db_path}...")

    try:
        catalog, semantic = migrate_to_sqlite(
            yaml_config_dir=config_dir,
            sqlite_db_path=db_path,
            export_back=False
        )

        print(f"✓ Migration completed successfully")
        print(f"  Database: {db_path}")
        print(f"  Tables: {len(catalog.get_all_tables())}")
        print(f"  Metrics: {len(semantic.get_all_metrics())}")
        print(f"  Dimensions: {len(semantic.get_all_dimensions())}")
        print()

    except Exception as e:
        print(f"✗ Migration failed: {e}")
        print()


def example_2_basic_usage():
    """Example 2: Basic usage with factory methods."""
    print("=" * 80)
    print("Example 2: Basic Usage with Factory Methods")
    print("=" * 80)
    print()

    # Try SQLite first, fallback to YAML
    try:
        catalog = create_catalog("metadata.db")
        semantic = create_semantic_layer("metadata.db")
        mode = "SQLite"
    except:
        config_dir = Path(__file__).parent.parent / "config"
        catalog = create_catalog(config_dir)
        semantic = create_semantic_layer(config_dir)
        mode = "YAML"

    print(f"Mode: {mode}")
    print()

    # Get all tables
    print("Tables:")
    tables = catalog.get_all_tables()
    for i, table in enumerate(tables[:5], 1):
        print(f"  {i}. {table}")
    if len(tables) > 5:
        print(f"  ... and {len(tables) - 5} more")
    print()

    # Get all metrics
    print("Metrics:")
    metrics = semantic.get_all_metrics()
    for i, metric in enumerate(metrics, 1):
        print(f"  {i}. {metric.name} - {metric.display_name}")
    print()

    # Get all dimensions
    print("Dimensions:")
    dimensions = semantic.get_all_dimensions()
    for i, dim in enumerate(dimensions, 1):
        print(f"  {i}. {dim.name} - {dim.display_name}")
    print()


def example_3_query_workflow():
    """Example 3: Complete query workflow with SQLite."""
    print("=" * 80)
    print("Example 3: Complete Query Workflow")
    print("=" * 80)
    print()

    # Initialize components
    try:
        catalog = create_catalog("metadata.db")
        semantic = create_semantic_layer("metadata.db")
        mode = "SQLite"
    except:
        config_dir = Path(__file__).parent.parent / "config"
        catalog = create_catalog(config_dir)
        semantic = create_semantic_layer(config_dir)
        mode = "YAML"

    print(f"Using {mode} mode")
    print()

    # Simulate a query workflow
    question = "最近一个月的销售额是多少？"
    print(f"Question: {question}")
    print()

    # Step 1: Resolve metric
    print("Step 1: Resolve metric...")
    metrics = semantic.get_all_metrics()
    if metrics:
        metric = metrics[0]  # Use first metric for demo
        print(f"  Metric: {metric.name}")
        print(f"  Display: {metric.display_name}")
        print(f"  Expression: {metric.expression}")
        print(f"  Tables: {metric.tables}")
        print()
    else:
        print("  No metrics found")
        return

    # Step 2: Resolve dimension
    print("Step 2: Resolve dimension...")
    dimensions = semantic.get_all_dimensions()
    if dimensions:
        dimension = dimensions[0]  # Use first dimension for demo
        print(f"  Dimension: {dimension.name}")
        print(f"  Table: {dimension.table}")
        print(f"  Column: {dimension.column}")
        print()
    else:
        print("  No dimensions found")

    # Step 3: Resolve time range
    print("Step 3: Resolve time range...")
    time_range = semantic.resolve_time_range("最近一个月")
    print(f"  Start: {time_range['start_date']}")
    print(f"  End: {time_range['end_date']}")
    print()

    # Step 4: Get schema
    print("Step 4: Get schema...")
    if metric.tables:
        table_name = metric.tables[0]
        table_def = catalog.get_table(table_name)
        if table_def:
            print(f"  Table: {table_def.name}")
            print(f"  Columns: {len(table_def.columns)}")
            print(f"  Sample columns: {list(table_def.columns.keys())[:3]}")
            print()

    # Step 5: Get join paths
    print("Step 5: Get join paths...")
    if len(metric.tables) > 1:
        joins = catalog.get_join_paths(metric.tables)
        print(f"  Joins found: {len(joins)}")
        for join in joins[:2]:
            print(f"    {join.left_table}.{join.left_column} -> "
                  f"{join.right_table}.{join.right_column}")
        print()
    else:
        print("  No joins needed (single table)")
        print()

    # Step 6: Get examples
    print("Step 6: Get examples...")
    examples = semantic.get_examples(limit=2)
    print(f"  Examples found: {len(examples)}")
    for i, example in enumerate(examples, 1):
        print(f"    {i}. {example.question[:50]}...")
    print()

    print("✓ Workflow completed successfully")
    print()


def example_4_performance_comparison():
    """Example 4: Performance comparison."""
    print("=" * 80)
    print("Example 4: Performance Comparison")
    print("=" * 80)
    print()

    import time

    # Test YAML mode
    config_dir = Path(__file__).parent.parent / "config"
    if not config_dir.exists():
        print("Config directory not found, skipping comparison")
        return

    print("Testing YAML mode...")
    start = time.time()
    yaml_catalog = create_catalog(config_dir)
    yaml_tables = yaml_catalog.get_all_tables()
    yaml_time = time.time() - start
    print(f"  Time: {yaml_time*1000:.2f} ms")
    print(f"  Tables: {len(yaml_tables)}")
    print()

    # Test SQLite mode
    if Path("metadata.db").exists():
        print("Testing SQLite mode...")
        start = time.time()
        sqlite_catalog = create_catalog("metadata.db")
        sqlite_tables = sqlite_catalog.get_all_tables()
        sqlite_time = time.time() - start
        print(f"  Time: {sqlite_time*1000:.2f} ms")
        print(f"  Tables: {len(sqlite_tables)}")
        print()

        # Comparison
        print("Comparison:")
        speedup = yaml_time / sqlite_time if sqlite_time > 0 else 0
        print(f"  SQLite is {speedup:.1f}x faster for initial load")
        print()
    else:
        print("SQLite database not found, run migration first")
        print()


def example_5_search_capabilities():
    """Example 5: Search capabilities (SQLite only)."""
    print("=" * 80)
    print("Example 5: Search Capabilities (SQLite)")
    print("=" * 80)
    print()

    if not Path("metadata.db").exists():
        print("SQLite database not found, run migration first")
        return

    semantic = create_semantic_layer("metadata.db")

    # Full-text search in examples
    print("Full-text search in examples:")
    results = semantic.search_examples("SELECT", limit=3)
    print(f"  Found {len(results)} examples containing 'SELECT'")
    for i, example in enumerate(results, 1):
        print(f"    {i}. {example.question[:60]}...")
    print()


def example_6_dual_mode_support():
    """Example 6: Dual mode support."""
    print("=" * 80)
    print("Example 6: Dual Mode Support")
    print("=" * 80)
    print()

    print("The same code works with both YAML and SQLite:")
    print()

    # Your application code
    def get_sales_metrics(config_source):
        """Generic function that works with both modes."""
        catalog = create_catalog(config_source)
        semantic = create_semantic_layer(config_source)

        metrics = semantic.get_all_metrics()
        sales_metrics = [m for m in metrics if "sales" in m.name.lower()]

        return sales_metrics

    # Use with YAML
    config_dir = Path(__file__).parent.parent / "config"
    if config_dir.exists():
        print("YAML mode:")
        yaml_metrics = get_sales_metrics(config_dir)
        print(f"  Sales metrics: {len(yaml_metrics)}")
        print()

    # Use with SQLite
    if Path("metadata.db").exists():
        print("SQLite mode:")
        sqlite_metrics = get_sales_metrics("metadata.db")
        print(f"  Sales metrics: {len(sqlite_metrics)}")
        print()

    print("✓ Same code, different backends!")
    print()


def main():
    """Run all examples."""
    print("\n")
    print("=" * 80)
    print("SQLite Adapter Examples for RDS Agent")
    print("=" * 80)
    print()

    examples = [
        ("Migration", example_1_migration),
        ("Basic Usage", example_2_basic_usage),
        ("Query Workflow", example_3_query_workflow),
        ("Performance", example_4_performance_comparison),
        ("Search", example_5_search_capabilities),
        ("Dual Mode", example_6_dual_mode_support),
    ]

    for name, example_func in examples:
        try:
            example_func()
        except Exception as e:
            print(f"✗ Example '{name}' failed: {e}")
            print()

    print("=" * 80)
    print("All examples completed!")
    print("=" * 80)


if __name__ == "__main__":
    main()
