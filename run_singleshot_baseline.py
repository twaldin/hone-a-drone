#!/usr/bin/env python3
"""CLI-agent-no-tools (single-shot) baseline ablation runner.

Calls claude-code via harness with explicit instructions to NOT use Edit / Read /
Bash tools, forcing a single completion per iter. This is the v3 ablation's floor
arm: isolates the "agent-with-tools vs agent-with-tools-disabled" contrast —
the actual v3 thesis (does tool access matter for the mutation surface?).

Original plan was anthropic SDK direct for a "single API completion vs agent-in-loop"
contrast, but we don't have API billing. Using claude-code OAuth (Max sub) with
no-tool scaffolding keeps the cost at $0 and tightens the control to
"LLM-completion-via-OAuth vs LLM-completion-via-OAuth-with-tool-access".

Usage:
  # Must run with claude-code OAuth; no ANTHROPIC_API_KEY needed.
  python run_singleshot_baseline.py --budget 100 --output-dir .hone-singleshot-baseline
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

# Import HarnessMutator from the installed hone-v3 package
from hone.mutators.harness_mutator import HarnessMutator
from hone.mutators.base import MutatorError


REPO = Path(__file__).parent.resolve()
CONTROLLERS = REPO / "controllers"
GRADER = REPO / "grader.sh"

NO_TOOLS_PROMPT = """You are improving a Python trajectory planner for a drone racing simulation.

# CRITICAL CONSTRAINT
You must operate in SINGLE-COMPLETION mode for this call.
- Do NOT use the Read tool. You have the full current planner.py in this prompt.
- Do NOT use the Edit tool. Return the complete replacement file as text.
- Do NOT use the Bash tool. Do not explore any workdir.
- Do NOT reason about files other than what is shown below.
- Your ENTIRE job is to read the current file + grader feedback, and return
  a better version as plain text.

# TASK
Return ONLY the complete replacement planner.py contents. No prose, no markdown
fences, no explanation. Just the file body, ready to save verbatim.

# INTERFACE CONSTRAINTS (cannot change)
- `class Planner:` at module scope.
- `__init__(self, obs, info, config)`
- `compute_target(self, obs, info, t) -> np.ndarray`  (13-component action vector)
- `step(self, obs, info, action, reward, terminated, truncated)` — may be pass.
- Imports allowed: numpy, scipy, toppra, sibling modules in controllers/
  (attitude_ctrl, state_estimator, gate_detector, world_model).
- Do NOT add pip dependencies. Do NOT print to stdout/stderr inside Planner.

# CURRENT planner.py
{current}

# RECENT GRADER FEEDBACK (last rollouts)
{feedback}

# OUTPUT
Return only the new planner.py file body. No preamble. No fences. No trailing prose.
"""


def grade_snapshot(planner_text: str) -> tuple[float, str, list[dict]]:
    """Materialize controllers/ with `planner_text` and invoke grader.sh."""
    tmp = Path(tempfile.mkdtemp(prefix="singleshot-baseline-"))
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
        score_line = next(
            (l for l in reversed(stdout.splitlines()) if l.strip()), "0.0"
        )
        try:
            score = float(score_line.strip())
        except ValueError:
            score = 0.0
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


def _strip_markdown_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)
    return text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=int, default=100)
    ap.add_argument(
        "--model",
        default="sonnet",
        help="claude-code model alias (default sonnet). Uses Max OAuth.",
    )
    ap.add_argument(
        "--output-dir",
        default=".hone-singleshot-baseline",
    )
    args = ap.parse_args()

    arm_label = f"harness:claude-code:{args.model}:no-tools"
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-singleshot"
    out = REPO / args.output_dir / f"run-{run_id}"
    out.mkdir(parents=True, exist_ok=True)
    mutations_path = out / "mutations.jsonl"

    seed_planner = (CONTROLLERS / "planner.py").read_text(encoding="utf-8")
    print(f"[singleshot-baseline] run_id={run_id}")
    print(f"[singleshot-baseline] arm={arm_label} budget={args.budget}")
    print(f"[singleshot-baseline] output={out}")

    mutator = HarnessMutator(harness_name="claude-code", model=args.model)

    print("[singleshot-baseline] grading seed...")
    seed_score, seed_stderr, seed_rollouts = grade_snapshot(seed_planner)
    print(f"[singleshot-baseline] seed score={seed_score:.4f}")

    best_planner = seed_planner
    best_score = seed_score

    totals = {
        "tokens_in": 0,
        "tokens_out": 0,
        "cost_usd": 0.0,
        "wall_s": 0.0,
        "errors": 0,
        "accepts": 0,
    }
    recent_rollouts = seed_rollouts

    for it in range(1, args.budget + 1):
        iter_start = time.time()
        feedback_json = json.dumps(recent_rollouts[:5], indent=2)[:4000]
        prompt = NO_TOOLS_PROMPT.format(current=best_planner, feedback=feedback_json)

        try:
            result = mutator.propose(prompt)
        except MutatorError as e:
            totals["errors"] += 1
            wall = time.time() - iter_start
            row = {
                "iter": it,
                "arm": arm_label,
                "error": str(e)[:300],
                "reward": 0.0,
                "cost_usd": 0.0,
                "wall_s": wall,
                "parent_score": best_score,
                "child_score": None,
            }
            with mutations_path.open("a") as f:
                f.write(json.dumps(row) + "\n")
            print(f"[singleshot-baseline iter {it}] ERROR: {e}")
            continue

        new_planner = _strip_markdown_fences(result.new_prompt)

        # Syntax check
        try:
            compile(new_planner, "<candidate>", "exec")
        except SyntaxError as e:
            totals["errors"] += 1
            wall = time.time() - iter_start
            print(f"[singleshot-baseline iter {it}] SYNTAX ERROR: {e}")
            row = {
                "iter": it,
                "arm": arm_label,
                "error": f"syntax: {e}",
                "reward": 0.0,
                "cost_usd": result.cost_usd or 0.0,
                "wall_s": wall,
                "parent_score": best_score,
                "child_score": None,
                "tokens_in": result.tokens_in,
                "tokens_out": result.tokens_out,
            }
            with mutations_path.open("a") as f:
                f.write(json.dumps(row) + "\n")
            continue

        # Grade
        child_score, child_stderr, child_rollouts = grade_snapshot(new_planner)
        wall = time.time() - iter_start
        reward = child_score - best_score
        totals["tokens_in"] += result.tokens_in or 0
        totals["tokens_out"] += result.tokens_out or 0
        totals["cost_usd"] += result.cost_usd or 0.0
        totals["wall_s"] += wall

        accepted = child_score > best_score
        row = {
            "iter": it,
            "arm": arm_label,
            "parent_score": best_score,
            "child_score": child_score,
            "reward": reward,
            "wall_s": wall,
            "cost_usd": result.cost_usd or 0.0,
            "tokens_in": result.tokens_in,
            "tokens_out": result.tokens_out,
            "accepted": accepted,
            "rollouts": child_rollouts,
        }
        with mutations_path.open("a") as f:
            f.write(json.dumps(row) + "\n")

        print(
            f"[singleshot-baseline iter {it}/{args.budget}] "
            f"score={child_score:.4f} (parent={best_score:.4f}) "
            f"reward={reward:+.4f} wall={wall:.1f}s "
            f"{'ACCEPT' if accepted else 'reject'}"
        )

        if accepted:
            best_planner = new_planner
            best_score = child_score
            totals["accepts"] += 1
            recent_rollouts = child_rollouts

    (out / "best_planner.py").write_text(best_planner, encoding="utf-8")
    summary = {
        "run_id": run_id,
        "mode": "claude-code-no-tools",
        "arm": arm_label,
        "model": args.model,
        "budget": args.budget,
        "seed_score": seed_score,
        "best_score": best_score,
        "gain": best_score - seed_score,
        "accepts": totals["accepts"],
        "errors": totals["errors"],
        "tokens_in": totals["tokens_in"],
        "tokens_out": totals["tokens_out"],
        "cost_usd": totals["cost_usd"],
        "total_wall_s": totals["wall_s"],
        "per_arm_stats": {
            arm_label: {
                "plays": args.budget - totals["errors"],
                "mean_reward": (best_score - seed_score) / max(args.budget, 1),
                "errors": totals["errors"],
                "total_wall_s": totals["wall_s"],
                "total_cost_usd": totals["cost_usd"],
            }
        },
        "ablation_role": "baseline: agent-with-tools-disabled (OAuth, no API billing)",
        "contrast_with_v3": (
            "v3 full stack = LLM-completion-via-OAuth-with-tool-access. "
            "This baseline = same OAuth agent, tool access suppressed via "
            "prompt scaffolding. Isolates the 'does tool access matter?' axis."
        ),
    }
    (out / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )

    print(
        f"[singleshot-baseline] DONE: best={best_score:.4f} "
        f"(seed={seed_score:.4f}, +{best_score - seed_score:.4f})"
    )
    print(f"[singleshot-baseline] summary → {out / 'summary.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
