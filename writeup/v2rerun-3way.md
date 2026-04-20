# v2-rerun 3-way: A/B/C results

Three runs in parallel, same grader, same seed (0), same budget (100),
same architecture (v2 multi-file + ACE observer + 600s timeout). Only
difference: mutator and observer harness choice.

- **A (cc-cc)**: `harness:claude-code:sonnet` mutator + observer. Started 2026-04-20 18:30 UTC.
- **B (oc-cc)**: `harness:opencode:openai/gpt-5.4` mutator + `harness:claude-code:sonnet` observer. Started 20:46 UTC.
- **C (oc-oc)**: `harness:opencode:openai/gpt-5.4` mutator + observer. Started 20:48 UTC.

## Final scores

| Run | Aggregate | L0 | L1 | L2 | L3 | vs seed | vs v1 (1.0778) |
|---|---|---|---|---|---|---|---|
| seed | 0.8093 | 2.238 | 2.238 | 0.200 | 0.025 | — | −25% |
| v1 evolved | 1.0778 | 2.588 | 2.577 | 0.739 | 0.050 | +33% | — |
| v2 (aborted) | 0.9041 | — | — | — | — | +12% | −16% |
| **A cc-cc** | *WIP — iter 79/100 at write time, best 0.9925* | | | | | *+23%* | *−8%* |
| **B oc-cc** | **0.8941** | 1.947 | 1.947 | 0.881 | 0.025 | +10% | −17% |
| **C oc-oc** | **0.9369** | 2.241 | 2.241 | 0.675 | 0.025 | +16% | −13% |

**Headline: none of B, C (and likely not A) clear v1's 1.0778.** L3
remains the ceiling across every architecture tried so far — v1 seed,
v1 evolved, v2, v2-rerun all sit at L3 ∈ {0.025, 0.050}, because none
of them ship online replanning. Any design that doesn't address L3
hits the same wall.

## Per-level pattern worth calling out

B specifically traded L0/L1 for L2. L0=L1=1.947 is 13% below the v1
seed's 2.238; L2=0.881 is 19% ABOVE v1 evolved's 0.739. The opencode
mutator's `CubicSpline` → `PchipInterpolator` swap (iter 29) made
the drone more robust on L2's randomized obstacles while regressing on
the deterministic L0/L1. Not a strict win — a trade. At the aggregate
weight (L2 = 2.0, L0+L1 = 2.5), L0/L1 losses dominated.

C picked the same PchipInterpolator swap earlier (iter 5), plus a big
rewrite at iter 45. It kept L0/L1 roughly at seed baseline and moved
L2 to 0.675 — worse than B's L2 but better than seed's 0.200, with no
L0/L1 regression. Net: higher aggregate than B.

## Run B (oc-cc): working observer, weakest final

- 100 iters, 0 mutator errors, ACE fired 6 times, 6/6 applied (2 rules
  distilled).
- Target distribution: planner.py 88 / world_model.py 8 / attitude_ctrl.py 3.
- Zero accepts on the 8 world_model.py and 3 attitude_ctrl.py edits.
- 4 accepted improvements (iters 29, 30, 56, 64); last at iter 64,
  then 36-iter plateau to budget exhaustion.

ACE playbook (final 2 rules) is tight and task-specific: "don't
replace PchipInterpolator with piecewise-linear — loses C1 continuity,
tracker amplifies heading discontinuities into out_of_bounds"; "when
fail_class plateaus on out_of_bounds regardless of seed, suspect
smoothness regression, not speed or alignment."

## Run C (oc-oc): broken observer, second-best final

- 100 iters, 0 mutator errors, ACE fired 10 times, **0/10 applied,
  10/10 errored** with `"mutator_failure: harness 'opencode' is not
  currently usable as a mutator — its output is a coding loop, not a
  text response"`.
- Target distribution: planner.py 89 / world_model.py 10. Zero accepts
  on world_model.py.
- 2 accepted improvements (iters 5 and 45); last at iter 45, then
  55-iter plateau.

**The opencode-as-observer configuration was a no-op for the entire
run.** Run C effectively ran "GEPA + opencode mutator + no ACE" and
still beat Run B (0.9369 > 0.8941) which had a working ACE observer.
This IS the negative data point for the v3 thesis's "ACE-helps"
slice. Not a causal claim in either direction — N=3, one broken
config, massive model confounds — but the straightforward reading is:
on this task, at this sample size, whether ACE fires or not did not
predict score rank.

Lesson folded into v3-spec §3.5: compatibility matrix as module
constant, pre-flight validation rejects `harness:opencode:*` as an
observer at CLI parse time. Mid-run, first-fire failure aborts
unless `--allow-partial-arm-failure` is set. The silent-degradation
mode is closed in v3.0.

## Cross-arm convergent discovery (the positive data point)

Both opencode runs (B, C) independently swapped `scipy.interpolate.CubicSpline`
for `PchipInterpolator`. B at iter 29; C at iter 5. Run A
(claude-code) never made the same swap — stayed in the CubicSpline
solution class and tuned parameters (`CRUISE_SPEED` 1.5→1.8, spline
vel/acc derivatives, hold-waypoints-after-last-gate for deceleration).

This is the cleanest evidence so far for v3's "harness-level arm
granularity" claim. Two runs with the same underlying model
(opencode → gpt-5.4) but different random seeds converged on a
structurally different code change from the claude-code arm. The
harness + model pair is carrying behavioral signal beyond what the
raw model API alone would produce.

## Plateau pattern across all three runs

Every arm found its last improvement well before the budget ran out:

| Run | Improvements | Last accept | Plateau length |
|---|---|---|---|
| A | 5 | iter 55 | 23+ iters (ongoing at iter 79) |
| B | 4 | iter 64 | 36 iters (to budget exhaustion) |
| C | 2 | iter 45 | 55 iters (to budget exhaustion) |

This opens a design question for v3.0 (forwarded to cairn): should the
bandit detect per-arm plateau and early-abort, or always exhaust
budget? GEPA-style evolutionary search is historically punctuated —
Run A itself went 35 iters between iters 20 and 55 before landing a
+0.15 jump. Early-abort would have killed that win. But B's final 36
and C's final 55 plateau iters produced strictly zero gain.

No implementation commitment yet; noted for v3.0 spec discussion.

## Cost

- A: ongoing. Final cost TBD when run lands.
- B: ~100 opencode/gpt-5.4 calls. Wall ~2h. Approximate spend TBD
  (opencode cost instrumentation goes through sqlite, not the
  claude-code envelope). (WIP)
- C: same ballpark as B.

## Status

- B and C: complete. Final scores locked.
- A: in flight, 79/100 iters, best 0.9925. ETA ~00:30 UTC 2026-04-21.
- This writeup will be updated with A's final score + consolidated
  summary + cost breakdown once A completes.

## References

- Seed controller: `controllers/planner.py` (pre-restructure).
- Best artifacts: `controllers.v2rerun-honed/` (A), `controllers.v2rerun-opencode-honed/` (B), `controllers.v2rerun-oc-observer-honed/` (C).
- Per-iter traces: `.hone/run-20260420-182940-1d2d06/mutations.jsonl` (A), `.hone/run-20260420-204634-4b87ed/mutations.jsonl` (B), `.hone/run-20260420-204811-5a8f07/mutations.jsonl` (C).
- ACE playbook versions: `claude_md_versions/v001.md`, `v002.md` in A and B's run dirs. C has no applied versions (observer broken).
- v3 spec lessons from this run: `writeup/v3-spec.md` §0 decisions 6-12
  (sliding-window UCB, bandit_state logging, arm compat matrix,
  fail-loud policy, edit-mode lock).
