# HONE-MODES — what hone can do, organized by axis

This is the one-file map of hone: everything the tool does today, everything
it will do after v3.0 lands, and the design directions that are under
discussion but not built yet. It sits above `v3-spec.md` and `v3.1-spec.md`
(those are the implementation contracts) and is meant for two readers:
a new user trying to figure out which knobs to turn, and a future drone
picking up the project mid-stream.

It is **not** the README (that lives at `github.com/twaldin/hone`) and it
is **not** the blog post (`BLOG-DRAFT.md`). Those tell you what the tool
IS and what happened when we pointed it at a drone sim. This tells you
what axes of choice the tool exposes and where each axis is on the
roadmap.

Status markers:
- **v0.3** — shipped today
- **v3.0** — spec locked, implementation in flight (see `v3-spec.md`)
- **v3.1** — stub spec, queued (see `v3.1-spec.md`)
- **v4+** / **future** — design idea, not on the critical path
- **WIP** — under active experiment; data pending

---

## 1. Framing

GEPA's [`optimize_anything`](https://gepa-ai.github.io/gepa/blog/2026/02/18/introducing-optimize-anything/)
is the base API hone implements. GEPA (Agrawal et al., arxiv 2507.19457)
is a reflective Pareto optimizer: propose candidates, grade them, keep
the winners, let the mutator see the trace of recent attempts. The
algorithm is generic over what the artifact IS — a prompt, a program, a
config file — as long as you have a grader that scores it.

Hone's distinguishing moves are three compositions on top of that base:

**Agent-as-mutator.** DSPy's default GEPA mutator is a single LLM
completion that rewrites a string. Hone swaps that completion for a full
coding-CLI invocation — claude-code, opencode, codex, aider, gemini —
abstracted through [harness](https://github.com/twaldin/harness). The
agent opens a workdir, uses its real Edit tool, reads other files for
context, and hands back a modified directory. The artifact under
optimization stops being a string and starts being a whole code project.
One "mutator call" is one agent turn, internally composed of many
tool-use steps.

**ACE as observer.** Zhang et al. ([arxiv 2510.04618](https://arxiv.org/abs/2510.04618),
ICLR 2026) published ACE — a Generator/Reflector/Curator loop that
incrementally edits the agent's context ("playbook") based on recent
execution traces. Hone ports the Reflector+Curator as an optional
parallel observer that edits the mutator's `CLAUDE.md` every N iters. ACE
was framed by its authors as a **competitor** to GEPA; hone stacks them
because they optimize different objects (GEPA = which candidate to keep,
ACE = how the agent thinks about the task).

**Bandit over agents.** v3.0 accepts a pool of `(coding-CLI, model)`
specs as mutator arms and a selector (UCB1 default) that picks one per
iteration based on observed reward. This is the same structural move
Sakana's [ShinkaEvolve](https://arxiv.org/abs/2509.19349) (Takei et
al., ICLR 2026) makes for API-level LLM ensembles in evolutionary code
search — hone extends it to coding-CLI agents as arms.

One-line story: **point hone at text plus a grader plus the agents you
want to use; it evolves the text AND picks agents simultaneously.**

Upstream credit (load-bearing, not ceremonial):
- [**GEPA**](https://github.com/gepa-ai/gepa) — the Pareto search
  algorithm hone wraps. Everything else sits on top.
- [**ACE**](https://arxiv.org/abs/2510.04618) — the reflector-curator
  split for incremental playbook refinement.
- [**ShinkaEvolve**](https://arxiv.org/abs/2509.19349) — established
  UCB1-over-LLMs for evolutionary code search. v3's bandit layer is not
  novel per se; the coding-CLI-arm granularity is.
- [**harness**](https://github.com/twaldin/harness) — the adapter
  library that makes "one CLI agent" the unit of abstraction, not "one
  API endpoint."

---

## 2. Axes of choice

Each axis below is one knob the user can turn (now or in the future). For
each: what it is, what the options are today, what's coming, default
behavior.

### 2.1 Artifact

*What's being optimized.*

| Option | Status | Note |
|---|---|---|
| Single file (`--file` or positional arg) | v0.3 | The v1 drone-racing run used this. Pass a path; hone mutates just that file each iter. |
| Directory (`--dir`) | v0.3 | Pass a directory; hone treats the whole tree as one candidate. Grader gets a directory path. |
| Multi-directory / multi-repo | future | Evolve code spanning repositories. No implementation; open question what "one candidate" means when it spans repos. |

**Default:** single file is the historical default; `--dir` flips on
directory mode. v3.0 keeps both unchanged.

**When to change:** single-file if your improvement target is one module
and the grader imports just that. Directory if there's real cross-file
work (SWE-bench Live, orchestrators, libraries). Hone-a-drone v2-rerun
evidence: if the dominant file gets 90%+ of the accepts, the directory
machinery idles (see `BLOG-DRAFT.md` §"v2-rerun"). Not a bug — a task
shape — but worth knowing before you enable it.

### 2.2 Mutator

*Who does the editing each iter.*

| Option | Status | Note |
|---|---|---|
| Single `harness:<cli>:<model>` spec | v0.3 | `--mutator harness:claude-code:sonnet`. Same agent every iter. |
| Pool of specs (bandit-selected) | v3.0 | `--mutator-pool spec1,spec2,spec3`. Selector picks one per iter. |
| Agent-internal edit decisions | v0.3 (always on) | Inside one mutator call, the agent decides which files to edit via its own tool use — independent of the `--dir` scheduler (which picks the "primary target" file to brief the agent about). |

**Default (v3.0):** single-spec pool behaves identically to `--mutator`.
Pool mode is opt-in via comma-separated list.

**Arm compatibility:** `harness:opencode:*` works as mutator but
explicitly fails as observer (see §2.5, `v3-spec.md` §3.5 for the
matrix). Pre-flight validation in v3.0 rejects incompatible specs at
CLI parse time rather than silently continuing at degraded fidelity —
lesson from v2-rerun Run C where the opencode observer was a no-op for
all 6 fires and we only caught it after-the-fact (`BLOG-DRAFT.md` §"v3").

### 2.3 Edit mode

*The shape of what the mutator produces.*

| Option | Status | Note |
|---|---|---|
| Text-response (single file rewrite) | v1 only | Mutator returned a full file as text. Simple, zero-error-rate historically, but caps the artifact at one file. |
| Edit-tool (single file per iter, multi-file workdir) | v0.3 | Scheduler picks a target file; agent gets the workdir and edits that file via its real Edit tool. Current v0.3 default when `--dir` is set. |
| Whole-workdir-per-iter | future | Agent edits any files in the workdir in one turn, scheduler doesn't pick. Untested. Risk: no obvious reward attribution per file. Would need the bandit/attribution story rethought. |
| Inside-agent-decides | v0.3 (implicit) | Already how claude-code behaves inside the workdir — it reads and writes whatever it wants. The knob is whether we constrain its primary-target brief or let it roam. |

**Default (v3.0):** edit-tool with scheduler-picked target. Whole-workdir
mode is a v4+ idea because the reward signal is per-iter and the agent's
multi-file changes would blur which file caused the delta.

### 2.4 Scheduler

*Given multi-file `--dir` mode, which file to brief the mutator on.*

| Option | Status | Note |
|---|---|---|
| `round-robin` | v0.3 default | Cycles through mutable files. Zero policy information. |
| `random` | v0.3 | Uniform sample per iter. |
| `diagnose` | v0.3 | Rule-based: reads structured grader stderr per rollout and routes by `fail_class` or domain fields. Rules live in a `scheduler.json`. Falls back to round-robin if no rule matches. |
| Adaptive file weights | v3.1 opt-in | `--scheduler-adaptive-file-weights {off\|accept_rate\|ucb1}`, default `off`. Weights each file's selection probability by cumulative accept rate (see `v3.1-spec.md` §5a). Deferred from v3.0 because single-task evidence (hone-a-drone) is not enough to justify overfitting the scheduler to one file topology. |

**Default (v3.0):** `round-robin` when `--dir` is set and no
`--scheduler` given. `diagnose` is recommended when the user has
structured stderr from the grader.

**Evidence from v2-rerun:** on hone-a-drone, 14 `world_model.py` edits
across two runs produced **zero** accepted improvements; every gain was
on `planner.py`. The diagnose scheduler WAS firing correctly
(`out_of_bounds` dominant → `planner.py` rule), but its non-planner
routing was wasted budget. Adaptive-file-weights would down-weight the
dead-end files; the v3.1 design holds it as opt-in until we see the
pattern on another reference problem.

### 2.5 Observer

*Whether and how the mutator's context gets evolved.*

| Option | Status | Note |
|---|---|---|
| Off (no observer) | v0.3 default | CLAUDE.md / AGENTS.md stays at whatever the user seeds it with. GEPA alone. |
| ACE on single CLAUDE.md | v0.3 | `--observer harness:<cli>:<model>`. Reflector is the given agent; Curator is deterministic Python that applies ADD/MODIFY/REMOVE deltas to a `managed:ace` block. |
| Per-arm ACE playbooks | v3.0 | Each mutator arm in `--mutator-pool` gets its own playbook, seeded from a shared start. Observer fire on arm X reads arm X's recent failures, writes only to arm X's playbook. See `v3-spec.md` §4.2. |
| Option C (shared base + per-arm delta) | v3.1 deferred | Split the playbook into universal-rules and arm-specific-rules. Deferred pending v3.0 data on how much per-arm playbooks actually diverge. |
| Hot/cold skills + subagent templates | v4+ | Multi-file playbook: some rules always hot, some loaded conditionally by trigger (test failure class, file extension). Skill-creator + ACE hybrid. No implementation. |

**Default:** off. Enabled with `--observer` (v0.3) or
`--observer-pool` (v3.0).

**Compatibility matrix** (repeated from `v3-spec.md` §3.5.1 because it
lives here too):

| Harness | Mutator | Observer |
|---|---|---|
| claude-code | ✅ | ✅ |
| opencode    | ✅ | ❌ (output is a coding loop, not text) |
| codex       | ✅ | ❌ (assumed; validate before enabling) |
| aider       | ? | ? |
| gemini      | ✅ | ✅ |

Pre-flight validation in v3.0 rejects incompatible pairs at parse time.
Mid-run, the first fire on any observer arm is fail-loud — abort if it
errors (silent partial-function observer = invalidated comparison).
Override: `--allow-partial-arm-failure` for exploratory runs only.

### 2.6 Grader

*How candidates are scored.*

| Option | Status | Note |
|---|---|---|
| Single grader script | v0.3 | `--grader ./grader.sh`. Contract: last non-empty stdout line is a float, unbounded. Stderr is free-form trace fed back to the mutator (and the diagnose scheduler). |
| Multi-grader (repeatable `--grader`) | v3.1 | `--grader ./g1.sh --grader ./g2.sh …`. Each grader is one axis. |
| Combine strategies (multi-grader) | v3.1 | `--grader-combine {pareto\|weighted\|lexicographic\|epsilon}`, default `pareto`. Pareto default rationale: weighted-sum forces unit calibration across non-commensurable axes; Pareto exposes the tradeoff structure (see `v3.1-spec.md` §3). |

**Contract (v0.3, unchanged through v3.1):** `<grader> <path>` →
- stdout last line: score, a float. Higher = better. No cap, no
  normalization, negatives allowed.
- stderr: one JSON per rollout with `fail_class` or domain fields.

**Grader-failure sentinel:** non-zero exit → score 0.0. Conflates with
legit zero. Known quirk; not blocking.

### 2.7 Reward mode

*What the bandit optimizes when `--mutator-pool` has more than one arm.*

| Option | Status | Note |
|---|---|---|
| `score_delta` | v3.0 default | Raw `child_score - parent_score`. Unbounded. Can be negative. |
| `score_per_dollar` | v3.0 opt-in | `score_delta / max(cost_usd, 0.01)`. Skip-update-and-warn if `cost_usd is None`. Opt-in because cost instrumentation is unreliable across adapters (claude-code envelope, opencode sqlite, codex unknown, Claude Max subs report $0 → div-by-zero). |
| `binary` | v3.0 | 1 if child > parent else 0. |
| `normalized` | v3.0 | `score_delta / (1 - parent_score)` — how close to a notional 1.0 it pushed. Assumes scores ≤ 1; use with caution on unbounded graders. |

**Default:** `score_delta`. The default user goal is "best score," not
"cheapest score." Cost-adjusted analysis is always available post-hoc
from `mutations.jsonl`.

**Reward normalization before UCB:** because hone's grader contract is
unbounded (and drone-racing aggregates sit in roughly [0, 4], not [0,
1]), v3.0 ships `--bandit-normalize {window_minmax\|none}` defaulting to
`window_minmax`. UCB1's exploration constant `c = sqrt(2)` is calibrated
for rewards in [0, 1]; without normalization the exploration term is
undersized relative to the mean and the bandit under-explores. See
`v3-spec.md` §3.3.

### 2.8 Selector

*Given a mutator pool, which arm this iter.*

| Option | Status | Note |
|---|---|---|
| UCB1 | v3.0 (classic) | `c = sqrt(2)`. Assumes stationary rewards and [0, 1] range — neither holds for us natively, see §2.7 and the sliding-window point below. |
| Sliding-window UCB1 | **v3.0 default**, W=20 | Discards observations older than W iters before computing mean and count. Needed because GEPA evolves the parent and ACE rewrites playbooks — rewards are non-stationary. Reference: Garivier & Moulines, 2011. |
| eps-greedy | v3.0 | With prob ε (default 0.1): random arm; else: argmax mean. Debug / baseline. |
| round-robin | v3.0 | Cycles through arms. Zero policy info. Useful for forced A/B. |
| pareto-dominance | v3.1 stretch | Tracks each arm on (mean_reward, cost). Picks randomly from non-dominated arms. Relevant when cost matters as much as reward. |
| Thompson sampling | rejected | Gaussian assumption wrong for code-edit rewards (zero-inflated, heavy-tailed). If a Bayesian selector is wanted, revisit with beta-bernoulli. |
| UCB-V (variance-aware) | v3.1 fallback | Audibert, Munos & Szepesvári 2009. Exploration bonus scales with empirical variance. Queued as a fallback if `window_minmax` normalization misbehaves on long runs. |

**Default:** sliding-window UCB1 with `W=20`. `--bandit-window 0`
disables sliding (degenerates to classic UCB1) for A/B testing the
effect.

### 2.9 Reward attribution

*How scores map back to arms, files, playbook rules.*

| Option | Status | Note |
|---|---|---|
| Per-iter reward to single arm | v3.0 | Every `mutations.jsonl` row has `arm` field. Reward = score_delta of that iter. |
| Per-iter `bandit_state` block | v3.0 | Full selector snapshot in each row: arm picked, per-arm UCB score, plays-in-window, mean-reward-in-window, pick reason enum. Mandatory, not optional debug. |
| Per-arm aggregate stats | v3.0 | `summary.json` gains `per_arm_stats` block (plays, total_reward, mean_reward, cost, wall, errors). |
| Per-file attribution | v3.1 follow-up | Currently inferable from `mutations.jsonl` (each row has `target`) but not first-class. See adaptive-file-weights proposal in `v3.1-spec.md` §5a. |
| Per-rule attribution (ACE) | future | Which playbook rule drove which iter's improvement. Requires marking rule-IDs in the generator's output and parsing that back. Not built. |

---

## 3. Presets by task shape

Rough recipes by what your task looks like. These are guidance, not
contracts.

| Task shape | Recommended stack |
|---|---|
| **Single-dominant-file** — one module has all the headroom, siblings well-tuned (e.g. drone-racing planner). | Single file (or `--dir` with diagnose scheduler routing to the dominant file), single mutator, ACE on, budget 20–50. |
| **Multi-file refactor / bug-fix** — real cross-file coherence work (e.g. SWE-bench Live, library APIs). | `--dir`, diagnose scheduler (with domain fail-classes in the grader stderr), mutator pool of 2–3 CLIs, ACE per-arm, budget 100+. |
| **Prompt / skill optimization** — the artifact IS the text the agent reads. | Single file pointing at the prompt/skill; ACE **off** (playbook IS the artifact — ACE would compete); subagent-friendly mutator. |
| **Multi-quality system** — agent orchestrator scored on many non-commensurable axes. | v3.1: multi-grader with `--grader-combine pareto`, per-arm ACE, mutator pool. |
| **Unknown shape** — you don't know yet. | v4+ "auto" preset (see §5). For today, start with single-file + single-mutator + ACE off + budget 20 smoke, then widen based on what the smoke shows. |

The "single-dominant-file" row is specifically the v1 hone-a-drone setup
and the v1 Haiku bug-fixing setup. Both of those hit clean wins
(+33% aggregate on drone, +37pp solve-rate on bug-fixing) inside that
simple preset. The other rows are mostly design-intent — we have less
running evidence.

---

## 4. What v3.0 actually ships

The concrete set of CLI flags that will exist once v3.0 lands. Defaults
in bold. Full rationale for each default lives in `v3-spec.md` §0 (eight
locked decisions, 2026-04-20).

```
# Artifact
--dir <path>                            # directory mode
--file <path>                           # single-file mode (default if no --dir)

# Mutator pool
--mutator <spec>                        # v0.3, aliases to single-item pool
--mutator-pool <spec>[,<spec>...]       # v3.0 new

# Observer pool
--observer <spec>                       # v0.3, aliases to single-item pool
--observer-pool <spec>[,<spec>...]      # v3.0 new
--observer-interval N                   # default **10**
--observer-window N                     # default **20**

# Selector / bandit
--selector {ucb1|eps-greedy|round-robin|pareto}   # default **ucb1**
--bandit-window W                       # sliding window size, default **20**; 0 disables sliding
--bandit-normalize {window_minmax|none} # default **window_minmax**
--explore-until N                       # cold-start round-robin iters, default **min(2×pool_size, 10)**

# Reward
--reward-mode {score_delta|score_per_dollar|binary|normalized}   # default **score_delta**

# Scheduler
--scheduler {round-robin|random|diagnose}   # default **round-robin** (with --dir)
--scheduler-config <path>               # e.g. ./scheduler.json for diagnose rules

# Grader
--grader <path>                         # required

# Budget
--budget N                              # required
--seed N                                # reproducibility
--output <path>                         # where the final candidate goes

# Safety / validation
--allow-partial-arm-failure             # off; enable for exploratory runs only
```

v3.0 also adds (non-flag):
- Pre-flight CLI validation against the harness compatibility matrix
  (§2.5) — run aborts at parse time on incompatible specs.
- Mid-run abort on first-fire failure for any arm (unless
  `--allow-partial-arm-failure`).
- Per-arm playbook files under `.hone/run-<id>/playbooks/<arm-hash>.md`,
  versioned under `playbook_versions/`.
- Per-iter `bandit_state` block in every `mutations.jsonl` row.

---

## 5. Auto mode — "just optimize it" (concept, not v3.0)

This is the forward idea: the user supplies a directory, a grader, and a
budget, and hone figures out the rest.

The appeal is real — most of the axes in §2 have reasonable defaults,
and the ones that don't can often be decided from the first 5–10 iters
of a run. The rough shape:

1. **Start conservative.** Single-file mode (or `--dir` with
   round-robin), one mutator (the cheapest compatible one on the user's
   machine), ACE off, `diagnose` scheduler if the grader emits
   structured stderr.
2. **Observe early iters.** If accept rate is flat by iter 10, turn
   ACE on. If one file is getting 80%+ of the accepts, switch to single
   file mode and skip the scheduler overhead. If iter latency is blowing
   budget, narrow the mutator pool.
3. **Open a small bandit once signal is clear.** Add 1–2 more mutator
   arms from a presets list (claude-code:sonnet, opencode:gpt-5.4, maybe
   codex:gpt-5.4) and let the bandit explore. Small pool, small
   `explore_until`, sliding-window tight.
4. **Cost cap.** Abort if budget-per-iter exceeds a config threshold or
   the user's stated cap. Fail-loud with a summary.

The reason this is v4+, not v3.0, is cold-start cost. Every auto-mode
decision point burns iters. A 20-iter smoke to decide "turn ACE on" is
tolerable on a 100-iter run but punishing on a 30-iter one. Auto-mode
makes sense once we have enough per-task heuristics to avoid blowing
half the budget on meta-decisions.

Minimum viable version worth building first: an "auto-defaults" preset
(no bandit, fixed heuristic thresholds, no mid-run axis switches) as a
single `--preset auto` flag. That's shipable maybe six weeks after v3.1
stabilizes.

---

## 6. What we KNOW vs SUSPECT vs UNKNOWN

Honest-labeling. Evidence-backed claims only in the "Known" column.

| Known (evidence in hand) | Suspect (partial / single-case) | Unknown (no data) |
|---|---|---|
| v1 single-file + ACE off on drone-racing: **+33% aggregate, +270% L2, $4.08, 13 iters.** Reproducible via `make demo` at the repo. | Cross-CLI bandit improves exploration — N=3 in v2-rerun, both opencode runs independently found `PchipInterpolator`, claude-code didn't. Convergent-discovery signal; tiny N. | Multi-grader Pareto efficacy. v3.1 stub spec, no runs. |
| v1 single-file + ACE on Haiku system-prompt bug-fixing: **+37pp solve rate** (55% → 92% on 20-bug train, 65% → 85% on 9-bug holdout). Writeup at `writeup/2026-04-18-haiku-20train-9holdout.md`. | Adaptive-file-weights helps on dominant-file tasks. Run-2 showed `world_model.py` got 14 edits / 0 accepts; weights would have saved those edits. N=1 task. | Whole-workdir-per-iter edit mode. No attribution story, never implemented. |
| agentelo Haiku-honed leaderboard entry at **#18** (from an earlier v1 run). | cc-sonnet mutator steady (5 accepts, +0.18 cumulative in v2-rerun); opencode bursty (fewer accepts, bigger jumps). Too confounded at N=3 to call. | Auto-mode viability. Concept only, not prototyped. |
| ACE infrastructure is sound: v2 produced 13 substantive rules across 5 fires, zero parse failures. v2-rerun Runs A and B each applied 100% of their fires. | Harness-level arm granularity carries reward signal (v3 claim). Run-2's PchipInterpolator convergence across opencode runs is the strongest single piece of evidence but N=2 on that axis. | ACE-helps-over-no-observer. v1 data was 70/30 on threshold 80/20; v2 was confounded; v2-rerun has one broken observer. Unresolved. |
| Per-iter `bandit_state` logging catches "why did the selector pick X" questions that would otherwise be unanswerable after the run. | | Multi-dir / multi-repo hone. No design, no prototype. |
| Grader contract is unbounded float, and treating it as [0, 1] in UCB math under-explores. (Drone aggregate sits in ~[0, 4].) Caught while writing `selectors.py`. | | GEPA-on-GEPA meta. Cost analysis says $600+/run; not practical. |
| | | Grader evolution (evolve the scorer). Reward-hacking risk makes this load-bearing dangerous. |

Three specific non-results worth calling out, because they update priors:

1. **v2 multi-file machinery idled on hone-a-drone.** Not a hone bug —
   the task is planner-dominated. But "multi-file is a generic win" is
   NOT a claim v2 supports. SWE-bench Live is where the multi-file
   thesis gets a fair test.
2. **v2-rerun did not beat v1.** Mid-run best 0.9925 (Run A) vs v1's
   1.0778. If the final numbers don't close that gap, the honest framing
   is "multi-file + bandit architecture at v2-rerun's config did not
   clear the v1 bar on this task." v3.0 is still justified (the
   convergent-discovery signal and the v3.1 multi-grader wedge carry
   weight), but not via "v2-rerun confirmed the thesis."
3. **ACE-justified is still inconclusive.** The infrastructure works;
   the score-lift causation isn't established. Pre-registered threshold
   from v1 was 80/20; data came in 70/30. v2 couldn't test. v2-rerun
   has one broken observer (Run C). We need a run where the comparison
   is clean.

---

## 7. Research directions (not on the v3 critical path)

Short bullets. Each has a "why interesting" and a "blocked on" so you
can tell which are real ideas versus idle speculation.

- **Hot/cold skill files with trigger conditions.**
  *Why:* ACE playbooks grow monotonically and eventually hit context
  limits. Conditional-load skills (fire when `fail_class='X'`) keep the
  active context tight.
  *Blocked on:* trigger-rule language design; ACE Curator extension to
  emit hot/cold tags. No implementation.

- **Subagent templates evolved by ACE.**
  *Why:* Some mutator failures are "agent dispatch failures" (wrong
  subagent, wrong prompt shape). Treating the subagent's prompt as the
  object-of-evolution opens a second optimization surface.
  *Blocked on:* clean hooks into claude-code's subagent API; spec work.

- **Multi-dir / multi-repo hone.**
  *Why:* Real refactors span repositories. Evolving a shared-lib repo
  plus three consumer repos simultaneously is a legit want.
  *Blocked on:* what "one candidate" means when it spans repos;
  grader contract for cross-repo scoring.

- **GEPA-on-GEPA meta (outer loop tunes inner's CLAUDE.md).**
  *Why:* Clean theoretical story — optimize the optimizer.
  *Blocked on:* cost. At inner $30/run × outer 20 candidates = $600 per
  outer iter, ~13h wall. Not a product. ACE approximates the same idea
  at ~2% of the cost and ships in v0.3.

- **ACE-on-ACE (evolve the Curator itself).**
  *Why:* The Curator is deterministic Python today; it could be an LLM
  with its own playbook. Self-referential and interesting.
  *Blocked on:* Curator stability — ACE's paper insisted on a
  deterministic Curator to prevent playbook collapse. Need a
  correctness-preserving way to evolve it.

- **Grader evolution.**
  *Why:* Grader contracts miss edge cases; an evolved grader could
  catch them.
  *Blocked on:* reward hacking. A self-modifying grader can always
  optimize its own score to 1.0 by rewriting the scorer. Requires a
  meta-meta-grader to prevent collapse; the "you must go deeper" trap.
  Dangerous without a ground-truth oracle.

- **Bandit coupling between mutator-arm and observer-arm choices.**
  *Why:* Right now the two bandits are independent. In reality, some
  observer arms produce rules more useful to some mutator arms (e.g.
  cc-observer rules mention Edit-tool idioms; opencode-mutator doesn't
  use Edit). Contextual bandit coupling the two would close that loop.
  *Blocked on:* empirical signal from v3.0 runs that the coupling
  actually matters; the v3.0 simple design ships first.

- **Per-rule ACE attribution.**
  *Why:* "Which of the 7 playbook rules caused the +0.12 score jump"
  is currently unanswerable. Attribution would let ACE prune rules
  that never fire in the generator's output and promote the ones that
  consistently do.
  *Blocked on:* instrumentation in the Generator to mark which rules
  it explicitly followed; parsing back from agent output.

- **Offline counterfactual replay.**
  *Why:* After a run, replay the same seed+iter sequence under a
  different bandit selector or reward mode without re-running the LLM
  calls. Needs the per-iter candidate cache on disk. Useful for
  A/B-ing selector math cheaply.
  *Blocked on:* storage design (mutation cache) and adapter support
  for deterministic replay.

---

## End-of-doc pointer

For implementation-level contracts see `writeup/v3-spec.md` and
`writeup/v3.1-spec.md`. For the narrative of how we got here and what
v2-rerun actually showed, see `writeup/BLOG-DRAFT.md` at the repo root
(not yet published). For the upstream-novelty framing and competitor
landscape, see `~/dev/hone-novelty/` (NOVELTY.md, POSITIONING.md,
LANDSCAPE.md).
