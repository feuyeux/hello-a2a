#!/bin/bash

# 启动前端应用的脚本
# 自动设置正确的PYTHONPATH并启动前端服务

# 获取脚本所在目录的绝对路径
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"

# 激活虚拟环境
source "$PROJECT_ROOT/venv/bin/activate"

# 定义前端目录
FRONTEND_DIR="$PROJECT_ROOT/hosts/webui/frontend"

# 设置PYTHONPATH
export PYTHONPATH="$PROJECT_ROOT:$FRONTEND_DIR:$PYTHONPATH"

# 设置环境变量（可选）
export A2A_UI_HOST="${A2A_UI_HOST:-0.0.0.0}"
export A2A_UI_PORT="${A2A_UI_PORT:-12000}"

echo "🚀 启动 A2A 前端应用..."
echo "📁 项目根目录: $PROJECT_ROOT"
echo "🐍 PYTHONPATH: $PYTHONPATH"
echo "🌐 服务地址: http://$A2A_UI_HOST:$A2A_UI_PORT"
echo ""

# 切换到前端目录并启动应用
cd "$PROJECT_ROOT/hosts/webui/frontend"
python main.py
