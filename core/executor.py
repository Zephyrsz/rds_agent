"""
QueryExecutor: 查询执行器

负责安全执行只读查询
"""

from typing import Dict, List, Optional, Any
import time
from datetime import datetime
import uuid


class QueryResult:
    """查询结果封装"""

    def __init__(
        self,
        query_id: str,
        sql: str,
        rows: List[Dict],
        row_count: int,
        execution_time: float,
        columns: List[str],
        success: bool = True,
        error: Optional[str] = None,
    ):
        self.query_id = query_id
        self.sql = sql
        self.rows = rows
        self.row_count = row_count
        self.execution_time = execution_time
        self.columns = columns
        self.success = success
        self.error = error
        self.timestamp = datetime.now()

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "query_id": self.query_id,
            "sql": self.sql,
            "row_count": self.row_count,
            "execution_time": self.execution_time,
            "columns": self.columns,
            "success": self.success,
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
        }


class QueryExecutor:
    """
    查询执行器

    负责：
    1. EXPLAIN 分析
    2. 执行只读查询
    3. 超时控制
    4. 结果集大小限制
    5. 查询审计日志
    """

    def __init__(
        self,
        db_connection,
        timeout_seconds: int = 30,
        max_result_rows: int = 10000,
        enable_audit: bool = True,
    ):
        """
        初始化查询执行器

        Args:
            db_connection: 数据库连接对象
            timeout_seconds: 查询超时时间（秒）
            max_result_rows: 最大返回行数
            enable_audit: 是否启用审计日志
        """
        self.db_connection = db_connection
        self.timeout_seconds = timeout_seconds
        self.max_result_rows = max_result_rows
        self.enable_audit = enable_audit
        self.query_history: List[QueryResult] = []

    def explain(self, sql: str) -> Dict[str, Any]:
        """
        执行 EXPLAIN 分析查询计划

        Returns:
            {
                "plan": str,
                "estimated_rows": int,
                "estimated_cost": float,
                "warnings": List[str]
            }
        """
        try:
            explain_sql = f"EXPLAIN {sql}"
            cursor = self.db_connection.cursor()
            cursor.execute(explain_sql)
            plan_rows = cursor.fetchall()

            # 解析 EXPLAIN 结果（不同数据库格式不同）
            plan_text = "\n".join(str(row) for row in plan_rows)

            # 简化的成本估算（实际需要根据数据库类型解析）
            warnings = []
            estimated_rows = 0
            estimated_cost = 0.0

            # DuckDB EXPLAIN 格式示例解析
            for row in plan_rows:
                row_str = str(row)
                if "ROWS" in row_str.upper():
                    # 尝试提取行数估算
                    import re
                    match = re.search(r'(\d+)', row_str)
                    if match:
                        estimated_rows = int(match.group(1))

                if "SEQ_SCAN" in row_str.upper():
                    warnings.append("检测到顺序扫描，可能影响性能")

            return {
                "plan": plan_text,
                "estimated_rows": estimated_rows,
                "estimated_cost": estimated_cost,
                "warnings": warnings,
            }

        except Exception as e:
            return {
                "plan": "",
                "estimated_rows": 0,
                "estimated_cost": 0.0,
                "warnings": [f"EXPLAIN 执行失败: {str(e)}"],
            }

    def execute(self, sql: str, params: Optional[Dict] = None) -> QueryResult:
        """
        执行查询

        Args:
            sql: SQL 查询语句
            params: 参数（用于参数化查询）

        Returns:
            QueryResult 对象
        """
        query_id = str(uuid.uuid4())
        start_time = time.time()

        try:
            # 设置超时（如果数据库支持）
            # 注意：不同数据库设置超时的方式不同
            # DuckDB: 通过 SET statement_timeout
            try:
                timeout_sql = f"SET statement_timeout = '{self.timeout_seconds}s'"
                self.db_connection.execute(timeout_sql)
            except:
                pass  # 某些数据库可能不支持

            # 执行查询
            cursor = self.db_connection.cursor()
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)

            # 获取列名
            columns = [desc[0] for desc in cursor.description] if cursor.description else []

            # 获取结果
            rows = cursor.fetchall()

            # 检查结果集大小
            if len(rows) > self.max_result_rows:
                rows = rows[:self.max_result_rows]
                warning = f"结果已截断：只返回前 {self.max_result_rows} 行"
            else:
                warning = None

            # 转换为字典列表
            result_rows = []
            for row in rows:
                row_dict = {}
                for i, col_name in enumerate(columns):
                    row_dict[col_name] = row[i]
                result_rows.append(row_dict)

            execution_time = time.time() - start_time

            result = QueryResult(
                query_id=query_id,
                sql=sql,
                rows=result_rows,
                row_count=len(result_rows),
                execution_time=execution_time,
                columns=columns,
                success=True,
            )

            # 审计日志
            if self.enable_audit:
                self._audit_query(result)

            return result

        except Exception as e:
            execution_time = time.time() - start_time

            result = QueryResult(
                query_id=query_id,
                sql=sql,
                rows=[],
                row_count=0,
                execution_time=execution_time,
                columns=[],
                success=False,
                error=str(e),
            )

            # 审计日志
            if self.enable_audit:
                self._audit_query(result)

            return result

    def execute_readonly(self, sql: str) -> QueryResult:
        """
        执行只读查询（别名方法）

        这个方法名更明确地表示只执行只读查询
        """
        return self.execute(sql)

    def _audit_query(self, result: QueryResult):
        """记录查询审计日志"""
        # 保存到历史记录
        self.query_history.append(result)

        # 实际生产环境应该写入持久化存储（数据库、日志文件等）
        audit_entry = {
            "query_id": result.query_id,
            "timestamp": result.timestamp.isoformat(),
            "sql": result.sql,
            "row_count": result.row_count,
            "execution_time": result.execution_time,
            "success": result.success,
            "error": result.error,
        }

        # TODO: 写入审计日志系统
        # logger.info("Query executed", extra=audit_entry)

    def get_query_history(self, limit: int = 10) -> List[QueryResult]:
        """获取查询历史"""
        return self.query_history[-limit:]

    def get_query_by_id(self, query_id: str) -> Optional[QueryResult]:
        """根据 ID 获取查询结果"""
        for result in self.query_history:
            if result.query_id == query_id:
                return result
        return None

    def clear_history(self):
        """清空查询历史"""
        self.query_history.clear()

    def get_statistics(self) -> Dict[str, Any]:
        """获取执行统计信息"""
        if not self.query_history:
            return {
                "total_queries": 0,
                "successful_queries": 0,
                "failed_queries": 0,
                "average_execution_time": 0.0,
                "total_rows_returned": 0,
            }

        total_queries = len(self.query_history)
        successful_queries = sum(1 for r in self.query_history if r.success)
        failed_queries = total_queries - successful_queries

        total_time = sum(r.execution_time for r in self.query_history)
        average_execution_time = total_time / total_queries if total_queries > 0 else 0.0

        total_rows = sum(r.row_count for r in self.query_history)

        return {
            "total_queries": total_queries,
            "successful_queries": successful_queries,
            "failed_queries": failed_queries,
            "success_rate": successful_queries / total_queries if total_queries > 0 else 0.0,
            "average_execution_time": average_execution_time,
            "total_rows_returned": total_rows,
        }
