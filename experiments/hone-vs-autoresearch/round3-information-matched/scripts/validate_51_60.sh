#!/usr/bin/env bash
set -euo pipefail
ROOT="/Users/twaldin/dev/hone-a-drone"
CANDIDATE_DIR="${1:?candidate dir}"
python3 "$ROOT/experiments/hone-vs-autoresearch/scripts/eval_controller.py" \
  --controller-dir "$CANDIDATE_DIR" \
  --levels 0 1 2 3 \
  --seeds 51 52 53 54 55 56 57 58 59 60 \
  --timeout 35 \
  --workers 4
