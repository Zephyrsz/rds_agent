#!/bin/bash
# Git 初始化和分支创建脚本

set -e

echo "=========================================="
echo "Git 仓库初始化和分支创建"
echo "=========================================="
echo ""

cd /Users/rgwei/pj/pj_data/rds_agent

# 1. 清理可能存在的锁文件
echo "1. 清理 Git 锁文件..."
if [ -f .git/index.lock ]; then
    rm -f .git/index.lock
    echo "   ✓ 锁文件已删除"
else
    echo "   ✓ 无需清理"
fi

# 2. 检查暂存区状态
echo ""
echo "2. 检查暂存区..."
git status --short | head -10
echo "   ... (共 $(git status --short | wc -l) 个文件已暂存)"

# 3. 完成首次提交到 master
echo ""
echo "3. 提交到 master 分支..."
git commit -m "Initial commit: RDS Agent - LangGraph based data analysis agent

Features:
- Complete LangGraph workflow with 10+ nodes
- Business semantic layer with metrics, dimensions, and terms
- Multi-layer SQL security (AST parsing, whitelist, validation)
- Automatic SQL generation and repair with LLM
- Result validation and answer composition
- DuckDB adapter with sample data
- 5 integration methods: MCP Server, REST API, LangChain Tool, Function Calling, Python SDK
- Comprehensive documentation and examples

Project Stats:
- 20 Python files (~2200 lines)
- 5 YAML configs (~200 lines)
- 5 Markdown docs (~2000 lines)
- 3 test files
- 2 runnable examples
- 5 integration implementations"

echo "   ✓ 首次提交完成"

# 4. 创建并切换到新分支
echo ""
echo "4. 创建新分支 meta-in-sqlite..."
git checkout -b meta-in-sqlite

echo "   ✓ 分支创建成功"

# 5. 显示当前状态
echo ""
echo "=========================================="
echo "完成！当前状态："
echo "=========================================="
echo ""
echo "分支列表:"
git branch -v
echo ""
echo "提交历史:"
git log --oneline --graph --all
echo ""
echo "当前分支:"
git branch --show-current
echo ""
echo "工作区状态:"
git status
