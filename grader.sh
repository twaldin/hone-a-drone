#!/usr/bin/env bash
# grader.sh <planner_path>
# Called by hone as: ./grader.sh <temp_file_with_planner_code>
# Stdout: per-rollout JSON lines + aggregate score float on final line
# Stderr: human-readable per-rollout lines (consumed by GEPA mutator)
set -euo pipefail

PLANNER="$1"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$SCRIPT_DIR/.venv/bin/python"

exec "$PYTHON" "$SCRIPT_DIR/run_parallel.py" \
    --planner "$PLANNER" \
    --levels 0 1 2 3 \
    --seeds-per-level 5 \
    --timeout 35
