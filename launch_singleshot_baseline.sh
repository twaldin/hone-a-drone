#!/usr/bin/env bash
# Launch the single-shot baseline ablation arm. Run ONLY after v3 full-stack
# completes (cairn 2026-04-21: sequential, not parallel, to avoid cross-run
# cc-sonnet rate limit hits via harness on two concurrent runs).
#
# No ANTHROPIC_API_KEY needed. Uses claude-code OAuth (Max sub) via harness,
# with prompt scaffolding that forces single-completion / no-tool-use.
# Baseline contrast: "agent-with-tools vs agent-with-tools-disabled".
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"

if pgrep -f "hone run.*mutator-pool" > /dev/null 2>&1; then
    echo "ERROR: v3 full-stack (PID $(pgrep -f 'hone run.*mutator-pool' | head -1)) still running."
    echo "Wait for it to finish before launching the baseline."
    exit 1
fi

mkdir -p "$REPO/runs-v3-ablation"
LOG="$REPO/runs-v3-ablation/singleshot-baseline.log"

echo "Launching claude-code single-shot (no-tools) baseline. Log: $LOG"
cd "$REPO"
"$REPO/.venv/bin/python" "$REPO/run_singleshot_baseline.py" \
    --budget 100 \
    --model sonnet \
    --output-dir .hone-singleshot-baseline \
    > "$LOG" 2>&1 &
PID=$!
echo "launched PID=$PID"
echo "tail $LOG to monitor"
