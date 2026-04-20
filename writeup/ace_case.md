# ACE case — build `hone run --observer` next?

**Status: FINAL after Run 2 completion (13 mutator iters, +33% aggregate).**

> ACE proposal: `hone run file.py --observer claude-code:sonnet
> --observer-interval 10`. An observer agent watches logs, proposes CLAUDE.md
> edits (or rejects, letting the human approve). Key question: is the manual
> observer work actually automatable, or is it human-judgment-heavy?
>
> Scope expansion noted mid-run: observer might ALSO decide which target
> file(s) the mutator edits each turn (multi-module routing).

## TL;DR

**ACE is not justified by this data.** Across two runs (6-iter aborted + 13-iter
successful = 19 total mutator calls), only 2 CLAUDE.md edits were made, both
in Run 1, both of which turned out to be no-ops (harness wasn't injecting
CLAUDE.md — a bug, not a gap ACE would have identified). Run 2 succeeded
**without any CLAUDE.md edits** and improved +33% on its own. The bottleneck
was never CLAUDE.md content; it was:
1. The harness layer (fixed by honefix PRs — static, one-shot work)
2. GEPA's `skip_perfect_score` burning budget too fast (observer couldn't have
   fixed this — it's a GEPA config issue)

The data strongly suggests **the next investment should be hone/harness
robustness, not an observer layer**. Observer design question is still
worth holding open once we reach 100-iter runs with actual pattern formation.

## The four questions, answered with full Run 1 + Run 2 data

### 1. How many CLAUDE.md edits did the human observer make?

**Total: 2 edits, both in Run 1, both ultimately no-ops.**

| Edit | Run | Iter trigger | Outcome |
|---   |---  |---          |---      |
| #1   | 1   | iter 2 — mutator returning prose | Did not affect subsequent iters (harness didn't inject workdir CLAUDE.md) |
| #2   | 1   | iter 4 — Tim noticed "return ... no tools" conflicted with claude-code default | Same — did not affect subsequent iters |

In Run 2, **zero CLAUDE.md edits** were needed. I made a slim-down edit at
Run 2 start (removing the Run 1 self-patch) but did NOT edit during the run.
Budget 25-iter rule was never triggered — Run 2 ended at iter 20 before the
first allowed edit window.

**Would an automatic observer have triggered at the same points?**
- Run 1 Edit #1: yes, trivially. Any LLM reading mutations.jsonl can detect
  "response doesn't start with docstring/import/#" and flag it. Pure output-
  shape detection.
- Run 1 Edit #2: partly. Identifying that "return X" prose implies "no tools
  allowed" and that this conflicts with Claude Code's default Edit-tool
  workflow — that's UX intuition about the mutator tool. An observer could
  potentially learn this with enough documentation or prior runs, but a
  greenfield observer would miss it.

**Score: 1 of 2 edits mechanically detectable; 1 needed Tim's human insight.**

### 2. How often did "mutator keeps making the same mistake" patterns appear?

**0 confirmed patterns across 19 total iterations.**

- Run 1 (6 iters): every iter scored 0, but for **three different reasons**
  (prose, markdown-fenced, no-Planner-class). Not a repeated pattern class.
- Run 2 (13 iters): 6 iters regressed vs seed (iters 1, 2, 3, 5, 6, 7),
  but the regressions varied:
  - Iter 1: CRUISE_SPEED 1.8 (Mellinger tracking break)
  - Iter 2: unknown specific change, score 0.031
  - Iter 3: closer to seed but worse
  - Iter 5: regressed from iter-4 baseline
  - Iters 6-7: different specific breaks

No single repeated bug class was observable at ≥5-occurrence frequency. The
mutator explored widely rather than making the same bad edit over and over.

**Threshold for ACE justification was ≥5 same-pattern observations. Got 0.**

### 3. Did manual CLAUDE.md edits measurably help?

**Run 1: no. Run 2: no edits were made, so N/A.**

For Run 1: flat score trajectory (every iter 0.0) — no correlation possible.
The post-mortem probe confirmed the harness wasn't delivering CLAUDE.md to
the mutator at all, so edits couldn't have helped.

For Run 2: the run improved +33% with zero CLAUDE.md intervention. So:
**CLAUDE.md edits were unnecessary for this run.** That's a direct data point
against ACE. The real levers were:
- Harness: inject CLAUDE.md as system prompt (fixed upstream)
- Hone: use code-aware mutator prompt template (fixed upstream)
- Hone: post-validate output with ast.parse (fixed upstream)

All three are one-shot static fixes. An ACE observer would have been
irrelevant here.

### 4. What fraction of observations could a reflection-LLM have caught?

Counting all observer-relevant observations from Run 1 + Run 2:

| # | Observation | LLM-catchable? |
|---|---         |---             |
| A | R1 iter 1+2: response prose not Python | **YES** — `compile()` on response head |
| B | R1 iter 3: valid Python wrapped in markdown fences | **YES** — string prefix check |
| C | R1 Edit #1 language implicitly conflicts with claude-code default | **NO** — needed human UX intuition |
| D | R1 throughput 3.5 min/iter | YES (trivial arithmetic) |
| E | R1 per-iter cost skew 3× (iter 3 at $0.41) | YES (aggregate log) |
| F | R1 harness doesn't actually load workdir CLAUDE.md | **NO** — needed intentional probe, not a passive observation |
| G | R2 iter 1 confirmed Python — fixes work | YES (trivial) |
| H | R2 iter 4 first winner with new `LOOKAHEAD_TIME` param | YES (string diff the candidates) |
| I | R2 iter 13 final winner with tight param tuning vs iter 4 | YES (same) |
| J | R2 mutator over-indexes on L0/L1 despite those being already-completed | **partial** — needs stderr analysis + weighting awareness; an LLM could do it with the CLAUDE.md guidance already present |
| K | R2 GEPA `skip_perfect_score` ended run at iter 20 with budget unused | YES (grep hone log) |
| L | R2 L2 gains came without L2-specific changes (parameter-cascade, not targeted) | partial — needs cross-candidate analysis |
| M | R2 L3 untouched — requires architectural change | **NO** — needs domain knowledge about drone racing (random tracks → need replanning) |

**Split: 9 of 13 (~70%) purely LLM-catchable. 4 of 13 (~30%) needed human
judgment / domain knowledge / active probing.**

Tim's earlier named threshold was 80/20 → build ACE; 30/70 → don't. We're
closer to 70/30, which is BETWEEN those thresholds. The 4 human-needed
observations are:
- C: UX knowledge of claude-code tool-use semantics
- F: required an active probe, not passive log-watching
- M: domain knowledge (drone racing L3 semantics)
- J (partial): weighting awareness

None of these are small. C directly surfaced the fix that made Run 2 work.
M is the whole "what do we build next for L3" question.

## Recommendation

**Don't build ACE yet. Ship the honefix patterns as hone/harness features
(several already in). Run hone on 2-3 more real code-optimization problems
to see if the MUTATOR-REPEAT pattern emerges in other domains. Revisit ACE
when we have data from those runs.**

Reasons for this position:
1. Runs 1+2 never produced a single repeated mutator-bug class, let alone
   five. The claim "observer would catch patterns the mutator repeats" has
   no supporting data here.
2. The specific Run 1 failure was static-validation territory (compile-check
   output, detect markdown fences). Shipping those as harness post-processing
   beats shipping them as "observer fires after N iters and edits CLAUDE.md."
3. Every CLAUDE.md edit made (2 of them) was ultimately moot — either
   superseded by upstream fixes or never reached the mutator. That's not a
   signal that CLAUDE.md editing is valuable; it's a signal that the
   information ecosystem was broken.

**Reasons ACE might still be worth building**:
1. This was a small, single-file, single-rotation-target run. ACE's "which
   module next" scope extension is untested — it might be where ACE shines.
2. L3-style domain knowledge (observation M above) WOULD benefit from an
   observer that reads ROADMAP.md + STACK.md and proposes "rotate to
   world_model.py next." This is a very different role than "fix the
   mutator's output." The two-observers-one-loop framing Tim raised might
   make sense.
3. If we ran 10 hone runs per week, the observer's "infrastructure friction"
   category (our INFRA observations) would amortize over lots of runs.

## Escalations to `hone` / `harness` (final list)

| # | Project | Escalation | Priority | Landed? |
|---|---      |---         |---       |---      |
| 1 | hone | `--component-kind {prompt|code:py|code:ts|...}` + auto-detect | high | **YES** (code:python auto-detect from `.py`) |
| 2 | hone | Post-validate mutator output (parse, retry, don't charge budget on fail) | high | **YES** (`_syntax_check_python` with one retry) |
| 3 | hone | Rename "prompt" → "component" in code-kind template | medium | **YES** (new template: "editing a Python module") |
| 4 | harness | Inject workdir/CLAUDE.md via --append-system-prompt | high | **YES** (commit 435b361) |
| 5 | hone | File-based mutator mode (worktree + Edit + read back) | medium | **NOT YET** — won't add before text-mode is proven insufficient |
| 6 | hone | Diff-visibility between iterations | low | **NOT YET** |
| 7 | hone | `skip_perfect_score=False` (or configurable) for code:python to avoid budget under-utilization | **NEW / medium** | **NOT YET** |
| 8 | hone | Name CSVs by iter+role for forensics | low | **NOT YET** |
| 9 | hone | `PYTHONUNBUFFERED=1` in recommended launch pattern | low | **NOT YET** |

## Scope expansion notes (from Tim, mid-Run 1)

Carried over for next time:
- ACE could also decide which target file(s) the mutator gets each turn.
  Multi-module routing — overlap with ROADMAP.md Level 2.
- Single observer with two powers vs two observers. Still undecided —
  needs multi-module-run data to answer.

## Observations that don't fit the above

- **The most interesting observer insight across both runs was Tim's** — he
  caught the claude-code-default-mode UX conflict in 2 sentences. I wouldn't
  have caught that without many more iterations. Human-loop-integration isn't
  optional.
- **Run 2 ended with 87% of the budget unused ($4 of $30 spent).** This is
  partly a GEPA optimization (it converged) and partly a budget-utilization
  bug (skip_perfect_score on a 1-example trainset). Either way, "observer
  interval 10" is the wrong default when runs can end at iter 20.
- **Meta-point for ACE design:** observer-interval should probably NOT be
  a fixed number of iterations. It should be keyed on
  (`budget_used / budget_total`, `valset_score_stagnation`, `recent_error_rate`).
  If we build ACE, this adaptive-trigger design question matters more than
  the "what does the observer do when it fires" question.
