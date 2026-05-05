#!/usr/bin/env bash
set -euo pipefail
ROOT="/Users/twaldin/dev/hone-a-drone"
LOCK="$ROOT/experiments/hone-vs-autoresearch/round1-clean/scorer.lock"
CANDIDATE_DIR="${1:-.}"
mkdir -p "$(dirname "$LOCK")"
python3 - "$LOCK" "$ROOT" "$CANDIDATE_DIR" <<'PY'
import fcntl
import subprocess
import sys
from pathlib import Path
lock_path, root, candidate = sys.argv[1:4]
root = Path(root)
candidate = Path(candidate).resolve()
with open(lock_path, "w") as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    proc = subprocess.run([
        sys.executable,
        str(root / "experiments/hone-vs-autoresearch/scripts/eval_controller.py"),
        "--controller-dir", str(candidate),
        "--levels", "0", "1", "2", "3",
        "--seeds", "41", "42", "43", "44", "45", "46", "47", "48", "49", "50",
        "--timeout", "35",
        "--workers", "4",
    ], cwd=str(root))
    raise SystemExit(proc.returncode)
PY
