"""
Test suite for SemanticLayer
"""

import pytest
from pathlib import Path
from datetime import datetime, timedelta
from core.semantic import SemanticLayer


@pytest.fixture
def config_dir(tmp_path):
    """创建临时配置目录"""
    config_path = tmp_path / "config"
    config_path.mkdir()

    # 创建 metrics.yaml
    metrics_yaml = """
metrics:
  sales_amount:
    name: 销售额
    description: 有效订单的净销售额
    expression: SUM(order_items.net_amount)
    tables:
      - orders
      - order_items
    filters:
      - orders.status IN ('paid', 'completed')
    time_column: orders.paid_at
"""
    (config_path / "metrics.yaml").write_text(metrics_yaml, encoding='utf-8')

    # 创建 dimensions.yaml
    dimensions_yaml = """
dimensions:
  region:
    name: 地区
    table: regions
    column: region_name
    mappings:
      华东:
        - EAST_CHINA
"""
    (config_path / "dimensions.yaml").write_text(dimensions_yaml, encoding='utf-8')

    # 创建 terms.yaml
    terms_yaml = """
terms:
  sales_amount:
    standard_name: 销售额
    synonyms:
      - 销售金额
      - 营收
"""
    (config_path / "terms.yaml").write_text(terms_yaml, encoding='utf-8')

    return config_path


def test_load_metrics(config_dir):
    """测试加载指标"""
    semantic = SemanticLayer(config_dir)

    assert "sales_amount" in semantic.metrics
    metric = semantic.metrics["sales_amount"]
    assert metric.display_name == "销售额"
    assert metric.expression == "SUM(order_items.net_amount)"


def test_resolve_metric(config_dir):
    """测试解析指标"""
    semantic = SemanticLayer(config_dir)

    # 精确匹配
    metric = semantic.resolve_metric("sales_amount")
    assert metric is not None
    assert metric.name == "sales_amount"

    # 通过同义词
    metric = semantic.resolve_metric("营收")
    assert metric is not None
    assert metric.name == "sales_amount"


def test_resolve_dimension_value(config_dir):
    """测试解析维度值"""
    semantic = SemanticLayer(config_dir)

    condition = semantic.resolve_dimension_value("region", "华东")
    assert "EAST_CHINA" in condition
    assert "regions.region_name" in condition


def test_resolve_time_range(config_dir):
    """测试解析时间范围"""
    semantic = SemanticLayer(config_dir)

    reference_date = datetime(2024, 9, 1)

    # 最近3天
    result = semantic.resolve_time_range("最近3天", reference_date)
    assert result["start_date"] == reference_date - timedelta(days=3)
    assert result["end_date"] == reference_date

    # 本月
    result = semantic.resolve_time_range("本月", reference_date)
    assert result["start_date"].day == 1
    assert result["end_date"] == reference_date


def test_extract_intent(config_dir):
    """测试意图提取"""
    semantic = SemanticLayer(config_dir)

    question = "最近一个月华东地区的销售额是多少？"
    intent = semantic.extract_intent(question)

    assert "sales_amount" in intent["metrics"] or "销售额" in str(intent)
    assert intent["time_range"] is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
