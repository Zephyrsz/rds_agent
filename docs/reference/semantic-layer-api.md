---
document_type: api-behavior-reference
status: current
last_verified: 2026-09-04
source_revision: d612543 plus working-tree changes
generated: false
---

# RDS Agent 当前版本语义层实现与 API 调用指南

> 适用版本：Phase 0-2
>
> 更新日期：2026-09-04
>
> 运行时 metadata 存储：SQLite
>
> 示例业务数据库：DuckDB

## 1. 文档范围

本文档记录当前代码中已经实现的语义层能力，重点说明：

1. 语义层包含哪些 metadata 对象。
2. YAML、SQLite 和 Python 对象之间的关系。
3. 当前版本可以调用的语义层、Catalog、Compiler 和 SDK API。
4. Agent 如何在查询过程中调用这些 API 获取语义数据。
5. SDK、MCP、REST、Function Calling 和 LangChain 入口当前分别使用哪套 metadata 路径。
6. 当前限制以及尚未进入 Phase 0-2 的能力。

本文档以当前代码为准。附件设计中的 Policy Engine、Trusted Assets、向量检索、完整同比环比和配置 Web UI 等内容不作为当前已实现能力。

主要实现文件：

- [core/semantic.py](../../core/semantic.py)：核心语义对象及 YAML 兼容实现。
- [core/catalog.py](../../core/catalog.py)：Catalog 核心对象及 YAML 兼容实现。
- [adapters/sqlite_semantic.py](../../adapters/sqlite_semantic.py)：SQLite 语义层 API。
- [adapters/sqlite_catalog.py](../../adapters/sqlite_catalog.py)：SQLite Catalog API。
- [adapters/sqlite_schema.sql](../../adapters/sqlite_schema.sql)：SQLite metadata schema。
- [adapters/yaml_to_sqlite.py](../../adapters/yaml_to_sqlite.py)：YAML 与 SQLite 迁移。
- [core/compiler.py](../../core/compiler.py)：确定性 SemanticQuery 编译器。
- [workflow/nodes.py](../../workflow/nodes.py)：Agent 工作流节点。
- [integration/sdk.py](../../integration/sdk.py)：当前主 SDK 入口。

## 2. 当前架构

主运行时链路：

```text
config/*.yaml
    |
    | migrate_yaml_to_sqlite()
    v
SQLite metadata.db
    |
    +-- SQLiteCatalog
    +-- SQLiteSemanticLayer
    +-- SemanticQueryCompiler
             |
             v
自然语言问题 -> SemanticQuery -> 确定性 SQL
                                  |
                                  v
                              SQLGuard
                                  |
                                  v
                           DuckDB Executor
                                  |
                                  v
                         ResultValidator
                                  |
                                  v
                         SDK / MCP 响应
```

当前架构约束：

- SQLite 是 `RDSAgent` SDK 的运行时 metadata 唯一来源。
- `config/*.yaml` 是可版本控制的 seed 和迁移输入，不是 SDK 每次查询时直接读取的数据源。
- SQLite SDK 路径的最终 SQL 由 `SemanticQueryCompiler` 生成，不依赖 LLM 输出。
- 生成的 SQL 必须经过 `SQLGuard`，再交给 `QueryExecutor` 执行。
- YAML `DatabaseCatalog`、YAML `SemanticLayer` 和 LLM SQLGenerator 仍保留，用于兼容旧入口。

## 3. Metadata 生命周期

### 3.1 YAML seed 文件

默认 seed 目录是仓库根目录下的 `config/`。

| 文件 | 内容 | 迁移目标 |
| --- | --- | --- |
| `schema.yaml` | 表、列、grain、entities、Join | `tables`、`columns`、`entities`、`joins` |
| `metrics.yaml` | 指标、表达式、过滤、时间列 | `metrics` |
| `dimensions.yaml` | 维度、展示列、过滤列、值映射 | `dimensions` |
| `terms.yaml` | 标准术语和同义词 | `terms`、`terms_fts` |
| `examples.yaml` | 示例问题、意图和参考 SQL | `examples`、`examples_fts` |
| `domains.yaml` | Domain 范围、允许表和指标 | `domains` |
| `measures.yaml` | 原子度量 | `measures` |
| `filters.yaml` | 可复用过滤器 | `filters` |

### 3.2 当前 SQLite 对象

| SQLite 表 | 用途 | 示例数据数量 |
| --- | --- | ---: |
| `tables` | 物理表定义和 grain | 5 |
| `columns` | 列类型、PK、FK、枚举 | 22 |
| `joins` | Join Graph 和安全属性 | 4 |
| `domains` | 语义域 | 1 |
| `entities` | 业务实体及其表关联 | 7 |
| `measures` | 原子度量 | 4 |
| `filters` | 可复用业务过滤 | 1 |
| `metrics` | 对外业务指标 | 6 |
| `dimensions` | 对外业务维度 | 5 |
| `terms` | 术语和同义词 | 11 |
| `examples` | 示例问题和 SQL | 7 |

### 3.3 迁移 API

```python
from pathlib import Path
from adapters.yaml_to_sqlite import migrate_yaml_to_sqlite

migrate_yaml_to_sqlite(
    Path("config"),
    "/tmp/rds_metadata.db",
)
```

签名：

```python
migrate_yaml_to_sqlite(config_dir: Path, db_path: str) -> None
```

实际行为：

- 初始化 SQLite schema。
- 对旧 metadata DB 补充 Phase 1/2 新字段。
- 迁移表、列、Join、指标、维度、术语和 examples。
- 可选迁移 Domain、Measure 和 Filter，旧配置没有对应文件时仍可使用。
- 使用 `INSERT OR REPLACE` 保持重复迁移可执行。
- 迁移失败时 rollback。

注意：`RDSAgent` 对已经存在且非空的 `metadata_db_path` 不会在每次启动时重新覆盖。修改 YAML 后，需要显式重新执行迁移，或者使用新的 SQLite 文件。

### 3.4 导出 API

```python
from adapters.yaml_to_sqlite import export_sqlite_to_yaml

export_sqlite_to_yaml(
    "/tmp/rds_metadata.db",
    Path("/tmp/exported_config"),
)
```

当前导出实现主要覆盖 schema、metrics、dimensions、terms 和 examples。Domain、Entity、Measure、Filter 的完整反向导出尚未作为主流程使用。

## 4. 核心数据模型

### 4.1 SemanticQuery

`core.semantic.SemanticQuery` 是自然语言意图与 SQL compiler 之间的稳定契约。

```python
from core.semantic import SemanticQuery

query = SemanticQuery(
    metrics=["sales_amount"],
    dimensions=["region"],
    filters={"region": "华东"},
    semantic_filters=["valid_order"],
    time_range="最近一个月",
    order_by={"field": "sales_amount", "direction": "desc"},
    limit=1000,
    question_type="simple_query",
)
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `metrics` | `list[str]` | canonical 指标名，至少一个 |
| `dimensions` | `list[str]` | canonical 维度名 |
| `filters` | `dict[str, Any]` | 维度过滤，例如 `region: 华东` |
| `semantic_filters` | `list[str]` | 可复用 Filter 名，例如 `valid_order` |
| `time_range` | `str | None` | 相对或日历时间表达式 |
| `order_by` | `dict | None` | `field` 和 `direction` |
| `limit` | `int` | compiler 会限制到 1-10000 |
| `question_type` | `str` | simple、comparison、trend、diagnostic 等 |

可以从 intent 字典构造：

```python
query = SemanticQuery.from_intent(intent)
```

### 4.2 MetricDefinition

指标对象的主要属性：

```python
metric.name
metric.display_name
metric.description
metric.expression
metric.tables
metric.filters
metric.time_column
metric.unit
metric.data_type
metric.min_value
metric.max_value
metric.metric_type
metric.numerator
metric.denominator
metric.base_measure
metric.comparison
metric.format
metric.certification
metric.valid_dimensions
```

当前示例指标：

| 指标 | 表达式或含义 |
| --- | --- |
| `sales_amount` | 有效订单 `SUM(order_items.net_amount)` |
| `order_count` | 有效订单 `COUNT(DISTINCT orders.id)` |
| `customer_count` | 去重客户数 |
| `avg_order_amount` | 销售额 / 去重有效订单数 |
| `product_sales` | 商品销售数量 |
| `gmv` | 包含所有订单状态的成交总额 |

### 4.3 DimensionDefinition

维度对象的主要属性：

```python
dimension.name
dimension.display_name
dimension.table
dimension.column
dimension.filter_column
dimension.mappings
dimension.dimension_type
dimension.granularities
```

`column` 是查询结果展示列，`filter_column` 是过滤列，两者可以不同。例如：

```text
region.column        = regions.region_name
region.filter_column = regions.region_code
华东                 -> EAST_CHINA
```

所以结果展示“华东”，过滤条件使用 `regions.region_code = 'EAST_CHINA'`。

### 4.4 其他语义对象

- `DomainDefinition`：Domain 名、允许表、允许指标、默认时区和币种。
- `FilterDefinition`：过滤器表达式、适用表和同义词。
- `MeasureDefinition`：原子表达式、聚合方法、类型、单位和可加性。
- `ExampleSQL`：示例问题、SQL、问题类型、标签和描述。

### 4.5 Catalog 对象

- `ColumnInfo`：列类型、描述、主键、外键、枚举。
- `TableDefinition`：名称、描述、columns、tags、grain、entities。
- `JoinPath`：左右字段、Join 类型、基数、优先级、自动 Join 和 fan-out 风险。

## 5. SQLiteSemanticLayer API

初始化：

```python
from datetime import date
from adapters.sqlite_semantic import SQLiteSemanticLayer

semantic = SQLiteSemanticLayer(
    "/tmp/rds_metadata.db",
    reference_date=date(2024, 9, 30),
)
```

`reference_date` 用于相对时间解析。不传时使用当前日期；SDK 使用内存示例 DuckDB 时默认设置为 `2024-09-30`，保证结果与测试数据匹配。

### 5.1 指标 API

#### `resolve_metric`

```python
metric = semantic.resolve_metric("revenue")
assert metric.name == "sales_amount"
```

签名：

```python
resolve_metric(metric_name: str) -> MetricDefinition | None
```

解析顺序：

1. 按 `metrics.name` 精确查询。
2. 查询 `terms` 中的 canonical name、标准名和同义词。
3. 使用 canonical name 再查 `metrics`。

因此 `sales_amount`、`销售额`、`营收`、`收入`、`revenue` 均可解析到同一指标。未知指标返回 `None`。

#### 指标列表及兼容别名

```python
metrics = semantic.get_all_metrics()
metric = semantic.get_metric("sales_amount")
```

- `get_all_metrics() -> list[MetricDefinition]`
- `get_metric(metric_name) -> MetricDefinition | None`

`get_metric()` 是 `resolve_metric()` 的别名。`get_all_metrics()` 从 SQLite 读取所有 `active = TRUE` 的指标，并按名称排序。

### 5.2 维度 API

#### `resolve_dimension`

```python
dimension = semantic.resolve_dimension("地区")
assert dimension.name == "region"
```

签名：

```python
resolve_dimension(dim_name: str) -> DimensionDefinition | None
```

支持 canonical name、display name 和 `terms` 同义词。未知维度返回 `None`。

#### 维度列表及兼容别名

```python
dimensions = semantic.get_all_dimensions()
dimension = semantic.get_dimension("region")
```

- `get_all_dimensions() -> list[DimensionDefinition]`
- `get_dimension(dim_name) -> DimensionDefinition | None`

#### `resolve_dimension_value`

```python
predicate = semantic.resolve_dimension_value("region", "华东")
# regions.region_code = 'EAST_CHINA'
```

签名：

```python
resolve_dimension_value(dimension_name: str, value: str) -> str | None
```

规则：

- 有 mapping 时使用 mapping 后的值。
- 单值生成 `=`。
- 多值生成 `IN (...)`。
- 没有 mapping 时使用原值。
- 字符串中的单引号会转义。
- 未知维度返回 `None`。

### 5.3 业务术语 API

```python
semantic.resolve_business_term("华东")
# ["EAST_CHINA"]
```

签名：

```python
resolve_business_term(term: str) -> list[str]
```

该 API 先查询 `terms`，再检查所有维度的 mappings。没有匹配时返回 `[term]`。它主要用于兼容术语或维度值解析，不负责判断一个词是指标还是维度；这两类对象应调用各自的 resolve API。

### 5.4 Filter API

```python
filter_def = semantic.resolve_filter("valid_order")
print(filter_def.expression)
# orders.status IN ('paid', 'completed')
```

签名：

```python
resolve_filter(filter_name: str) -> FilterDefinition | None
```

支持按名称、显示名和 Filter 自身的同义词查找。当前示例 Filter：

```yaml
valid_order:
  name: 有效订单
  expression: "orders.status IN ('paid', 'completed')"
  applies_to: [orders]
  synonyms: [有效订单, 正常订单, 成功订单]
```

在 `SemanticQuery` 中的使用方式：

```python
query = SemanticQuery(
    metrics=["sales_amount"],
    semantic_filters=["valid_order"],
)
```

### 5.5 Domain API

```python
domain = semantic.resolve_domain("retail_sales")
print(domain.allowed_tables)
print(domain.allowed_metrics)
```

签名：

```python
resolve_domain(domain_name: str) -> DomainDefinition | None
```

当前可以从 SQLite 读取 Domain，但 compiler 尚未把 Domain 用作自动路由和强制白名单。当前 Domain 更接近可查询的 metadata 契约。

### 5.6 Measure API

```python
measure = semantic.resolve_measure("net_revenue")
print(measure.aggregation)  # sum
```

签名：

```python
resolve_measure(measure_name: str) -> MeasureDefinition | None
```

当前 Measure 可以独立读取。对外查询仍以 `MetricDefinition` 为 compiler 入口，Measure 引用的完整递归编译属于后续增强。

### 5.7 时间范围 API

```python
semantic.resolve_time_range("最近一个月")
# {
#   "start_date": "2024-09-01",
#   "end_date": "2024-09-30",
#   "column": "order_date"
# }
```

签名：

```python
resolve_time_range(expression: str) -> dict[str, str]
```

当前支持：

- `最近7天`、`最近三周`、`最近三个月`、`最近一年`。
- `last 7 days`、`last 3 weeks`、`last 3 months`。
- `本周`、`本月`、`今年`。
- `上月`、`今天`、`昨天`。

中文数字支持一至十九等当前解析范围。月份按日历月份起点，而不是固定减 30 天。例如参考日期为 `2024-09-30`：

```text
最近一个月 -> 2024-09-01 至 2024-09-30
最近三个月 -> 2024-07-01 至 2024-09-30
```

compiler 最终使用半开区间：

```sql
orders.paid_at >= '2024-09-01'
AND orders.paid_at < '2024-10-01'
```

返回对象中的 `column` 当前为兼容字段，compiler 实际优先使用指标的 `metric.time_column`。

### 5.8 自然语言意图 API

```python
intent = semantic.extract_intent("最近一个月华东地区的营收是多少？")
```

返回示例：

```python
{
    "question_type": "simple_query",
    "metrics": ["sales_amount"],
    "dimensions": ["region"],
    "filters": {"region": "华东"},
    "semantic_filters": [],
    "time_range": "最近一个月",
}
```

签名：

```python
extract_intent(question: str) -> dict[str, Any]
```

当前实现基于 SQLite metadata 的关键词和同义词，不调用 LLM：

- 遍历所有指标并匹配名称、显示名、terms 同义词。
- 遍历所有维度并匹配名称、显示名、terms 同义词。
- 检查维度 mapping 的中文值并写入 `filters`。
- 检查 Filter 显示名和同义词并写入 `semantic_filters`。
- 使用正则识别常见时间表达式。
- 根据“对比、趋势、原因”等词识别问题类型。

复杂问句可能无法完整解析。生产级 LLM/NLP 解析器可以在本 API 前后增加，但最终应输出 `SemanticQuery` 并继续使用确定性 compiler。

### 5.9 Examples API

```python
examples = semantic.get_examples(question_type="simple_query", limit=3)
matches = semantic.search_examples("销售额", limit=5)
```

- `get_examples(question_type=None, limit=3) -> list[ExampleSQL]`
- `search_examples(query, limit=5) -> list[ExampleSQL]`

`search_examples()` 使用 SQLite FTS5。Examples 当前可用于参考和兼容查询，但确定性 compiler 不依赖示例 SQL。

### 5.10 缓存和连接

```python
semantic.clear_cache()
semantic.close()
```

缓存包括单个指标、单个维度以及全部指标/维度列表。metadata 被其他连接修改后，应调用 `clear_cache()` 再读取。

## 6. SQLiteCatalog API

初始化：

```python
from adapters.sqlite_catalog import SQLiteCatalog

catalog = SQLiteCatalog("/tmp/rds_metadata.db")
```

### 6.1 表 API

```python
catalog.get_all_tables()
table = catalog.get_table("order_items")
ddl = catalog.get_ddl_summary("orders")
```

- `get_all_tables() -> list[str]`
- `get_table(table_name) -> TableDefinition | None`
- `get_ddl_summary(table_name) -> str`

`TableDefinition` 包含：

```python
table.name
table.description
table.columns
table.tags
table.grain
table.entities
```

`ColumnInfo` 包含：

```python
column.type
column.description
column.primary_key
column.foreign_key
column.enum
```

### 6.2 Schema 搜索 API

```python
tables = catalog.search_schema(
    required_tables=["orders", "order_items"],
)
```

签名：

```python
search_schema(
    question: str | None = None,
    required_tables: list[str] | None = None,
) -> list[str]
```

SQLite 实现的行为：

- 有 `required_tables`：验证表是否存在并返回存在的表。
- 有 `question`：按表名和表描述做简单 LIKE 匹配。
- 无参数：返回所有激活表。

兼容注意：YAML `DatabaseCatalog.search_schema(question, max_tables)` 返回 `{"tables": ..., "joins": ...}`，SQLite 版本返回表名列表。Workflow 已对两种返回类型做兼容处理。

### 6.3 Join Graph API

```python
joins = catalog.get_join_paths(
    ["order_items", "orders", "customers", "regions"]
)
path = catalog.find_join_path("order_items", "regions")
valid = catalog.is_valid_join("orders", "customers")
```

- `get_join_paths(tables) -> list[JoinPath]`
- `find_join_path(from_table, to_table) -> list[JoinPath]`
- `is_valid_join(left_table, right_table) -> bool`

`find_join_path()` 使用 BFS 查找最短路径。`JoinPath` 包含：

```python
join.name
join.left
join.right
join.left_table
join.right_table
join.join_type
join.cardinality
join.auto_join
join.priority
join.fan_out_risk
join.temporal_validity
```

### 6.4 缓存和关闭

```python
catalog.clear_cache()
catalog.close()
```

Catalog 缓存表定义、Join 列表和全部表名。

## 7. SemanticQueryCompiler API

初始化：

```python
from core.compiler import SemanticQueryCompiler

compiler = SemanticQueryCompiler(
    semantic_layer=semantic,
    catalog=catalog,
    default_limit=1000,
)
```

主 API：

```python
sql = compiler.compile(query)
```

签名：

```python
compile(query: SemanticQuery | dict) -> str
```

如果传入字典，compiler 会通过 `SemanticQuery.from_intent()` 转换。

### 7.1 编译时调用的 metadata API

| 编译步骤 | 使用的 API | 目的 |
| --- | --- | --- |
| 解析指标 | `semantic.resolve_metric()` | 获取表达式、表、默认过滤和时间列 |
| 解析维度 | `semantic.resolve_dimension()` | 获取展示列、过滤列和值映射 |
| 解析维度过滤 | `semantic.resolve_dimension()` | 把 filter key 映射到实际表 |
| 解析复用过滤 | `semantic.resolve_filter()` | 获取标准 Filter expression |
| 解析时间 | `semantic.resolve_time_range()` | 获取开始和结束日期 |
| 查找 Join | `catalog.find_join_path()` | 连接事实表与维度表 |
| 检查 Join | `JoinPath` 属性 | 判断基数、fan-out 和自动 Join 权限 |

### 7.2 编译流程

`compile()` 当前依次执行：

1. 校验至少存在一个 metric。
2. 解析所有 dimension，未知维度立即失败。
3. 解析所有 metric，未知指标立即失败。
4. 根据指标表达式和 `metric.tables` 选择基础事实表。
5. 收集指标、维度和 filter 所需的所有表。
6. 从基础表到每个目标表查找最短 Join 路径。
7. 拒绝不安全路径。
8. 生成维度列和指标表达式。
9. 合并指标默认过滤器、semantic filters、维度值 filters。
10. 从指标的 `time_column` 生成时间条件。
11. 生成 `GROUP BY`、`ORDER BY` 和 `LIMIT`。

### 7.3 Join 安全规则

compiler 拒绝以下情况：

- 找不到 Join 路径。
- `cardinality = many_to_many`。
- `cardinality = one_to_many`。
- `fan_out_risk = true`。
- `auto_join = false`。

当前实现允许从事实表沿 `many_to_one` 或 `one_to_one` 路径访问维度表。

### 7.4 SQL 字面值和 LIMIT

- 字符串单引号通过重复单引号转义。
- 整数和浮点数不加引号。
- LIMIT 最小为 1，最大为 10000。
- `order_by.field` 必须是本次查询中的 metric 或 dimension。
- `order_by.direction` 只能是 `ASC` 或 `DESC`。

### 7.5 编译示例

```python
query = SemanticQuery(
    metrics=["sales_amount"],
    dimensions=["region"],
    filters={"region": "华东"},
    time_range="最近一个月",
    limit=1000,
)

sql = compiler.compile(query)
```

结果结构：

```sql
SELECT regions.region_name AS region,
       SUM(order_items.net_amount) AS sales_amount
FROM order_items
INNER JOIN orders
    ON order_items.order_id = orders.id
INNER JOIN customers
    ON orders.customer_id = customers.id
INNER JOIN regions
    ON customers.region_id = regions.id
WHERE orders.status IN ('paid', 'completed')
  AND regions.region_code = 'EAST_CHINA'
  AND orders.paid_at >= '2024-09-01'
  AND orders.paid_at < '2024-10-01'
GROUP BY regions.region_name
LIMIT 1000
```

### 7.6 当前支持范围

metadata 表达式当前可使用：

- `SUM(...)`
- `COUNT(...)`
- `COUNT(DISTINCT ...)`
- `AVG(...)`
- `ratio` 表达式，例如平均订单金额。

典型失败信息：

```text
at least one metric is required
unknown metric: missing_metric
unknown dimension: missing_dimension
unknown semantic filter: missing_filter
no join path from order_items to another_table
unsafe join path includes join_name
```

完整同比、环比、YTD、MTD、复杂窗口和 `time_period` 趋势展开尚未实现。

## 8. Factory API

Factory 定义在 `adapters/factory.py`，用于创建 YAML 或 SQLite 实现。

### 8.1 create_catalog

```python
from adapters.factory import create_catalog

sqlite_catalog = create_catalog("/tmp/rds_metadata.db")
yaml_catalog = create_catalog(Path("config"))
```

签名：

```python
create_catalog(config_source: Path | str)
```

### 8.2 create_semantic_layer

```python
from adapters.factory import create_semantic_layer

sqlite_semantic = create_semantic_layer("/tmp/rds_metadata.db")
yaml_semantic = create_semantic_layer(Path("config"))
```

签名：

```python
create_semantic_layer(config_source: Path | str)
```

识别规则：

- `.db`、`.sqlite` 文件创建 SQLite 实现。
- 配置目录创建 YAML 实现。

### 8.3 migrate_to_sqlite

```python
from adapters.factory import migrate_to_sqlite

catalog, semantic = migrate_to_sqlite(
    "config/",
    "/tmp/rds_metadata.db",
    export_back=False,
)
```

签名：

```python
migrate_to_sqlite(
    yaml_config_dir: Path | str,
    sqlite_db_path: str,
    export_back: bool = False,
) -> tuple[SQLiteCatalog, SQLiteSemanticLayer]
```

### 8.4 get_config_mode

```python
get_config_mode("config/")       # yaml
get_config_mode("metadata.db")   # sqlite
```

## 9. Agent 初始化时如何连接语义层

当前推荐入口是 `integration.sdk.RDSAgent`。

```python
from datetime import date
from integration.sdk import RDSAgent

agent = RDSAgent(
    config_dir=None,
    db_path=":memory:",
    metadata_db_path=None,
    reference_date=date(2024, 9, 30),
)
```

初始化步骤：

1. `config_dir=None` 时使用项目 `config/`。
2. `metadata_db_path=None` 或 `:memory:` 时创建临时 `.db` 文件。
3. metadata 文件不存在或为空时，从 YAML 迁移到 SQLite。
4. `db_path=:memory:` 时创建带测试数据的 DuckDB。
5. 创建 `SQLiteCatalog(metadata_db_path)`。
6. 创建 `SQLiteSemanticLayer(metadata_db_path, reference_date)`。
7. 创建 `SemanticQueryCompiler(semantic_layer, catalog)`。
8. 创建 Planner、Generator、Guard、Executor、Validator 和 Composer。
9. 创建 `DataAgentWorkflow`。

核心对象关系：

```text
RDSAgent
  +-- db_adapter: DuckDBAdapter
  +-- catalog: SQLiteCatalog
  +-- semantic_layer: SQLiteSemanticLayer
  +-- compiler: SemanticQueryCompiler
  +-- planner: QueryPlanner
  +-- generator: SQLGenerator(compiler=compiler)
  +-- guard: SQLGuard
  +-- executor: QueryExecutor
  +-- validator: ResultValidator
  +-- composer: AnswerComposer
  +-- workflow: DataAgentWorkflow
```

如果 `OPENAI_API_KEY` 存在，SDK 会创建 `ChatOpenAI` 供 AnswerComposer 或兼容流程使用；确定性 SQL 生成本身不依赖 API Key。

### 9.1 示例数据库参考日期

当 `db_path == ":memory:"` 且没有显式传入 `reference_date` 时，SDK 使用 `2024-09-30`。这是示例数据的业务参考日期，不是生产默认日期。

外部业务数据库没有传入参考日期时，语义层使用当前日期。

### 9.2 持久化 metadata

```python
agent = RDSAgent(
    metadata_db_path="/data/rds_agent/metadata.db",
    db_path="/data/rds_agent/business.duckdb",
)
```

显式指定的 metadata DB 在 `agent.close()` 时不会被删除。SDK 自动创建的临时 metadata 文件会被删除。

## 10. 一次查询中的语义 API 调用链

用户入口：

```python
result = agent.query("最近一个月华东地区的营收是多少？")
```

完整调用链：

```text
RDSAgent.query
  -> DataAgentWorkflow.run
    -> classify_request
       -> SQLiteSemanticLayer.extract_intent
    -> resolve_semantics
       -> resolve_metric
       -> resolve_dimension
       -> resolve_time_range
       -> SemanticQuery.from_intent
    -> select_schema
       -> SQLiteCatalog.search_schema(required_tables=...)
       -> get_table / get_ddl_summary / get_join_paths
    -> create_query_plan
       -> QueryPlanner.create_plan
    -> generate_sql
       -> SQLGenerator.generate
       -> SemanticQueryCompiler.compile
          -> resolve_metric / resolve_dimension / resolve_filter
          -> resolve_time_range
          -> catalog.find_join_path
    -> validate_sql
       -> SQLGuard.validate_sql
    -> explain_sql
       -> QueryExecutor.explain
    -> execute_sql
       -> QueryExecutor.execute
    -> validate_result
       -> ResultValidator.validate
    -> compose_answer
  -> integration.sdk.QueryResult
```

### 10.1 classify_request

调用：

```python
intent = semantic_layer.extract_intent(state["question"])
```

写入状态：

- `question_type`
- `intent`
- `audit_trail`

### 10.2 resolve_semantics

调用：

```python
semantic_layer.resolve_metric(metric_name)
semantic_layer.resolve_dimension(dimension_name)
semantic_layer.resolve_time_range(time_range)
```

写入：

```python
intent["resolved_metrics"]
intent["resolved_dimensions"]
intent["time_range_parsed"]
intent["semantic_query"]
```

`semantic_query` 由下式创建：

```python
SemanticQuery.from_intent(updated_intent)
```

### 10.3 select_schema

Workflow 从 resolved metric 的 `tables` 和 resolved dimension 的 `table` 收集 required tables，然后调用：

```python
catalog.search_schema(required_tables=sorted(required_tables))
catalog.get_table(table_name)
catalog.get_ddl_summary(table_name)
catalog.get_join_paths(relevant_tables)
```

这意味着主路径不再只依赖自然语言中的表名关键词。

### 10.4 create_query_plan

```python
plan = planner.create_plan(intent)
```

`QueryStep` 携带：

- `metrics`
- `dimensions`
- `filters`
- `semantic_query`

### 10.5 generate_sql

```python
sql = generator.generate(step, schema_context)
```

当 generator 配置了 compiler 时，实际调用：

```python
compiler.compile(step.semantic_query)
```

只有没有 compiler 的旧模式才调用 `llm.invoke(prompt)`。

### 10.6 validate_sql 与 execute_sql

```python
guard.validate_sql(sql, user_context)
executor.explain(sql)
executor.execute(sql)
```

SQLGuard 检查只读语句、表权限、敏感列、多语句、危险函数、笛卡尔积和 LIMIT。

### 10.7 validate_result

Workflow 将状态字典转换为 `core.executor.QueryResult`，然后调用：

```python
validation = validator.validate(plan_step, query_result)
```

结果写入：

- `result_validated`
- `validation_issues`
- `audit_trail`

空结果属于 warning，不自动视为执行失败。

### 10.8 compose_answer

最终状态包含：

```python
state["sql"]
state["query_result"]
state["answer"]
state["validation_issues"]
state["audit_trail"]
```

SDK 将这些字段转换成对外 `QueryResult`。

## 11. Python SDK 对外 API

`integration.sdk.RDSAgent` 是当前最完整、最推荐的进程内接入方式。它把 metadata 初始化、语义解析、SQL 编译、安全检查、执行和结果验证封装在同一个对象中。

### 11.1 构造函数

```python
RDSAgent(
    config_dir: Optional[Path] = None,
    db_path: str = ":memory:",
    llm_model: str = "gpt-4",
    llm_temperature: float = 0.0,
    metadata_db_path: Optional[str] = None,
    reference_date: Optional[date] = None,
)
```

参数说明：

| 参数 | 含义 | 当前行为 |
| --- | --- | --- |
| `config_dir` | YAML seed 目录 | 默认使用项目下的 `config/` |
| `db_path` | DuckDB 业务数据路径 | `:memory:` 时创建内置测试数据库；路径不存在时也会创建样例数据库 |
| `llm_model` | 可选 LLM 型号 | 仅在设置 `OPENAI_API_KEY` 时初始化 `ChatOpenAI` |
| `llm_temperature` | LLM 温度 | 默认 `0.0` |
| `metadata_db_path` | SQLite metadata 路径 | 未设置或设置为 `:memory:` 时创建临时 `.db` 文件；指定持久路径时复用该文件 |
| `reference_date` | 相对时间解析基准 | 样例内存数据库默认使用 `2024-09-30`；外部数据库默认不固定 |

初始化过程如下：

1. 确定 `config_dir` 和 metadata DB 路径。
2. 如果 metadata DB 不存在或为空，执行 YAML 到 SQLite 的迁移。
3. 连接业务 DuckDB。
4. 创建 `SQLiteCatalog`、`SQLiteSemanticLayer` 和 `SemanticQueryCompiler`。
5. 将同一组实例注入 Planner、Generator、Validator 和 Workflow。

指定的持久化 metadata DB 已包含数据时，SDK 不会自动用 YAML 覆盖它。这是生产环境通过 SQLite 管理 metadata 的关键行为。

### 11.2 query

```python
result = agent.query(
    question: str,
    user_context: Optional[Dict] = None,
) -> QueryResult
```

`question` 是自然语言业务问题。`user_context` 当前会传入 Workflow 和 SQLGuard；其中 `reference_date` 还会更新语义层的相对时间基准。

```python
result = agent.query(
    "最近一个月华东地区的营收",
    user_context={"reference_date": "2024-09-30"},
)
```

当前方法捕获执行异常并返回 `success=False` 的 `QueryResult`，不会把普通查询失败继续抛给调用方。

### 11.3 aquery

```python
result = await agent.aquery(question, user_context=None) -> QueryResult
```

异步版本调用 `workflow.arun()`，返回结构与 `query()` 相同。它适合异步 Agent 或 Web 服务，但底层业务数据库驱动的实际并发能力仍取决于连接和部署方式。

### 11.4 QueryResult

SDK 的 `QueryResult` 是 dataclass：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `success` | `bool` | 整个查询工作流是否成功 |
| `question` | `str` | 原始自然语言问题 |
| `sql` | `Optional[str]` | 最终执行的 SQL |
| `data` | `Optional[List[Dict]]` | 行记录列表 |
| `row_count` | `int` | 返回行数 |
| `execution_time` | `float` | 数据库执行耗时，单位为秒 |
| `error` | `Optional[str]` | 失败原因 |
| `warnings` | `Optional[List[str]]` | 结果验证或回答生成阶段的警告 |

注意：SDK 的 `QueryResult` 与 `core.executor.QueryResult` 不是同一个类。后者包含 `query_id`、`columns`、`timestamp` 等执行器内部字段，SDK 只向外暴露精简后的结果。

### 11.5 get_schema

```python
agent.get_schema(table_name: Optional[str] = None) -> Dict[str, Any]
```

- 不传 `table_name`：返回表名和表描述列表。
- 传入 `table_name`：返回表描述及列的类型、主键、外键、枚举等信息。
- 表不存在或读取失败：返回包含 `error` 的字典。

```python
all_tables = agent.get_schema()
orders = agent.get_schema("orders")
```

该 API 直接读取 `SQLiteCatalog`，不经过 LLM。

### 11.6 get_metrics

```python
agent.get_metrics() -> List[Dict[str, Any]]
```

返回所有指标的：

- `name`
- `display_name`
- `description`
- `expression`
- `tables`

该 API 调用 `SQLiteSemanticLayer.get_all_metrics()`。别名、过滤规则、时间列和指标类型当前没有出现在 SDK 的精简响应中；需要这些字段时应直接调用 `agent.semantic_layer`。

### 11.7 get_dimensions

```python
agent.get_dimensions() -> List[Dict[str, Any]]
```

返回所有维度的 `name`、`display_name`、`table`、`column` 和 `mappings`。它直接调用 `SQLiteSemanticLayer.get_all_dimensions()`。

### 11.8 get_statistics

```python
agent.get_statistics() -> Dict[str, Any]
```

返回当前 Agent 实例进程内的执行统计：

```python
{
    "total_queries": 3,
    "successful_queries": 3,
    "failed_queries": 0,
    "success_rate": 1.0,
    "average_execution_time": 0.0012,
    "total_rows_returned": 5,
}
```

统计来自 `QueryExecutor.query_history`，不会写入 SQLite metadata，也不会跨进程保留。

### 11.9 close 和上下文管理器

```python
agent.close()
```

`close()` 关闭业务数据库、Catalog 和 SemanticLayer 连接；如果 SDK 创建的是临时 metadata 文件，还会删除该临时文件。

推荐使用上下文管理器：

```python
from integration.sdk import RDSAgent

with RDSAgent() as agent:
    result = agent.query("华东地区订单数")
```

也可以使用一次性便捷函数：

```python
from integration.sdk import quick_query

result = quick_query("最近一个月的销售额")
```

## 12. Agent 和外部系统的接入方式

### 12.1 接入状态总览

| 接入方式 | 对外入口 | Metadata 运行时来源 | SQL 生成路径 | 当前建议 |
| --- | --- | --- | --- | --- |
| Python SDK | `RDSAgent` | SQLite | `SemanticQueryCompiler` 优先 | 推荐 |
| MCP | `query_data(question)` | SQLite，由 SDK 初始化 | `SemanticQueryCompiler` 优先 | 推荐给支持 MCP 的 Agent |
| REST | `/api/v1/*` | YAML | LLM `SQLGenerator` | 兼容接口，尚未统一到 SQLite |
| Function Calling | 3 个 function | YAML | LLM `SQLGenerator` | 示例性质，尚未统一到 SQLite |
| LangChain Tool | `rds_query`、Schema Tool | YAML | LLM `SQLGenerator` | 示例性质，存在命名兼容问题 |

“Metadata 运行时来源”指查询期间读取的后端，不代表配置最初的录入格式。SDK/MCP 在 metadata DB 首次创建时仍可以用 YAML 作为 seed。

### 12.2 MCP API

MCP server 通过 stdio 暴露一个粗粒度工具：

```text
query_data(question: string) -> string
```

工具执行链：

```text
MCP Client
  -> query_data
  -> asyncio.to_thread(agent.query, question)
  -> RDSAgent Workflow
  -> SQLite metadata + SemanticQueryCompiler
  -> Markdown 文本结果
```

成功响应包含：

- 原始问题
- 行数和执行耗时
- 最终 SQL
- 最多 20 行的 JSON preview
- warnings

SDK 返回失败时，MCP 使用 `ToolError` 把错误传回调用方。

启动方式：

```bash
python -m integration.mcp_server \
  --config-dir /path/to/config \
  --db-path /path/to/business.duckdb \
  --llm-model gpt-4
```

也可以使用：

- `RDS_CONFIG_DIR`
- `RDS_DB_PATH`
- `RDS_LLM_MODEL`

当前 MCP CLI 没有暴露 `metadata_db_path` 参数，因此每次进程启动时由 SDK 创建临时 SQLite metadata DB 并从 YAML seed 迁移。MCP 查询期间读取的仍然是 SQLite，但 metadata 修改不会跨 MCP 进程保留。需要直接使用持久 metadata DB 时，应扩展 CLI 参数或在自定义启动代码中构造 `RDSAgent(metadata_db_path=...)`。

### 12.3 REST API

当前 FastAPI 应用提供：

| Method | Path | 作用 |
| --- | --- | --- |
| `GET` | `/` | 服务入口信息 |
| `GET` | `/health` | 初始化状态和版本 |
| `POST` | `/api/v1/query` | 执行自然语言查询 |
| `GET` | `/api/v1/schema` | 获取全部或指定表 Schema |
| `GET` | `/api/v1/metrics` | 获取指标列表 |
| `GET` | `/api/v1/dimensions` | 获取维度列表 |

查询请求：

```json
{
  "question": "最近一个月华东地区的营收",
  "user_id": "user-123",
  "context": {
    "reference_date": "2024-09-30"
  }
}
```

查询响应主要包含 `query_id`、`sql`、`result`、`row_count`、`execution_time`、`status`、`error`、`warnings` 和 `audit_info`。

REST 当前有以下重要边界：

- 启动函数直接创建 `DatabaseCatalog(config_dir)` 和 `SemanticLayer(config_dir)`，运行时仍读 YAML。
- `SQLGenerator` 没有注入 `SemanticQueryCompiler`，因此查询依赖 LLM。
- `ChatOpenAI` 无条件初始化；部署需要正确的模型凭证和网络配置。
- `verify_api_key` 当前只是占位实现，没有实际认证。
- CORS 当前允许全部来源，不适合直接作为生产安全配置。
- Schema endpoint 仍按字典展开列对象，而当前 `ColumnInfo` 是 dataclass；此接口需要统一序列化后再作为稳定 API 使用。

### 12.4 Function Calling

`integration.function_calling.FUNCTIONS` 定义了三个函数：

| 函数 | 参数 | 返回用途 |
| --- | --- | --- |
| `query_database` | `question` | SQL、行数、耗时及最多 10 行数据 |
| `get_database_schema` | 可选 `table_name` | 表列表或指定表列信息 |
| `get_available_metrics` | 无 | 指标定义列表 |

`RDSAgentFunctionCalling.call_function(function_name, arguments)` 完成函数名到 Python 方法的分发。OpenAI 和 Anthropic 示例都在外层 LLM 识别 function/tool call 后调用该方法。

该包装器当前直接使用 YAML `DatabaseCatalog`/`SemanticLayer`，并依赖 LLM 生成 SQL。`get_database_schema()` 仍把列对象当字典调用 `.get()`，与当前 dataclass Catalog 模型不完全兼容。

### 12.5 LangChain Tool

当前文件定义：

- `RDSQueryTool`，工具名 `rds_query`，支持 `_run()` 和 `_arun()`。
- `RDSSchematool`，工具名 `rds_schema`，查询表结构。

`RDSQueryTool` 延迟初始化 YAML Catalog、YAML SemanticLayer、LLM SQLGenerator 和完整 Workflow。输出是包含 SQL、行数、执行时间、前 5 行数据及警告的 Markdown 字符串。

当前示例引用 `RDSSchemaTool()`，但实际类名是 `RDSSchematool`，大小写不一致会导致示例运行失败。该集成尚未纳入 Phase 0-2 的 SQLite 主路径验证范围。

### 12.6 Agent 应如何选择 API

推荐决策顺序：

1. Agent 支持 MCP：调用 `query_data`，只传自然语言业务问题。
2. Agent 与项目在同一 Python 进程：创建 `RDSAgent`，调用 `query()` 或 `aquery()`。
3. Agent 需要探索 metadata：通过 `agent.get_schema()`、`agent.get_metrics()`、`agent.get_dimensions()` 获取精简信息，或直接访问 `agent.catalog` 和 `agent.semantic_layer` 的详细 API。
4. 需要稳定 HTTP 服务：先把 REST 初始化路径统一到 SDK/SQLite，再对外发布。

对大多数上层 Agent，不建议自己拼装 SQL。上层只需提供自然语言问题；语义对象解析和确定性编译在 RDS Agent 内完成。

## 13. 安全、验证和错误传播

### 13.1 编译阶段验证

`SemanticQueryCompiler` 在 SQL 生成前检查：

- 至少包含一个指标。
- 所有 metric、dimension、filter 都能从 SQLite metadata 解析。
- `order_by.field` 必须是本次请求中的 metric 或 dimension。
- 排序方向只能是 `ASC` 或 `DESC`。
- 指标必须包含非空 expression。
- Phase 2 仅支持 `simple` 和 `ratio` 指标类型。
- 指标表达式禁止 `;`、`--` 和 `/*`。
- 多指标使用时间范围时必须使用同一个时间列。
- `limit` 被限制在 `1..10000`，非法值回退到默认值。

维度过滤值通过 `_quote_literal()` 转义单引号。字符串 `O'Reilly` 会被编译成 `'O''Reilly'`。

### 13.2 Join 安全

Compiler 以指标来源表为 base table，并通过 Catalog join graph 寻找 required tables 的路径。自动 Join 必须同时满足：

- 存在 join path。
- `auto_join=True`。
- cardinality 不是 `many_to_many` 或 `one_to_many`。
- `fan_out_risk=False`。

任一条件不满足即抛出 `ValueError`，不会退回到猜测 Join。这一规则优先保证聚合指标不因 fan-out 被重复计算。

### 13.3 SQLGuard

SQL 生成后、执行前会调用：

```python
is_valid, error = guard.validate_sql(sql, user_context)
```

当前检查包括：

- SQL 非空。
- 单条语句。
- 第一条有效 token 必须是 `SELECT`。
- 禁止 DML、DDL、权限、文件和系统操作关键词。
- 物理表必须在 allowed tables 中，且不是系统表或 denied table。
- 检查配置的 sensitive columns。
- 禁止危险函数。
- 检查明显的多表笛卡尔积风险。
- 必须带 `LIMIT`，且不能超过 `max_result_rows`。

`validate_sql()` 不直接抛出业务异常，而是返回 `(False, "error_type: message")`。Workflow 将其写入 `state["error"]` 并终止执行。

### 13.4 执行和结果验证

`QueryExecutor` 先尝试设置 statement timeout，再执行 SQL，并将结果转成字典列表。超过 `max_result_rows` 的结果会在执行器中截断；查询成功与失败都会进入当前进程内的 query history。

`ResultValidator` 在执行后检查：

- 查询本身是否成功。
- 空结果 warning。
- 数值负值和极大值 warning。
- 同一列的数据类型一致性。
- 结果时间列中的未来日期。
- 多结果之间的行数差异。

聚合一致性检查当前仍是 TODO，尚未执行指标总计、明细之和或 fan-out 结果的二次校验。

### 13.5 错误传播路径

```text
metadata/compile/guard/execute error
  -> Workflow state["error"]
  -> SDK QueryResult(success=False, error=...)
  -> MCP ToolError / REST failed response / Tool 文本错误
```

直接调用底层 `resolve_*` API 时，未找到对象通常返回 `None`；直接调用 Compiler 时，未知或不安全的语义对象会抛出 `ValueError`。调用方应根据所选抽象层处理不同的错误协议。

## 14. 完整调用示例

### 14.1 直接读取 SQLite 语义 metadata

```python
from adapters.sqlite_catalog import SQLiteCatalog
from adapters.sqlite_semantic import SQLiteSemanticLayer

metadata_db = "metadata.db"
catalog = SQLiteCatalog(metadata_db)
semantic = SQLiteSemanticLayer(metadata_db)

try:
    metric = semantic.resolve_metric("营收")
    dimension = semantic.resolve_dimension("地区")
    values = semantic.resolve_dimension_value("region", "华东")
    join_path = catalog.find_join_path("order_items", "regions")

    print(metric.name, metric.expression)
    print(dimension.table, dimension.column)
    print(values)
    print([edge.name for edge in join_path])
finally:
    catalog.close()
    semantic.close()
```

### 14.2 直接编译 SemanticQuery

```python
from datetime import date

from adapters.sqlite_catalog import SQLiteCatalog
from adapters.sqlite_semantic import SQLiteSemanticLayer
from core.compiler import SemanticQueryCompiler
from core.semantic import SemanticQuery

metadata_db = "metadata.db"
catalog = SQLiteCatalog(metadata_db)
semantic = SQLiteSemanticLayer(metadata_db, reference_date=date(2024, 9, 30))
compiler = SemanticQueryCompiler(semantic, catalog)

query = SemanticQuery(
    metrics=["revenue"],
    dimensions=[],
    filters={"region": "华东"},
    time_range="最近一个月",
    limit=1000,
)

try:
    sql = compiler.compile(query)
    print(sql)
finally:
    catalog.close()
    semantic.close()
```

这条查询会使用 SQLite 中的指标、维度映射、时间列和 Join Graph 生成只读 SQL，不调用 LLM。

### 14.3 通过完整 SDK 查询

```python
from datetime import date
from integration.sdk import RDSAgent

with RDSAgent(reference_date=date(2024, 9, 30)) as agent:
    result = agent.query("最近一个月华东地区的营收")

    if not result.success:
        raise RuntimeError(result.error)

    print(result.sql)
    print(result.data)
    print(result.warnings)
```

使用当前内置测试数据，已验证该问题的营收结果为 `3891.00`。

### 14.4 使用持久化 metadata DB

首次从 YAML 迁移：

```python
from adapters.yaml_to_sqlite import migrate_yaml_to_sqlite

migrate_yaml_to_sqlite("config", "var/metadata.db")
```

后续 Agent 直接复用：

```python
from integration.sdk import RDSAgent

with RDSAgent(
    config_dir="config",
    db_path="var/business.duckdb",
    metadata_db_path="var/metadata.db",
) as agent:
    result = agent.query("各地区销售额")
```

只要 `var/metadata.db` 已存在且非空，`config/` 中 YAML 的后续修改不会自动覆盖 SQLite。metadata 发布流程应显式执行迁移或数据库更新，并配合版本管理和校验。

### 14.5 上层 Agent 先探索再查询

```python
with RDSAgent(metadata_db_path="var/metadata.db") as semantic_agent:
    capabilities = {
        "schema": semantic_agent.get_schema(),
        "metrics": semantic_agent.get_metrics(),
        "dimensions": semantic_agent.get_dimensions(),
    }

    # 上层 Agent 根据 capabilities 选择业务问题，而不是自行拼 SQL。
    result = semantic_agent.query("按地区统计销售额")
```

如果只需要回答问题，上层 Agent 可以跳过探索调用，直接使用 `query()` 或 MCP `query_data()`；Workflow 会自行解析语义对象。

## 15. 当前限制

### 15.1 Phase 0-2 主路径限制

- 一个 SemanticQuery 至少需要一个 metric，暂不支持纯明细/纯维度查询的确定性编译。
- 指标类型仅支持 `simple` 和 `ratio`；累计、窗口、同比、环比和派生指标尚未进入 Compiler。
- 自动 Join 有意拒绝 `one_to_many` 和 `many_to_many`，尚无基于 grain/bridge 的安全聚合改写。
- time range 使用第一个一致的 metric time column，不支持同一请求中多个时间语义。
- `resolve_query_intent()` 依赖规则、别名和词匹配；复杂自然语言歧义尚无置信度和澄清交互。
- reusable filter expression 和 metric expression 是 metadata 中的 SQL 片段；当前做了基础危险标记检查，但还不是完整 SQL AST 白名单。
- SQLite 是 metadata 存储，不是业务查询数据库；业务数据当前由 DuckDB adapter 执行。

### 15.2 治理与运维限制

- Domain、Entity、Measure 和 Filter 已可存储和读取，但尚未形成完整的权限、血缘和指标认证体系。
- `user_context` 已进入 SQLGuard，但 metadata 中的行级/列级 policy 尚未实现。
- metadata 没有正式的版本号、审批、发布、回滚和并发更新协议。
- Catalog/SemanticLayer 使用进程内缓存；外部修改 SQLite 后需要重建实例或显式调用 `clear_cache()`。
- 执行审计仅保存在内存，未写入持久审计库。
- 结果验证的聚合一致性仍为空实现。

### 15.3 接入层限制

- SDK 和 MCP 已采用 SQLite 主路径，其他三个集成尚未统一。
- MCP 暂无持久 metadata DB CLI 参数，也只暴露自然语言查询工具。
- REST 认证和 CORS 是开发配置，且 Schema 序列化需要修复。
- Function Calling 仍使用旧式 `functions` 示例，且 Schema 列序列化与当前 dataclass 不一致。
- LangChain 示例的 Schema Tool 类名不一致。

## 16. 建议的后续实施顺序

Phase 0-2 已建立“SQLite metadata + SemanticQuery + deterministic compiler”的可运行主路径。下一步建议按风险优先级推进：

1. **统一接入层。** REST、Function Calling 和 LangChain 全部改为封装 `RDSAgent`，删除重复的 YAML/LLM 组件装配；为 MCP 增加 `metadata_db_path` 配置。
2. **补齐 metadata 发布流程。** 增加 schema version、migration version、校验、差异预览、事务发布和回滚策略，明确 YAML seed 与 SQLite source of truth 的边界。
3. **实现 Policy Engine。** 将用户身份、行级过滤、列脱敏和 domain/table/metric 权限落实到编译前与 SQLGuard 两层。
4. **增强语义编译器。** 支持派生指标、累计、同比/环比、多时间角色、明确的 grain，以及可证明安全的 one-to-many 聚合。
5. **完善可信度与验证。** 增加指标测试、Join fan-out 检测、聚合一致性、metadata 引用完整性和 golden query regression suite。
6. **增加可观测性。** 持久化 query id、语义解析、metadata version、生成 SQL、耗时、结果摘要、错误类型和用户上下文中的审计标识。

在第 1 项完成前，生产 Agent 应优先使用 Python SDK 或 MCP；REST、Function Calling 和 LangChain Tool 应视为待统一的兼容/示例入口。
