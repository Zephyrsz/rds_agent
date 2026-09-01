#!/bin/bash
# RDS Agent 快速启动脚本

echo "=========================================="
echo "RDS Agent 快速启动"
echo "=========================================="
echo ""

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误: 未找到 Python 3"
    exit 1
fi

echo "✓ Python 版本: $(python3 --version)"

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo ""
    echo "创建虚拟环境..."
    python3 -m venv venv
    echo "✓ 虚拟环境已创建"
fi

# 激活虚拟环境
echo ""
echo "激活虚拟环境..."
source venv/bin/activate

# 安装依赖
echo ""
echo "安装依赖包..."
pip install -q --upgrade pip
pip install -q -r requirements.txt
echo "✓ 依赖包安装完成"

# 检查环境变量
echo ""
if [ -z "$OPENAI_API_KEY" ]; then
    echo "⚠️  警告: 未设置 OPENAI_API_KEY 环境变量"
    echo ""
    echo "请设置 API Key:"
    echo "  export OPENAI_API_KEY=your_api_key"
    echo ""
    echo "或者在 .env 文件中配置"
    exit 1
else
    echo "✓ OPENAI_API_KEY 已配置"
fi

echo ""
echo "=========================================="
echo "启动交互式演示..."
echo "=========================================="
echo ""

python3 examples/interactive_demo.py
