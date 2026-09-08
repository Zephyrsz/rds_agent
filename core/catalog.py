"""
DatabaseCatalog: 管理和检索数据库 Schema 信息
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set
import yaml
from pathlib import Path


@dataclass
class ColumnInfo:
    """Normalized column metadata used by both YAML and SQLite adapters."""

    type: str
    description: str = ""
    primary_key: bool = False
    foreign_key: Optional[str] = None
    enum: Optional[List[str]] = None

    def get(self, key: str, default: Any = None) -> Any:
        """Provide the mapping-style API used by the YAML catalog."""
        return getattr(self, key, default)

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)


class TableDefinition:
    """表定义"""

    def __init__(
        self,
        name: str,
        description: str,
        columns: Dict,
        tags: Optional[List[str]] = None,
        grain: Optional[str] = None,
        entities: Optional[List[Dict[str, Any]]] = None,
    ):
        self.name = name
        self.description = description
        self.columns = columns
        self.tags = tags or []
        self.grain = grain
        self.entities = entities or []

    def get_ddl_summary(self) -> str:
        """生成表结构摘要"""
        lines = [f"Table: {self.name}", f"Description: {self.description}", "Columns:"]
        for col_name, col_info in self.columns.items():
            col_type = col_info.get("type", "UNKNOWN")
            col_desc = col_info.get("description", "")
            pk = " [PK]" if col_info.get("primary_key") else ""
            fk = f" [FK -> {col_info.get('foreign_key')}]" if col_info.get("foreign_key") else ""
            lines.append(f"  - {col_name}: {col_type}{pk}{fk} - {col_desc}")
        return "\n".join(lines)


class JoinPath:
    """Join 路径定义"""

    def __init__(
        self,
        left: Optional[str] = None,
        right: Optional[str] = None,
        cardinality: str = "many_to_one",
        description: str = "",
        *,
        left_table: Optional[str] = None,
        left_column: Optional[str] = None,
        right_table: Optional[str] = None,
        right_column: Optional[str] = None,
        join_type: str = "INNER",
        name: Optional[str] = None,
        auto_join: bool = True,
        priority: int = 100,
        fan_out_risk: bool = False,
        temporal_validity: Optional[str] = None,
    ):
        if left is None and left_table and left_column:
            left = f"{left_table}.{left_column}"
        if right is None and right_table and right_column:
            right = f"{right_table}.{right_column}"
        if not left or not right:
            raise ValueError("JoinPath requires left/right column references")

        self.left = left  # e.g., "orders.customer_id"
        self.right = right  # e.g., "customers.id"
        self.cardinality = cardinality  # one_to_one, many_to_one, one_to_many, many_to_many
        self.description = description
        self.join_type = join_type.upper()
        self.name = name or f"{left}_to_{right}".replace(".", "_")
        self.auto_join = auto_join
        self.priority = priority
        self.fan_out_risk = fan_out_risk
        self.temporal_validity = temporal_validity

        # 解析表名
        self.left_table = left.split('.')[0]
        self.right_table = right.split('.')[0]


class DatabaseCatalog:
    """
    数据库目录管理器

    负责：
    1. 加载和管理 Schema 配置
    2. 根据问题检索相关表和字段
    3. 提供 Join 路径
    4. 返回字段说明和示例值
    """

    def __init__(self, config_dir: Path):
        self.config_dir = Path(config_dir)
        self.tables: Dict[str, TableDefinition] = {}
        self.joins: List[JoinPath] = []
        self.join_graph: Dict[str, List[JoinPath]] = {}  # table -> list of joins

        self._load_schema()

    def _load_schema(self):
        """加载 Schema 配置"""
        schema_file = self.config_dir / "schema.yaml"
        if not schema_file.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_file}")

        with open(schema_file, 'r', encoding='utf-8') as f:
            schema_config = yaml.safe_load(f)

        # 加载表定义
        for table_name, table_info in schema_config.get("tables", {}).items():
            self.tables[table_name] = TableDefinition(
                name=table_name,
                description=table_info.get("description", ""),
                columns=table_info.get("columns", {}),
                tags=table_info.get("tags", []),
                grain=table_info.get("grain"),
                entities=table_info.get("entities", []),
            )

        # 加载 Join 关系
        for join_info in schema_config.get("joins", []):
            join_path = JoinPath(
                left=join_info["left"],
                right=join_info["right"],
                cardinality=join_info.get("cardinality", "many_to_one"),
                description=join_info.get("description", ""),
                join_type=join_info.get("join_type", "INNER"),
                name=join_info.get("name"),
                auto_join=join_info.get("auto_join", True),
                priority=join_info.get("priority", 100),
                fan_out_risk=join_info.get("fan_out_risk", False),
                temporal_validity=join_info.get("temporal_validity"),
            )
            self.joins.append(join_path)

            # 构建 Join 图
            if join_path.left_table not in self.join_graph:
                self.join_graph[join_path.left_table] = []
            if join_path.right_table not in self.join_graph:
                self.join_graph[join_path.right_table] = []

            self.join_graph[join_path.left_table].append(join_path)
            self.join_graph[join_path.right_table].append(join_path)

    def search_schema(self, question: str, max_tables: int = 5) -> Dict:
        """
        根据问题检索相关 Schema

        简单实现：基于关键词匹配
        生产环境可以使用向量检索或更复杂的相关性算法
        """
        question_lower = question.lower()

        # 计算每个表的相关性分数
        table_scores = {}
        for table_name, table_def in self.tables.items():
            score = 0

            # 表名匹配
            if table_name.lower() in question_lower:
                score += 10

            # 表描述匹配
            desc_words = table_def.description.lower().split()
            for word in desc_words:
                if word in question_lower:
                    score += 2

            # 列名匹配
            for col_name, col_info in table_def.columns.items():
                if col_name.lower() in question_lower:
                    score += 5
                col_desc = col_info.get("description", "").lower()
                if col_desc and any(word in question_lower for word in col_desc.split()):
                    score += 1

            # 标签匹配
            for tag in table_def.tags:
                if tag.lower() in question_lower:
                    score += 3

            if score > 0:
                table_scores[table_name] = score

        # 选择得分最高的表
        top_tables = sorted(table_scores.items(), key=lambda x: x[1], reverse=True)[:max_tables]
        selected_tables = [table_name for table_name, _ in top_tables]

        # 获取这些表的完整定义
        schema_context = {
            "tables": {},
            "joins": []
        }

        for table_name in selected_tables:
            schema_context["tables"][table_name] = self.tables[table_name].get_ddl_summary()

        # 获取相关的 Join 路径
        schema_context["joins"] = self.get_join_paths(selected_tables)

        return schema_context

    def get_table(self, name: str) -> Optional[TableDefinition]:
        """获取表定义"""
        return self.tables.get(name)

    def get_column(self, table: str, column: str) -> Optional[Dict]:
        """获取列定义"""
        table_def = self.get_table(table)
        if table_def:
            return table_def.columns.get(column)
        return None

    def get_join_paths(self, tables: List[str]) -> List[str]:
        """
        获取表之间的 Join 路径

        返回格式: ["orders.customer_id = customers.id", ...]
        """
        if len(tables) <= 1:
            return []

        table_set = set(tables)
        relevant_joins = []

        for join in self.joins:
            if join.left_table in table_set and join.right_table in table_set:
                join_str = f"{join.left} = {join.right}"
                if join.cardinality:
                    join_str += f" ({join.cardinality})"
                if join.description:
                    join_str += f" -- {join.description}"
                relevant_joins.append(join_str)

        return relevant_joins

    def find_join_path(self, from_table: str, to_table: str) -> Optional[List[JoinPath]]:
        """
        查找两个表之间的 Join 路径（BFS）

        返回 Join 序列，如果找不到则返回 None
        """
        if from_table == to_table:
            return []

        if from_table not in self.join_graph or to_table not in self.join_graph:
            return None

        # BFS 查找路径
        queue = [(from_table, [])]
        visited = {from_table}

        while queue:
            current_table, path = queue.pop(0)

            if current_table not in self.join_graph:
                continue

            for join in self.join_graph[current_table]:
                # 确定下一个表
                next_table = join.right_table if join.left_table == current_table else join.left_table

                if next_table == to_table:
                    return path + [join]

                if next_table not in visited:
                    visited.add(next_table)
                    queue.append((next_table, path + [join]))

        return None

    def get_all_tables(self) -> List[str]:
        """获取所有表名"""
        return list(self.tables.keys())

    def get_table_columns(self, table_name: str) -> List[str]:
        """获取表的所有列名"""
        table_def = self.get_table(table_name)
        if table_def:
            return list(table_def.columns.keys())
        return []
