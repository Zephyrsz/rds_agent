"""
DuckDB Adapter for RDS Agent
"""

from typing import Optional, Any
import duckdb
from pathlib import Path


class DuckDBAdapter:
    """
    DuckDB 数据库适配器

    提供与 DuckDB 的连接和基本操作
    """

    def __init__(self, database: Optional[str] = None, read_only: bool = False):
        """
        初始化 DuckDB 适配器

        Args:
            database: 数据库文件路径（None 表示内存数据库）
            read_only: 是否只读模式
        """
        self.database = database
        self.read_only = read_only
        self.connection = None

    def connect(self) -> duckdb.DuckDBPyConnection:
        """建立数据库连接"""
        if self.connection is None:
            self.connection = duckdb.connect(
                database=self.database,
                read_only=self.read_only
            )
        return self.connection

    def close(self):
        """关闭数据库连接"""
        if self.connection:
            self.connection.close()
            self.connection = None

    def execute(self, sql: str, params: Optional[tuple] = None) -> Any:
        """
        执行 SQL 语句

        Args:
            sql: SQL 语句
            params: 参数

        Returns:
            查询结果
        """
        conn = self.connect()
        if params:
            return conn.execute(sql, params)
        return conn.execute(sql)

    def cursor(self):
        """获取游标"""
        conn = self.connect()
        return conn.cursor()

    def __enter__(self):
        """上下文管理器入口"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.close()


def create_sample_database(db_path: str = ":memory:") -> DuckDBAdapter:
    """
    创建示例数据库

    创建一个包含示例数据的 DuckDB 数据库，用于测试

    Schema:
    - customers: 客户表
    - regions: 地区表
    - products: 产品表
    - orders: 订单表
    - order_items: 订单明细表
    """
    adapter = DuckDBAdapter(database=db_path)
    conn = adapter.connect()

    # 创建地区表
    conn.execute("""
        CREATE TABLE regions (
            id INTEGER PRIMARY KEY,
            region_name VARCHAR,
            region_code VARCHAR
        )
    """)

    # 插入地区数据
    conn.execute("""
        INSERT INTO regions VALUES
        (1, '华东', 'EAST_CHINA'),
        (2, '华北', 'NORTH_CHINA'),
        (3, '华南', 'SOUTH_CHINA'),
        (4, '西南', 'SOUTHWEST_CHINA')
    """)

    # 创建客户表
    conn.execute("""
        CREATE TABLE customers (
            id INTEGER PRIMARY KEY,
            name VARCHAR,
            region_id INTEGER,
            created_at TIMESTAMP
        )
    """)

    # 插入客户数据
    conn.execute("""
        INSERT INTO customers VALUES
        (1, '客户A', 1, '2024-01-15 10:00:00'),
        (2, '客户B', 1, '2024-02-20 11:30:00'),
        (3, '客户C', 2, '2024-03-10 09:15:00'),
        (4, '客户D', 3, '2024-04-05 14:20:00'),
        (5, '客户E', 2, '2024-05-12 16:45:00')
    """)

    # 创建产品表
    conn.execute("""
        CREATE TABLE products (
            id INTEGER PRIMARY KEY,
            name VARCHAR,
            category VARCHAR,
            price DECIMAL(10, 2)
        )
    """)

    # 插入产品数据
    conn.execute("""
        INSERT INTO products VALUES
        (1, '产品X', '电子产品', 999.00),
        (2, '产品Y', '电子产品', 1999.00),
        (3, '产品Z', '家居用品', 299.00),
        (4, '产品W', '服装', 199.00),
        (5, '产品V', '食品', 99.00)
    """)

    # 创建订单表
    conn.execute("""
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY,
            customer_id INTEGER,
            status VARCHAR,
            order_date TIMESTAMP,
            paid_at TIMESTAMP
        )
    """)

    # 插入订单数据（最近6个月）
    conn.execute("""
        INSERT INTO orders VALUES
        (1, 1, 'completed', '2024-06-01 10:00:00', '2024-06-01 10:30:00'),
        (2, 1, 'completed', '2024-06-15 14:20:00', '2024-06-15 14:50:00'),
        (3, 2, 'completed', '2024-07-03 09:15:00', '2024-07-03 09:45:00'),
        (4, 3, 'completed', '2024-07-20 16:30:00', '2024-07-20 17:00:00'),
        (5, 2, 'paid', '2024-08-05 11:00:00', '2024-08-05 11:30:00'),
        (6, 4, 'completed', '2024-08-18 13:40:00', '2024-08-18 14:10:00'),
        (7, 5, 'cancelled', '2024-08-25 10:20:00', NULL),
        (8, 1, 'completed', '2024-09-01 15:00:00', '2024-09-01 15:30:00'),
        (9, 3, 'paid', '2024-09-10 12:10:00', '2024-09-10 12:40:00'),
        (10, 2, 'completed', '2024-09-15 09:30:00', '2024-09-15 10:00:00')
    """)

    # 创建订单明细表
    conn.execute("""
        CREATE TABLE order_items (
            id INTEGER PRIMARY KEY,
            order_id INTEGER,
            product_id INTEGER,
            quantity INTEGER,
            unit_price DECIMAL(10, 2),
            net_amount DECIMAL(10, 2)
        )
    """)

    # 插入订单明细数据
    conn.execute("""
        INSERT INTO order_items VALUES
        (1, 1, 1, 2, 999.00, 1998.00),
        (2, 1, 3, 1, 299.00, 299.00),
        (3, 2, 2, 1, 1999.00, 1999.00),
        (4, 3, 4, 3, 199.00, 597.00),
        (5, 3, 5, 2, 99.00, 198.00),
        (6, 4, 1, 1, 999.00, 999.00),
        (7, 5, 3, 2, 299.00, 598.00),
        (8, 6, 2, 1, 1999.00, 1999.00),
        (9, 7, 4, 1, 199.00, 199.00),
        (10, 8, 5, 5, 99.00, 495.00),
        (11, 8, 1, 1, 999.00, 999.00),
        (12, 9, 3, 1, 299.00, 299.00),
        (13, 10, 2, 1, 1999.00, 1999.00),
        (14, 10, 4, 2, 199.00, 398.00)
    """)

    print("✓ 示例数据库创建完成")
    print(f"  - 地区: 4 条记录")
    print(f"  - 客户: 5 条记录")
    print(f"  - 产品: 5 条记录")
    print(f"  - 订单: 10 条记录")
    print(f"  - 订单明细: 14 条记录")

    return adapter


if __name__ == "__main__":
    # 测试创建示例数据库
    adapter = create_sample_database()

    # 测试查询
    result = adapter.execute("SELECT COUNT(*) as count FROM orders WHERE status = 'completed'")
    print(f"\n已完成订单数: {result.fetchone()[0]}")

    # 测试统计查询
    result = adapter.execute("""
        SELECT
            SUM(oi.net_amount) as total_sales,
            COUNT(DISTINCT o.id) as order_count
        FROM orders o
        JOIN order_items oi ON o.id = oi.order_id
        WHERE o.status IN ('paid', 'completed')
    """)
    row = result.fetchone()
    print(f"总销售额: {row[0]}, 订单数: {row[1]}")

    adapter.close()
