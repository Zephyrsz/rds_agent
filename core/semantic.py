"""
SemanticLayer: 业务语义层

负责将用户的业务语言映射到数据库查询语言
"""

from typing import Dict, List, Optional, Any
import yaml
from pathlib import Path
from datetime import datetime, timedelta
import re


class MetricDefinition:
    """指标定义"""

    def __init__(
        self,
        name: str,
        display_name: str,
        description: str,
        expression: str,
        tables: List[str],
        filters: Optional[List[str]] = None,
        time_column: Optional[str] = None,
    ):
        self.name = name
        self.display_name = display_name
        self.description = description
        self.expression = expression
        self.tables = tables
        self.filters = filters or []
        self.time_column = time_column


class DimensionDefinition:
    """维度定义"""

    def __init__(
        self,
        name: str,
        display_name: str,
        table: str,
        column: str,
        mappings: Optional<Dict[str, List[str]]] = None,
    ):
        self.name = name
        self.display_name = display_name
        self.table = table
        self.column = column
        self.mappings = mappings or {}


class SemanticLayer:
    """
    业务语义层

    负责：
    1. 解析业务指标（如"销售额"→ SUM(net_amount)）
    2. 解析维度（如"华东"→ region='EAST_CHINA'）
    3. 解析时间范围（如"最近三个月"）
    4. 解析业务术语和同义词
    """

    def __init__(self, config_dir: Path):
        self.config_dir = Path(config_dir)
        self.metrics: Dict[str, MetricDefinition] = {}
        self.dimensions: Dict[str, DimensionDefinition] = {}
        self.terms: Dict[str, str] = {}  # 业务术语 -> 标准名称
        self.synonyms: Dict[str, List[str]] = {}  # 标准名称 -> 同义词列表

        self._load_config()

    def _load_config(self):
        """加载配置"""
        self._load_metrics()
        self._load_dimensions()
        self._load_terms()

    def _load_metrics(self):
        """加载指标定义"""
        metrics_file = self.config_dir / "metrics.yaml"
        if not metrics_file.exists():
            return

        with open(metrics_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        for metric_name, metric_info in config.get("metrics", {}).items():
            self.metrics[metric_name] = MetricDefinition(
                name=metric_name,
                display_name=metric_info.get("name", metric_name),
                description=metric_info.get("description", ""),
                expression=metric_info.get("expression", ""),
                tables=metric_info.get("tables", []),
                filters=metric_info.get("filters", []),
                time_column=metric_info.get("time_column"),
            )

    def _load_dimensions(self):
        """加载维度定义"""
        dimensions_file = self.config_dir / "dimensions.yaml"
        if not dimensions_file.exists():
            return

        with open(dimensions_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        for dim_name, dim_info in config.get("dimensions", {}).items():
            self.dimensions[dim_name] = DimensionDefinition(
                name=dim_name,
                display_name=dim_info.get("name", dim_name),
                table=dim_info.get("table", ""),
                column=dim_info.get("column", ""),
                mappings=dim_info.get("mappings", {}),
            )

    def _load_terms(self):
        """加载业务术语"""
        terms_file = self.config_dir / "terms.yaml"
        if not terms_file.exists():
            return

        with open(terms_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        # 加载术语映射
        for standard_name, term_info in config.get("terms", {}).items():
            synonyms = term_info.get("synonyms", [])
            self.synonyms[standard_name] = synonyms

            # 建立反向索引：同义词 -> 标准名称
            self.terms[standard_name.lower()] = standard_name
            for syn in synonyms:
                self.terms[syn.lower()] = standard_name

    def resolve_metric(self, name: str) -> Optional[MetricDefinition]:
        """
        解析指标

        支持：
        - 精确匹配指标名称
        - 通过同义词查找
        """
        # 精确匹配
        if name in self.metrics:
            return self.metrics[name]

        # 通过术语查找
        name_lower = name.lower()
        if name_lower in self.terms:
            standard_name = self.terms[name_lower]
            if standard_name in self.metrics:
                return self.metrics[standard_name]

        # 模糊匹配（搜索显示名称）
        for metric in self.metrics.values():
            if name.lower() in metric.display_name.lower():
                return metric

        return None

    def resolve_dimension(self, name: str) -> Optional[DimensionDefinition]:
        """解析维度"""
        # 精确匹配
        if name in self.dimensions:
            return self.dimensions[name]

        # 通过术语查找
        name_lower = name.lower()
        if name_lower in self.terms:
            standard_name = self.terms[name_lower]
            if standard_name in self.dimensions:
                return self.dimensions[standard_name]

        # 模糊匹配
        for dim in self.dimensions.values():
            if name.lower() in dim.display_name.lower():
                return dim

        return None

    def resolve_dimension_value(self, dimension_name: str, value: str) -> Optional[str]:
        """
        解析维度值

        例如："华东" -> "region IN ('Shanghai', 'Jiangsu', 'Zhejiang')"
        """
        dim = self.resolve_dimension(dimension_name)
        if not dim:
            return None

        # 检查是否有映射
        if value in dim.mappings:
            mapped_values = dim.mappings[value]
            if len(mapped_values) == 1:
                return f"{dim.table}.{dim.column} = '{mapped_values[0]}'"
            else:
                values_str = ", ".join(f"'{v}'" for v in mapped_values)
                return f"{dim.table}.{dim.column} IN ({values_str})"

        # 没有映射，直接使用值
        return f"{dim.table}.{dim.column} = '{value}'"

    def resolve_time_range(self, expression: str, reference_date: Optional[datetime] = None) -> Dict[str, Any]:
        """
        解析时间范围表达式

        支持的格式：
        - "最近3个月" / "last 3 months"
        - "最近7天" / "last 7 days"
        - "本月" / "this month"
        - "上月" / "last month"
        - "今年" / "this year"
        - "2024年1月" / "January 2024"

        返回: {
            "start_date": datetime,
            "end_date": datetime,
            "description": str
        }
        """
        if reference_date is None:
            reference_date = datetime.now()

        expression_lower = expression.lower()

        # 最近 N 天/周/月
        match = re.search(r'最近\s*(\d+)\s*(天|周|月|年)', expression)
        if not match:
            match = re.search(r'last\s+(\d+)\s+(day|week|month|year)s?', expression_lower)

        if match:
            count = int(match.group(1))
            unit = match.group(2)

            if unit in ['天', 'day']:
                start_date = reference_date - timedelta(days=count)
            elif unit in ['周', 'week']:
                start_date = reference_date - timedelta(weeks=count)
            elif unit in ['月', 'month']:
                # 简化处理：每月按30天计算
                start_date = reference_date - timedelta(days=count * 30)
            elif unit in ['年', 'year']:
                start_date = reference_date - timedelta(days=count * 365)
            else:
                start_date = reference_date

            return {
                "start_date": start_date,
                "end_date": reference_date,
                "description": f"从 {start_date.strftime('%Y-%m-%d')} 到 {reference_date.strftime('%Y-%m-%d')}"
            }

        # 本月
        if '本月' in expression or 'this month' in expression_lower:
            start_date = reference_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            return {
                "start_date": start_date,
                "end_date": reference_date,
                "description": f"本月 ({start_date.strftime('%Y-%m')})"
            }

        # 上月
        if '上月' in expression or 'last month' in expression_lower:
            # 计算上个月的第一天
            first_of_this_month = reference_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            end_date = first_of_this_month - timedelta(days=1)
            start_date = end_date.replace(day=1)
            return {
                "start_date": start_date,
                "end_date": end_date,
                "description": f"上月 ({start_date.strftime('%Y-%m')})"
            }

        # 今年
        if '今年' in expression or 'this year' in expression_lower:
            start_date = reference_date.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            return {
                "start_date": start_date,
                "end_date": reference_date,
                "description": f"今年 ({reference_date.year})"
            }

        # 默认：最近30天
        start_date = reference_date - timedelta(days=30)
        return {
            "start_date": start_date,
            "end_date": reference_date,
            "description": "最近30天（默认）"
        }

    def resolve_business_term(self, text: str) -> str:
        """
        解析业务术语

        将文本中的业务术语替换为标准名称
        """
        result = text
        for term, standard_name in self.terms.items():
            # 使用词边界匹配，避免部分匹配
            pattern = r'\b' + re.escape(term) + r'\b'
            result = re.sub(pattern, standard_name, result, flags=re.IGNORECASE)
        return result

    def get_metric_tables(self, metric_name: str) -> List[str]:
        """获取指标涉及的表"""
        metric = self.resolve_metric(metric_name)
        if metric:
            return metric.tables
        return []

    def get_metric_filters(self, metric_name: str) -> List[str]:
        """获取指标的默认过滤条件"""
        metric = self.resolve_metric(metric_name)
        if metric:
            return metric.filters
        return []

    def extract_intent(self, question: str) -> Dict[str, Any]:
        """
        从问题中提取结构化意图

        这是一个简化版本，实际生产环境会使用 LLM 来完成
        """
        intent = {
            "metrics": [],
            "dimensions": [],
            "filters": {},
            "time_range": None,
            "question_type": "simple_query"  # simple_query, comparison, trend, diagnostic
        }

        question_lower = question.lower()

        # 识别指标
        for metric_name, metric_def in self.metrics.items():
            if metric_def.display_name.lower() in question_lower:
                intent["metrics"].append(metric_name)

        # 识别维度
        for dim_name, dim_def in self.dimensions.items():
            if dim_def.display_name.lower() in question_lower:
                intent["dimensions"].append(dim_name)

        # 识别时间范围
        time_keywords = ['最近', '本月', '上月', '今年', 'last', 'this month', 'this year']
        for keyword in time_keywords:
            if keyword in question_lower:
                # 提取包含时间关键词的片段
                time_match = re.search(r'(\S*' + re.escape(keyword) + r'\S*\s+\d+\S*)', question, re.IGNORECASE)
                if time_match:
                    intent["time_range"] = time_match.group(1)
                    break

        # 识别问题类型
        if any(word in question_lower for word in ['对比', '比较', 'compare', 'vs']):
            intent["question_type"] = "comparison"
        elif any(word in question_lower for word in ['趋势', '变化', 'trend', 'change']):
            intent["question_type"] = "trend"
        elif any(word in question_lower for word in ['为什么', '原因', 'why', 'reason']):
            intent["question_type"] = "diagnostic"

        return intent
