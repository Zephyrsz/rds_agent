# 已有 DuckDB 接入与元数据生成指南

本文档说明如何将一个已有的 DuckDB 文件接入 RDS Agent，并生成和维护 RDS Agent 所需的元数据文件。

当前项目的元数据分为两类：

- 技术元数据：表、列、类型、主键、外键和 Join 关系。这部分可以从 DuckDB 自动生成初稿。
- 业务语义元数据：指标、维度、术语、默认过滤条件和示例 SQL。这部分不能只依赖数据库结构推断，必须结合业务规则审核。

## 1. 当前实现的行为

RDS Agent 通过 integration/sdk.py 初始化数据库：

~~~python
if db_path == ":memory:" or not Path(db_path).exists():
    self.db_adapter = create_sample_database(db_path)
else:
    self.db_adapter = DuckDBAdapter(db_path)
~~~

因此：

- RDS_DB_PATH=:memory: 会创建内存示例数据库。
- RDS_DB_PATH 指向一个已存在的文件时，会打开该 DuckDB 文件。
- 路径不存在时，会进入示例数据库创建逻辑，不能把不存在的路径当作生产数据库配置。

接入真实数据库前，必须检查文件存在：

~~~bash
export RDS_DB_PATH=/absolute/path/to/business.duckdb
test -n "$RDS_DB_PATH"
test -f "$RDS_DB_PATH"
~~~

当前默认连接是 read_only=False。SQLGuard 会限制 Agent 生成的 SQL，但数据库连接本身仍然是可写连接。如果生产环境要求数据库层面的物理只读，需要将 SDK 初始化改为：

~~~python
DuckDBAdapter(db_path, read_only=True)
~~~

## 2. 推荐目录布局

生产数据库文件不要提交到 Git。建议使用如下目录：

~~~text
rds_agent/
├── config/
│   ├── schema.yaml
│   ├── metrics.yaml
│   ├── dimensions.yaml
│   ├── terms.yaml
│   └── examples.yaml
├── data/
│   └── business.duckdb
└── integration/
    ├── mcp_server.py
    └── deepseek-harness.cordis.yml
~~~

如果同一份代码需要服务多个数据库，可以为每个数据库建立独立配置目录：

~~~text
rds_agent/
├── config/
│   ├── demo/
│   │   ├── schema.yaml
│   │   ├── metrics.yaml
│   │   └── dimensions.yaml
│   └── business/
│       ├── schema.yaml
│       ├── metrics.yaml
│       ├── dimensions.yaml
│       ├── terms.yaml
│       └── examples.yaml
└── data/
    └── business.duckdb
~~~

通过 RDS_CONFIG_DIR 选择对应的配置目录。

## 3. 准备和检查 DuckDB 文件

### 3.1 复制或挂载数据库

如果数据库来自另一台机器，先将文件复制到当前节点，或者挂载共享目录：

~~~bash
mkdir -p "$RDS_AGENT_ROOT/data"
cp /path/from/source/business.duckdb "$RDS_AGENT_ROOT/data/business.duckdb"
export RDS_DB_PATH="$RDS_AGENT_ROOT/data/business.duckdb"
~~~

生产环境建议先制作备份：

~~~bash
cp "$RDS_DB_PATH" "$RDS_DB_PATH.backup"
~~~

不要在数据库正在被其他进程写入时直接复制文件。需要一致性快照时，应使用业务侧备份机制或先停止写入。

### 3.2 使用只读连接探查

~~~bash
cd "$RDS_AGENT_ROOT"

venv/bin/python - <<'PY'
import os
import duckdb

db_path = os.environ["RDS_DB_PATH"]
con = duckdb.connect(db_path, read_only=True)

tables = con.execute("""
    SELECT table_schema, table_name, table_type
    FROM information_schema.tables
    WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
    ORDER BY table_schema, table_name
""").fetchall()

for row in tables:
    print(row)

con.close()
PY
~~~

检查重点：

- 哪些对象是业务表，哪些是视图；
- 是否存在临时表或内部表；
- 是否有同名表位于不同 schema；
- 哪些表允许被 Agent 查询；
- 哪些字段包含手机号、邮箱、身份证号、地址等敏感信息。

当前 DatabaseCatalog 使用不带 schema 的表名作为 key，因此实际运行最好先只接入 main schema，并保证表名唯一。多 schema 或同名表需要先扩展 Catalog 和 SQL 生成逻辑。

### 3.3 查看列、主键和外键

~~~bash
venv/bin/python - <<'PY'
import os
import duckdb

con = duckdb.connect(os.environ["RDS_DB_PATH"], read_only=True)

for table_name in ["orders", "customers", "order_items"]:
    print(f"\n--- {table_name} ---")
    result = con.execute(f'PRAGMA table_info("{table_name}")')
    print(result.fetchall())

print("\n--- constraints ---")
for row in con.execute("SELECT * FROM duckdb_constraints()").fetchall():
    print(row)

con.close()
PY
~~~

请把示例中的表名替换为真实表名。对地区、状态、类别等字段执行去重查询：

~~~sql
SELECT DISTINCT status FROM orders ORDER BY status;
SELECT DISTINCT region FROM customers ORDER BY region;
SELECT DISTINCT category FROM products ORDER BY category;
~~~

还应记录时间字段范围和各表行数：

~~~sql
SELECT COUNT(*) AS row_count FROM orders;
SELECT MIN(order_date), MAX(order_date) FROM orders;
SELECT MIN(paid_at), MAX(paid_at) FROM orders;
~~~

这些结果有助于填写指标时间口径，并发现元数据和真实数据不一致的问题。

## 4. 自动生成 schema.yaml 初稿

当前项目没有内置的 generate_metadata 命令。可以使用下面的临时脚本，从 main schema 的基础表生成技术元数据：

~~~bash
cd "$RDS_AGENT_ROOT"

RDS_DB_PATH="$RDS_DB_PATH" \
SCHEMA_OUT="$RDS_AGENT_ROOT/config/schema.generated.yaml" \
venv/bin/python - <<'PY'
import os
from pathlib import Path

import duckdb
import yaml

db_path = Path(os.environ["RDS_DB_PATH"])
output = Path(os.environ["SCHEMA_OUT"])

if not db_path.is_file():
    raise SystemExit(f"DuckDB file does not exist: {db_path}")

def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'

con = duckdb.connect(str(db_path), read_only=True)

tables = [
    row[0]
    for row in con.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'main'
          AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """).fetchall()
]

foreign_keys = {}
for table, constraint_type, columns, referenced_table, referenced_columns in con.execute("""
    SELECT
        table_name,
        constraint_type,
        constraint_column_names,
        referenced_table,
        referenced_column_names
    FROM duckdb_constraints()
    WHERE schema_name = 'main'
""").fetchall():
    if constraint_type != "FOREIGN KEY" or not referenced_table:
        continue

    for column, referenced_column in zip(columns or [], referenced_columns or []):
        foreign_keys[(table, column)] = f"{referenced_table}.{referenced_column}"

schema = {"tables": {}, "joins": []}

for table in tables:
    columns = {}

    for _, name, data_type, _, _, is_primary_key in con.execute(
        f"PRAGMA table_info({quote_identifier(table)})"
    ).fetchall():
        column = {
            "type": data_type,
            "description": "",
        }

        if is_primary_key:
            column["primary_key"] = True

        foreign_key = foreign_keys.get((table, name))
        if foreign_key:
            column["foreign_key"] = foreign_key

        columns[name] = column

    schema["tables"][table] = {
        "description": "",
        "tags": [],
        "columns": columns,
    }

for (table, column), referenced in foreign_keys.items():
    schema["joins"].append({
        "left": f"{table}.{column}",
        "right": referenced,
        "cardinality": "many_to_one",
        "description": "",
    })

output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(
    yaml.safe_dump(schema, allow_unicode=True, sort_keys=False),
    encoding="utf-8",
)

con.close()
print(f"Generated: {output}")
PY
~~~

查看生成结果：

~~~bash
sed -n '1,260p' config/schema.generated.yaml
~~~

确认结果后再替换正式文件：

~~~bash
mv config/schema.generated.yaml config/schema.yaml
~~~

自动生成的文件只是初稿，必须人工补全：

~~~yaml
tables:
  orders:
    description: 订单主表，记录订单状态和时间
    tags: [order, transaction]
    columns:
      id:
        type: BIGINT
        description: 订单唯一标识
        primary_key: true
      customer_id:
        type: BIGINT
        description: 下单客户 ID
        foreign_key: customers.id
~~~

需要人工审核的内容包括：

- description：表和列的业务含义；
- tags：中文业务词和英文别名；
- primary_key：复合主键或非标准约束；
- foreign_key：数据库未声明但业务上存在的关系；
- cardinality：many_to_one、one_to_many 等真实基数；
- 不应开放给 Agent 查询的表；
- 敏感列的访问策略。

## 5. 补充业务语义文件

### 5.1 metrics.yaml

metrics.yaml 定义用户口中的“销售额”“订单数”等指标如何计算。

~~~yaml
metrics:
  sales_amount:
    name: 销售额
    description: 已支付和已完成订单的净销售额
    expression: SUM(order_items.net_amount)
    tables:
      - orders
      - order_items
    filters:
      - orders.status IN ('paid', 'completed')
    time_column: orders.paid_at

  order_count:
    name: 订单数
    description: 有效订单数量
    expression: COUNT(DISTINCT orders.id)
    tables:
      - orders
    filters:
      - orders.status IN ('paid', 'completed')
    time_column: orders.order_date
~~~

每个指标都要明确：

- SQL 表达式；
- 是否去重；
- 默认状态过滤；
- 时间字段；
- 所需表；
- Join 后是否会重复计数。

例如订单数通常需要 COUNT(DISTINCT orders.id)，不能默认使用 COUNT(*)。

### 5.2 dimensions.yaml

dimensions.yaml 将自然语言维度映射到真实表和字段：

~~~yaml
dimensions:
  region:
    name: 地区
    description: 客户所属地区
    table: regions
    column: region_name
    mappings:
      华东:
        - EAST_CHINA
      华北:
        - NORTH_CHINA

  product_category:
    name: 产品类别
    description: 商品所属类别
    table: products
    column: category
    mappings:
      电子:
        - 电子产品
      家居:
        - 家居用品
~~~

mappings 左侧是用户表达，右侧必须是数据库中真实存在的值。不要只根据业务猜测映射值，应先执行：

~~~sql
SELECT DISTINCT region_name FROM regions ORDER BY region_name;
SELECT DISTINCT category FROM products ORDER BY category;
SELECT DISTINCT status FROM orders ORDER BY status;
~~~

### 5.3 terms.yaml

terms.yaml 保存业务术语和同义词：

~~~yaml
terms:
  sales_amount:
    standard_name: sales_amount
    synonyms:
      - 销售额
      - 销售金额
      - 营收
      - 收入
      - revenue

  order_count:
    standard_name: order_count
    synonyms:
      - 订单数
      - 订单量
      - 成交单数
~~~

内部名称应与 metrics.yaml 或 dimensions.yaml 一致。新增指标后，应同时补充它的常用说法。

### 5.4 examples.yaml

examples.yaml 可以记录已审核的问题、意图和 SQL：

~~~yaml
examples:
  - question: 华东地区的订单数是多少？
    intent:
      question_type: simple_query
      metrics: [order_count]
      dimensions: [region]
    sql: |
      SELECT
        r.region_name,
        COUNT(DISTINCT o.id) AS order_count
      FROM orders o
      JOIN customers c ON o.customer_id = c.id
      JOIN regions r ON c.region_id = r.id
      WHERE o.status IN ('paid', 'completed')
        AND r.region_code = 'EAST_CHINA'
      GROUP BY r.region_name
      LIMIT 1000;
~~~

当前 RDSAgent 初始化 SQLGenerator 时没有读取 examples.yaml，因此这些示例目前不会自动进入 MCP/SDK 的生成提示词。它们仍然适合作为：

- 人工回归查询；
- 业务口径文档；
- 后续接入示例检索功能的输入。

如果希望模型实际使用示例，需要在 SDK 初始化 SQLGenerator 时显式加载 YAML 并传入 examples。

## 6. 校验数据库和元数据

### 6.1 检查表集合

~~~bash
export RDS_CONFIG_DIR="$RDS_AGENT_ROOT/config"

cd "$RDS_AGENT_ROOT"

venv/bin/python - <<'PY'
import os
from pathlib import Path

import duckdb
from core.catalog import DatabaseCatalog
from core.semantic import SemanticLayer

db_path = os.environ["RDS_DB_PATH"]
config_dir = Path(os.environ["RDS_CONFIG_DIR"])

con = duckdb.connect(db_path, read_only=True)
actual_tables = {
    row[0]
    for row in con.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'main'
          AND table_type = 'BASE TABLE'
    """).fetchall()
}
con.close()

catalog = DatabaseCatalog(config_dir)
declared_tables = set(catalog.get_all_tables())
semantic = SemanticLayer(config_dir)

print("Actual tables:   ", sorted(actual_tables))
print("Declared tables: ", sorted(declared_tables))
print("Missing metadata:", sorted(actual_tables - declared_tables))
print("Stale metadata:  ", sorted(declared_tables - actual_tables))
print("Metrics:         ", sorted(semantic.metrics))
print("Dimensions:      ", sorted(semantic.dimensions))
print("Terms:           ", len(semantic.terms))

if actual_tables != declared_tables:
    raise SystemExit("schema.yaml does not match the DuckDB tables")
PY
~~~

schema.yaml 中的表集合必须和真实数据库一致。SQLGuard 使用 Catalog 的表集合建立允许访问的白名单；缺少声明的表会导致生成的 SQL 被拒绝。

### 6.2 检查字段、指标和 Join

逐项确认：

- metrics.tables 中的表真实存在；
- metrics.time_column 是真实字段；
- metrics.expression 使用 DuckDB 支持的 SQL；
- dimensions.table 和 dimensions.column 存在；
- joins.left 和 joins.right 两端都存在；
- Join 不会导致订单或金额重复计算；
- 生产查询只访问允许公开的表和列；
- 示例 SQL 可以在只读连接中执行并得到已知结果。

### 6.3 运行 RDS Agent 测试

~~~bash
cd "$RDS_AGENT_ROOT"
venv/bin/python -m pytest -q
~~~

再用一个已知答案的问题做回归测试。不要只验证“能生成 SQL”，还要比较：

- SQL 使用的表和列；
- 默认过滤条件；
- 返回行数；
- 数值结果；
- 时间范围；
- 空结果和错误结果的处理。

## 7. 让 DeepSeek Harness 使用真实数据库

### 7.1 设置环境变量

在启动 Harness 的同一个 shell 中设置：

~~~bash
export RDS_AGENT_ROOT=/absolute/path/to/rds_agent
export HARNESS_ROOT=/absolute/path/to/deepseek-harness
export RDS_DB_PATH=/absolute/path/to/business.duckdb
export RDS_CONFIG_DIR="$RDS_AGENT_ROOT/config"

export DEEPSEEK_API_KEY='<your-deepseek-api-key>'
export RDS_LLM_API_KEY="$DEEPSEEK_API_KEY"
export RDS_LLM_BASE_URL='https://api.deepseek.com'
export RDS_LLM_MODEL='deepseek-chat'

test -n "$RDS_AGENT_ROOT"
test -n "$RDS_DB_PATH"
test -n "$RDS_CONFIG_DIR"
test -f "$RDS_DB_PATH"
test -f "$RDS_CONFIG_DIR/schema.yaml"
test -x "$RDS_AGENT_ROOT/venv/bin/python"
~~~

如果配置放在 config/business/，将变量改为：

~~~bash
export RDS_CONFIG_DIR="$RDS_AGENT_ROOT/config/business"
~~~

当前 MCP server 会从 RDS_CONFIG_DIR 读取 schema.yaml、metrics.yaml、dimensions.yaml 和 terms.yaml。

### 7.2 当前 Harness patch

integration/deepseek-harness.cordis.yml 已经传递：

~~~yaml
RDS_DB_PATH: !!js process.env.RDS_DB_PATH || ':memory:'
~~~

因此：

- 导出 RDS_DB_PATH 时，MCP 使用已有 DuckDB 文件；
- 未导出时，会回退到 :memory: 示例数据库。

当前 patch 没有单独声明 RDS_CONFIG_DIR。如果始终使用项目默认的 config/，无需修改 patch。如果使用独立配置目录，为了避免不同节点的环境继承差异，建议在 patch 的 env 中增加：

~~~yaml
RDS_CONFIG_DIR: !!js process.env.RDS_CONFIG_DIR
~~~

添加这一行后，启动前必须确保 RDS_CONFIG_DIR 已设置，否则 Harness 会因为 MCP 配置环境值为空而失败。

### 7.3 启动 Web profile

~~~bash
cd "$HARNESS_ROOT"

pnpm dsh web \
  --patch "$RDS_AGENT_ROOT/integration/deepseek-harness.cordis.yml" \
  --no-open \
  --port 3081
~~~

--patch 必须位于 --no-open 和 --port 前面。启动日志中应能看到完整的 patch 路径：

~~~text
/absolute/path/to/rds_agent/integration/deepseek-harness.cordis.yml
~~~

不要出现：

~~~text
/integration/deepseek-harness.cordis.yml
~~~

启动前可以只检查配置组合：

~~~bash
pnpm dsh web \
  --patch "$RDS_AGENT_ROOT/integration/deepseek-harness.cordis.yml" \
  --dump-config
~~~

## 8. 验证 Harness 调用

在 Web UI 中提问：

~~~text
请使用 RDS 数据工具查询最近一个月的总销售额，并说明生成的 SQL。
~~~

确认：

1. 工具名为 mcp__rds__query_data；
2. 工具只接收 question 参数；
3. SQL 中使用真实数据库的表和列；
4. 返回结果与人工 SQL 一致；
5. 返回内容包含 SQL、行数、执行时间和数据预览；
6. SQLGuard 拒绝危险 SQL或未授权表；
7. MCP 子进程的 stdout 没有混入日志文本。

Headless 冒烟测试：

~~~bash
cd "$HARNESS_ROOT"

pnpm dsh --profile headless \
  --patch "$RDS_AGENT_ROOT/integration/deepseek-harness.cordis.yml" \
  '请查询最近一个月的总销售额，并返回结果。'
~~~

## 9. 常见问题

### 9.1 查询仍然返回示例数据

检查：

~~~bash
printf 'RDS_DB_PATH=%s\n' "$RDS_DB_PATH"
test -f "$RDS_DB_PATH"
~~~

如果 RDS_DB_PATH 为空，patch 会使用 :memory:。如果路径拼写错误，当前 SDK 可能尝试创建示例数据库。

### 9.2 schema.yaml 找不到

检查：

~~~bash
printf 'RDS_CONFIG_DIR=%s\n' "$RDS_CONFIG_DIR"
test -f "$RDS_CONFIG_DIR/schema.yaml"
~~~

DatabaseCatalog 必须找到 schema.yaml；metrics.yaml、dimensions.yaml 和 terms.yaml 缺失时，语义层会以空配置启动，查询质量会明显下降。

### 9.3 表存在但 SQLGuard 拒绝

确认表名已写入 schema.yaml 的 tables，并且大小写、schema 和 SQL 中使用的名称一致。当前 Guard 以未限定的表名建立白名单，不适合直接混用多个 schema。

### 9.4 指标结果重复或数值过大

通常是 Join 基数或指标表达式错误。检查：

- 订单表和明细表是一对多关系；
- 订单数是否使用 COUNT(DISTINCT order_id)；
- 金额是否在正确的明细粒度上聚合；
- 是否错误地 Join 了另一张一对多表。

### 9.5 MCP 配置提示 env 无效

@deepseek-ai/dsh-mcp-client 要求 env 中的值全部是字符串。不要把未定义环境变量直接传入。启动前检查：

~~~bash
test -n "$DEEPSEEK_API_KEY"
test -n "$RDS_AGENT_ROOT"
test -n "$RDS_DB_PATH"
~~~

YAML 中必须使用 !!js，不能使用单感叹号的 !js。

### 9.6 MCP JSON-RPC 解析失败

stdio 的 stdout 是协议通道。不要在 integration/mcp_server.py 或它依赖的启动代码中使用普通 print() 输出日志。诊断信息必须写 stderr。

## 10. 接入完成标准

一个真实 DuckDB 接入完成，至少应满足：

- DuckDB 文件在当前节点可读，且 RDS_DB_PATH 指向它；
- schema.yaml 的表和列与数据库一致；
- 主键、外键和 Join 关系经过审核；
- 指标计算口径经过业务确认；
- 维度映射值来自真实数据；
- 敏感字段有访问策略；
- 已知问题的 SQL 和结果通过回归测试；
- venv/bin/python -m pytest -q 通过；
- Harness 的 mcp__rds__query_data 调用返回真实数据库结果；
- README、YAML、日志和 Git 历史中没有 API key 或生产数据库文件。

