"""Launch hone with mutator workdir pinned to the project root.

The updated harness injects workdir/CLAUDE.md via --append-system-prompt, so
pinning workdir here is what lets the mutator see the project CLAUDE.md.

Also logs each mutator result to runs/mutations.jsonl for later analysis.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path("/Users/twaldin/dev/hone-a-drone")
sys.path.insert(0, str(PROJECT_ROOT))

from hone.mutators.harness_mutator import HarnessMutator  # noqa: E402
from hone.optimizer import optimize  # noqa: E402


def _instrument_mutator(mutator: HarnessMutator, log_path: Path):
    """Wrap mutator.propose so every call appends a jsonl line with timing/cost/text."""
    original = mutator.propose
    start = time.time()

    def instrumented(prompt: str):
        t0 = time.time()
        try:
            result = original(prompt)
            err = None
        except Exception as e:
            err = str(e)
            result = None
        dt = time.time() - t0
        ts = datetime.now(tz=timezone.utc).isoformat()
        elapsed = t0 - start
        entry = {
            "ts": ts,
            "elapsed_s": round(elapsed, 1),
            "mutator_s": round(dt, 1),
            "prompt_len": len(prompt),
            "error": err,
        }
        if result is not None:
            entry.update({
                "response_len": len(result.new_prompt),
                "tokens_in": result.tokens_in,
                "tokens_out": result.tokens_out,
                "cost_usd": result.cost_usd,
                "response_head": result.new_prompt[:400],
                "response_tail": result.new_prompt[-400:],
            })
        with open(log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
        if err is not None:
            raise Exception(err)
        return result

    mutator.propose = instrumented
    return mutator


def main():
    budget = int(sys.argv[1]) if len(sys.argv) > 1 else 100

    mutations_log = PROJECT_ROOT / "runs" / "mutations.jsonl"
    mutations_log.parent.mkdir(exist_ok=True)
    mutations_log.write_text("")  # reset

    mutator = HarnessMutator(
        harness_name="claude-code",
        model="sonnet",
        workdir=PROJECT_ROOT,
        timeout_seconds=600,
    )
    mutator = _instrument_mutator(mutator, mutations_log)

    seed_prompt_path = PROJECT_ROOT / "controllers" / "planner.py"
    grader_path = PROJECT_ROOT / "grader.sh"
    output_path = PROJECT_ROOT / "controllers" / "planner.py.best.md"

    seed_prompt = seed_prompt_path.read_text(encoding="utf-8")

    print(f"budget={budget}")
    print(f"seed={seed_prompt_path} ({len(seed_prompt)} chars)")
    print(f"grader={grader_path}")
    print(f"mutations log={mutations_log}")
    print(f"output={output_path}")
    sys.stdout.flush()

    result = optimize(
        seed_prompt=seed_prompt,
        grader_path=grader_path,
        mutator=mutator,
        mutator_spec="claude-code:sonnet",
        prompt_path=seed_prompt_path,
        budget=budget,
        component_name="instruction",
        component_kind="code:python",
        grader_timeout_seconds=600,
        seed=0,
        display_progress_bar=False,
    )

    output_path.write_text(result.best_prompt, encoding="utf-8")
    print()
    print(f"best score: {result.best_score:.4f}")
    print(f"iterations: {result.total_iterations}")
    print(f"mutator calls: {result.mutator_calls} ({result.mutator_failures} failed)")
    print(f"mutator tokens: in={result.mutator_tokens_in:,} out={result.mutator_tokens_out:,}")
    print(f"mutator cost: ${result.mutator_cost_usd:.4f}")
    print(f"run dir: {result.run_dir}")
    print(f"best prompt written to: {output_path}")


if __name__ == "__main__":
    main()
