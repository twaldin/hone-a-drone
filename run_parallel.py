"""Parallel rollout fanout. Fans out run_rollout.py subprocesses, aggregates, scores.

Stdout: one JSON line per rollout + aggregate score float on the final line.
Stderr: one human-readable line per rollout (for hone/GEPA mutator consumption).

Usage:
    python run_parallel.py --planner <path> [--levels 0 1 2 3] [--seeds-per-level 5]

Score formula (higher = better):
  per-rollout: completed → 1 + 10/lap_time; crashed → 0.5*(gates/n); DNF → gates/n
  per-level: average across seeds
  aggregate: weighted sum (L0=1, L1=1.5, L2=2, L3=3) / total_weight
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

PYTHON = str(Path(__file__).parent / ".venv" / "bin" / "python")
RUNNER = str(Path(__file__).parent / "run_rollout.py")
RUNS_DIR = Path(__file__).parent / "runs"
LEVEL_WEIGHTS = {0: 1.0, 1: 1.5, 2: 2.0, 3: 3.0}


def _run_one(planner: str, level: int, seed: int, timeout: float) -> dict:
    try:
        proc = subprocess.run(
            [PYTHON, RUNNER, "--planner", planner, "--level", str(level),
             "--seed", str(seed), "--timeout", str(timeout)],
            capture_output=True,
            text=True,
            timeout=timeout + 15,
        )
    except subprocess.TimeoutExpired:
        return {"level": level, "seed": seed, "error": "subprocess_timeout",
                "gates_passed": 0, "n_gates": 4, "lap_time": timeout,
                "crashed": True, "crash_reason": "timeout",
                "max_velocity": 0.0, "gate_times": [], "approach_angles": [],
                "loop_latency_p50": 0.0, "loop_latency_p99": 0.0}

    stdout = proc.stdout.strip()
    if proc.returncode != 0 or not stdout:
        err = (proc.stderr or "")[-300:]
        return {"level": level, "seed": seed, "error": f"rollout_failed: {err}",
                "gates_passed": 0, "n_gates": 4, "lap_time": timeout,
                "crashed": True, "crash_reason": "import_error",
                "max_velocity": 0.0, "gate_times": [], "approach_angles": [],
                "loop_latency_p50": 0.0, "loop_latency_p99": 0.0}

    last_line = next((l for l in reversed(stdout.split("\n")) if l.strip()), None)
    try:
        return json.loads(last_line)
    except (json.JSONDecodeError, TypeError) as e:
        return {"level": level, "seed": seed, "error": f"json_parse: {e}",
                "gates_passed": 0, "n_gates": 4, "lap_time": timeout,
                "crashed": True, "crash_reason": "parse_error",
                "max_velocity": 0.0, "gate_times": [], "approach_angles": [],
                "loop_latency_p50": 0.0, "loop_latency_p99": 0.0}


def _score_rollout(r: dict) -> float:
    gp = r.get("gates_passed", 0)
    ng = max(r.get("n_gates", 4), 1)
    t = max(r.get("lap_time", 30.0), 0.1)
    if r.get("crash_reason") == "completed":
        return 1.0 + 10.0 / t
    if r.get("crashed"):
        return 0.5 * gp / ng
    return float(gp) / ng


def _fmt_stderr(r: dict) -> str:
    gp = r.get("gates_passed", 0)
    ng = r.get("n_gates", 4)
    gt = r.get("gate_times", [])
    aa = r.get("approach_angles", [])
    err = r.get("error", "")
    if err:
        return (f"level={r['level']} seed={r['seed']} ERROR={err}")
    return (
        f"level={r['level']} seed={r['seed']} "
        f"gates={gp}/{ng} "
        f"lap_time={r.get('lap_time', 0):.2f}s "
        f"crashed={r.get('crashed')} crash_reason={r.get('crash_reason')} "
        f"max_vel={r.get('max_velocity', 0):.2f}m/s "
        f"gate_times={gt} "
        f"approach_angles={aa} "
        f"latency_p50={r.get('loop_latency_p50', 0):.2f}ms "
        f"latency_p99={r.get('loop_latency_p99', 0):.2f}ms"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--planner", required=True)
    parser.add_argument("--levels", type=int, nargs="+", default=[0, 1, 2, 3])
    parser.add_argument("--seeds-per-level", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=35.0)
    parser.add_argument("--run-tag", default=None, help="Optional tag for runs/ CSV filename")
    args = parser.parse_args()

    combos = [
        (lv, seed)
        for lv in args.levels
        for seed in range(1, args.seeds_per_level + 1)
    ]
    n_workers = min(len(combos), os.cpu_count() or 8)

    t_start = time.time()
    results: list[dict] = []

    # Thread pool: each thread spawns one subprocess. JAX JIT isolation per subprocess.
    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        futures = {
            pool.submit(_run_one, args.planner, lv, seed, args.timeout): (lv, seed)
            for lv, seed in combos
        }
        for future in as_completed(futures):
            r = future.result()
            print(_fmt_stderr(r), file=sys.stderr, flush=True)
            print(json.dumps(r), flush=True)
            results.append(r)

    wall = time.time() - t_start
    print(
        f"benchmark: {len(combos)} rollouts in {wall:.1f}s "
        f"({wall / max(len(combos), 1):.1f}s avg) workers={n_workers}",
        file=sys.stderr,
    )

    # --- Score aggregation ---
    results_by_level: dict[int, list[dict]] = {lv: [] for lv in args.levels}
    for r in results:
        lv = r.get("level", -1)
        if lv in results_by_level:
            results_by_level[lv].append(r)

    level_scores: dict[int, float] = {}
    for lv, rs in results_by_level.items():
        level_scores[lv] = (sum(_score_rollout(r) for r in rs) / len(rs)) if rs else 0.0

    total_w = sum(LEVEL_WEIGHTS.get(lv, 1.0) for lv in args.levels)
    aggregate = sum(LEVEL_WEIGHTS.get(lv, 1.0) * level_scores.get(lv, 0.0) for lv in args.levels) / total_w

    score_str = "  ".join(f"L{lv}={level_scores.get(lv, 0):.3f}" for lv in args.levels)
    print(f"per-level scores: {score_str}", file=sys.stderr)
    print(f"aggregate (weighted): {aggregate:.4f}", file=sys.stderr)

    # --- Persist to runs/ CSV ---
    RUNS_DIR.mkdir(exist_ok=True)
    tag = args.run_tag or datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S")
    csv_path = RUNS_DIR / f"{tag}.csv"
    if results:
        fieldnames = list(results[0].keys()) + ["rollout_score"]
        with open(csv_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            w.writeheader()
            for r in results:
                w.writerow({**r, "rollout_score": round(_score_rollout(r), 4)})
    print(f"results saved: {csv_path}", file=sys.stderr)

    # Score on stdout last line — hone reads this
    print(aggregate)


if __name__ == "__main__":
    main()
