#!/bin/zsh
# Script to run A2A agents with UV

# Help function
show_help() {
    echo "Usage: ./run_agent.sh [options]"
    echo ""
    echo "Options:"
    echo "  -t, --type TYPE     Agent type: 'currency' or 'element' (default: element)"
    echo "  -p, --port PORT     Port number (default: 10000)"
    echo "  -h, --host HOST     Host address (default: localhost)"
    echo "  --help              Show this help message"
    echo ""
    echo "Examples:"
    echo "  ./run_agent.sh                  # Run element agent on default port"
    echo "  ./run_agent.sh -t currency      # Run currency agent on default port"
    echo "  ./run_agent.sh -p 8080          # Run element agent on port 8080"
}

# Default values
AGENT_TYPE="element"
PORT=10000
HOST="localhost"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    key="$1"
    case $key in
    -t | --type)
        AGENT_TYPE="$2"
        shift 2
        ;;
    -p | --port)
        PORT="$2"
        shift 2
        ;;
    -h | --host)
        HOST="$2"
        shift 2
        ;;
    --help)
        show_help
        exit 0
        ;;
    *)
        echo "Unknown option: $1"
        show_help
        exit 1
        ;;
    esac
done

# Validate agent type
if [[ "$AGENT_TYPE" != "currency" && "$AGENT_TYPE" != "element" ]]; then
    echo "Error: Agent type must be either 'currency' or 'element'"
    exit 1
fi

echo "Starting $AGENT_TYPE agent on http://$HOST:$PORT/"
cd $(dirname "$0")/0.2
uv run . --agent-type $AGENT_TYPE --host $HOST --port $PORT
