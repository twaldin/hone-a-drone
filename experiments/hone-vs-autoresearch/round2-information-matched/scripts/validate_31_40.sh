#!/usr/bin/env bash
set -euo pipefail
ROOT="/Users/twaldin/dev/hone-a-drone"
CANDIDATE_DIR="${1:?candidate dir}"
python3 "$ROOT/experiments/hone-vs-autoresearch/scripts/eval_controller.py" \
  --controller-dir "$CANDIDATE_DIR" \
  --levels 0 1 2 3 \
  --seeds 31 32 33 34 35 36 37 38 39 40 \
  --timeout 35 \
  --workers 4
