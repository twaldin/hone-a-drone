# v2 observations — hone budget-100 with ACE + diagnose scheduler

## Setup context — 2026-04-20 11:40:46Z

- PID: 83234
- hone-v2 at ~/hone-v2 (commit: v2 branch, local fork of hone)
- harness 0.2.0 (unchanged from v1)
- Config: --dir controllers/, budget 100, diagnose scheduler,
  observer claude-code:sonnet every 10 iters
- 6 mutable files: attitude_ctrl.py, baseline.py, gate_detector.py,
  planner.py, state_estimator.py, world_model.py
- Scheduler rules (scheduler.json):
  * crash_reason=out_of_bounds → planner.py
  * crash_reason=collision     → planner.py
  * crash_reason=gate_miss     → gate_detector.py
  * gates_passed=0             → world_model.py
  * loop_latency_p99 > 1.0     → attitude_ctrl.py
  * fallback: round-robin

## v1 baseline to beat
- Seed aggregate: 0.8093
- v1 best (iter 13): 1.0778 (+33%)
- Per-level: L0 +15.6%, L1 +15.1%, L2 +270%, L3 +100%

## Smoke gate verification (5-iter round-robin)
- (a) PASSED — scheduler picked 5 distinct files
- (b) PASSED — observer applied 3 deltas at iter 2 (version=1)
- Score trajectory: flat at 0.8093 except iter 4 (planner) regressed to 0.13
- Structural note: 5 of 6 files are grader-inert (planner.py self-contained;
  grader loads only planner.py). Diagnose scheduler should concentrate on
  planner.py for most iters, giving ~80 effective planner mutations over
  budget 100 — 6× v1's sample size.

## Scheduler choice for full run
Using **diagnose** for the full run (switched from round-robin-only smoke).
Per cairn's original brief — diagnose was the intended default. Smoke used
round-robin to exercise "picks multiple files" gate; full run uses diagnose
for actual policy-driven routing.

## Observations

## Post-run hone feature escalations (to file after v2 writeup lands)

### 1. Hone resume capability — CITATIONS.md:21 is aspirational copy, not implemented
- Claim in `CITATIONS.md:21`: "Persistent runs with resume (.hone/run-<id>/)"
- Reality (verified 2026-04-20 by cairn): .hone/run-<id>/ dirs exist, GEPA internally
  checkpoints `gepa_state.bin`, but hone has NO CLI surface to pick up a partial run
  and NO Python API that reads prior state back. `optimize()` and `optimize_dir()`
  both initialize from scratch even when given an existing `run_dir`.
- Invocation we'd want: `hone resume <run-id>` or `hone run --resume <run-id>`.
- Fix options: (a) implement it — optimize_dir already writes mutations.jsonl +
  snapshot files, so reading prior state back is ~30 LOC; (b) delete the
  CITATIONS.md line until implemented. Either is fine, but shipping with the
  promise in marketing copy and not in code is the worst of both.
- Priority: medium. Blocked Run 2 from salvage-after-crash path; would have
  saved budget on v1's abort. Not needed for v2 since v2 ran to completion.
