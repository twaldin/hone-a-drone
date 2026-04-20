# Observations log — hone budget-100 primitive run

Timestamped observer notes. Three categories:
- **MUTATOR-REPEAT** — mutator keeps introducing the same class of bug across iterations
- **STERR-IGNORED** — grader emits info that would have prevented a failure, but mutator doesn't read it
- **INFRA** — friction the observer notices that a machine could have caught

Run 1 (aborted) notes moved to `runs-aborted-run1/observations.md`. Run 2
continues below.

---

### RUN 2 setup — 2026-04-20 09:18Z

Context after Run 1 kill:
- Run 1 killed at iter 6/100 with $1.39 spent, all candidates scoring 0.0
- Root causes (2): (a) hone's "improve the prompt" template made claude-code
  return prose; (b) harness didn't inject workdir CLAUDE.md so my Edits #1/#2
  were invisible to the mutator.

**Fixes now live (via honefix PRs on hone + harness):**
1. `hone`: auto-detects `.py` seed → `component_kind="code:python"`, swaps the
   mutator prompt template to "You are editing a Python module. Output ONLY
   the complete replacement module body as plain text. NO prose. NO markdown
   fences. Output must parse as valid Python."
2. `hone`: post-validates mutator output with `ast.parse()`; on SyntaxError,
   retries once with the error message appended; if retry fails, raises
   `MutatorError` (doesn't charge the iteration against budget as "improvement").
3. `harness`: `claude-code` adapter passes `--append-system-prompt
   "$(cat workdir/CLAUDE.md)"` — injects project CLAUDE.md as system prompt,
   fixing the invisibility observed in Run 1's post-mortem probe.
4. `harness`: `claude-code` adapter strips markdown fences from the response's
   `result` field (defense-in-depth against iter-3-style wrapping).

**Run 2 plumbing:**
- CLAUDE.md slimmed back to Planner interface + level semantics + failure
  modes + don't-dos. Removed the "this is NOT a normal Claude Code session /
  return code, not prose / self-check" sections that Run 1 added — those are
  all in the harness now.
- `runs/launcher.py` passes `component_kind="code:python"` explicitly to
  `hone.optimize()` (matches the CLI auto-detection path).
- `hone` upgraded to commit `83d29e9e` (post-honefix).
- `harness` at `0.2.0` from `~/harness` (editable install).

**Baselines for comparison (unchanged — seed unchanged):**
- lsy_state_controller: L0+L1 completed @ 13.86s; L2+L3 mostly DNF
- min-snap seed (v0): aggregate **0.8093**, L0+L1 @ 8.08s, L2 2-3g DNF, L3 ≤1g

## CLAUDE.md edits during Run 2

(Empty. One edit already made at start: slim-down per honefix. No further
edits unless a new failure pattern appears at ≥ iter 25.)

## Observations

### 2026-04-20 09:23 — RUN 2 iter 1 CONFIRMED PYTHON, fixes work

**Iter 1 response (4674 chars, $0.277):**
```
from __future__ import annotations
import numpy as np
from scipy.interpolate import CubicSpline
from scipy.spatial.transform import Rotation

CRUISE_SPEED: float = 1.8
MAX_SPEED: ...
```

**Unambiguously Python.** First line is `from __future__ import annotations`,
followed by imports, then the `Planner` class. No prose, no markdown fences,
no self-reflection. The hone code:python template + harness
`--append-system-prompt` + fence-stripping are all working.

**Iter 1 was graded (not skipped):**
- CSV `runs/20260420T092214.csv` = iter 1 candidate evaluation
- Per-level gates: L0 2.0/4, L1 2.0/4, L2 1.2/4, L3 0.2/4 (avg)
- L0 and L1 dropped from 5/5 completed (seed) to 0/5 completed — the
  mutator raised `CRUISE_SPEED` 1.5→1.8 m/s, and at 1.8 m/s the Mellinger
  low-level controller stops tracking cleanly.
- Aggregate rollout score: **0.538** (seed = 1.604 per-rollout = 0.8093
  weighted aggregate).

GEPA will see this is worse and skip. This is normal, healthy GEPA
operation — the loop is doing what it's supposed to do.

**Classification of observations:**
- MUTATOR-REPEAT: none yet (one data point).
- STDERR-IGNORED: none yet — the mutator did read the stderr but went
  the wrong direction on speed tuning. That's normal exploration, not
  a systematic ignore.
- INFRA: no new friction to report. The two residual things I noticed
  (a) hone's `Iteration N` log lines aren't flushing through `nohup ... >
  log` — suspect Python stdout buffering. Doesn't affect correctness,
  just makes log-tailing less informative. Would propose `PYTHONUNBUFFERED=1`
  in the launcher as a cheap fix for future runs. (b) Multiple CSVs per
  iteration in `runs/` — GEPA seems to call the grader several times
  per mutation (subsample + valset comparisons). Not a bug, just more
  noise in `runs/` than the initial design expected.

No CLAUDE.md edit needed. Continuing observation.

### 2026-04-20 09:55 — RUN 2 at iter 7: first winner is ITER 4 (+6.4%)

**Score trajectory** (rollout_score avg per candidate; seed avg = 1.175):

| Iter | cand avg rollout | vs seed | notes |
|---   |---               |---      |---    |
| 0    | 1.175            | —       | seed baseline, valset 0.8093 |
| 1    | 0.169            | −86%    | raised CRUISE_SPEED 1.5→1.8, broke L0/L1 tracking |
| 2    | 0.031            | −97%    | much worse, unknown change (deeper in file) |
| 3    | 1.014            | −14%    | closer but still below |
| 4    | **1.223**        | **+4%** | **WINNER** (hone valset: 0.8612 vs 0.8093, +6.4%) |
| 5    | 0.785            | −33%    | regressed |
| 6    | 0.250            | −79%    | terrible |
| 7    | 0.156            | −87%    | terrible |

**Iter 4 (the winner) diff vs seed:**
- `CRUISE_SPEED: 1.5 → 2.0` (+33%)
- `MAX_SPEED: 2.5 → 3.0` (+20%)
- `EXIT_DIST: 0.5 → 0.55` (+10%)
- `MIN_SEGMENT_TIME: 0.5 → 0.3` (-40%)
- **ADDED** `LOOKAHEAD_TIME: float = 0.4` — genuinely new parameter, suggesting the mutator introduced a lookahead mechanism (not just tuned existing numbers).
- Also adds `N_CACHED...` (truncated at 400 chars in our instrumentation — won't know full details without parsing the stored variant).

This is a real structural change, not pure parameter tuning. Mutator is actually reasoning about the algorithm.

### Observations / classifications

**MUTATOR-REPEAT (emerging):** 6 of 7 candidates scored worse than seed.
Pattern: raising speeds / tightening tolerances / changing tracking behavior
tends to break L0+L1 which were already clean. Mutator hasn't yet noticed
that **seed L0+L1 are already 5/5 completed — further "improvements" to those
levels cost more than they gain,** and real upside is L2/L3 (where seed is
0-3/4 gates). Need ~5+ more occurrences before this is confirmed and
escalatable.

**STDERR-IGNORED (possible):** The seed's per-level grid shows L0=2.238,
L1=2.238, L2=0.200, L3=0.025 (weighted). Dominant aggregate term is L0+L1
because those levels score highest-per-rollout when completed. Mutator's
focus on global "make it faster" rather than "unlock L3" may reflect the
stderr traces not making per-level prioritization visible enough — the
aggregate score dominates the signal. Would consider a future grader stderr
extension: "top bottleneck level" explicitly named per iteration.

**INFRA (confirmed earlier):** hone log buffering; multi-CSV per iter (GEPA
subsample + valset). No new infra issues.

### Cost / throughput after 7 iters
- Wall time: ~37 min since launch
- Mutator time: 1564s (26 min) summed
- Mutator calls: 7, avg mutator_s ≈ 224s (3.7 min/call)
- Grader time: ~11 min summed
- Total cost: **$2.157** → projected ~**$31** for budget 100
- Projected total wall time: ~6-7 hours

No CLAUDE.md edit. Continue.

### 2026-04-20 10:48 — RUN 2 COMPLETED (GEPA early-stop, not crash)

**Final state:**
- PID 86491 exited cleanly at ~10:28.
- Best score: **1.0778** valset aggregate (vs seed 0.8093 = **+33%**)
- Budget used: 13 mutator calls (of 100). Iters 14-20 GEPA-internal skipped
  with "All subsample scores perfect. Skipping. Reflective mutation did not
  propose a new candidate."
- Cost: **$4.0825** (tokens in=29, out=214,738). Wall time ~100 min.
- Winners: iter 4 (0.8612, +6.4%), then iter 13 (1.0778, +33%).

**GEPA early-stop behavior — observer note:**
GEPA's `skip_perfect_score=True` (hone default) + small trainset (size 1) +
deterministic grader means: once the pareto-frontier candidate(s) hit a high
subsample score, GEPA considers the subsample "solved" and stops proposing.
This ended our run at effectively iter 20 instead of 100. Not a bug, but a
**budget-utilization inefficiency** — we spent $4 to explore ~13 candidates
when the true budget allowed ~100. Escalation target for hone: either (a)
disable `skip_perfect_score` by default for code:python kind, (b) make it
configurable via CLI, or (c) re-score the pareto frontier on a held-out set
to detect when "perfect on subsample" is actually overfitting.

**Final per-level breakdown (best candidate graded on fresh seeds):**

| Level | Seed     | Best     | Δ     | Notable |
|---    |---       |---       |---    |---      |
| L0    | 2.238    | 2.588    | +15.6% | 5/5 completed, faster lap (8.08→6.30s) |
| L1    | 2.238    | 2.577    | +15.1% | 5/5 completed, faster lap (8.08→6.30s) |
| L2    | 0.200    | 0.739    | **+270%** | From 0/5 completed to some completions at 6.36s |
| L3    | 0.025    | 0.050    | +100% | Still tough, only 1/5 passed any gate (timeouts dominate) |

**L2 breakthrough is the story.** Seed couldn't complete any L2 rollout;
best candidate completes several. On L3 the gains are small absolute — the
planner still doesn't have dynamic replanning for random tracks (STACK.md
Level 3 territory).

**MUTATOR-REPEAT pattern — NOT confirmed at ≥5 occurrences.**
Run didn't use enough budget to see this emerge. Iterations 1,2,3,5,6,7
regressed (6 of 13 = 46%) but the pattern varied (not the same broken edit
5 times in a row). By iter 8, GEPA had locked onto iter 4's baseline and
iters 8-12 proposed from that parent, most scoring in the 0.4-0.6 range
(subsample) — lower than parent's 2.58. Iter 13 broke through. I didn't
observe a single specific repeated bug class — I observed **high variance
exploration** where the mutator occasionally stumbles on a good tune.

**STDERR-IGNORED — observation logged for ace_case.md.**
Baseline's L0+L1 perfectly completed, L2+L3 struggled. Mutator's
improvements were evenly distributed across L0 and L1 (+15% each) and
strongly on L2 (+270%) but barely on L3 (+100% of a tiny number). The
mutator doesn't seem to have focused effort on L3 proportional to its
3x weight. This MIGHT be an L3-priority-underweighted signal. But it could
also be that L3 is genuinely harder (random tracks) and the gains require
actual replanning logic, not parameter tuning. Inconclusive.

**INFRA findings (final):**
- `PYTHONUNBUFFERED=1` in launcher would make tailing `hone_run.v2.log`
  useful in real time. Without it the Iteration N log lines only flush at
  buffer fills or exit.
- `runs/` accumulated 46 CSVs by end of run (one per GEPA eval). Not a bug
  but a tidy-up-opportunity: name CSVs with iter number + role
  (e.g. `iter4-subsample.csv`, `iter4-valset.csv`) for easier forensics.

**Run 2 complete. No further CLAUDE.md edits. Proceeding to final writeups.**

