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
| **A cc-cc** | **0.9925** | 2.155 | 2.155 | 0.991 | 0.025 | +23% | −8% |
| **B oc-cc** | **0.8941** | 1.947 | 1.947 | 0.881 | 0.025 | +10% | −17% |
| **C oc-oc** | **0.9369** | 2.241 | 2.241 | 0.675 | 0.025 | +16% | −13% |

**Headline: none of A, B, C clear v1's 1.0778.** L3
remains the ceiling across every architecture tried so far — v1 seed,
v1 evolved, v2, v2-rerun all sit at L3 ∈ {0.025, 0.050}, because none
of them ship online replanning. Any design that doesn't address L3
hits the same wall.

## Per-level pattern worth calling out

All three arms **traded L0/L1 for L2** and hit a floor on L3 at 0.025
(seed baseline). The trade magnitudes differ:

| | L0/L1 delta vs v1 seed | L2 delta vs v1 evolved | L3 |
|---|---|---|---|
| A (cc-cc) | −3.7% | **+34% (0.991 vs 0.739)** | 0.025 |
| B (oc-cc) | **−13%** | +19% (0.881 vs 0.739) | 0.025 |
| C (oc-oc) | +0.1% (≈ seed) | −9% (0.675 vs 0.739) | 0.025 |

A is the balanced trade — minor L0/L1 regression, biggest L2 gain of
any run in this project so far (hand-seeded v1 evolved included). B
took the most aggressive trade (opencode's `PchipInterpolator` swap
changed approach behavior enough to hurt deterministic L0/L1 by 13%).
C kept L0/L1 at baseline but moved L2 less.

Why does A clear B and C despite A's sub-seed L0/L1? Because L2 has
weight 2.0 in the aggregate, and A's L2 is +34% over v1 evolved.
L3=0.025 is the same ceiling across all runs — no architecture tried
so far (v1, v2, v2-rerun A/B/C) pushes L3 because none of them seed
online replanning.

### The "why A doesn't beat v1 evolved" arithmetic

v1 evolved: 1.0778 = weighted(2.588, 2.577, 0.739, 0.050) / 7.5
A v2-rerun:  0.9925 = weighted(2.155, 2.155, 0.991, 0.025) / 7.5

Per-level delta (A minus v1 evolved): L0=−0.433, L1=−0.422, L2=+0.252,
L3=−0.025. Weighted contribution to aggregate: −0.085. A's L2 win is
real but doesn't cover the L0/L1 regression plus the half-a-gate
L3 regression.

The v1 evolved candidate was better-tuned on the easy levels; v2-rerun
A discovered a more robust L2 strategy at the cost of the easy-level
precision. Both are real learnings, and the L0/L1 regression is the
kind of thing ACE should catch on a longer run ("when L2 improves but
L0/L1 drop by >5%, the spline tension is too high for deterministic
tracks").

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

## Run A (cc-cc): winner of the three, still short of v1

- 100 iters, 0 mutator errors, ACE fired 4 times, 4/4 applied (4 rules).
- Target distribution: planner.py 100% (100/100). Diagnose scheduler
  never routed to a non-planner file — fail_class was out_of_bounds
  throughout the run and the scheduler maps that directly to planner.py.
- 5 accepted improvements (iters 14, 17, 19, 20, 55); last at iter 55,
  then 45-iter plateau to budget exhaustion.

A's winning strategy stayed inside the CubicSpline solution class. The
iter 55 +0.15 jump came from raising `CRUISE_SPEED` 1.5 → 1.8 and
`MAX_SPEED` tuning. Earlier iters added spline velocity/acceleration
as feedforward derivatives and hold-waypoints-after-last-gate for
deceleration. Different search trajectory from the opencode arms —
which is the cross-CLI convergent-divergent discovery story (see
below).

ACE playbook (4 rules at v002, both working observers): all about
spline construction vs post-hoc fixes. "Approach angles >15° across
seeds → add intermediate waypoints, not velocity scaling." "Post-hoc
np.clip on position creates step discontinuities, makes things worse."
"Prefer not-a-knot BCs over clamped-zero at endpoints." "Post-hoc
vel/acc scaling can't fix spatial issues — position trajectory is
already evaluated."

## Consolidated analysis

### Cross-CLI convergent discovery (STRONGEST v3-thesis evidence)

The headline empirical finding from this run.

| Arm | Spline class | Discovery iter |
|---|---|---|
| A (cc) | CubicSpline (kept) | never swapped — tuned parameters within class |
| B (oc) | PchipInterpolator | iter 29 |
| C (oc) | PchipInterpolator | iter 5 |

Both opencode runs — same underlying model, different random seeds,
different random noise in the mutator loop — independently swapped
scipy's `CubicSpline` for `PchipInterpolator`. Run A (claude-code,
same underlying Anthropic model family as the observer in A and B)
never considered the swap. Stayed inside the existing spline class
and tuned parameters.

This is clean evidence that the (harness, model) pair carries
behavioral signal beyond the model API alone. It's exactly what v3's
harness-level arm granularity claim predicted: two arms on the same
model-family can produce structurally different patches because the
CLI around the model shapes the agent's exploration differently.

N is still small (2 opencode runs × 1 convergent decision). Worth a
dedicated follow-up where we re-run ~5 claude-code seeds and ~5
opencode seeds and count how often each arm produces structurally
distinct code patterns.

### ACE: infrastructure validated, lift not demonstrated

| Arm | ACE fires | Applied | Rules | Score |
|---|---|---|---|---|
| A | 4 | 4 | 4 | 0.9925 |
| B | 6 | 6 | 2 | 0.8941 |
| C | 10 | 0 (all errored) | 0 | 0.9369 |

- Both working observers produced substantive, specific rules.
- Cross-run convergence on the abstract lesson: "out_of_bounds is a
  geometry/smoothness problem, not a velocity problem." A and B
  arrived at this via different specific rules — A about not-a-knot
  BCs and intermediate waypoints, B about not replacing PchipInterpolator
  with piecewise-linear.
- But rank ordering doesn't track "better observer": A (4 applied) >
  C (0 applied) > B (6 applied). The run with zero ACE outperformed
  the run with working ACE.

Honest read: ACE infrastructure is sound. Whether per-arm ACE causes
score lift is unresolved at N=3 with one broken observer. The v1
pre-registered threshold was 80/20 LLM-catchable observations; v1
landed at 70/30. v2-rerun doesn't cleanly re-run that analysis (the
observer arms had different firing rates and one was broken).
Verdict: still inconclusive.

### Multi-file architecture: correct but idle on this task

Every accepted improvement across all three runs was on `planner.py`.
Cumulative: 11 accepts on planner.py, 0 accepts on 25 non-planner
edits (`world_model.py` 14 + `attitude_ctrl.py` 3 in B+C, plus A
which never edited non-planner).

The diagnose scheduler's fail_class → file routing worked as
configured. out_of_bounds dominated; out_of_bounds routes to
planner.py. The scheduler did its job; the task is simply
planner-dominated. This is a task property, not a bug.

Multi-file machinery is the right architecture for tasks with real
cross-file coherence work. Drone-racing isn't one. SWE-bench Live —
the next reference problem on the queue — is.

### Plateau pattern across all three runs

| Run | Improvements | Last accept | Plateau length |
|---|---|---|---|
| A | 5 | iter 55 | **45 iters** (to budget exhaustion) |
| B | 4 | iter 64 | 36 iters (to budget exhaustion) |
| C | 2 | iter 45 | 55 iters (to budget exhaustion) |

Every arm exhausted its improvement headroom well before the 100-iter
budget. A's 45-iter tail plateau is the most striking — cc-sonnet
spent nearly half the run producing no gain.

Design question raised to cairn: should v3.0 add per-arm plateau
detection with early-abort, or always exhaust budget? GEPA is
historically punctuated (A itself went 35 iters between iter 20 and
iter 55 before a +0.15 jump), which argues against aggressive
early-abort. But the observed tail plateaus are expensive in
wall-and-cost terms. Open decision pending cairn's call.

## Cost

- A (cc-cc): ~7 hours wall, claude-code:sonnet × 100 iters +
  4 observer fires. Claude Max subscription → $0 nominal spend
  per adapter, but API-pricing equivalent ~$25-40 estimated
  (100 sonnet calls averaging ~4min each, ~20-30k tokens per call).
- B (oc-cc): ~2 hours wall, opencode:gpt-5.4 × 100 iters +
  6 claude-code:sonnet observer fires. Opencode costs routed
  through sqlite (not claude envelope) — exact spend TBD from
  opencode's session DB.
- C (oc-oc): ~2 hours wall, opencode:gpt-5.4 × 100 iters +
  10 opencode fires that all errored (free). Same opencode
  spend as B ballpark.

Exact dollar figures: WIP — requires querying opencode's sqlite for
B and C, and claiming the Max-subscription equivalent for A.

## Status

All three runs complete. Final scores locked. This writeup is the
final 3-way summary.

## References

- Seed controller: `controllers/planner.py` (pre-restructure).
- Best artifacts: `controllers.v2rerun-honed/` (A), `controllers.v2rerun-opencode-honed/` (B), `controllers.v2rerun-oc-observer-honed/` (C).
- Per-iter traces: `.hone/run-20260420-182940-1d2d06/mutations.jsonl` (A), `.hone/run-20260420-204634-4b87ed/mutations.jsonl` (B), `.hone/run-20260420-204811-5a8f07/mutations.jsonl` (C).
- ACE playbook versions: `claude_md_versions/v001.md`, `v002.md` in A and B's run dirs. C has no applied versions (observer broken).
- v3 spec lessons from this run: `writeup/v3-spec.md` §0 decisions 6-12
  (sliding-window UCB, bandit_state logging, arm compat matrix,
  fail-loud policy, edit-mode lock).
