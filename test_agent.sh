#!/bin/zsh
# Script to run the A2A test client

# Help function
show_help() {
    echo "Usage: ./test_agent.sh [options]"
    echo ""
    echo "Options:"
    echo "  -t, --type TYPE     Agent type to test: 'currency' or 'element' (default: element)"
    echo "  -p, --port PORT     Port number (default: 10000)"
    echo "  -h, --host HOST     Host address (default: localhost)"
    echo "  -q, --query QUERY   Custom query to send"
    echo "  -s, --streaming     Use streaming mode"
    echo "  --tests             Run predefined test suite"
    echo "  --help              Show this help message"
    echo ""
    echo "Examples:"
    echo "  ./test_agent.sh                  # Test element agent with sample queries"
    echo "  ./test_agent.sh -t currency      # Test currency agent with sample queries"
    echo "  ./test_agent.sh -q \"氢元素的信息\"   # Test with a specific query"
}

# Default values
AGENT_TYPE="element"
PORT=10000
HOST="localhost"
QUERY=""
STREAMING=""
RUN_TESTS=""

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
    -q | --query)
        QUERY="$2"
        shift 2
        ;;
    -s | --streaming)
        STREAMING="--streaming"
        shift
        ;;
    --tests)
        RUN_TESTS="--run-tests"
        shift
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

URL="http://$HOST:$PORT"
QUERY_PARAM=""
if [[ -n "$QUERY" ]]; then
    QUERY_PARAM="--query \"$QUERY\""
fi

echo "Testing $AGENT_TYPE agent at $URL"
cd $(dirname "$0")/0.2

# Construct the command
CMD="uv run a2a_test_client.py --url $URL --agent-type $AGENT_TYPE $STREAMING $RUN_TESTS"
if [[ -n "$QUERY" ]]; then
    CMD="$CMD --query \"$QUERY\""
fi

# Execute the command
eval "$CMD"
