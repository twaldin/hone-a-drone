# Drone state snapshot — 2026-04-20 ~21:15 UTC (post-clear)

**If you're a fresh drone reading this after /clear: read `.drone-brief.md`
at repo root FIRST. That's the full original overnight brief. Then this file.**

## Who/what
- **You** are the `drone` agent in Tim's flt fleet. Parent = `cairn` (orchestrator).
- **Communication**: `flt send parent "..."` for milestones/blockers. Terminal output has no human viewer.
- **Project**: `~/dev/hone-a-drone` — repo at https://github.com/twaldin/hone-a-drone (public)
- **Date**: 2026-04-20 (Apr 20). Overnight run for Tim's Anduril AI Grand Prix qualifier prep (May-July 2026).

## Where the arc is right now

**THREE PARALLEL v2-rerun runs ACTIVE.** Same architecture, different mutator/observer combos.

| Run | PID | Mutator | Observer | .hone dir | output dir | log |
|---|---|---|---|---|---|---|
| A (cc-cc) | **31029** | harness:claude-code:sonnet | harness:claude-code:sonnet | `.hone/run-20260420-182940-1d2d06` | `controllers.v2rerun-honed` | `runs-v2-rerun/logs/full.log` |
| B (oc-cc) | **37659** | harness:opencode:openai/gpt-5.4 | harness:claude-code:sonnet | `.hone/run-20260420-204634-4b87ed` | `controllers.v2rerun-opencode-honed` | `runs-v2-rerun-opencode/logs/full.log` |
| C (oc-oc) | **40763** | harness:opencode:openai/gpt-5.4 | harness:opencode:openai/gpt-5.4 | `.hone/run-20260420-204811-5a8f07` | `controllers.v2rerun-oc-observer-honed` | `runs-v2-rerun-oc-observer/logs/full.log` |

All started afternoon 2026-04-20, budget 100 each. ~4h expected to completion. Run A started ~2h earlier than B+C.

**Check any run**: `ps -p <PID>` alive? `wc -l <.hone dir>/mutations.jsonl`. Latest scores: `grep best= <log> | tail -3`.

## Baselines + results so far

| Run | Best score | Δ seed | Notes |
|---|---|---|---|
| seed (v1 min-snap+cubic+obstacle) | 0.8093 | — | unchanged for all runs; `controllers/planner.py` pre-v3-restructure |
| v1 (single-file, text-mode, hone+GEPA only) | **1.0778** | +33% | iter 13/100, GEPA early-stop. $4.08. See `writeup/first_run.md`. |
| v2 (dir-mode + diagnose + ACE, edit-tool) | 0.9041 | +11.7% | iter 53, 100 iters, $27.06, 24% error rate. Underperformed v1 because grader was single-file. See `writeup/v2.md`. |
| v2-rerun A (cc-cc, 600s timeout, multi-file grader) | 0.8424 (iter 46/100, plateaued since iter ~23) | +4.1% | running. |
| v2-rerun B (oc-cc) | 0.8093 (iter 25/100, no improvement over seed yet) | 0% | running |
| v2-rerun C (oc-oc) | 0.8168 (iter 25/100) | +0.9% | running |

**Per-level v1 best**: L0=2.588, L1=2.577, **L2=0.739 (+270%)**, L3=0.050. Seed: L0=L1=2.238, L2=0.200, L3=0.025.

## Key architectural changes in v2-rerun vs v2

1. **`run_rollout.py`**: inserts `Path(planner_path).parent.resolve()` at `sys.path[0]` before importlib, so planner.py can `from attitude_ctrl import make_state_command`, etc. Also purges cached sibling modules per iter.
2. **`controllers/planner.py`** (seed): now composes with all siblings:
   - `from attitude_ctrl import make_state_command`
   - `from state_estimator import StateEstimator`
   - `from gate_detector import GateDetector`
   - `from world_model import WorldModel`
3. **CLAUDE.md**: updated constraints #3 and #4 — multi-file imports are now ALLOWED within `controllers/`. Picked correct layer for each change.
4. **hone-v2**: `HarnessMutator.DEFAULT_TIMEOUT_SECONDS` bumped 300→600.
5. **hone-v2 `proposer.propose_for_file`**: dual-writes both `CLAUDE.md` and `AGENTS.md` into workdir (so claude-code adapter AND opencode/codex adapters both see ACE-managed rules).

## Active crons

```
every 30m  v2rerun-wrapup       → sends wrap-up prompt when cc-cc run done
every 30m  v2rerun-oc-wrapup    → for oc-cc run
every 30m  v2rerun-oc-obs-wrapup → for oc-oc run
```

Remove each with `flt cron remove <name>` after its run wraps.

## Pending actions (in order)

1. **Wait for 3-way to finish.** 4h wall expected. Cron wrap-ups will trigger the wrap-up prompt.
2. **When EACH run finishes**:
   - `./grader.sh controllers.<runname>-honed` → lock final per-level scores
   - Compare to v1 1.0778 and v2 0.9041
   - Write section of `writeup/v2rerun-3way.md` OR separate writeup per run
   - `git add -A && git commit -m "v2-rerun <variant>: ..." && git push`
   - `flt send parent` with URL + headline numbers
   - `flt cron remove <cron-name>` for that run's cron
3. **After all three done**: write consolidated `writeup/v2rerun-summary.md` with harness A/B/C comparison populating the leaderboard table (see `writeup/harness-metric-design.md`).
4. **Then implement v3 per `writeup/v3-spec.md`** — bandit over mutator-pool + observer-pool. ~1-2 days. Smoke first, then full run.

## Writeups authored so far

- `writeup/first_run.md` — v1 experiment report (+33% win)
- `writeup/ace_case.md` — ACE not-yet-justified verdict from v1
- `writeup/v2.md` — v2 aborted-grader underperformance analysis
- `writeup/harness-metric-design.md` — leaderboard design (per-arm stats, Pareto, $/score)
- `writeup/v3-spec.md` — bandit-over-mutators full SPEC (3-layer meta-optimizer)

## Hone fork state

- **v1 hone** (github.com/twaldin/hone): the upstream. Uninstalled from project venv in favor of v2.
- **hone-v2 local fork at `~/hone-v2/`** (branch `v2`): installed editable in project venv.
- Key hone-v2 files (ALL created/modified by drone):
  - `src/hone/dir_target.py` (NEW): DirSnapshot, DirTarget
  - `src/hone/scheduler.py` (NEW): Scheduler ABC, RoundRobin, Random, Diagnose, build_scheduler
  - `src/hone/observer.py` (NEW): Reflector+Curator per arxiv 2510.04618
  - `src/hone/optimizer.py` (MOD): added `optimize_dir()`, helpers
  - `src/hone/cli.py` (MOD): `--dir`, `--observer`, `--scheduler`, `--mutator-pool`-style flags wired
  - `src/hone/proposer.py` (MOD): added `propose_for_file`, dual-writes CLAUDE.md/AGENTS.md
  - `src/hone/storage.py` (MOD): RunManifest `mode`, `dir_root`, `scheduler_spec`, `observer_spec`
  - `src/hone/mutators/harness_mutator.py` (MOD): `propose_edit_mode`, `DEFAULT_TIMEOUT_SECONDS=600`

## Honefix feature requests filed (upstream hone/harness)

Already escalated, some landed:
- (LANDED v1) hone `--component-kind code:python` auto-detect + AST syntax-check on mutator output + "you are editing a Python module" prompt for code kind
- (LANDED v1) harness `claude-code` adapter: `--append-system-prompt "$(cat CLAUDE.md)"` to inject workdir CLAUDE.md
- (LANDED v1) harness: strip markdown fences from response `result` field
- (NOT YET) `hone resume <run-id>` — CITATIONS.md:21 aspirational, NO implementation. Either ship or delete the line.
- (NOT YET) `hone --mutator-timeout 600` CLI flag — currently HarnessMutator default is bumped in hone-v2 src.

## Raw data locations

- `runs-aborted-run1/` — v1 Run 1 archived (broken-harness era, $1.39)
- `runs/` — v1 Run 2 data ($4.08 winner), csvs + mutations.jsonl
- `runs-v2/` — v2 data, observations.md, logs, csvs
- `runs-v2-rerun/` — v2-rerun A (cc-cc), live
- `runs-v2-rerun-opencode/` — v2-rerun B (oc-cc), live
- `runs-v2-rerun-oc-observer/` — v2-rerun C (oc-oc), live
- `.hone/run-*/` — per-GEPA-run storage (mutations.jsonl, observations.jsonl, claude_md_versions/)
- `controllers/` — the mutation target (planner.py, attitude_ctrl.py, state_estimator.py, gate_detector.py, world_model.py, baseline.py)
- `controllers.v2-honed/` — v2 best artifact
- `controllers.v2rerun-honed/`, `...-opencode-honed/`, `...-oc-observer-honed/` — v2-rerun outputs (populated at run-end)

## Open research questions carried for cairn

From the novelty investigation request:
1. Is `hone v2` (GEPA + harness + ACE) a new combo in the DSPy/LLM-opt literature?
2. Ship as ONE project (v1 evolves to v2/v3) or separate projects?
3. GEPA-on-GEPA (nested hone runs, outer tunes the CLAUDE.md of inner) — meaningfully different from ACE-over-GEPA?

These were sent to cairn earlier; no response logged yet. Carry for v3 writeup reasoning.

## Tim's preferences (from ~/.claude/CLAUDE.md + interactions)

- Direct comms, no preambles, no filler
- Never `Co-Authored-By` trailers or Claude attribution on commits
- TDD when possible; no over-engineering
- POC speed > correctness theater (repeated in cairn's briefs)
- "Zero-guesswork from SPEC means follow it without second-guessing"
- Honest negative data points > positive-result theater

## If the current session is compacted

1. Read `.drone-brief.md` (original overnight brief) first.
2. Then read THIS file (`memory/state.md`).
3. Then `writeup/v3-spec.md` for what's queued next.
4. Check running runs: `ps -p 31029 37659 40763` and the mutations.jsonl counts.
5. The crons will self-fire — don't panic if I'm not actively checking.
6. `flt list` to see fleet status. I'm "drone" under "cairn".

## Last human message I was responding to

Tim asked me to spec out v3 (bandit over mutator/observer pools) and inform
cairn. I drafted `writeup/v3-spec.md` and sent cairn a flt summary.

## 2026-04-20 ~21:15 UTC — v3 spec decisions locked by cairn

Cairn delivered 5 decisions (Tim approved). All now written into
`writeup/v3-spec.md` §0 (decisions block at the top) AND into the
relevant detailed sections. **READ §0 FIRST when resuming work on v3.**

Summary of what changed in v3-spec.md:

1. **Per-arm ACE playbook** — new §4.2 with dispatch flow, file layout,
   arm-hash convention. Seeded from the shared task CLAUDE.md. Observer
   writes only to the selected arm's playbook. Dual-write (v2 workaround)
   is retired because we know which file each adapter reads.
2. **Default reward = `score_delta`** — updated CLI table, §3.2 reward-mode
   table (default swapped), §8 full-run command, §5.3 summary.json example.
   `score_per_dollar` stays opt-in with a cost-flooring / skip-on-None
   policy to avoid div-by-zero on Max subs.
3. **Thompson removed** from selector list in §3.3 and from §4 observer
   pool. Observer default is now UCB1 with `c=2.0` (larger exploration
   constant for low-sample regime).
4. **Error reward = 0** — §3.2 now argues this with the self-correction
   math (error-prone arm's mean drops to 0 × success_rate × E[r|success];
   UCB1 exploration bonus also shrinks with plays). Minor caveat about
   consistently-regressive arms noted but not blocking.
5. **Cold-start cap** — §3.4 now `min(2 * pool_size, 10)`.

Also deleted the §6.2 "mutator-agnostic rules" mitigation (obsolete with
per-arm playbooks) and added `playbooks.py` to the implementation file
list in §5.1 + bumped the implementation-order list in §11.

**Next**: nothing. Cairn said "no action needed on 3-way runs." The 3 v2-rerun
runs are still grinding; crons will wrap them. Scout agent is handling
NOVELTY/PITFALLS/POSITIONING separately at `~/dev/hone-novelty/`.

If I wake again before the 3-way finishes, I idle. If a run wraps (cron
fires its wrap-up prompt), I run through the wrap-up sequence in §62 above.

## 2026-04-20 ~21:40 UTC — scout findings folded into v3-spec

Cairn forwarded scout's key findings. Spec updated accordingly:

1. **§0 gained decisions 6, 7, 8** — sliding-window UCB (W=20) becomes v3.0
   default, per-iter bandit_state logging is mandatory, novelty framing
   narrowed because ShinkaEvolve (arxiv 2509.19349, ICLR 2026) already did
   UCB1-over-LLMs for code evolution.
2. **§3.3 UCB1 selector rewritten** as sliding-window UCB with a working
   pseudocode impl + citation to Garivier & Moulines 2011. Flag:
   `--bandit-window 0` disables sliding (degenerates to classic UCB1).
3. **§5.4 per-iter logging** — `mutations.jsonl` now specifies a full
   `bandit_state` JSON block per iter (arm_ucb_scores, plays_in_window,
   mean_reward_in_window, picked_reason enum).
4. **§10 novelty rewritten** — credits ShinkaEvolve, narrows v3's
   contribution to (a) harness-level arm granularity (CLI + model pair),
   (b) per-arm ACE playbook scoping. Workshop-publishable not full-venue.
   Real competitors listed: OpenEvolve, ShinkaEvolve, DSPy/GEPA — not
   orchestration (LangGraph, AutoGen) or eval (Braintrust).
5. **§11 implementation order** — step 1 now requires TWO synthetic tests
   (classic UCB + sliding-window on a mid-run arm-flip scenario).
   `--bandit-window` CLI flag added to step 2.

Scout docs at `~/dev/hone-novelty/`: NOVELTY.md, PITFALLS.md,
POSITIONING.md, SCOUT-ADDENDUM.md. Still pending: LANDSCAPE.md,
MULTI-GRADER.md — cairn will forward.

No code change yet — all doc. Acknowledged to cairn via flt.

## 2026-04-20 ~22:00 UTC — scout LANDSCAPE + MULTI-GRADER folded in

Cairn forwarded last 2 scout deliverables. Did NOT rescope v3.0
(decisions §0 still locked). Added forward-looking §12 to v3-spec.md +
drafted `writeup/v3.1-spec.md` stub.

**v3-spec.md §12 now covers:**
- §12.1 — v3.1 = multi-grader, 2 person-weeks, default combine = Pareto
- §12.2 — moat = MODERATE; strongest component = harness cross-CLI
  abstraction (first-mover value). Biggest risk = DSPy ships coding-CLI
  adapter for GEPA (<6mo probability). Defense: ship fast or contribute
  harness lib upstream to DSPy.
- §12.3 — weekly watchlist: DSPy changelog for coding-CLI adapter
  mentions, ShinkaEvolve extensions, OpenEvolve multi-grader.
- §12.4 — v3.2+ flagged (SWE-bench Live Q3 2026, Stockfish Q4 2026,
  hone-on-hone meta Q1 2027, contextual bandit coupling, ACE Option C).

**New file: `writeup/v3.1-spec.md`** (stub, ~100 lines):
- CLI: `--grader` repeatable + `--grader-combine {pareto|weighted|lex|eps}`
  defaulting to pareto
- Bandit reward for Pareto = hypervolume contribution
- summary.json per-grader-per-arm stats + pareto_frontier block
- Open questions flagged: HV reference point, >3 graders, partial
  grader failures, lineage under Pareto

Parent acknowledged via flt.

## 2026-04-20 ~22:30 UTC — run-2 mid-run analysis + v3 spec responses

Dug into the 3 live runs (57/64/62 iters) to pull writeup-useful data.
Sent cairn 3-part findings message. Then cairn answered 3 questions;
I folded responses into v3-spec.md + v3.1-spec.md.

### Key findings from mid-run inspection

- **Grader contract is unbounded float** (hone-v2/src/hone/grader.py:71).
  Drone aggregate practical ceiling ~3.5; v1's 1.0778 ≈ 30% of ceiling.
  L3 weight 3.0 is dominant headroom.
- **Per-file gains: 100% from planner.py across all 3 runs.**
  world_model.py got 14 edits across B+C with ZERO accepts.
  attitude_ctrl.py got 3 edits in B with zero accepts.
  Dynamic scheduler IS firing, but non-planner edits uniformly fail
  the GEPA parent-beats check.
- **Run C's ACE observer never applied a single rule.** 6/6 fires
  errored with "opencode not usable as mutator — coding loop not text."
  Yet C (0.9369) > B (0.8941) which had a working cc observer.
  N=3 + one broken config gives NO evidence ACE helps on this task.
- **Cross-arm convergent discovery: both opencode runs (B, C) swapped
  CubicSpline → PchipInterpolator independently. cc (A) didn't.**
  Divergent algorithmic search across arms — real v3-novelty signal.
- **cc observer rules converged on same high-level lesson** across
  runs A and B: "out_of_bounds is a geometry/smoothness problem, not
  a velocity problem." Different specific rules, same abstract lesson.

### v3-spec.md edits this turn

- §3.3 gained reward-range caveat + `--bandit-normalize window_minmax`
  default (because grader contract is unbounded and classic UCB1
  assumes [0,1]).
- §3.5 NEW: arm compatibility matrix (claude-code ✅✅, opencode ✅❌,
  codex ✅?, aider ??, gemini ✅✅). Pre-flight CLI validation rejects
  incompatible specs. Mid-run: abort on FIRST observer fire failure
  (silent degradation invalidates comparison). Override:
  `--allow-partial-arm-failure` for exploratory runs.
- §12.1 gained adaptive-file-weights paragraph as v3.1 follow-up,
  citing run-2's all-gains-from-planner data.

### v3.1-spec.md edits this turn

- §5a NEW: `--scheduler-adaptive-file-weights {off|accept_rate|ucb1}`,
  default off. Three rationales: single-task evidence insufficient,
  users can force-route via scheduler.json, bandit-style target
  selection reuses v3.0's selector module.

### Cairn's writer-facing framing call (no action from me)

Cairn told writer to reframe: "v2-rerun multi-file + bandit did NOT
clear v1's 1.0778 on hone-a-drone. Task is planner-dominated; siblings
had no headroom. L3 still the ceiling. What we LEARNED: (a) cross-CLI
arm granularity produces real divergent search. (b) ACE inconclusive at
N=3 with one broken observer. (c) Multi-file architecture is right for
other tasks but wrong tool for this demo — next reference problem
(SWE-bench Live) needs it to prove itself."

## 2026-04-20 ~23:00 UTC — HONE-MODES.md drafted

New unifying forward-look doc at `writeup/HONE-MODES.md` (494 lines / 4082
words). 7 sections: Framing → Axes (9 subsections) → Presets → v3.0 ships
→ Auto mode concept → Known/Suspect/Unknown → Research directions.

Intent: one file for readers (new users + future drones) to understand
the shape of the project without reading v3-spec + v3.1-spec + BLOG-DRAFT
simultaneously. Sits ABOVE the spec docs, not a replacement.

Slop-check passed (no banned words per writing skill).

Reported to cairn: axes with most 'unknown' content ranked (Observer,
Edit mode, Reward attribution), and four candidate additions to v3-spec
§0 locked list:
- D9: --bandit-normalize window_minmax default
- D10: --allow-partial-arm-failure defaults OFF
- D11: Harness compat matrix as module-level constant (not just docs)
- D12 candidate: Edit-mode locked to 'single-file-per-iter via scheduler
  brief' (whole-workdir explicitly deferred).

Waiting for cairn's ack before folding any of these into v3-spec §0.

## 2026-04-20 ~23:15 UTC — v3-spec §0 gained decisions 9-12

Cairn approved all four candidate promotions. Folded in.

9. `--bandit-normalize window_minmax` default ON (cites §3.3 unbounded-
   grader rationale).
10. `--allow-partial-arm-failure` default OFF, fail-loud on first fire
    (cites §3.5.3, Run C opencode-observer silent-fail incident).
11. Harness compat matrix is `HARNESS_COMPAT` module constant in code,
    not just docs. Unknown adapters rejected by default.
12. Edit mode locked to "single file per iter via scheduler brief."
    Whole-workdir-per-iter is v4+ and requires a new proposal with
    reward-attribution story (cites HONE-MODES.md §2.3).

§12.4 updated to reference HONE-MODES.md as the unified forward-look.
Ack'd to cairn. Idling.
