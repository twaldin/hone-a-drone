#!/usr/bin/env bash
# grader.sh <arg>
# v1 single-file: arg is a path to a planner.py (or temp .prompt file).
# v2 dir-mode: arg is a directory; we use <dir>/planner.py as the planner.
set -euo pipefail

ARG="$1"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$SCRIPT_DIR/.venv/bin/python"

if [ -d "$ARG" ]; then
    PLANNER="$ARG/planner.py"
else
    PLANNER="$ARG"
fi

exec "$PYTHON" "$SCRIPT_DIR/run_parallel.py" \
    --planner "$PLANNER" \
    --levels 0 1 2 3 \
    --seeds-per-level 5 \
    --timeout 35
