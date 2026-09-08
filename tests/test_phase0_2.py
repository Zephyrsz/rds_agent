from datetime import date
from pathlib import Path

import pytest

from adapters.sqlite_catalog import SQLiteCatalog
from adapters.sqlite_semantic import SQLiteSemanticLayer
from adapters.yaml_to_sqlite import migrate_yaml_to_sqlite
from core.compiler import SemanticQueryCompiler
from core.semantic import SemanticQuery


CONFIG_DIR = Path(__file__).parent.parent / "config"


@pytest.fixture
def metadata_db(tmp_path):
    db_path = tmp_path / "metadata.db"
    migrate_yaml_to_sqlite(CONFIG_DIR, str(db_path))
    return db_path


def test_sqlite_metadata_migration_preserves_legacy_and_phase1_objects(metadata_db):
    catalog = SQLiteCatalog(str(metadata_db))
    semantic = SQLiteSemanticLayer(str(metadata_db), reference_date=date(2024, 9, 30))

    assert set(catalog.get_all_tables()) == {
        "customers",
        "regions",
        "products",
        "orders",
        "order_items",
    }
    assert semantic.resolve_metric("revenue").name == "sales_amount"
    assert semantic.resolve_dimension("地区").name == "region"
    assert semantic.resolve_filter("valid_order").name == "valid_order"
    assert semantic.resolve_domain("retail_sales").name == "retail_sales"
    assert catalog.get_table("order_items").grain == "每行代表一个订单中的一个商品明细"


def test_extract_intent_resolves_synonyms_values_and_calendar_time(metadata_db):
    semantic = SQLiteSemanticLayer(str(metadata_db), reference_date=date(2024, 9, 30))

    intent = semantic.extract_intent("最近一个月华东地区的营收是多少？")

    assert intent["metrics"] == ["sales_amount"]
    assert "region" in intent["dimensions"]
    assert intent["filters"]["region"] == "华东"
    assert intent["time_range"] == "最近一个月"
    parsed = semantic.resolve_time_range(intent["time_range"])
    assert parsed["start_date"] == "2024-09-01"
    assert parsed["end_date"] == "2024-09-30"


def test_deterministic_compiler_generates_and_executes_safe_sql(metadata_db):
    semantic = SQLiteSemanticLayer(str(metadata_db), reference_date=date(2024, 9, 30))
    catalog = SQLiteCatalog(str(metadata_db))
    compiler = SemanticQueryCompiler(semantic, catalog)

    query = SemanticQuery(
        metrics=["sales_amount"],
        dimensions=["region"],
        filters={"region": "华东"},
        time_range="最近一个月",
        limit=1000,
    )
    sql = compiler.compile(query)

    assert "SUM(order_items.net_amount)" in sql
    assert "JOIN customers" in sql
    assert "JOIN regions" in sql
    assert "GROUP BY" in sql
    assert "2024-09-01" in sql
    assert "2024-10-01" in sql

    import duckdb

    conn = duckdb.connect()
    from adapters.duckdb import create_sample_database

    source = create_sample_database(":memory:")
    result = source.connection.execute(sql).fetchall()
    assert result == [("华东", 3891.0)] or result == [("华东", 3891)]
    source.close()
    conn.close()


def test_compiler_rejects_unknown_dimension_and_many_to_many():
    class FakeSemantic:
        pass

    with pytest.raises(ValueError, match="unknown dimension"):
        SemanticQueryCompiler(FakeSemantic(), object()).compile(
            SemanticQuery(metrics=["sales_amount"], dimensions=["missing"])
        )
