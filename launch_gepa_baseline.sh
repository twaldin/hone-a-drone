#!/usr/bin/env bash
# Launch the GEPA-only ablation arm. Run this ONLY after the v3 full-stack
# ablation completes (cairn 2026-04-21: sequential, not parallel, to avoid
# cross-run rate limits on cc-sonnet via harness + direct anthropic SDK).
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"

# Abort if v3 full-stack is still grinding
if pgrep -f "hone run.*mutator-pool" > /dev/null 2>&1; then
    echo "ERROR: v3 full-stack (PID $(pgrep -f 'hone run.*mutator-pool' | head -1)) still running."
    echo "Wait for it to finish before launching the GEPA baseline."
    exit 1
fi

# Source the API key (from Tim's dev env file)
if [ ! -f /Users/twaldin/dev/.env ]; then
    echo "ERROR: /Users/twaldin/dev/.env not found"
    exit 1
fi
set -a
. /Users/twaldin/dev/.env
set +a

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
    echo "ERROR: ANTHROPIC_API_KEY not set after sourcing .env"
    exit 1
fi

mkdir -p "$REPO/runs-v3-ablation"
LOG="$REPO/runs-v3-ablation/gepa-baseline.log"

echo "Launching GEPA-only baseline. Log: $LOG"
cd "$REPO"
"$REPO/.venv/bin/python" "$REPO/run_gepa_baseline.py" \
    --budget 100 \
    --model claude-sonnet-4-6 \
    --output-dir .hone-gepa-baseline \
    > "$LOG" 2>&1 &
PID=$!
echo "launched PID=$PID"
echo "tail $LOG to monitor"
