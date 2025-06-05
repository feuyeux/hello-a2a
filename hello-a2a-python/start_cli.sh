#!/bin/bash

# 启动后端CLI组件的脚本

# 获取脚本所在目录的绝对路径
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"

# 激活虚拟环境
source "$PROJECT_ROOT/venv/bin/activate"

# 设置PYTHONPATH
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

echo "🚀 启动 A2A CLI 客户端..."
echo "📁 项目根目录: $PROJECT_ROOT"
echo "🐍 PYTHONPATH: $PYTHONPATH"
echo ""

# 切换到项目根目录并启动CLI
cd "$PROJECT_ROOT"
python -m hosts.cli "$@"
