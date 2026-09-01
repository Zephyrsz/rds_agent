"""
RESTful API Implementation for RDS Agent

将 RDS Agent 暴露为 RESTful API，供任何支持 HTTP 的 Agent 调用。

使用 FastAPI 框架实现，支持：
- 异步处理
- 自动 API 文档（Swagger UI）
- 请求验证
- 错误处理
"""

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from pathlib import Path
import time
import uuid

# RDS Agent 核心组件
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from adapters.duckdb import create_sample_database
from core import (
    DatabaseCatalog,
    SemanticLayer,
    QueryPlanner,
    SQLGenerator,
    SQLGuard,
    QueryExecutor,
    ResultValidator,
    AnswerComposer,
)
from workflow import DataAgentWorkflow

from langchain_openai import ChatOpenAI


# ============ Pydantic Models ============

class QueryRequest(BaseModel):
    """查询请求"""
    question: str = Field(..., description="用户的自然语言问题", example="最近一个月的销售额是多少？")
    user_id: Optional[str] = Field(None, description="用户ID")
    context: Optional[Dict[str, Any]] = Field(default_factory=dict, description="额外的上下文信息")


class QueryResponse(BaseModel):
    """查询响应"""
    query_id: str = Field(..., description="查询唯一标识")
    question: str = Field(..., description="用户问题")
    sql: Optional[str] = Field(None, description="生成的 SQL")
    result: Optional[Dict[str, Any]] = Field(None, description="查询结果")
    row_count: int = Field(..., description="返回行数")
    execution_time: float = Field(..., description="执行时间（秒）")
    status: str = Field(..., description="查询状态: success, failed, error")
    error: Optional[str] = Field(None, description="错误信息")
    warnings: List[str] = Field(default_factory=list, description="警告信息")
    audit_info: Dict[str, Any] = Field(default_factory=dict, description="审计信息")


class SchemaInfo(BaseModel):
    """Schema 信息"""
    table_name: str
    description: str
    columns: List[Dict[str, Any]]


class MetricInfo(BaseModel):
    """指标信息"""
    name: str
    display_name: str
    description: str
    expression: str
    tables: List[str]


class DimensionInfo(BaseModel):
    """维度信息"""
    name: str
    display_name: str
    table: str
    column: str
    mappings: Dict[str, List[str]]


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str
    version: str
    timestamp: str


# ============ FastAPI App ============

app = FastAPI(
    title="RDS Agent API",
    description="基于 LangGraph 的数据分析 Agent RESTful API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============ 全局状态 ============

class AppState:
    """应用状态"""
    def __init__(self):
        self.workflow: Optional[DataAgentWorkflow] = None
        self.catalog: Optional[DatabaseCatalog] = None
        self.semantic_layer: Optional[SemanticLayer] = None
        self.initialized = False


app_state = AppState()


# ============ 依赖注入 ============

async def verify_api_key(x_api_key: Optional[str] = Header(None)):
    """
    验证 API Key（示例实现）

    生产环境应该：
    1. 从数据库或配置中读取有效的 API Key
    2. 实现更复杂的认证机制（JWT, OAuth）
    3. 添加限流
    """
    # 暂时跳过验证
    # if not x_api_key or x_api_key != "your-secret-api-key":
    #     raise HTTPException(status_code=401, detail="Invalid API Key")
    return x_api_key


def get_workflow() -> DataAgentWorkflow:
    """获取工作流实例"""
    if not app_state.initialized or app_state.workflow is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    return app_state.workflow


# ============ 启动和关闭事件 ============

@app.on_event("startup")
async def startup_event():
    """应用启动时初始化"""
    print("初始化 RDS Agent...")

    project_root = Path(__file__).parent.parent
    config_dir = project_root / "config"

    # 创建数据库
    db_adapter = create_sample_database(":memory:")
    print("✓ 示例数据库已创建")

    # 初始化组件
    catalog = DatabaseCatalog(config_dir)
    semantic_layer = SemanticLayer(config_dir)
    planner = QueryPlanner(semantic_layer, catalog)

    llm = ChatOpenAI(model="gpt-4", temperature=0)

    generator = SQLGenerator(
        llm=llm,
        catalog=catalog,
        semantic_layer=semantic_layer,
    )

    guard = SQLGuard(
        allowed_tables=set(catalog.get_all_tables()),
        max_result_rows=10000,
        default_limit=1000,
    )

    executor = QueryExecutor(
        db_connection=db_adapter.connection,
        timeout_seconds=30,
        max_result_rows=10000,
    )

    validator = ResultValidator(semantic_layer)
    composer = AnswerComposer(llm=llm)

    # 创建工作流
    workflow = DataAgentWorkflow(
        catalog=catalog,
        semantic_layer=semantic_layer,
        planner=planner,
        generator=generator,
        guard=guard,
        executor=executor,
        validator=validator,
        composer=composer,
    )

    # 保存到全局状态
    app_state.workflow = workflow
    app_state.catalog = catalog
    app_state.semantic_layer = semantic_layer
    app_state.initialized = True

    print("✓ RDS Agent 初始化完成")


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时清理"""
    print("关闭 RDS Agent...")
    app_state.initialized = False


# ============ API Endpoints ============

@app.get("/", response_model=Dict[str, str])
async def root():
    """根路径"""
    return {
        "message": "RDS Agent API",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """健康检查"""
    return HealthResponse(
        status="healthy" if app_state.initialized else "initializing",
        version="1.0.0",
        timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
    )


@app.post("/api/v1/query", response_model=QueryResponse)
async def query_data(
    request: QueryRequest,
    workflow: DataAgentWorkflow = Depends(get_workflow),
    api_key: str = Depends(verify_api_key),
):
    """
    执行数据查询

    ## 示例请求
    ```json
    {
        "question": "最近一个月的销售额是多少？",
        "user_id": "user123"
    }
    ```

    ## 示例响应
    ```json
    {
        "query_id": "...",
        "question": "...",
        "sql": "SELECT ...",
        "result": {...},
        "row_count": 10,
        "execution_time": 1.23,
        "status": "success"
    }
    ```
    """
    query_id = str(uuid.uuid4())
    start_time = time.time()

    try:
        # 执行工作流
        final_state = workflow.run(
            question=request.question,
            user_context={"user_id": request.user_id, **request.context}
        )

        execution_time = time.time() - start_time

        # 检查错误
        if final_state.get("error"):
            return QueryResponse(
                query_id=query_id,
                question=request.question,
                sql=final_state.get("sql"),
                result=None,
                row_count=0,
                execution_time=execution_time,
                status="failed",
                error=final_state["error"],
            )

        # 提取结果
        query_result = final_state.get("query_result", {})
        answer = final_state.get("answer", {})

        return QueryResponse(
            query_id=query_id,
            question=request.question,
            sql=final_state.get("sql"),
            result=query_result,
            row_count=query_result.get("row_count", 0),
            execution_time=execution_time,
            status="success",
            warnings=answer.get("warnings", []),
            audit_info=answer.get("audit_info", {}),
        )

    except Exception as e:
        execution_time = time.time() - start_time
        return QueryResponse(
            query_id=query_id,
            question=request.question,
            sql=None,
            result=None,
            row_count=0,
            execution_time=execution_time,
            status="error",
            error=str(e),
        )


@app.get("/api/v1/schema", response_model=List[SchemaInfo])
async def get_schema(
    table_name: Optional[str] = None,
    api_key: str = Depends(verify_api_key),
):
    """
    获取数据库 Schema 信息

    - 不提供 table_name: 返回所有表
    - 提供 table_name: 返回特定表的详细信息
    """
    if not app_state.catalog:
        raise HTTPException(status_code=503, detail="Service not initialized")

    try:
        if table_name:
            # 特定表
            table = app_state.catalog.get_table(table_name)
            if not table:
                raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found")

            return [SchemaInfo(
                table_name=table.name,
                description=table.description,
                columns=[
                    {"name": col_name, **col_info}
                    for col_name, col_info in table.columns.items()
                ]
            )]
        else:
            # 所有表
            tables = app_state.catalog.get_all_tables()
            result = []
            for tbl_name in tables:
                table = app_state.catalog.get_table(tbl_name)
                result.append(SchemaInfo(
                    table_name=table.name,
                    description=table.description,
                    columns=[
                        {"name": col_name, **col_info}
                        for col_name, col_info in table.columns.items()
                    ]
                ))
            return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/metrics", response_model=List[MetricInfo])
async def get_metrics(api_key: str = Depends(verify_api_key)):
    """获取所有可用的业务指标"""
    if not app_state.semantic_layer:
        raise HTTPException(status_code=503, detail="Service not initialized")

    try:
        result = []
        for metric_name, metric in app_state.semantic_layer.metrics.items():
            result.append(MetricInfo(
                name=metric.name,
                display_name=metric.display_name,
                description=metric.description,
                expression=metric.expression,
                tables=metric.tables,
            ))
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/dimensions", response_model=List[DimensionInfo])
async def get_dimensions(api_key: str = Depends(verify_api_key)):
    """获取所有可用的业务维度"""
    if not app_state.semantic_layer:
        raise HTTPException(status_code=503, detail="Service not initialized")

    try:
        result = []
        for dim_name, dim in app_state.semantic_layer.dimensions.items():
            result.append(DimensionInfo(
                name=dim.name,
                display_name=dim.display_name,
                table=dim.table,
                column=dim.column,
                mappings=dim.mappings,
            ))
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 运行服务器 ============

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )
