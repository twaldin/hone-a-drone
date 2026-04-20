# First hone run — experiment report

**Status: FINAL. Run 2 completed 2026-04-20 10:28. Seed → best: +33% aggregate
score. Run 1 (aborted) archived at `runs-aborted-run1/`.**

## Configuration

- **Seed**: `controllers/planner.py` — min-snap-philosophy cubic-spline
  trajectory through gate-normal-aligned waypoints with obstacle nudging.
  Pure numpy + scipy + toppra (dep only, not yet used). 8,075 characters.
- **Grader** (`grader.sh`): 4 difficulty levels × 5 seeds = 20 rollouts per
  candidate, ~14s wall each. Score = weighted aggregate with level weights
  L0=1.0, L1=1.5, L2=2.0, L3=3.0.
- **Mutator**: `claude-code:sonnet` via `harness` 0.2.0 (post-honefix).
- **Hone**: git `83d29e9e` (post-honefix, auto-detects `component_kind=code:python`
  from `.py` seed).
- **Budget**: 100 iterations (GEPA stopped at 13 mutator calls — explanation below).
- **Start / end**: 2026-04-20 09:18:30Z → 10:28 (wall ~70 min).

## Baselines for comparison

| Controller               | L0 complete | L1 complete | L2 complete | L3 complete | Aggregate |
|---                       |---          |---          |---          |---          |---        |
| `lsy_state_controller`   | 5/5 @ 13.86s | 5/5 @ 13.86s | 0/5         | 0/5         | ~0.55     |
| `min-snap seed (v0)`     | 5/5 @ 8.08s  | 5/5 @ 8.08s  | 0/5 (1.6/4g)| 0/5 (0.2/4g)| **0.8093** |
| **hone-evolved (iter 13)** | 5/5 @ 6.30s | 5/5 @ 6.30s | 2/5 @ 6.36s | 1/5 timeout | **1.0778** |

## Results

### Score trajectory (valset aggregate)

| Iter | valset score | hone verdict |
|---   |---           |---           |
| 0    | 0.8093       | seed baseline |
| 1-3  | (subsample < seed) | skipped |
| 4    | **0.8612**   | **winner #1** (+6.4%) |
| 5-12 | (subsample ≤ seed) | skipped (10 consecutive rejections) |
| 13   | **1.0778**   | **winner #2 / final best** (+33%) |
| 14-20 | —           | GEPA `skip_perfect_score` — no mutator call |

### Per-level breakdown (best candidate, graded on fresh seeds)

| Level | Seed  | Best  | Δ       | Notable change |
|---    |---    |---    |---      |---             |
| L0    | 2.238 | 2.588 | +15.6%  | 5/5 completed, lap 8.08s → 6.30s |
| L1    | 2.238 | 2.577 | +15.1%  | 5/5 completed, lap 8.08s → 6.30s |
| L2    | 0.200 | 0.739 | **+270%** | 2/5 completed at 6.36s (seed couldn't complete any) |
| L3    | 0.025 | 0.050 | +100%   | 1/5 passed 1 gate; rest timeout |

**L2 is the headline.** Seed never completed an L2 rollout; best candidate
completes several. L3 remains stubbornly hard — requires dynamic replanning
the current architecture doesn't support.

### What the mutator actually changed

Iter 4 (first winner) vs seed:
- `CRUISE_SPEED`: 1.5 → 2.0 m/s (+33%)
- `MAX_SPEED`: 2.5 → 3.0 m/s (+20%)
- `EXIT_DIST`: 0.5 → 0.55 m (+10%)
- `MIN_SEGMENT_TIME`: 0.5 → 0.3 s (-40%)
- ADDED `LOOKAHEAD_TIME: float = 0.4` — genuinely new parameter / mechanism

Iter 13 (final best) vs iter 4:
- `CRUISE_SPEED`: 2.0 → 2.2 m/s (+10%)
- `EXIT_DIST`: 0.55 → 0.6 m (+9%)
- `MIN_SEGMENT_TIME`: 0.3 → 0.25 s (-17%)
- `LOOKAHEAD_TIME`: 0.4 → 0.35 (-13%)

The final best is iter 4's design with tighter parameters. The big
structural change (`LOOKAHEAD_TIME`) came from iter 4; iter 13 tuned it.
The mutator's pattern was "one big idea, followed by fine tuning."

### Why GEPA stopped at iter 20 instead of 100

GEPA uses `skip_perfect_score=True` (hone default). After iter 13's pareto
frontier contained a "perfect subsample" entry, iterations 14-20 logged "All
subsample scores perfect. Skipping. Reflective mutation did not propose a
new candidate." With `trainset=[1 example]`, subsample == full set, so
"perfect subsample" triggers easily once any candidate pushes hard.

This is a **budget-utilization inefficiency**, not a bug. We got $4.08 worth
of results out of a $30 nominal budget. To squeeze more out, either disable
`skip_perfect_score` for code:python, or use a larger/held-out valset.

### Cost

- Mutator calls: 13 (100 budget)
- Mutator tokens out: 214,738
- Mutator cost: **$4.0825**
- Avg per mutation: $0.31
- Wall time: ~70 min total, 4.3 min/iter, 26 min total mutator time

### Mutation classes observed

1. **Parameter tuning** (most iterations): adjust `CRUISE_SPEED`,
   `MAX_SPEED`, `APPROACH_DIST`, etc. Iter 13's tweaks are pure tuning.
2. **Structural addition** (iter 4): introduced `LOOKAHEAD_TIME` +
   `N_CACHED...` — a new mechanism not in the seed. This was the single
   biggest algorithmic leap in the run.
3. **Aggressive regressions** (iters 1, 2, 6): raised speeds beyond
   Mellinger tracking bandwidth, crashed L0+L1. GEPA rejected all of these.

### Surprises

- **The mutator reliably emits valid Python now.** All 13 calls parsed
  cleanly (0 failed per hone stats). The harness `--append-system-prompt`
  fix + hone's `code:python` prompt template are sufficient. In Run 1 this
  was 0-for-6; in Run 2 it was 13-for-13. Clean infrastructure win.
- **L2 jump from 0.200 to 0.739 (+270%) without any L2-specific changes.**
  The mutator didn't target L2 — it just improved parameters that happened
  to help all randomized-obstacle scenarios.
- **L3 was untouched.** Random-track generalization needs online replanning
  (per-seed gate sequences), which no iter attempted. Consistent with
  STACK.md's prediction that L3 needs the next architectural layer
  (`world_model.py` for gate re-estimation), not planner tuning.
- **Iter 13 won with tight parameter tuning, not structural insight.**
  The mutator's "winner-builds-on-winner" pattern in GEPA is an asset when
  the search space is local (small tweaks matter).
- **Budget utilization:** only 13% of the nominal $30 budget used. Good for
  this loop's economics, but a signal that hone's early-stop is aggressive
  when the grader is deterministic + trainset is small.

## Comparison against Run 1 (aborted)

| Metric               | Run 1 (aborted) | Run 2 (successful) |
|---                   |---              |---                 |
| Iterations           | 6 (all scored 0)| 13 (2 winners)     |
| Valid Python outputs | 1 of 6 (fenced) | 13 of 13           |
| Best valset score    | 0.8093 (= seed) | 1.0778 (+33%)      |
| Cost                 | $1.39           | $4.08              |
| Wall time            | 22 min (killed) | 70 min (natural end) |

**Run 2 succeeded because the harness layer was fixed, not because of
better CLAUDE.md content.** My two CLAUDE.md edits in Run 1 had near-zero
effect (see post-mortem probe in observations.md). The honefix PRs to hone
(`component_kind=code:python` prompt template) and harness (`--append-system-prompt`
to inject workdir CLAUDE.md) carried the weight.

## Anduril-relevant takeaway

This loop is validated end-to-end on a proxy sim. The full hone→grader→mutator
pipeline works, produces measurable improvement (+33% aggregate / +270% on
the hardest level that completed), and costs ~$4 per budget-100 run. When
the real Anduril sim drops in May, swapping the sim/obs adapter layer should
preserve everything else. Open work before that (see ROADMAP.md + STACK.md):

- L3 generalization requires online replanning, which needs `world_model.py`
  (gate re-estimation from sensor updates) or dynamic-pointing multi-module
  hone rotation.
- The min-snap seed is not yet literal min-snap — it's quintic-cubic-spline
  parameter + obstacle-aware routing. True degree-8 min-snap QP (Richter et
  al. 2016) is the next upgrade target, as is TOPP-RA time-optimal
  parameterization (`toppra` is already a dep).

## Run artifacts

- `controllers/planner.py.best.md` — the iter 13 source (6,856 chars).
- `runs/mutations.jsonl` — per-iter mutator telemetry.
- `runs/2026*.csv` — per-GEPA-eval grader CSVs (46 files for 13 iters +
  initial eval + skipped-iter re-evals).
- `runs/observations.md` — timestamped observer log.
- `runs/logs/hone_run.v2.log` — hone stdout/stderr.
- `.hone/run-20260420-091830-85559b/` — GEPA internal state.
- `runs-aborted-run1/` — Run 1 archive (broken-harness data).
