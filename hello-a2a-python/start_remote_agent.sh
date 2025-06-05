#!/bin/bash

# 启动远程代理的脚本 - 专为前端A2A协议交互优化
# 用法: ./start_remote_agent.sh <agent_type> [--host HOST] [--port PORT] [additional_args]
# 例如: ./start_remote_agent.sh google_adk --host localhost --port 10000

# 获取脚本所在目录的绝对路径
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"

# 默认配置
DEFAULT_HOST="localhost"
DEFAULT_PORTS=(
    google_adk:10000
    ag2:10001
    langgraph:10002
    semantickernel:10003
    llama_index_file_chat:10004
)

# 帮助信息
show_help() {
    echo "🚀 A2A 远程代理启动器"
    echo ""
    echo "用法: $0 <agent_type> [options] [additional_args]"
    echo ""
    echo "可用的代理类型:"
    echo "  google_adk         - Google ADK 代理 (默认端口: 10000)"
    echo "  ag2                - AG2 代理 (默认端口: 10001)"
    echo "  langgraph          - LangGraph 代理 (默认端口: 10002)"
    echo "  semantickernel     - Semantic Kernel 代理 (默认端口: 10003)"
    echo "  llama_index_file_chat - LlamaIndex 文件聊天代理 (默认端口: 10004)"
    echo ""
    echo "选项:"
    echo "  --host HOST        指定主机地址 (默认: localhost)"
    echo "  --port PORT        指定端口号 (如未指定，使用默认端口)"
    echo "  --help, -h         显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0 google_adk                           # 使用默认配置启动"
    echo "  $0 ag2 --port 10011                    # 使用自定义端口"
    echo "  $0 semantickernel --host 0.0.0.0       # 绑定所有接口"
    echo ""
    echo "注意:"
    echo "  - 代理启动后，前端可通过 http://HOST:PORT 访问A2A接口"
    echo "  - 在前端Agent页面中添加代理地址进行注册"
}

# 获取默认端口
get_default_port() {
    local agent_type="$1"
    for pair in "${DEFAULT_PORTS[@]}"; do
        if [[ "$pair" == "$agent_type:"* ]]; then
            echo "${pair#*:}"
            return
        fi
    done
    echo "8000" # fallback
}

# 检查参数
if [ $# -lt 1 ] || [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    show_help
    exit 0
fi

AGENT_TYPE="$1"
shift

# 解析参数
HOST="$DEFAULT_HOST"
PORT=""
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
    case $1 in
    --host)
        HOST="$2"
        shift 2
        ;;
    --port)
        PORT="$2"
        shift 2
        ;;
    --help | -h)
        show_help
        exit 0
        ;;
    *)
        EXTRA_ARGS+=("$1")
        shift
        ;;
    esac
done

# 如果没有指定端口，使用默认端口
if [ -z "$PORT" ]; then
    PORT=$(get_default_port "$AGENT_TYPE")
fi

# 验证代理类型
if [ ! -d "$PROJECT_ROOT/remotes/$AGENT_TYPE" ]; then
    echo "❌ 错误: 代理类型 '$AGENT_TYPE' 不存在"
    echo ""
    echo "可用的代理目录:"
    ls -1 "$PROJECT_ROOT/remotes/" | sed 's/^/  /'
    echo ""
    echo "运行 '$0 --help' 查看使用说明"
    exit 1
fi

# 激活虚拟环境
if [ ! -d "$PROJECT_ROOT/venv" ]; then
    echo "❌ 错误: 虚拟环境不存在，请先运行："
    echo "   python -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

source "$PROJECT_ROOT/venv/bin/activate"

# 设置PYTHONPATH
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

echo "🚀 启动 A2A 远程代理"
echo "┌─────────────────────────────────────────┐"
echo "│ 代理类型: $AGENT_TYPE"
echo "│ 监听地址: $HOST:$PORT"
echo "│ A2A 接口: http://$HOST:$PORT"
echo "│ 项目根目录: $PROJECT_ROOT"
echo "└─────────────────────────────────────────┘"

# 保持在项目根目录，使用模块方式运行
cd "$PROJECT_ROOT"

# 构建启动命令
CMD_ARGS=("--host" "$HOST" "--port" "$PORT")
if [ ${#EXTRA_ARGS[@]} -gt 0 ]; then
    CMD_ARGS+=("${EXTRA_ARGS[@]}")
fi

lsof -ti:$PORT | xargs kill -9 2>/dev/null || true

echo "🔧 执行命令: python -m remotes.$AGENT_TYPE ${CMD_ARGS[*]}"
echo "⏰ $(date '+%Y-%m-%d %H:%M:%S') - 代理启动中..."
echo "─────────────────────────────────────────"

# 启动代理 - 使用模块方式运行以支持相对导入
python -m "remotes.$AGENT_TYPE" "${CMD_ARGS[@]}"
