#!/usr/bin/env python3
"""GEPA-only baseline ablation runner.

Runs the same evolutionary accept-if-better loop hone uses, but with a SINGLE
anthropic SDK call per iter (no coding-CLI agent, no ACE observer, no bandit).
This is the v3 ablation's floor — it isolates the contribution of "agent-in-loop
with real tool access" vs "single-completion text rewrite" that the rest of the
stack stacks on top of.

Usage:
  export ANTHROPIC_API_KEY=...
  python run_gepa_baseline.py --budget 100 --model claude-sonnet-4-6 \\
      --output-dir .hone-gepa-baseline

The runner writes mutations.jsonl + summary.json in the same schema as v3's
optimize_dir_pool so the ablation matrix can be analyzed uniformly.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path


REPO = Path(__file__).parent.resolve()
CONTROLLERS = REPO / "controllers"
GRADER = REPO / "grader.sh"

MUTATOR_PROMPT_TEMPLATE = """You are improving a Python trajectory planner for a drone racing simulation.
The file `planner.py` is the ONLY thing you can change. Keep the `Planner` class
interface identical (signatures + 13-component action vector from compute_target).

Imports allowed: numpy, scipy, toppra, sibling modules in controllers/.
Do NOT add new pip dependencies. Do NOT print to stdout/stderr inside the class.

Return ONLY the complete replacement planner.py contents. No prose, no markdown
fences. Just the code.

=== CURRENT planner.py ===
{current}

=== GRADER FEEDBACK FROM LAST ROLLOUT ===
{feedback}

=== TASK ===
Edit planner.py to score higher on the grader. Return only the new file body.
"""


def grade_snapshot(planner_text: str) -> tuple[float, str, list[dict]]:
    """Materialize controllers/ with `planner_text` and invoke grader.sh.

    Returns (aggregate_score, stderr, rollout_jsons).
    """
    # Copy controllers/ to a temp dir, replace planner.py with the candidate
    tmp = Path(tempfile.mkdtemp(prefix="gepa-baseline-"))
    try:
        tmp_controllers = tmp / "controllers"
        shutil.copytree(CONTROLLERS, tmp_controllers)
        (tmp_controllers / "planner.py").write_text(planner_text, encoding="utf-8")
        proc = subprocess.run(
            [str(GRADER), str(tmp_controllers)],
            capture_output=True,
            text=True,
            timeout=600,
        )
        stdout = proc.stdout.strip()
        stderr = proc.stderr
        # Last non-empty line is the aggregate score
        score_line = next(
            (l for l in reversed(stdout.splitlines()) if l.strip()), "0.0"
        )
        try:
            score = float(score_line.strip())
        except ValueError:
            score = 0.0
        # Parse per-rollout JSON from stdout (all but last line)
        rollouts: list[dict] = []
        for line in stdout.splitlines()[:-1]:
            s = line.strip()
            if s.startswith("{"):
                try:
                    rollouts.append(json.loads(s))
                except json.JSONDecodeError:
                    pass
        return score, stderr, rollouts
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def anthropic_propose(current: str, feedback: str, model: str) -> tuple[str, dict]:
    """Single anthropic SDK call. Returns (new_text, meta)."""
    from anthropic import Anthropic

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    client = Anthropic()
    prompt = MUTATOR_PROMPT_TEMPLATE.format(current=current, feedback=feedback)
    t0 = time.time()
    resp = client.messages.create(
        model=model,
        max_tokens=16000,
        messages=[{"role": "user", "content": prompt}],
    )
    wall = time.time() - t0
    text = "\n".join(
        b.text for b in resp.content if getattr(b, "type", None) == "text"
    ).strip()
    meta = {
        "tokens_in": resp.usage.input_tokens
        + getattr(resp.usage, "cache_read_input_tokens", 0)
        + getattr(resp.usage, "cache_creation_input_tokens", 0),
        "tokens_out": resp.usage.output_tokens,
        "wall_s": wall,
    }
    # Strip markdown fences if any
    if text.startswith("```"):
        # drop first line (```python or ```) and possibly trailing ```
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)
    return text, meta


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=int, default=100)
    ap.add_argument("--model", default="claude-sonnet-4-6")
    ap.add_argument(
        "--output-dir",
        default=".hone-gepa-baseline",
        help="Where mutations.jsonl / summary.json / best.py land",
    )
    args = ap.parse_args()

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-gepa"
    out = REPO / args.output_dir / f"run-{run_id}"
    out.mkdir(parents=True, exist_ok=True)
    mutations_path = out / "mutations.jsonl"

    seed_planner = (CONTROLLERS / "planner.py").read_text(encoding="utf-8")
    print(f"[gepa-baseline] run_id={run_id}")
    print(f"[gepa-baseline] model={args.model} budget={args.budget}")
    print(f"[gepa-baseline] output={out}")

    # Seed grade
    print("[gepa-baseline] grading seed...")
    seed_score, seed_stderr, seed_rollouts = grade_snapshot(seed_planner)
    print(f"[gepa-baseline] seed score={seed_score:.4f}")

    best_planner = seed_planner
    best_score = seed_score

    totals = {
        "tokens_in": 0,
        "tokens_out": 0,
        "wall_s": 0.0,
        "errors": 0,
        "accepts": 0,
    }

    for it in range(1, args.budget + 1):
        iter_start = time.time()
        try:
            feedback_json = json.dumps(seed_rollouts[:5], indent=2)[:4000]
            new_planner, meta = anthropic_propose(
                best_planner, feedback_json, args.model
            )
        except Exception as e:
            totals["errors"] += 1
            row = {
                "iter": it,
                "arm": f"anthropic:{args.model}",
                "error": str(e)[:300],
                "reward": 0.0,
                "cost_usd": 0.0,
                "wall_s": time.time() - iter_start,
                "parent_score": best_score,
                "child_score": None,
            }
            with mutations_path.open("a") as f:
                f.write(json.dumps(row) + "\n")
            print(f"[gepa-baseline iter {it}] ERROR: {e}")
            continue

        # Syntax check
        try:
            compile(new_planner, "<candidate>", "exec")
        except SyntaxError as e:
            totals["errors"] += 1
            print(f"[gepa-baseline iter {it}] SYNTAX ERROR: {e}")
            row = {
                "iter": it,
                "arm": f"anthropic:{args.model}",
                "error": f"syntax: {e}",
                "reward": 0.0,
                "cost_usd": 0.0,
                "wall_s": time.time() - iter_start,
                "parent_score": best_score,
                "child_score": None,
            }
            with mutations_path.open("a") as f:
                f.write(json.dumps(row) + "\n")
            continue

        # Grade
        child_score, child_stderr, child_rollouts = grade_snapshot(new_planner)
        wall = time.time() - iter_start
        reward = child_score - best_score
        totals["tokens_in"] += meta["tokens_in"]
        totals["tokens_out"] += meta["tokens_out"]
        totals["wall_s"] += wall

        accepted = child_score > best_score
        row = {
            "iter": it,
            "arm": f"anthropic:{args.model}",
            "parent_score": best_score,
            "child_score": child_score,
            "reward": reward,
            "wall_s": wall,
            "tokens_in": meta["tokens_in"],
            "tokens_out": meta["tokens_out"],
            "accepted": accepted,
            "rollouts": child_rollouts,
        }
        with mutations_path.open("a") as f:
            f.write(json.dumps(row) + "\n")

        print(
            f"[gepa-baseline iter {it}/{args.budget}] "
            f"score={child_score:.4f} (parent={best_score:.4f}) "
            f"reward={reward:+.4f} wall={wall:.1f}s "
            f"{'ACCEPT' if accepted else 'reject'}"
        )

        if accepted:
            best_planner = new_planner
            best_score = child_score
            totals["accepts"] += 1
            seed_rollouts = child_rollouts  # newest feedback

    # Write outputs
    (out / "best_planner.py").write_text(best_planner, encoding="utf-8")
    summary = {
        "run_id": run_id,
        "mode": "gepa-only-baseline",
        "model": args.model,
        "budget": args.budget,
        "seed_score": seed_score,
        "best_score": best_score,
        "gain": best_score - seed_score,
        "accepts": totals["accepts"],
        "errors": totals["errors"],
        "tokens_in": totals["tokens_in"],
        "tokens_out": totals["tokens_out"],
        "total_wall_s": totals["wall_s"],
        "per_arm_stats": {
            f"anthropic:{args.model}": {
                "plays": args.budget - totals["errors"],
                "mean_reward": (best_score - seed_score) / max(args.budget, 1),
                "errors": totals["errors"],
                "total_wall_s": totals["wall_s"],
            }
        },
    }
    (out / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )

    print(f"[gepa-baseline] DONE: best={best_score:.4f} (seed={seed_score:.4f}, +{best_score-seed_score:.4f})")
    print(f"[gepa-baseline] summary → {out / 'summary.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
