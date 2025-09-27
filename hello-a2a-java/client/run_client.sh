#!/usr/bin/env bash
set -euo pipefail

# client/run_client.sh
# macOS / Linux launcher for the client module.
# Usage:
#   ./run_client.sh --message "your message" --server-url http://localhost:11000
# If no arguments are provided, a sensible default Chinese test message is used.

# Ensure UTF-8 for Maven and the JVM
export LC_ALL=en_US.UTF-8
export LANG=en_US.UTF-8

DEFAULT_MESSAGE='你能掷一个 12 面的骰子并检查结果是否为素数吗?'

# Helper: escape double quotes and backslashes for embedding inside a double-quoted string
_escape_for_maven() {
  local s="$1"
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  printf '%s' "$s"
}

if [ $# -eq 0 ]; then
  # No args: use the default message
  escaped=$(_escape_for_maven "$DEFAULT_MESSAGE")
  execArgs="--message \"${escaped}\""
else
  # Build a single exec.args string where each token that contains whitespace
  # is wrapped in escaped double quotes, so Maven's exec plugin receives
  # the intended arguments (e.g. --message "... with spaces ...").
  parts=()
  for token in "$@"; do
    if [[ "$token" =~ [[:space:]] ]]; then
      esc=$(_escape_for_maven "$token")
      parts+=("\"${esc}\"")
    else
      parts+=("$token")
    fi
  done
  execArgs="${parts[*]}"
fi

# Optional: enable Log4j2 debug output by setting LOG4J2_DEBUG=1 in the environment.
# Example: LOG4J2_DEBUG=1 ./client/run_client.sh --help
EXEC_JVM_ARGS=""
if [ "${LOG4J2_DEBUG:-}" = "1" ] || [ "${LOG4J2_DEBUG:-}" = "true" ]; then
  EXEC_JVM_ARGS="-Dlog4j2.debug=true"
fi

# Run the client via Maven exec plugin. The POM already supplies the mainClass.
# Use -pl to limit to the client module so this works when executed from repo root.
if [ -n "$EXEC_JVM_ARGS" ]; then
  mvn -pl client exec:java -Dexec.jvmArgs="$EXEC_JVM_ARGS" -Dexec.args="$execArgs"
else
  mvn -pl client exec:java -Dexec.args="$execArgs"
fi
