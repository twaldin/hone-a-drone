#!/usr/bin/env python3
"""Evaluate a drone controller directory over explicit levels/seeds.

This is a benchmark helper used by hone/autoresearch experiments. It is separate
from the baseline run_parallel.py because benchmark splits need explicit seed
lists (e.g. train 21-30, validation 31-40) rather than seeds-per-level 1..N.

Stdout:
  - one JSON line per rollout
  - final line is the aggregate float score (legacy hone scorer protocol)
Stderr:
  - human-readable rollout traces
  - per-level summary
  - summary_json envelope
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
PYTHON = str(ROOT / ".venv" / "bin" / "python")
RUNNER = str(ROOT / "run_rollout.py")
LEVEL_WEIGHTS = {0: 1.0, 1: 1.5, 2: 2.0, 3: 3.0}


def _run_one(planner: str, level: int, seed: int, timeout: float) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            [PYTHON, RUNNER, "--planner", planner, "--level", str(level), "--seed", str(seed), "--timeout", str(timeout)],
            capture_output=True,
            text=True,
            timeout=timeout + 20,
        )
    except subprocess.TimeoutExpired:
        return {
            "level": level,
            "seed": seed,
            "error": "subprocess_timeout",
            "gates_passed": 0,
            "n_gates": 4,
            "lap_time": timeout,
            "crashed": True,
            "crash_reason": "timeout",
            "max_velocity": 0.0,
            "gate_times": [],
            "approach_angles": [],
            "loop_latency_p50": 0.0,
            "loop_latency_p99": 0.0,
        }

    stdout = proc.stdout.strip()
    if proc.returncode != 0 or not stdout:
        err = ((proc.stderr or "") + (proc.stdout or ""))[-500:]
        return {
            "level": level,
            "seed": seed,
            "error": f"rollout_failed: {err}",
            "gates_passed": 0,
            "n_gates": 4,
            "lap_time": timeout,
            "crashed": True,
            "crash_reason": "import_error",
            "max_velocity": 0.0,
            "gate_times": [],
            "approach_angles": [],
            "loop_latency_p50": 0.0,
            "loop_latency_p99": 0.0,
        }

    last_line = next((line for line in reversed(stdout.splitlines()) if line.strip()), "")
    try:
        return json.loads(last_line)
    except json.JSONDecodeError as exc:
        return {
            "level": level,
            "seed": seed,
            "error": f"json_parse: {exc}",
            "gates_passed": 0,
            "n_gates": 4,
            "lap_time": timeout,
            "crashed": True,
            "crash_reason": "parse_error",
            "max_velocity": 0.0,
            "gate_times": [],
            "approach_angles": [],
            "loop_latency_p50": 0.0,
            "loop_latency_p99": 0.0,
        }


def _score_rollout(r: dict[str, Any]) -> float:
    gp = r.get("gates_passed", 0)
    ng = max(r.get("n_gates", 4), 1)
    t = max(r.get("lap_time", 30.0), 0.1)
    if r.get("crash_reason") == "completed":
        return 1.0 + 10.0 / t
    if r.get("crashed"):
        return 0.5 * gp / ng
    return float(gp) / ng


def _fmt_stderr(r: dict[str, Any]) -> str:
    if r.get("error"):
        return f"level={r['level']} seed={r['seed']} ERROR={r['error']}"
    return (
        f"level={r['level']} seed={r['seed']} "
        f"gates={r.get('gates_passed', 0)}/{r.get('n_gates', 4)} "
        f"lap_time={r.get('lap_time', 0):.2f}s "
        f"crashed={r.get('crashed')} crash_reason={r.get('crash_reason')} "
        f"max_vel={r.get('max_velocity', 0):.2f}m/s "
        f"gate_times={r.get('gate_times', [])} "
        f"approach_angles={r.get('approach_angles', [])} "
        f"latency_p50={r.get('loop_latency_p50', 0):.2f}ms "
        f"latency_p99={r.get('loop_latency_p99', 0):.2f}ms"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--controller-dir", required=True, help="Directory containing planner.py and sibling modules")
    parser.add_argument("--levels", type=int, nargs="+", default=[0, 1, 2, 3])
    parser.add_argument("--seeds", type=int, nargs="+", required=True)
    parser.add_argument("--timeout", type=float, default=35.0)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    controller_dir = Path(args.controller_dir).resolve()
    planner = controller_dir / "planner.py"
    if not planner.exists():
        print(f"missing planner.py in {controller_dir}", file=sys.stderr)
        print(0.0)
        return

    combos = [(lv, seed) for lv in args.levels for seed in args.seeds]
    max_workers = max(1, min(args.workers, len(combos), os.cpu_count() or args.workers))
    t0 = time.time()
    results: list[dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_run_one, str(planner), lv, seed, args.timeout): (lv, seed) for lv, seed in combos}
        for fut in as_completed(futures):
            r = fut.result()
            results.append(r)
            print(_fmt_stderr(r), file=sys.stderr, flush=True)
            print(json.dumps(r), flush=True)

    by_level: dict[int, list[dict[str, Any]]] = {lv: [] for lv in args.levels}
    for r in results:
        lv = int(r.get("level", -1))
        if lv in by_level:
            by_level[lv].append(r)

    level_scores = {
        lv: (sum(_score_rollout(r) for r in rs) / len(rs) if rs else 0.0)
        for lv, rs in by_level.items()
    }
    total_w = sum(LEVEL_WEIGHTS.get(lv, 1.0) for lv in args.levels)
    aggregate = sum(LEVEL_WEIGHTS.get(lv, 1.0) * level_scores.get(lv, 0.0) for lv in args.levels) / max(total_w, 1e-9)
    wall = time.time() - t0

    print(f"validation: {len(combos)} rollouts in {wall:.1f}s workers={max_workers}", file=sys.stderr)
    print("per-level scores: " + "  ".join(f"L{lv}={level_scores.get(lv, 0):.3f}" for lv in args.levels), file=sys.stderr)
    print(f"aggregate (weighted): {aggregate:.4f}", file=sys.stderr)
    summary = {
        "aggregate": aggregate,
        "level_scores": {str(k): v for k, v in level_scores.items()},
        "rollouts": len(combos),
        "wall_seconds": wall,
    }
    print("summary_json: " + json.dumps(summary), file=sys.stderr)
    print(aggregate)


if __name__ == "__main__":
    main()
