"""
Test suite for SQLGuard
"""

import pytest
from core.guard import SQLGuard, SQLValidationError


@pytest.fixture
def guard():
    """创建 SQLGuard 实例"""
    return SQLGuard(
        allowed_tables={'orders', 'customers', 'products'},
        denied_tables={'users', 'credentials'},
        sensitive_columns={'customers': ['phone', 'email']},
        max_result_rows=10000,
        default_limit=1000,
        enforce_limit=True,
    )


def test_valid_select(guard):
    """测试有效的 SELECT 查询"""
    sql = "SELECT * FROM orders WHERE id = 1 LIMIT 100"
    is_valid, error = guard.validate_sql(sql)
    assert is_valid
    assert error is None


def test_forbidden_insert(guard):
    """测试禁止的 INSERT 操作"""
    sql = "INSERT INTO orders VALUES (1, 'test')"
    is_valid, error = guard.validate_sql(sql)
    assert not is_valid
    assert "INSERT" in error or "forbidden" in error.lower()


def test_forbidden_delete(guard):
    """测试禁止的 DELETE 操作"""
    sql = "DELETE FROM orders WHERE id = 1"
    is_valid, error = guard.validate_sql(sql)
    assert not is_valid
    assert "DELETE" in error or "forbidden" in error.lower()


def test_forbidden_table(guard):
    """测试禁止访问的表"""
    sql = "SELECT * FROM users LIMIT 100"
    is_valid, error = guard.validate_sql(sql)
    assert not is_valid
    assert "users" in error.lower() or "forbidden" in error.lower()


def test_missing_limit(guard):
    """测试缺少 LIMIT"""
    sql = "SELECT * FROM orders"
    is_valid, error = guard.validate_sql(sql)
    assert not is_valid
    assert "limit" in error.lower()


def test_add_limit_if_missing(guard):
    """测试自动添加 LIMIT"""
    sql = "SELECT * FROM orders"
    sql_with_limit = guard.add_limit_if_missing(sql)
    assert "LIMIT" in sql_with_limit.upper()
    assert "1000" in sql_with_limit


def test_estimate_cost(guard):
    """测试成本估算"""
    # 简单查询
    sql = "SELECT * FROM orders WHERE id = 1 LIMIT 10"
    cost = guard.estimate_cost(sql)
    assert cost["cost_level"] == "low"

    # 复杂查询（多个 JOIN）
    sql = """
    SELECT * FROM orders o
    JOIN customers c ON o.customer_id = c.id
    JOIN products p ON o.product_id = p.id
    LIMIT 100
    """
    cost = guard.estimate_cost(sql)
    assert cost["cost_score"] > 0


def test_multiple_statements(guard):
    """测试多条语句"""
    sql = "SELECT * FROM orders LIMIT 10; DROP TABLE orders;"
    is_valid, error = guard.validate_sql(sql)
    assert not is_valid


def test_comment_removal(guard):
    """测试注释移除"""
    sql = """
    SELECT * FROM orders -- this is a comment
    WHERE id = 1 LIMIT 100
    """
    is_valid, error = guard.validate_sql(sql)
    assert is_valid  # 应该能通过验证


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
