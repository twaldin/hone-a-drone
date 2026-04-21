<!-- STATUS: WIP, living doc, not ready to publish -->

# hone-a-drone: +33% on a drone racing sim in 13 mutator calls, $4.08

I pointed hone at a drone racing sim last night. 13 mutator calls, $4.08 in mutator tokens, ~70 minutes wall. The evolved trajectory planner came out +33% on weighted aggregate score across four difficulty levels, and +270% on level 2 — where the seed couldn't complete a single rollout out of five and the final candidate completed two at 6.36s lap. Seed was already +40% over the sim's own `lsy_state_controller` example before hone touched it, which is what makes this interesting to me: it's improvement on top of a competitive baseline, not on top of an educational-example PID loop.

Code is at [github.com/twaldin/hone-a-drone](https://github.com/twaldin/hone-a-drone). `make demo` reproduces a smoke run; the full write-up with per-iter mutator diffs is at [`writeup/first_run.md`](https://github.com/twaldin/hone-a-drone/blob/main/writeup/first_run.md).

## what hone actually is

hone is not a prompt optimizer. It's an implementation of GEPA's [`optimize_anything`](https://gepa-ai.github.io/gepa/blog/2026/02/18/introducing-optimize-anything/) protocol using a CLI coding agent as the mutator. That's the one-liner but it's the differentiation worth explaining.

DSPy's GEPA works over prompts — the mutator is a single LLM completion that rewrites a string. hone swaps that completion out for a full Claude Code invocation (or codex / opencode / gemini / aider / swe-agent — my [harness](https://github.com/twaldin/harness) abstracts six of them behind one API). The agent opens a workdir, edits files with its real Edit tool, reads other files for context, and hands back a modified directory. Artifact under optimization stops being a string and starts being a whole code project.

Closest published prior art is GEPA's Feb 2026 blog post on [learning skills for coding agents](https://gepa-ai.github.io/gepa/blog/2026/02/18/automatically-learning-skills-for-coding-agents/) — same shape, different artifact. They use GEPA to evolve skill files that get fed into an agent (the generic prompt that goes across tasks), and report wild transfer numbers (Haiku 4.5 79.3% → 100% on Bleve, 24% → 93% on one other repo). hone optimizes the target code itself — the skill file's counterpart on the other side of the agent.

The name "hone" lets me put GEPA inside the mutator call *and* inside the outer budget without the vocabulary tangling. GEPA-the-algorithm does reflective Pareto search over candidates; hone is the wrapper that makes one of those candidates "a Python file Claude Code just edited."

## the v1 experiment

Seed was [`controllers/planner.py`](https://github.com/twaldin/hone-a-drone/blob/main/controllers/planner.py) — 8,075 characters of min-snap-philosophy cubic-spline trajectory generation through gate-normal-aligned waypoints, with obstacle-aware nudging on the approach waypoints. Pure numpy + scipy. No neural nets, no trained weights. I picked this seed deliberately: STACK.md says hone should start from a competitive seed, not a PID loop you'd assign as a homework problem.

Grader runs 4 difficulty levels × 5 seeds = 20 rollouts per candidate, ~14s wall each. Aggregate score is weighted — L0=1.0, L1=1.5, L2=2.0, L3=3.0 — so level 3 dominates (L3 is the random-tracks generalization level). Budget was 100 iterations. Run stopped at 13 mutator calls because GEPA's `skip_perfect_score` triggered early on a small trainset (a budget-utilization inefficiency I filed upstream, not a bug).

| level | seed | evolved | Δ | notable |
|---|---|---|---|---|
| L0 | 2.238 | 2.588 | +15.6% | 5/5 complete, lap 8.08s → 6.30s |
| L1 | 2.238 | 2.577 | +15.1% | 5/5 complete (randomized inertia) |
| L2 | 0.200 | 0.739 | **+270%** | 0/5 → 2/5 complete (randomized obstacles) |
| L3 | 0.025 | 0.050 | +100% | 1 gate passed instead of 0 |

L2 is the headline because 0-of-5 → 2-of-5 is a phase transition, not a tuning win. The seed literally could not finish an L2 rollout; the final candidate could.

Two winners emerged across 13 iterations. Iter 4 was the algorithmic leap: the mutator added a `LOOKAHEAD_TIME = 0.4` parameter and a waypoint-caching mechanism that wasn't in the seed at all (+6.4%). Iter 13 kept iter 4's structure and tuned five numbers on top of it — `CRUISE_SPEED` 2.0 → 2.2, `EXIT_DIST` 0.55 → 0.6, `MIN_SEGMENT_TIME` 0.3 → 0.25, `LOOKAHEAD_TIME` 0.4 → 0.35, plus one more. Compounded that iter-4 baseline up to +33% end-to-end.

Pattern I kept seeing: one structural idea, then several rounds of fine tuning off it. GEPA's "winner-builds-on-winner" Pareto move worked because the mutator was operating in a local region of the search space where small parameter tweaks actually mattered.

What hone didn't solve: L3. Random tracks need online replanning — re-estimating gate positions per rollout from the obs dict — and none of the iterations attempted that, because the architecture I handed the planner doesn't support it. STACK.md predicted this: L3 is where you need a `world_model.py` layer, not a smarter planner. Consistent with prediction. Uninteresting.

## v2: ACE bolted on, then a confound, then a rerun

v2 was supposed to test two ideas at once.

**First: `--dir` mode.** hone mutates one file per iter out of a directory (`controllers/`), with a scheduler picking which file each turn based on grader failure-mode signals — `out_of_bounds` routes to the planner, `gate_miss` routes to the detector, and so on. Scheduler reads structured JSON from grader stdout per rollout; existing stderr stream is untouched for GEPA's reflective dataset.

**Second: an ACE observer.** A parallel Claude Code agent wakes up every N iterations, reads the last 20 rows of `mutations.jsonl`, and rewrites the mutator's `CLAUDE.md` via deterministic delta-merge (ADD / MODIFY / REMOVE ops into a `# managed:ace` block). Paper-faithful port of Zhang et al., ICLR 2026 ([arxiv 2510.04618](https://arxiv.org/abs/2510.04618)) — same Generator/Reflector/Curator split, same discipline of "keep the Curator deterministic so the playbook doesn't collapse under LLM rewrite drift."

The ACE paper is interesting because it frames ACE as a **competitor** to GEPA, not a complement. Zhang et al. benchmark ACE *against* GEPA on AppWorld and report ACE using 80.8% fewer input tokens and needing 75.1% fewer rollouts. Their pitch: monolithic prompt rewrites suffer context collapse, incremental playbook deltas don't.

hone v2 stacks them instead. GEPA handles the thing GEPA is good at (Pareto candidate search — which candidate to keep). ACE handles the thing ACE is good at (incremental playbook refinement — how the generator thinks about the task). They optimize different objects, and I couldn't find prior art on putting them in the same loop. (Closest is DSPy's `BetterTogether` — which composes prompt-opt with weight-opt — but that's a different composition than stacking two reflective optimizers.)

The combination is also cheap. A full GEPA-on-GEPA nested meta-loop would be a research curiosity: if inner hone is $30/run at budget 100, outer GEPA of 20 candidates is ~$600 and ~13 hours wall per experiment. Not a product. ACE approximates the same idea — "give the generator better guidance mid-run" — at about 2% of the cost, because the outer step is one LLM call every N iters instead of a full nested search.

### what actually happened in v2

v2 ran 100 iterations, $27.06 mutator spend, ~6 hours wall. Aggregate score 0.9041: +11.7% over the v1 seed, but **−16.1% behind v1's evolved candidate**. Edit-mode crash rate was 24% (v1's text-response mode was 0%); first new-best landed at iter 53; iters 54-100 produced zero further improvements.

The honest reading isn't "v2 is worse than v1." It's that the grader I handed v2 didn't exercise v2's new features. `run_rollout.py` loads only `controllers/planner.py` via `importlib`. The other five files in the workdir — `attitude_ctrl.py`, `state_estimator.py`, `gate_detector.py`, `world_model.py`, `baseline.py` — get edited by the mutator and then ignored by the grader. v2's `--dir` machinery had nothing to lift, the diagnose scheduler was picking the only useful target 96/98 iterations, and the ACE observer's rules (13 produced across 5 fires, mostly substantive — "don't flip the cubic spline BC type away from `not-a-knot`", "clamping waypoints to arena bounds doesn't prevent spline overshoot") couldn't compound across files because cross-file coherence wasn't tested.

The drone agent caught this in the post-run audit. (The original me did not — I'd inherited the single-file constraint from v1 and ran v2 on top of it without rearchitecting the grader.) Embarrassing. Educational.

### v2-rerun: 3-way A/B/C

v2-rerun is v2's architecture with two fixes: a multi-file grader that actually loads sibling modules (so `world_model.py` and `state_estimator.py` show up in the scored code path), and a 600s harness timeout (the 300s default was responsible for most of v2's 24% mutator error rate — Edit-tool runs in a 6-file workdir frequently exceeded 300s).

Three runs simultaneously, same grader, same seed, same budget=100:

- **A**: claude-code:sonnet mutator + claude-code:sonnet observer
- **B**: opencode:gpt-5.4 mutator + claude-code:sonnet observer
- **C**: opencode:gpt-5.4 mutator + opencode:gpt-5.4 observer

The point of A/B/C is to see whether the mutator and the observer have separable contributions, and whether cross-vendor combos behave any differently from homogeneous ones. All three completed 100 iters. Zero mutator errors across every arm — the 600s timeout plus edit-mode lock cleanly retired v2's 24% mutator error rate.

**Headline: v2-rerun's multi-file + bandit-shaped architecture did not clear v1's single-file-focused bar on hone-a-drone.** Final best was Run A at 0.9925; v1's evolved candidate was 1.0778. Every arm traded L0/L1 for L2 and hit the same L3 floor at 0.025 (same as the v1 seed; v1 evolved reached 0.050 there). L3 (random tracks) needs online replanning, and none of v1, v2, or v2-rerun seeds one. Any design that doesn't fix L3 hits the same wall.

Per-arm final:

| arm | mutator + observer | best | gain vs seed | accept rate | observer fires (applied/total) |
|---|---|---|---|---|---|
| A | claude-code + claude-code | 0.9925 | +0.183 | 5% | 4 / 4 (4 rules) |
| B | opencode/gpt-5.4 + claude-code | 0.8941 | +0.085 | 4% | 6 / 6 (2 rules) |
| C | opencode/gpt-5.4 + opencode/gpt-5.4 | 0.9369 | +0.128 | 2% | 0 / 10 (broken) |

Three honest things to pull out of this, in descending order of how much they update my priors:

**1. Cross-CLI convergent discovery is the strongest evidence for v3's harness-arm-granularity claim so far.** Both opencode runs independently found `PchipInterpolator` (a monotonic cubic interpolant) and swapped it in for the seed's `CubicSpline`. Run C found it at iter 5, Run B at iter 29. Run A (claude-code) never found it — it stayed inside the existing-spline solution class and tuned parameters there. Different harness, different solution class explored. This is exactly the empirical signal v3's "coding-CLI agents as bandit arms" slice predicted: the harness around the model carries enough behavioral signal that two arms can find structurally different code, not just different tuning of the same code. N=2 opencode runs is small, but the convergence is hard to wave away.

**2. The multi-file thesis did not lift on this task.** `world_model.py` got 14 mutator edits across B and C, zero accepts. `attitude_ctrl.py` got 3 edits in B, zero accepts. Every accepted candidate was a `planner.py` edit. The honest read is that the seed siblings (`world_model.py`, `state_estimator.py`, `attitude_ctrl.py`, `gate_detector.py`) are well-tuned at start, and remaining headroom for drone-racing concentrates in the planner. Multi-file architecture is the right design for tasks with cross-file coherence work to do; drone-racing isn't that task. Don't read v2's multi-file machinery as a generic win when on this specific benchmark it idled. The diagnose scheduler routed 90% of iters to `planner.py` (A=98%, B=83%, C=87%) because `out_of_bounds` dominates fail_class and the scheduler config maps that to the planner — dynamic in intent, task-dominant in effect. (The next reference problem on the queue is a SWE-bench Live adaptation. That's where multi-file has a real chance to prove itself, because the artifact is genuinely cross-file.)

**3. ACE-helps-over-no-observer at N=3 is negative evidence, not just inconclusive.** The arm with fully working ACE (Run B: 6/6 fires applied, 2 distilled rules of real engineering content) scored the lowest of the three at 0.8941. The arm with fully broken ACE (Run C: 10/10 fires errored with `harness 'opencode' not usable as observer — output is coding loop not text`, so zero rules ever applied) scored 0.9369 — higher than B. B and C share the same mutator (opencode/gpt-5.4), so mutator-capability confound is at least partly controlled; the main remaining confound is model-independent search noise at N=1 per cell. Even so, "the broken-ACE arm outscored the working-ACE arm" is the straightforward reading, and it goes the wrong direction for the thesis. The two working observers (A: 4 rules, B: 2 rules) did converge on the same meta-lesson — *out_of_bounds is a smoothness problem, not a velocity problem* — via different specifics (A: not-a-knot BCs and intermediate waypoints for sharp approaches; B: don't replace `PchipInterpolator` with piecewise-linear, suspect smoothness regression not speed). That says the reflector reads the data. Whether reading the data causes score lift is what this run said no to. ACE infrastructure is validated (runs A and B: 10 fires, 10 applied, 6 rules, zero parse failures). ACE-lift on score is unproven and actively argued against by this N=3 evidence.

Side-observation: first accepts landed at iter 5 (C), iter 14 (A), and iter 29 (B). Sonnet was the steadiest (5 accepts from iter 14 to iter 55, +0.18 cumulative). C one-shot its biggest gain at iter 5 and only found one more accept in the remaining 95 iters. Argues against premature cost-tier optimization — the cheap arm wasn't cheating to a quick win even when it had one, and the expensive arm wasn't reliably faster to first signal.

So the v3 thesis update from v2-rerun, honestly:

- **(a) harness-level arm granularity:** strong evidence (convergent cross-CLI `PchipInterpolator` discovery; both opencode arms, neither claude-code arm)
- **(b) per-arm ACE playbook:** negative evidence at N=3 — working-ACE arm scored lowest, broken-ACE arm scored higher. Infrastructure validated, lift refuted.
- **(c) multi-file grader benefit:** idle on this task. 17 sibling edits across the three runs (14 `world_model.py`, 3 `attitude_ctrl.py`), zero accepts. Every gain was `planner.py`. Drone-racing is a planner-dominated task; v2-rerun's multi-file architecture had no axis to move along.

One out of three pieces validated, one actively refuted, one untested (because the task didn't have the shape that would exercise it). Better to call that than claim "thesis confirmed."

## the open question: interleaved vs two-phase

This is the part I don't know the answer to, and I want input.

The v2 plan runs ACE and GEPA **interleaved**: the observer fires every N GEPA iterations, reads the most recent mutations from the ongoing run, and edits `CLAUDE.md` in place. Co-evolution — the playbook adapts to the actual candidate distribution as GEPA is exploring it.

The alternative is **two-phase**: run ACE alone first (shorter agent+grader+observer cycles, no full Pareto search yet) until the mutator's `CLAUDE.md` plateaus — stops receiving meaningful edits. Then freeze that playbook and run a longer GEPA with the plateau'd mutator driving it. The case for this: during the actual Pareto exploration, every candidate gets generated by a much more disciplined mutator, so the search covers more real hypothesis space instead of burning budget on mutator-shape or discipline failures. In v1, the first several iterations were mutator-shape garbage before the winner at iter 4 landed. With a plateau'd mutator, that front-loaded waste disappears.

The case for interleaved: the playbook needs to see the full candidate distribution to learn the right rules. A two-phase ACE plateau based only on early mutations won't include the kinds of rules that ACE can only learn once GEPA has pushed candidates into regimes the seed never reaches. Co-evolution captures that; two-phase doesn't.

I think hone is a rare setup that can answer this empirically. Hold the mutator setup, grader, and seeds fixed; vary only the schedule of the two optimizers. v2 interleaved vs v2.5 two-phase, aggregate-trajectory comparison. If anyone has priors on how this goes (or has seen a paper I haven't), hit me up.

## honest status on ACE

The v1 data leaned against ACE being necessary yet. I logged observations across both runs (Run 1 = 6 iters aborted on harness bugs; Run 2 = 13 iters successful) and classified each one as LLM-catchable-from-logs or needing-human-judgment. Split came in at 70/30 — 70% of observations were things a reflection LLM could have caught from `mutations.jsonl` (output-shape checks, parameter diffs, budget arithmetic). The other 30% needed human judgment or domain knowledge (UX intuition about Claude Code's default tool-use behavior, recognizing L3 needs replanning not tuning).

My pre-registered threshold for "ACE is justified" was 80/20. 70/30 is close but not there. Also: zero repeated mutator-bug classes across 19 iters. The mutator didn't make the same mistake five times; it explored widely and GEPA rejected the bad moves. ACE's paper specifically targets recurring-pattern substrate, and a single-file 13-iter run doesn't generate enough of it.

v2 didn't move that verdict cleanly because v2 couldn't fairly test it (single-file grader). What v2 *did* show is that the ACE infrastructure is solid — 5 observer fires, 5 applied, 13 substantive rules produced, zero parse failures. The rules look like real engineering insight, not noise.

v2-rerun moved the verdict the wrong way. Run B ran ACE perfectly (6 fires, 6 applied, 2 distilled rules) and scored lowest of the three arms. Run C's ACE was broken end-to-end (opencode's output is a coding loop, not text; the reflector couldn't read it) and Run C still beat B. Same mutator model underneath both, so model-capability confound is at least partly controlled. The paper-infrastructure story stays fine; the score-lift story got weaker. A cleaner A/B (ACE-on vs ACE-off, matched arms, no opencode-as-observer bug) is what's needed to reverse this signal. Until then, the data doesn't support enabling ACE by default.

## v3: a bandit over coding agents

v2-rerun is three runs in parallel, picked manually. v3 collapses that into one run that picks for you.

The shape: pass `--mutator-pool` and `--observer-pool` as comma-separated lists, and a bandit selects which arm runs each iteration based on observed reward. UCB1 by default — the same algorithm Sakana's [ShinkaEvolve](https://arxiv.org/abs/2509.19349) (ICLR 2026) uses for ensemble-LLM picking in evolutionary code search. Three things get optimized against the same grader: the artifact (GEPA), the per-arm playbook (ACE), and which arm runs this iter (bandit).

Thirteen design decisions are locked. Seven worth flagging here, mostly because each one came from running into an edge rather than from theory:

- **Per-arm ACE playbook, seeded from a shared start.** Each mutator arm gets its own `CLAUDE.md` (or `AGENTS.md` for opencode/codex). When the observer fires on arm X, it reads arm X's recent failures and writes only arm X's playbook. Sharing the playbook would contaminate the bandit's reward signal — a rule added because of opencode's failure mode would bias claude-code's future plays for reasons unrelated to claude-code itself. Per-arm preserves clean reward attribution. Option C (shared base + per-arm delta) is deferred to v3.1 pending data on how much the per-arm playbooks actually diverge.
- **Sliding-window UCB1 with W=20, not standard UCB1.** Standard UCB1 assumes stationary reward distributions. They are not stationary here: GEPA evolves the parent candidate every iter, and ACE rewrites per-arm playbooks every observer fire. An arm's reward at iter 3 is not comparable to its reward at iter 42. Sliding-window discards observations older than W iters before computing mean and count (Garivier & Moulines, 2011). This is in v3.0, not v3.1 — if you build with non-stationary assumption from iter 1, classic UCB locks onto early winners and never re-explores; that's hard to undo retroactively.
- **Per-iter `bandit_state` logging.** Every `mutations.jsonl` row carries the full selector state at pick time: arm picked, UCB scores per arm, in-window plays per arm, in-window mean reward per arm. Without this, "why did the selector pick arm X at iter 42" is unanswerable after the fact. Mandatory, not optional debug.
- **Default reward = `score_delta`, not `score_per_dollar`.** I almost shipped score_per_dollar by default — it's the more "interesting" reward, and there's a real cost-aware-routing literature behind it (PILOT, ParetoBandit). The scout flagged that cost instrumentation is unreliable across adapters: claude-code emits cost via JSON envelope, opencode writes to sqlite, codex's path is unknown, and a Claude Max subscription reports `$0` per call (which div-by-zeros the reward). `score_per_dollar` stays available via `--reward-mode`, but the default is the raw delta because the default user goal is "best score," not "cheapest score."
- **Mutator-error reward = 0, not negative.** A crash conveys no signal about arm quality; don't penalize with a magic number. The errored iter still counts as a play, dragging the arm's mean reward down via `mean = Σ rewards / plays`. UCB1's `sqrt(ln(N)/n)` exploration bonus shrinks with `n` regardless. Chronic-error arms die out without any hand-tuned penalty.
- **Reward normalization (`--bandit-normalize window_minmax`, default).** This one came out of running into an edge, not theory. hone's grader returns an unbounded float — drone-racing aggregate scores in this run sit roughly in [0, 4], not [0, 1]. UCB1's exploration constant `c = sqrt(2)` is calibrated for rewards in [0, 1]; on a 0–4 scale the exploration term is undersized relative to the mean and the bandit under-explores. The drone agent caught this while implementing `selectors.py` and added `--bandit-normalize {window_minmax, none}`, defaulting to `window_minmax` (rescale rewards to [0, 1] using the min/max within the sliding window). UCB-V (Audibert et al., 2009 — variance-aware UCB) is queued as a v3.1 fallback if window-minmax doesn't behave on long runs. Pre-flight CLI check also lands in v3: `harness:opencode:*` is rejected as an observer arm because opencode's output is a coding loop, not parseable text — the v2-rerun's silent-failure mode (Run C, 0 of 10 fires applied) is the kind of thing a startup check catches in 2 seconds.
- **`--early-stop-patience` defaults off.** Every v2-rerun arm plateaued well before its 100-iter budget — Run A's last improvement at iter 55, then 45 iters of zero gain; B at iter 64, then 36 iters; C at iter 45, then 55 iters. A per-arm plateau detector would save that tail cost. But GEPA-style search is punctuated: Run A itself went 35 iters between iter 20 and iter 55 before a +0.15 jump. Aggressive early-abort would have killed that win. v3 ships plateau detection as a flag, off by default. Turn it on if you trust your signal and want to reclaim wall-and-dollar on the tail; leave it off if you're willing to pay for the possibility of a late punctuated jump.

### the novelty claim, narrowed

Earlier drafts of the v3 spec called the GEPA × ACE × bandit triple-stack "new." That claim was wrong. Sakana's [ShinkaEvolve](https://arxiv.org/abs/2509.19349) (Takei et al., ICLR 2026) already runs UCB1 over a pool of LLMs for evolutionary code search — the bandit layer alone is not novel. Stripping all the published precedent (GEPA, ACE, ShinkaEvolve, OpenEvolve, AOS-style bandit-over-operators in classical EAs, cost-aware routing in production serving) the defensible novel slice is two things:

1. **Coding-CLI agents as bandit arms.** ShinkaEvolve's arms are raw LLM API endpoints. hone v3's arms are `(coding-CLI, model)` pairs — `harness:claude-code:sonnet`, `harness:opencode:gpt-5.4`, `harness:codex:gpt-5.4`. The CLI matters because it determines tool access (Edit vs apply_patch vs shell), workspace discipline, default turn limits, system-prompt injection. Two arms with the same underlying model but different CLIs produce different patches. Whether harness identity carries enough reward signal to be worth splitting arms on is an empirical question; v3 is the experiment.
2. **Per-arm ACE playbook coupled to arm selection.** ACE as published is single-agent (one Generator, one evolving context). N ACE playbooks running in parallel — each scoped to one bandit arm — is a small extension, but the coupling to bandit arm choice is new work.

Workshop-publishable, not full-venue. If v3 shows (a) the bandit converges across coding-CLI arms, (b) per-arm playbooks diverge non-trivially, (c) the winning arm beats an equivalent v2-style solo run — that's a concrete result for an ICLR or NeurIPS workshop. Not main-track. ShinkaEvolve eats most of the algorithmic surface area.

ShinkaEvolve, ACE (arxiv 2510.04618), and GEPA (arxiv 2507.19457) get cited up front in the README and in v3.md when v3 ships. No "we invented this" framing.

## who hone is actually up against

The competitor question changes once you stop counting orchestration frameworks. LangGraph, AutoGen, CrewAI, Braintrust — these are not competitors. LangGraph orchestrates an agent's runtime flow; hone evolves the *code* the agent runs. Different layer.

The real competitor set is small: **DSPy** (the GEPA host framework — owns generic prompt optimization), **OpenEvolve** and **CodeEvolve** (open-source AlphaEvolve-style evolutionary code search via direct API calls), **ShinkaEvolve** (Sakana's bandit-LLM ensemble version of the same).

The biggest obsolescence risk is DSPy. GEPA's `optimize_anything` API is generic over text parameters. Writing a `ClaudeCodeMutator` adapter for DSPy is approximately one day of work for anyone on the DSPy team; if they ship it, hone v1's "GEPA over a coding CLI" niche commoditizes overnight. I budget that risk at <6 months. The defensive plays: ship v3 fast, claim the multi-CLI bandit + per-arm ACE niche publicly before they ship a single-CLI adapter, and consider contributing the harness library upstream to DSPy so hone becomes the de-facto adapter layer instead of getting run over.

The moat, honestly, is moderate. v1 is reproducible in a week by a competent two-person team that already knows GEPA and claude-code. v3 is 6-10 person-weeks. The strongest single moat component is the harness library — keeping claude-code, opencode, codex, aider, and gemini-cli interchangeable as mutators is ongoing maintenance (claude-code shipped ~10 breaking CLI changes between 2024 and 2026), and being the de-facto adapter layer is the kind of position that compounds the way `transformers` did for model loading. The algorithm is not the moat. The integration plus the reference problems plus moving fast is the moat.

## v3.1 preview: the multi-grader story

v3 is the bandit. v3.1 is the wedge.

`--grader` becomes repeatable. Multiple grader scripts run per iteration; each is its own scoring axis. `--grader-combine` defaults to `pareto` (alternatives: `weighted`, `lexicographic`, `epsilon`). The bandit's per-iter reward becomes the candidate's hypervolume contribution to the current Pareto frontier — when a candidate is dominated, reward is 0; when it expands the frontier, reward is the volume added.

Why this matters: nothing else in the OSS optimization space currently serves this. DSPy supports custom multi-metric functions but doesn't have first-class Pareto over per-objective scores (its Pareto bookkeeping is per-example). ShinkaEvolve and OpenEvolve default to single-scalar fitness. A multi-grader hone is the first OSS tool that lets you write four small grader scripts and ask "evolve this code under all four axes simultaneously, show me the frontier."

The killer use case is agent orchestrator optimization. Imagine optimizing a LangGraph-style orchestrator under four graders: `spawn_latency.sh`, `message_count.sh`, `kill_reliability.sh`, `task_completion.sh`. Single-scalar combination forces you to hand-calibrate weights across non-commensurable axes (how many seconds of latency = one missed kill?) and silently loses tradeoff structure. Pareto exposes the tradeoff and lets you pick from the frontier post-hoc.

Estimated effort to ship: 2 person-weeks. Most of the work is already in v3.0 (pool + selector + per-arm playbook); v3.1 adds one Pareto bookkeeping module plus the CLI plumbing.

## why drone racing

The point isn't drone racing, it's the competition. The [Anduril AI Grand Prix](https://www.anduril.com/) is an autonomous-controller challenge scored against human FPV experts on real gate sequences, and it has a §(d) clause forcing every entry to disclose exactly which AI tooling was used to produce their Entry. That's the kind of evaluation where an LLM-code-mutation loop either demonstrably works against the humans or demonstrably doesn't.

Most open-ended LLM-optimization work lives on benchmarks where you can argue about contamination and eval noise. Drone racing is a real-number problem: seconds on the clock and whether the drone hit a gate or a wall. hone-a-drone is the proxy harness while I wait for the real sim to drop in May — swapping the sim/obs adapter should preserve everything else in the stack.

## how this got decided

Quick process note (the "how it's made" version), since I keep getting asked. v3 is not a single brain's design. A scout agent did five docs of adversarial prior-art scan and found ShinkaEvolve before I shipped overclaiming. The drone agent ran the v2 experiments, caught the single-file grader confound in the post-run audit, and drafted the v3 spec. Cairn (the orchestrator) made the thirteen locked decisions — including the one where I almost defaulted to `score_per_dollar` until the scout flagged that a Claude Max subscription's $0/call kills UCB math, and the one where I almost shipped standard UCB1 until the scout pointed at Garivier & Moulines on non-stationary reward.

Several of the thirteen calls were direct corrections to my draft. The interesting part is that scout, drone, and cairn are all the same model class — what changed was role separation and adversarial prompting, not capability. Same trick that ACE's Generator/Reflector/Curator split exploits, basically.

## status

- **v1**: shipped. [github.com/twaldin/hone-a-drone](https://github.com/twaldin/hone-a-drone). +33% aggregate, +270% L2, $4.08 mutator spend, reproducible via `make demo`.
- **v2** (hone + ACE observer + `--dir` + dynamic scheduler, single-file grader): ran. +11.7% over seed, −16.1% behind v1, 24% mutator error rate. Confounded by single-file grader — multi-file machinery wasn't tested.
- **v2-rerun** (multi-file grader + 600s timeout, 3-way A/B/C across claude-code and opencode): 100 iters per arm, complete. Final best 0.9925 (Run A, cc-cc) — did not clear v1's 1.0778. B (oc-cc) 0.8941. C (oc-oc) 0.9369. Zero mutator errors across all three arms (600s timeout + edit-mode lock cleanly fixed v2's 24%). Cross-CLI convergent `PchipInterpolator` discovery (both opencode arms, neither claude-code arm) is the strongest single piece of v3-thesis evidence. Multi-file machinery idled — 17 sibling edits, zero accepts, every gain on `planner.py`. ACE-helps went from "inconclusive" pre-run to "negative at N=3" post-run: working-ACE Run B scored lowest; broken-ACE Run C scored above it.
- **v3** (bandit over `(harness, model)` arms + per-arm ACE playbooks + sliding-window UCB1 + per-iter bandit-state logging + `--bandit-normalize window_minmax` + `--early-stop-patience` flag off by default): thirteen decisions locked, implementation in flight on a fresh local fork. First full-run will include a `dspy-gepa-only` ablation arm (vanilla GEPA via a single LLM API call, no coding CLI, no ACE, no bandit) so the stack's lift over plain GEPA is a number, not a prior.
- **v3.1** (multi-grader, Pareto default, orchestrator optimization): stub spec, queued after v3.0 lands.
- **ACE justified?**: v1 data was 70/30, threshold was 80/20 — close, not there. v2 had a single-file grader and couldn't test it. v2-rerun gave negative evidence at N=3: working-ACE Run B (6/6 fires applied, 2 rules) scored 0.8941 (lowest); broken-ACE Run C (10/10 fires errored, 0 rules applied) scored 0.9369 (above B). Infrastructure is sound (Runs A and B combined: 10 fires, 10 applied, 6 rules, zero parse failures). ACE-lift on score is not — the current data argues against it. v3's GEPA-only ablation is the piece that settles it.
- **forward-look across all axes**: `writeup/HONE-MODES.md` — artifact, mutator, edit mode, scheduler, observer, grader, reward mode, selector, reward attribution. One axis per section, current status + what's queued. Separate from the v3 implementation contract.
- **next reference problem after drone-race v3**: SWE-bench Live adaptation, Q3 2026. That's where the multi-file thesis has a task shape that can exercise it.

Full tooling + dependency disclosure: [`disclosure.md`](https://github.com/twaldin/hone-a-drone/blob/main/disclosure.md). Credits to GEPA (Agrawal et al., arxiv 2507.19457), ACE (Zhang et al., arxiv 2510.04618), ShinkaEvolve (Takei et al., arxiv 2509.19349), and OpenEvolve. This post gets updated as v3 numbers land.
