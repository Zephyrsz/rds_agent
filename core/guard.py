"""
SQLGuard: SQL 安全网关

负责 SQL 安全检查和验证
"""

from typing import Dict, List, Optional, Set, Tuple
import re
import sqlparse
from sqlparse.sql import Token, TokenList, Identifier, Function
from sqlparse.tokens import Keyword, DML, DDL


class SQLValidationError(Exception):
    """SQL 验证错误"""

    def __init__(self, message: str, error_type: str, details: Optional[Dict] = None):
        super().__init__(message)
        self.error_type = error_type
        self.details = details or {}


class SQLGuard:
    """
    SQL 安全网关

    负责：
    1. AST 解析（禁止 DML/DDL）
    2. 表和字段白名单检查
    3. 检测笛卡尔积风险
    4. 评估查询成本
    5. 强制 LIMIT 限制
    6. 敏感字段检查
    """

    # 禁止的 SQL 关键词
    FORBIDDEN_KEYWORDS = {
        'INSERT', 'UPDATE', 'DELETE', 'DROP', 'TRUNCATE', 'ALTER',
        'CREATE', 'GRANT', 'REVOKE', 'EXEC', 'EXECUTE', 'CALL',
        'COPY', 'LOAD', 'BACKUP', 'RESTORE', 'SHUTDOWN'
    }

    # 危险函数（系统函数、文件操作等）
    FORBIDDEN_FUNCTIONS = {
        'load_extension', 'read_csv_auto', 'read_parquet',
        'copy', 'export', 'pg_read_file', 'pg_ls_dir',
        'system', 'shell', 'exec'
    }

    # 系统表前缀
    SYSTEM_TABLE_PREFIXES = {
        'pg_', 'information_schema', 'sys', 'mysql',
        'sqlite_', 'duckdb_'
    }

    def __init__(
        self,
        allowed_tables: Optional[Set[str]] = None,
        denied_tables: Optional[Set[str]] = None,
        sensitive_columns: Optional[Dict[str, List[str]]] = None,
        max_result_rows: int = 10000,
        default_limit: int = 1000,
        enforce_limit: bool = True,
    ):
        """
        初始化 SQL 安全网关

        Args:
            allowed_tables: 允许访问的表白名单
            denied_tables: 禁止访问的表黑名单
            sensitive_columns: 敏感字段 {table: [columns]}
            max_result_rows: 最大返回行数
            default_limit: 默认 LIMIT 值
            enforce_limit: 是否强制添加 LIMIT
        """
        self.allowed_tables = allowed_tables or set()
        self.denied_tables = denied_tables or set()
        self.sensitive_columns = sensitive_columns or {}
        self.max_result_rows = max_result_rows
        self.default_limit = default_limit
        self.enforce_limit = enforce_limit

    def validate_sql(self, sql: str, user_context: Optional[Dict] = None) -> Tuple[bool, Optional[str]]:
        """
        验证 SQL 是否安全

        Returns:
            (is_valid, error_message)
        """
        try:
            # 1. 基本格式检查
            if not sql or not sql.strip():
                raise SQLValidationError("SQL 不能为空", "empty_sql")

            # 移除注释（防止通过注释绕过检查）
            sql_cleaned = self._remove_comments(sql)

            # 2. 检查是否包含多条语句
            if self._has_multiple_statements(sql_cleaned):
                raise SQLValidationError(
                    "不允许执行多条 SQL 语句",
                    "multiple_statements"
                )

            # 3. 解析 SQL
            parsed = sqlparse.parse(sql_cleaned)
            if not parsed:
                raise SQLValidationError("SQL 解析失败", "parse_error")

            statement = parsed[0]

            # 4. 检查语句类型（只允许 SELECT）
            self._check_statement_type(statement)

            # 5. 检查禁用关键词
            self._check_forbidden_keywords(statement)

            # 6. 检查表访问权限
            tables = self._extract_tables(statement)
            self._check_table_permissions(tables)

            # 7. 检查敏感字段
            columns = self._extract_columns(statement)
            self._check_sensitive_columns(tables, columns)

            # 8. 检查危险函数
            self._check_forbidden_functions(statement)

            # 9. 检查笛卡尔积风险
            self._check_cartesian_product(statement, tables)

            # 10. 检查 LIMIT
            if self.enforce_limit:
                self._check_limit(statement)

            return True, None

        except SQLValidationError as e:
            return False, f"{e.error_type}: {str(e)}"
        except Exception as e:
            return False, f"validation_error: {str(e)}"

    def _remove_comments(self, sql: str) -> str:
        """移除 SQL 注释"""
        # 移除单行注释 --
        sql = re.sub(r'--[^\n]*', '', sql)
        # 移除多行注释 /* */
        sql = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)
        return sql

    def _has_multiple_statements(self, sql: str) -> bool:
        """检查是否包含多条语句"""
        # 简单检查：查找语句分隔符 ;
        # 注意：字符串内的 ; 不算
        statements = sqlparse.split(sql)
        return len(statements) > 1

    def _check_statement_type(self, statement: TokenList):
        """检查语句类型（只允许 SELECT）"""
        # 获取第一个有意义的 token
        first_token = statement.token_first(skip_ws=True, skip_cm=True)

        if not first_token:
            raise SQLValidationError("无法识别 SQL 语句类型", "unknown_statement_type")

        # 检查是否为 SELECT
        if first_token.ttype is not Keyword or first_token.normalized.upper() != 'SELECT':
            raise SQLValidationError(
                f"只允许 SELECT 查询，不允许 {first_token.normalized}",
                "forbidden_statement_type",
                {"statement_type": first_token.normalized}
            )

    def _check_forbidden_keywords(self, statement: TokenList):
        """检查禁用关键词"""
        sql_upper = statement.value.upper()

        for keyword in self.FORBIDDEN_KEYWORDS:
            # 使用词边界匹配
            if re.search(r'\b' + keyword + r'\b', sql_upper):
                raise SQLValidationError(
                    f"不允许使用关键词: {keyword}",
                    "forbidden_keyword",
                    {"keyword": keyword}
                )

    def _extract_tables(self, statement: TokenList) -> Set[str]:
        """提取 SQL 中涉及的表"""
        tables = set()

        # 简化实现：查找 FROM 和 JOIN 后的标识符
        from_seen = False
        join_seen = False

        for token in statement.flatten():
            if token.ttype is Keyword:
                keyword = token.normalized.upper()
                if keyword == 'FROM':
                    from_seen = True
                    join_seen = False
                elif keyword in ('JOIN', 'INNER JOIN', 'LEFT JOIN', 'RIGHT JOIN', 'FULL JOIN'):
                    join_seen = True
                    from_seen = False
                elif keyword in ('WHERE', 'GROUP', 'ORDER', 'HAVING', 'LIMIT'):
                    from_seen = False
                    join_seen = False

            # 在 FROM 或 JOIN 之后查找表名
            if (from_seen or join_seen) and token.ttype is None:
                table_name = token.value.strip('`"[]').split('.')[0]  # 处理 schema.table 格式
                if table_name and not token.is_keyword:
                    tables.add(table_name.lower())

        # 使用 sqlparse 的标识符提取（更可靠但可能更复杂）
        for token in statement.tokens:
            if isinstance(token, Identifier):
                table_name = str(token.get_real_name())
                if table_name:
                    tables.add(table_name.lower())

        return tables

    def _extract_columns(self, statement: TokenList) -> Set[str]:
        """提取 SQL 中涉及的列（简化实现）"""
        columns = set()

        # 这里只做简单的提取，实际生产环境需要更复杂的 AST 分析
        sql_upper = statement.value.upper()

        # 查找 SELECT 和 FROM 之间的内容
        match = re.search(r'SELECT\s+(.*?)\s+FROM', sql_upper, re.DOTALL | re.IGNORECASE)
        if match:
            select_clause = match.group(1)
            # 提取可能的列名（简化版本）
            potential_columns = re.findall(r'\b(\w+)\b', select_clause)
            columns.update(col.lower() for col in potential_columns)

        return columns

    def _check_table_permissions(self, tables: Set[str]):
        """检查表访问权限"""
        for table in tables:
            # 检查黑名单
            if table in self.denied_tables:
                raise SQLValidationError(
                    f"不允许访问表: {table}",
                    "forbidden_table",
                    {"table": table}
                )

            # 检查是否为系统表
            for prefix in self.SYSTEM_TABLE_PREFIXES:
                if table.startswith(prefix):
                    raise SQLValidationError(
                        f"不允许访问系统表: {table}",
                        "system_table",
                        {"table": table}
                    )

            # 检查白名单（如果配置了）
            if self.allowed_tables and table not in self.allowed_tables:
                raise SQLValidationError(
                    f"表 {table} 不在允许访问的列表中",
                    "table_not_allowed",
                    {"table": table, "allowed": list(self.allowed_tables)}
                )

    def _check_sensitive_columns(self, tables: Set[str], columns: Set[str]):
        """检查敏感字段访问"""
        for table in tables:
            if table in self.sensitive_columns:
                sensitive_cols = set(col.lower() for col in self.sensitive_columns[table])
                accessed_sensitive = sensitive_cols.intersection(columns)

                if accessed_sensitive:
                    raise SQLValidationError(
                        f"不允许访问表 {table} 的敏感字段: {', '.join(accessed_sensitive)}",
                        "sensitive_column",
                        {"table": table, "columns": list(accessed_sensitive)}
                    )

    def _check_forbidden_functions(self, statement: TokenList):
        """检查危险函数"""
        sql_upper = statement.value.upper()

        for func in self.FORBIDDEN_FUNCTIONS:
            if re.search(r'\b' + func.upper() + r'\s*\(', sql_upper):
                raise SQLValidationError(
                    f"不允许使用函数: {func}",
                    "forbidden_function",
                    {"function": func}
                )

    def _check_cartesian_product(self, statement: TokenList, tables: Set[str]):
        """
        检查笛卡尔积风险

        简化实现：检查是否有多表但没有 JOIN 或 WHERE
        """
        if len(tables) <= 1:
            return

        sql_upper = statement.value.upper()

        # 检查是否有 JOIN 或 WHERE
        has_join = 'JOIN' in sql_upper
        has_where = 'WHERE' in sql_upper

        if not has_join and not has_where:
            raise SQLValidationError(
                "检测到潜在的笛卡尔积：多表查询缺少 JOIN 或 WHERE 条件",
                "cartesian_product_risk",
                {"tables": list(tables)}
            )

    def _check_limit(self, statement: TokenList):
        """检查 LIMIT 子句"""
        sql_upper = statement.value.upper()

        # 检查是否有 LIMIT
        if 'LIMIT' not in sql_upper:
            raise SQLValidationError(
                f"查询必须包含 LIMIT 子句（建议值: {self.default_limit}）",
                "missing_limit"
            )

        # 提取 LIMIT 值
        match = re.search(r'LIMIT\s+(\d+)', sql_upper)
        if match:
            limit_value = int(match.group(1))
            if limit_value > self.max_result_rows:
                raise SQLValidationError(
                    f"LIMIT 值 {limit_value} 超过最大允许值 {self.max_result_rows}",
                    "limit_too_large",
                    {"limit": limit_value, "max": self.max_result_rows}
                )

    def add_limit_if_missing(self, sql: str) -> str:
        """如果 SQL 缺少 LIMIT，自动添加"""
        sql_upper = sql.upper()

        if 'LIMIT' in sql_upper:
            return sql

        # 添加 LIMIT
        sql_stripped = sql.rstrip().rstrip(';')
        return f"{sql_stripped} LIMIT {self.default_limit}"

    def estimate_cost(self, sql: str) -> Dict[str, any]:
        """
        估算查询成本

        这是一个简化版本，实际生产环境需要使用 EXPLAIN 分析
        """
        cost_score = 0
        warnings = []

        sql_upper = sql.upper()

        # 检查是否有索引友好的条件
        if 'WHERE' not in sql_upper:
            cost_score += 10
            warnings.append("缺少 WHERE 条件，可能全表扫描")

        # 检查是否有聚合
        if any(agg in sql_upper for agg in ['COUNT', 'SUM', 'AVG', 'MAX', 'MIN']):
            cost_score += 3

        # 检查 JOIN 数量
        join_count = sql_upper.count('JOIN')
        cost_score += join_count * 5
        if join_count > 3:
            warnings.append(f"JOIN 数量较多 ({join_count})")

        # 检查子查询
        subquery_count = sql_upper.count('SELECT') - 1
        cost_score += subquery_count * 5
        if subquery_count > 2:
            warnings.append(f"子查询数量较多 ({subquery_count})")

        # 评估成本等级
        if cost_score <= 10:
            cost_level = "low"
        elif cost_score <= 30:
            cost_level = "medium"
        else:
            cost_level = "high"

        return {
            "cost_score": cost_score,
            "cost_level": cost_level,
            "warnings": warnings
        }
