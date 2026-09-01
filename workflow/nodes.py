"""
LangGraph workflow nodes implementation
"""

from typing import Dict, Any
from datetime import datetime
import structlog

logger = structlog.get_logger()


class WorkflowNodes:
    """
    工作流节点实现

    每个节点都是一个函数，接收状态并返回更新后的状态
    """

    def __init__(self, catalog, semantic_layer, planner, generator, guard, executor, validator, composer):
        """
        初始化工作流节点

        Args:
            catalog: DatabaseCatalog 实例
            semantic_layer: SemanticLayer 实例
            planner: QueryPlanner 实例
            generator: SQLGenerator 实例
            guard: SQLGuard 实例
            executor: QueryExecutor 实例
            validator: ResultValidator 实例
            composer: AnswerComposer 实例
        """
        self.catalog = catalog
        self.semantic_layer = semantic_layer
        self.planner = planner
        self.generator = generator
        self.guard = guard
        self.executor = executor
        self.validator = validator
        self.composer = composer

    def classify_request(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """节点1: 分类请求"""
        logger.info("Node: classify_request", question=state["question"])

        try:
            # 提取意图
            intent = self.semantic_layer.extract_intent(state["question"])
            intent["question"] = state["question"]

            # 记录审计
            audit_entry = {
                "node": "classify_request",
                "timestamp": datetime.now().isoformat(),
                "intent": intent,
            }

            return {
                **state,
                "question_type": intent.get("question_type", "simple_query"),
                "intent": intent,
                "audit_trail": state["audit_trail"] + [audit_entry],
            }

        except Exception as e:
            logger.error("classify_request failed", error=str(e))
            return {
                **state,
                "error": f"分类请求失败: {str(e)}",
                "status": "failed",
            }

    def resolve_semantics(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """节点2: 解析语义"""
        logger.info("Node: resolve_semantics")

        try:
            intent = state["intent"]

            # 解析指标
            resolved_metrics = []
            for metric_name in intent.get("metrics", []):
                metric = self.semantic_layer.resolve_metric(metric_name)
                if metric:
                    resolved_metrics.append({
                        "name": metric.name,
                        "expression": metric.expression,
                        "tables": metric.tables,
                    })

            # 解析维度
            resolved_dimensions = []
            for dim_name in intent.get("dimensions", []):
                dim = self.semantic_layer.resolve_dimension(dim_name)
                if dim:
                    resolved_dimensions.append({
                        "name": dim.name,
                        "table": dim.table,
                        "column": dim.column,
                    })

            # 解析时间范围
            time_range = None
            if intent.get("time_range"):
                time_range = self.semantic_layer.resolve_time_range(intent["time_range"])

            # 更新意图
            updated_intent = {
                **intent,
                "resolved_metrics": resolved_metrics,
                "resolved_dimensions": resolved_dimensions,
                "time_range_parsed": time_range,
            }

            audit_entry = {
                "node": "resolve_semantics",
                "timestamp": datetime.now().isoformat(),
                "resolved_metrics": resolved_metrics,
                "resolved_dimensions": resolved_dimensions,
            }

            return {
                **state,
                "intent": updated_intent,
                "audit_trail": state["audit_trail"] + [audit_entry],
            }

        except Exception as e:
            logger.error("resolve_semantics failed", error=str(e))
            return {
                **state,
                "error": f"解析语义失败: {str(e)}",
                "status": "failed",
            }

    def select_schema(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """节点3: 选择相关 Schema"""
        logger.info("Node: select_schema")

        try:
            question = state["question"]

            # 搜索相关 Schema
            schema_context = self.catalog.search_schema(question, max_tables=5)

            # 提取表名
            relevant_tables = list(schema_context.get("tables", {}).keys())

            audit_entry = {
                "node": "select_schema",
                "timestamp": datetime.now().isoformat(),
                "relevant_tables": relevant_tables,
            }

            return {
                **state,
                "schema_context": schema_context,
                "relevant_tables": relevant_tables,
                "audit_trail": state["audit_trail"] + [audit_entry],
            }

        except Exception as e:
            logger.error("select_schema failed", error=str(e))
            return {
                **state,
                "error": f"选择 Schema 失败: {str(e)}",
                "status": "failed",
            }

    def create_query_plan(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """节点4: 创建查询计划"""
        logger.info("Node: create_query_plan")

        try:
            intent = state["intent"]

            # 创建查询计划
            plan = self.planner.create_plan(intent)

            audit_entry = {
                "node": "create_query_plan",
                "timestamp": datetime.now().isoformat(),
                "plan": plan.to_dict(),
            }

            return {
                **state,
                "query_plan": plan.to_dict(),
                "audit_trail": state["audit_trail"] + [audit_entry],
            }

        except Exception as e:
            logger.error("create_query_plan failed", error=str(e))
            return {
                **state,
                "error": f"创建查询计划失败: {str(e)}",
                "status": "failed",
            }

    def generate_sql(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """节点5: 生成 SQL"""
        logger.info("Node: generate_sql")

        try:
            # 获取当前步骤
            plan = state["query_plan"]
            step_index = state.get("current_step_index", 0)

            if step_index >= len(plan["steps"]):
                return {
                    **state,
                    "error": "所有步骤已完成",
                    "status": "completed",
                }

            current_step = plan["steps"][step_index]
            schema_context = state["schema_context"]

            # 生成 SQL（简化实现，实际应使用 generator）
            # 这里需要传入实际的 QueryStep 对象
            from core.planner import QueryStep
            step_obj = QueryStep(
                step_id=current_step["step_id"],
                purpose=current_step["purpose"],
                query_type=current_step.get("query_type", "data"),
                metrics=current_step.get("metrics", []),
                dimensions=current_step.get("dimensions", []),
                filters=current_step.get("filters", {}),
            )

            sql = self.generator.generate(step_obj, schema_context)

            # 自动添加 LIMIT（如果需要）
            sql = self.guard.add_limit_if_missing(sql)

            audit_entry = {
                "node": "generate_sql",
                "timestamp": datetime.now().isoformat(),
                "step": current_step["step_id"],
                "sql": sql,
            }

            return {
                **state,
                "sql": sql,
                "sql_history": state["sql_history"] + [sql],
                "audit_trail": state["audit_trail"] + [audit_entry],
            }

        except Exception as e:
            logger.error("generate_sql failed", error=str(e))
            return {
                **state,
                "error": f"生成 SQL 失败: {str(e)}",
                "status": "failed",
            }

    def validate_sql(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """节点6: 验证 SQL"""
        logger.info("Node: validate_sql")

        try:
            sql = state["sql"]
            user_context = state.get("user_context", {})

            # 验证 SQL
            is_valid, error_msg = self.guard.validate_sql(sql, user_context)

            audit_entry = {
                "node": "validate_sql",
                "timestamp": datetime.now().isoformat(),
                "is_valid": is_valid,
                "error": error_msg if not is_valid else None,
            }

            if is_valid:
                return {
                    **state,
                    "sql_validated": True,
                    "validation_errors": [],
                    "audit_trail": state["audit_trail"] + [audit_entry],
                }
            else:
                return {
                    **state,
                    "sql_validated": False,
                    "validation_errors": state["validation_errors"] + [error_msg],
                    "audit_trail": state["audit_trail"] + [audit_entry],
                }

        except Exception as e:
            logger.error("validate_sql failed", error=str(e))
            return {
                **state,
                "error": f"验证 SQL 失败: {str(e)}",
                "status": "failed",
            }

    def explain_sql(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """节点7: 分析执行计划"""
        logger.info("Node: explain_sql")

        try:
            sql = state["sql"]

            # 执行 EXPLAIN
            explain_result = self.executor.explain(sql)

            audit_entry = {
                "node": "explain_sql",
                "timestamp": datetime.now().isoformat(),
                "explain_result": explain_result,
            }

            return {
                **state,
                "explain_result": explain_result,
                "audit_trail": state["audit_trail"] + [audit_entry],
            }

        except Exception as e:
            logger.error("explain_sql failed", error=str(e))
            return {
                **state,
                "error": f"分析执行计划失败: {str(e)}",
                "status": "failed",
            }

    def execute_sql(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """节点8: 执行 SQL"""
        logger.info("Node: execute_sql")

        try:
            sql = state["sql"]

            # 执行查询
            query_result = self.executor.execute(sql)

            audit_entry = {
                "node": "execute_sql",
                "timestamp": datetime.now().isoformat(),
                "query_id": query_result.query_id,
                "success": query_result.success,
                "row_count": query_result.row_count,
                "execution_time": query_result.execution_time,
            }

            if query_result.success:
                return {
                    **state,
                    "query_result": query_result.to_dict(),
                    "execution_error": None,
                    "audit_trail": state["audit_trail"] + [audit_entry],
                }
            else:
                return {
                    **state,
                    "execution_error": query_result.error,
                    "audit_trail": state["audit_trail"] + [audit_entry],
                }

        except Exception as e:
            logger.error("execute_sql failed", error=str(e))
            return {
                **state,
                "execution_error": str(e),
                "audit_trail": state["audit_trail"] + [{
                    "node": "execute_sql",
                    "timestamp": datetime.now().isoformat(),
                    "error": str(e),
                }],
            }

    def validate_result(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """节点9: 验证结果"""
        logger.info("Node: validate_result")

        try:
            # 这里需要传入实际的对象（简化实现）
            # 在实际使用中需要将字典转换回对象

            validation_issues = []  # 简化：实际应调用 validator

            audit_entry = {
                "node": "validate_result",
                "timestamp": datetime.now().isoformat(),
                "issues_count": len(validation_issues),
            }

            return {
                **state,
                "result_validated": True,
                "validation_issues": validation_issues,
                "audit_trail": state["audit_trail"] + [audit_entry],
            }

        except Exception as e:
            logger.error("validate_result failed", error=str(e))
            return {
                **state,
                "error": f"验证结果失败: {str(e)}",
                "status": "failed",
            }

    def compose_answer(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """节点10: 组织答案"""
        logger.info("Node: compose_answer")

        try:
            question = state["question"]

            # 简化：直接构建答案
            answer = {
                "question": question,
                "summary": "查询成功完成",
                "query_result": state.get("query_result"),
                "audit_info": {
                    "total_steps": len(state["audit_trail"]),
                },
            }

            audit_entry = {
                "node": "compose_answer",
                "timestamp": datetime.now().isoformat(),
            }

            return {
                **state,
                "answer": answer,
                "status": "completed",
                "audit_trail": state["audit_trail"] + [audit_entry],
            }

        except Exception as e:
            logger.error("compose_answer failed", error=str(e))
            return {
                **state,
                "error": f"组织答案失败: {str(e)}",
                "status": "failed",
            }

    def revise_sql(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """修复 SQL（在验证失败后）"""
        logger.info("Node: revise_sql")

        try:
            sql = state["sql"]
            validation_errors = state["validation_errors"]
            schema_context = state["schema_context"]

            # 构建错误上下文
            error_context = {
                "error_type": "validation_failed",
                "error_message": "; ".join(validation_errors),
                "database_message": validation_errors[-1] if validation_errors else "",
                "schema_context": schema_context,
            }

            # 修复 SQL
            revised_sql = self.generator.repair(sql, error_context)
            revised_sql = self.guard.add_limit_if_missing(revised_sql)

            # 增加重试计数
            retry_count = state["retry_count"] + 1

            audit_entry = {
                "node": "revise_sql",
                "timestamp": datetime.now().isoformat(),
                "retry_count": retry_count,
                "revised_sql": revised_sql,
            }

            return {
                **state,
                "sql": revised_sql,
                "sql_history": state["sql_history"] + [revised_sql],
                "retry_count": retry_count,
                "sql_validated": False,
                "audit_trail": state["audit_trail"] + [audit_entry],
            }

        except Exception as e:
            logger.error("revise_sql failed", error=str(e))
            return {
                **state,
                "error": f"修复 SQL 失败: {str(e)}",
                "status": "failed",
            }

    def repair_sql(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """修复 SQL（在执行失败后）"""
        logger.info("Node: repair_sql")

        try:
            sql = state["sql"]
            execution_error = state["execution_error"]
            schema_context = state["schema_context"]

            # 构建错误上下文
            error_context = {
                "error_type": "execution_failed",
                "error_message": execution_error,
                "database_message": execution_error,
                "schema_context": schema_context,
            }

            # 修复 SQL
            repaired_sql = self.generator.repair(sql, error_context)
            repaired_sql = self.guard.add_limit_if_missing(repaired_sql)

            # 增加重试计数
            retry_count = state["retry_count"] + 1

            audit_entry = {
                "node": "repair_sql",
                "timestamp": datetime.now().isoformat(),
                "retry_count": retry_count,
                "repaired_sql": repaired_sql,
            }

            return {
                **state,
                "sql": repaired_sql,
                "sql_history": state["sql_history"] + [repaired_sql],
                "retry_count": retry_count,
                "execution_error": None,
                "audit_trail": state["audit_trail"] + [audit_entry],
            }

        except Exception as e:
            logger.error("repair_sql failed", error=str(e))
            return {
                **state,
                "error": f"修复 SQL 失败: {str(e)}",
                "status": "failed",
            }
