# hone v3 — SPEC

**Audience.** Drone of the future, implementing on a fresh local fork at
`~/hone-v3/` from `~/hone-v2/`. Starts after the current three-way v2-rerun
A/B/C finishes.

**One-line delta from v2.** v2 picks ONE mutator and ONE observer at run
start and sticks with them. **v3 accepts a POOL of mutator configs and a
POOL of observer configs; a bandit selector picks one per iteration based
on observed reward/cost.** Simultaneously optimizes three things against
the same grader:

1. GEPA: the artifact (drone code) — unchanged from v2
2. ACE observer: the mutator's CLAUDE.md rules — unchanged from v2
3. **Bandit (new): which agent runs this iteration**

Framed another way: find the best-performing, most price-optimal agent for
a task while simultaneously evolving the task's artifact. One run, not N
separate runs to compare.

---

## 0. Decisions locked 2026-04-20 (Tim approved via cairn)

1. **ACE playbook = per-arm, seeded from shared start.** Each mutator arm
   gets its own CLAUDE.md (claude-code) or AGENTS.md (opencode/codex),
   initialized from the same seed at run start. Observer fires on arm X
   read arm X's recent failures + arm X's playbook, write only to arm X's
   playbook. Details in §4.2. The "reflector produces mutator-agnostic
   rules" mitigation is deleted (§6.2) — obsolete with per-arm playbooks.
   Option C (shared base + per-arm delta) deferred to v3.1 pending
   empirical data.
2. **Default reward = `score_delta`, NOT `score_per_dollar`.** Cost
   instrumentation is unreliable across adapters (claude-code envelope,
   opencode sqlite, codex unknown, Claude Max sub reports $0 → div-by-zero).
   `score_per_dollar` stays available via `--reward-mode score_per_dollar`.
   When enabled: floor cost at `$0.01`; if `cost_usd is None`, skip that
   iter's arm update and log a warning (don't fake the number).
3. **Drop Thompson sampling. Keep UCB1 (default) + eps-greedy +
   round-robin + pareto (stretch).** Code-edit rewards are zero-inflated
   and heavy-tailed; Thompson's gaussian assumption doesn't fit. If we
   need a Bayesian selector later, revisit with beta-bernoulli or a
   proper zero-inflated model.
4. **Mutator-error reward = 0 (neutral).** Not `-1`, not
   `-0.1 * avg_reward_seen_so_far`. Self-correction argument: an arm that
   errors still accumulates 0-reward plays, dragging its `mean = Σ/plays`
   downward; UCB1's exploration bonus `sqrt(ln(N)/n)` also shrinks with
   `n`, so chronic-error arms don't dominate via exploration. Minor
   theoretical caveat (consistently-regressive arm gets negative reward,
   which is worse than an errored arm's 0) noted in §3.2; revisit if
   observed empirically.
5. **Cold-start: `explore_until = min(2 × pool_size, 10)`.** The cap
   prevents a 5+ arm pool from burning too much budget on forced
   round-robin before the bandit kicks in.

### Scout-derived decisions folded in 2026-04-20 (cairn → drone)

6. **Sliding-window UCB1 (W=20) is the default bandit, NOT standard UCB1.**
   Standard UCB1 assumes stationary reward distributions. GEPA candidate
   evolution and ACE rule updates both make per-arm rewards
   non-stationary — an arm that was great 30 iters ago against an easier
   parent may be mediocre against today's parent, and its playbook may
   have been rewritten twice since. Sliding-window UCB drops observations
   older than W iters before computing mean/count. Implement in
   `selectors.py` for v3.0 — not as v3.1 polish.
   Reference: Garivier & Moulines, *On Upper-Confidence Bound Policies
   for Non-Stationary Bandit Problems*, 2011.
7. **Per-iter `bandit_state` logging.** Every `mutations.jsonl` row must
   include the full selector state at pick time: `arm_picked`,
   `arm_ucb_scores` (UCB bound per arm), `arm_plays` (window-scoped
   count per arm), `arm_mean_rewards` (window-scoped mean per arm).
   Without this we cannot debug "why did UCB1 pick arm X at iter 42"
   after the fact. Scout flagged this as pitfall category H.
8. **Novelty framing narrowed.** ShinkaEvolve (Sakana AI, arxiv
   2509.19349, ICLR 2026) already runs UCB1-over-LLMs for code
   evolution — the bandit layer alone is NOT novel. See §10 for the
   corrected positioning; v3's defensible slice is (a) harness-level arm
   granularity (coding-CLI + model pair as the arm, not API model), and
   (b) per-arm ACE playbook for arm-scoped rule evolution. Credit
   ShinkaEvolve in README + credits when v3 ships.

Source docs (read when resuming if you need depth): `~/dev/hone-novelty/`
→ `NOVELTY.md`, `PITFALLS.md`, `POSITIONING.md`, `SCOUT-ADDENDUM.md`,
`LANDSCAPE.md`, `MULTI-GRADER.md`. Unified forward-look doc sitting
above this spec: `writeup/HONE-MODES.md`.

### Decisions promoted after HONE-MODES.md drafting (2026-04-20, cairn approved)

These were prose in detail sections; promoting to §0 status makes them
user-facing defaults that require a new proposal to change.

9. **`--bandit-normalize window_minmax` is the v3.0 default.** hone's
   grader contract is unbounded float (see `hone-v2/src/hone/grader.py:71-83`);
   classic UCB1's `c = sqrt(2)` exploration constant is calibrated for
   rewards in `[0, 1]`. Drone-racing aggregates sit in roughly `[0, 4]`,
   so without rescaling the exploration bonus is undersized relative to
   the mean and the bandit under-explores. Default ON; `--bandit-normalize
   none` opts out for A/B testing. Full rationale in §3.3; UCB-V stays
   queued as a v3.1 fallback if window-minmax misbehaves on long runs.
10. **`--allow-partial-arm-failure` defaults OFF (fail-loud).** If any
    arm errors on its very first fire (observer or mutator), abort the
    run with a loud error. Rationale from run-2 (2026-04-20): Run C's
    opencode observer errored 6/6 fires and the run silently continued
    for 62 iters at degraded fidelity, invalidating the arm comparison.
    Full abort semantics in §3.5.3. Override exists for exploratory runs
    where the user explicitly accepts reduced fidelity.
11. **Harness compatibility matrix is a module-level constant, not
    documentation.** The matrix in §3.5.1 (claude-code ✅✅, opencode ✅❌,
    etc.) lives in code as `HARNESS_COMPAT: dict[str, dict[Literal["mutator",
    "observer"], bool]]` and is the single source of truth for pre-flight
    validation. If docs and code drift, code is authoritative. Unknown
    adapters (missing matrix key) are rejected by default; users opt in
    by editing the constant after empirical validation.
12. **Edit mode for v3.0 is locked to "single file per iter, briefed by
    the scheduler."** Whole-workdir-per-iter (agent edits arbitrary files
    in the workdir in one turn) is explicitly v4+ and requires a new
    proposal covering reward attribution per file. Rationale: per-iter
    reward signal currently maps to one file's change; blurring that by
    letting the mutator edit N files per iter breaks the bandit's
    attribution story. See `writeup/HONE-MODES.md` §2.3 for the full
    axis treatment.

---

## 1. Scope

### In scope
- `--mutator-pool` (list of harness:model specs) replacing single `--mutator`
- `--observer-pool` (list) replacing single `--observer`
- Bandit selector (UCB1 default; eps-greedy, round-robin, pareto-dominance optional)
- Per-arm telemetry in `mutations.jsonl` + `summary.json`
- Per-arm ACE playbooks (each mutator arm gets its OWN CLAUDE.md/AGENTS.md, seeded from shared start)
- Default reward = `score_delta` (raw gain). `score_per_dollar` available opt-in.
- Back-compat: single-item pool works identically to v2

### Out of scope
- Upstream compat, tests, docs
- Contextual bandit (using parent-candidate features) — defer
- Observer-bandit-informs-mutator-bandit coupling — defer
- New harness adapters — use what harness already ships
- Multi-objective Pareto-per-iter optimization (just single scalar reward)

---

## 2. CLI

```bash
hone run --dir controllers/ \
    --grader ./grader.sh \
    --mutator-pool \
        harness:claude-code:sonnet,\
        harness:opencode:openai/gpt-5.4,\
        harness:codex:gpt-5.4 \
    --observer-pool \
        harness:claude-code:sonnet,\
        harness:opencode:openai/gpt-5.4 \
    --selector ucb1 \
    --reward-mode score_delta \
    --scheduler diagnose --scheduler-config ./scheduler.json \
    --budget 100
```

### Flag changes vs v2

| v2 flag | v3 equivalent |
|---      |---            |
| `--mutator SPEC` | `--mutator-pool SPEC[,SPEC,...]` (single-spec pool works as before) |
| `--observer SPEC` | `--observer-pool SPEC[,SPEC,...]` (optional; omit = no observer) |
| — | `--selector {ucb1\|eps-greedy\|round-robin\|pareto}` (default `ucb1`) |
| — | `--reward-mode {score_delta\|score_per_dollar\|binary\|normalized}` (default `score_delta`) |
| — | `--explore-until INT` (cold-start round-robin; default `min(2×pool_size, 10)`) |

### Back-compat

`--mutator` (singular) aliases to `--mutator-pool` with one entry. Same for
`--observer`. v2 invocations run unchanged.

---

## 3. Bandit design

### 3.1 State per arm

```python
@dataclass
class ArmStats:
    spec: str                  # e.g. "harness:claude-code:sonnet"
    plays: int = 0             # times this arm was selected
    total_reward: float = 0.0  # sum of rewards (definition varies, see 3.2)
    total_cost_usd: float = 0.0
    total_wall_s: float = 0.0
    total_errors: int = 0      # mutator errors
    rewards: list[float] = field(default_factory=list)  # for variance
```

### 3.2 Reward modes

For each iteration with mutator arm A, parent score P, child score C, arm cost X:

| Mode | Reward |
|---|---|
| `score_delta` | `C - P` (raw score gain; can be negative) — **default** |
| `score_per_dollar` | `(C - P) / max(X, 0.01)` (opt-in; see rationale below) |
| `binary` | `1` if `C > P` else `0` |
| `normalized` | `(C - P) / (1 - P)` — how close to perfect (1.0) it pushed |

**Why `score_delta` is default, not `score_per_dollar`** (decision 2026-04-20):
- Cost instrumentation is unreliable across adapters. Claude Code emits cost
  via JSON envelope; opencode writes to sqlite; codex's cost path is unknown;
  aider's unclear. On a Claude Max subscription `cost_usd` is effectively `0`
  → div-by-zero blows up the reward signal.
- The DEFAULT user goal is "get the best score," not "get the cheapest score."
  Reward axis should align with goal.
- `score_per_dollar` stays available via `--reward-mode score_per_dollar`.
  When enabled: pull `cost_usd` from `harness.RunResult.cost_usd`; floor at
  `0.01` to avoid div-by-zero; if `None`, skip arm update this iter and log
  a warning (don't fake the cost number).

**Mutator error → reward = 0** (decision 2026-04-20).
- A crash conveys no signal about arm quality, so don't penalize with a
  magic-number negative. The old `-0.1 * avg_reward_seen_so_far` proposal
  was magic-tuned and breaks when `avg_reward` is negative (sign flip).
- Self-correction argument (why this is safe): errored iters still count as
  plays. An arm with a 50% error rate accumulates zeros that drag its mean
  reward down: `mean = (Σ success_rewards + Σ zeros) / plays`. A low-error
  arm's mean is higher because more of its plays contribute positive reward.
  UCB1's exploration bonus shrinks as `plays` grows either way, so a
  chronically-broken arm will NOT dominate selection via `sqrt(ln(N)/n)`.
- Minor caveat (noted, not blocking): with `score_delta` default, a mutator
  that completes-but-regresses gives negative reward, which is WORSE than an
  errored arm's 0. In theory this could nudge the bandit toward a
  consistently-crashing arm over a subtly-regressive one. In practice
  mutators rarely generate random-worse code — the regression distribution
  is centered near zero with a small negative tail, so the bias is small.
  If we observe it empirically, revisit with a capped-negative error reward
  (e.g., `error_reward = min(-0.01, 5th-percentile(observed_rewards))`).

### 3.3 Selectors

```python
class Selector(ABC):
    @abstractmethod
    def pick(self, arms: dict[str, ArmStats], total_plays: int) -> str: ...
    def update(self, arm: str, reward: float, cost: float, wall_s: float, error: bool): ...
```

**Sliding-window UCB1** (default — handles non-stationary rewards).

The standard UCB1 formula assumes each arm's reward distribution is
stationary. It is NOT in this system: GEPA evolves the parent candidate
every iter, and ACE rewrites per-arm playbooks every observer fire. An
arm's observed reward from iter 3 is not directly comparable to its
reward at iter 42, so we discard old observations before computing mean
and count.

```python
WINDOW = 20  # default window size in iters (config: --bandit-window)
C = sqrt(2)  # exploration constant

def pick(self, arms, total_plays, history):
    # history[arm_spec] = list of (iter, reward) tuples in chronological order
    window_start = max(0, total_plays - WINDOW)

    # Force exploration of arms with zero in-window plays first
    for spec in arms:
        in_window = [r for (i, r) in history[spec] if i >= window_start]
        if not in_window:
            return spec

    def windowed_ucb(spec):
        in_window = [r for (i, r) in history[spec] if i >= window_start]
        n = len(in_window)
        mean = sum(in_window) / n
        total_window = sum(len([r for (i, r) in history[s] if i >= window_start])
                           for s in arms)
        return mean + C * sqrt(log(total_window) / n)

    return max(arms, key=windowed_ucb)
```

Reference: Garivier & Moulines, *On Upper-Confidence Bound Policies for
Non-Stationary Bandit Problems*, 2011.

Why this is in v3.0, not v3.1: if the assumption of stationarity is
violated from iter 1, a non-sliding UCB will lock in on arms that were
good early and stop exploring alternatives that might be better against
the evolved parent + playbook. Debugging this from bandit-state logs is
hard retroactively, so build it in up front. `--bandit-window 0` disables
sliding (degenerates to classic UCB1) if we want to A/B test the effect.

**Reward-range caveat (unbounded float contract).** hone's grader
contract is an unbounded float (see `hone-v2/src/hone/grader.py:71-83`:
final non-empty stdout line parsed with `float()`, no clipping, no
normalization). Classic UCB1's exploration constant `c = sqrt(2)` is
derived assuming rewards in `[0, 1]`. On the drone task, per-iter
`score_delta` is typically in `[-0.1, +0.2]` but a single level-3-
completion jump could deliver `+2.0` or more, and the aggregate score is
unbounded above (roughly capped at ~3.5 by physics, but the optimizer
doesn't know that). Two options for v3.0:

1. **Per-arm rolling min-max normalization.** Before feeding rewards to
   the UCB formula, normalize each arm's windowed reward stream to
   `[0, 1]` using that arm's observed min/max within the window.
   Simple, preserves ordering, handles heavy tails and negative rewards
   uniformly.
2. **UCB-V (variance-aware UCB).** Audibert, Munos & Szepesvári 2009.
   Exploration bonus scales with the empirical variance of observed
   rewards instead of assuming `[0, 1]` range:
   `bonus = sqrt(2 * var * log(t) / n) + 3 * b * log(t) / n`
   where `b` is the empirical range. Better fit for heavy-tailed
   rewards, more moving parts to get wrong.

**Recommendation:** ship option 1 (normalization) in v3.0 behind a flag
`--bandit-normalize {window_minmax|none}` defaulting to `window_minmax`.
Keep UCB-V as a v3.1 consideration only if empirical bandit regret looks
pathological in v3.0 runs.

**eps-greedy** (debug / baseline):
With prob ε: random arm. Else: argmax mean reward. Default ε=0.1.

**round-robin** (force A/B): cycles through arms. Uses zero policy info.

**pareto** (stretch / v3.1): tracks each arm on (mean_reward, cost) plane.
Picks randomly from non-dominated arms. Useful when cost matters as much as
reward.

**Why no Thompson sampling** (decision 2026-04-20): code-editing rewards are
zero-inflated (errors and no-ops both cluster at 0) and heavy-tailed
(occasional big score_delta jumps). The canonical Thompson formulation
assumes normally-distributed rewards — wrong family of assumptions for this
signal shape. If we need a Bayesian selector later, revisit with a
beta-bernoulli model or a proper zero-inflated prior, not the gaussian one.

### 3.4 Cold-start

First `explore_until = min(2 * len(pool), 10)` iters: round-robin regardless
of selector choice. Ensures every arm gets played at least twice before the
bandit starts preferring, BUT caps the forced-exploration cost at 10 iters
even for 5+ arm pools. Without the cap, a 6-arm pool would spend 12% of a
100-iter budget on forced exploration before the bandit even starts.

### 3.5 Arm compatibility matrix + pre-flight validation

Observed in run-2 (2026-04-20, three-way v2-rerun): the `oc-oc` run fired
the ACE observer 6 times; every fire errored with
`"mutator_failure: harness 'opencode' is not currently usable as a
mutator — its output is a coding loop, not a text response. Use
claude-code or gemini for prompt mutation."` The run silently continued
for 62 iters at degraded fidelity, invalidating any comparison of its
ACE contribution against the `cc-observer` runs.

**v3.0 policy: fail-loud, fail-early.** A silent partial-function
observer invalidates the scientific claim of fair arm comparison, which
is the whole point of v3. Detect the incompatibility at iter 0, not
iter 6.

#### 3.5.1 Compatibility matrix (v3.0)

| Harness | Mutator? | Observer? | Notes |
|---|---|---|---|
| `harness:claude-code:*` | ✅ | ✅ | Canonical. Adapter writes CLAUDE.md into workdir; text response via JSON envelope. |
| `harness:opencode:*`    | ✅ | ❌ | Mutator works (edits files in workdir). Observer does NOT — opencode's output is a coding loop, not a single text response; the ACE reflector expects a text response. |
| `harness:codex:*`       | ✅ (untested) | ❌ (assumed) | Same failure mode as opencode likely; validate before enabling. |
| `harness:aider:*`       | ? | ? | Unknown — verify empirically before enabling either slot. |
| `harness:gemini:*`      | ✅ | ✅ | Per upstream hone error message; untested in this project. |

Update this table as each new harness is empirically validated. The
table lives in this spec *and* in code (see §3.5.2) — if they drift,
the code is authoritative.

#### 3.5.2 Pre-flight validation

At CLI parse time, before `optimize_dir` starts:

1. Load the compatibility matrix from a module-level constant
   `HARNESS_COMPAT: dict[str, dict[Literal["mutator", "observer"], bool]]`.
2. For every `--mutator-pool` entry, check `HARNESS_COMPAT[adapter]["mutator"]
   is True`. Reject the run with a clear error message naming the
   offending spec if not.
3. Same for every `--observer-pool` entry against `["observer"]`.
4. Reject if the matrix key is missing (unknown adapter) — force users
   to opt in by editing `HARNESS_COMPAT` after validating.

```python
# pseudocode for the error
raise CLIError(
    f"Arm {spec!r} is not usable as an {slot}. "
    f"See v3-spec §3.5.1 compatibility matrix. "
    f"Compatible {slot}s: {[k for k,v in HARNESS_COMPAT.items() if v[slot]]}"
)
```

#### 3.5.3 Mid-run abort on first-fire failure

Even a matrix-approved arm might fail its first real fire (e.g.,
adapter API drift between harness versions). If the *first* observer
fire on any arm errors, abort the run. Do not continue "optimistically"
to the second fire — the whole run's comparison fidelity is compromised.

Same rule for the first mutator iter on an arm: if it errors, abort.
Subsequent errors on the same arm (after it produced at least one
successful fire) are treated per normal reward policy (`reward = 0`);
only the very first fire is fail-loud.

Flag to override: `--allow-partial-arm-failure` for exploratory runs
where the user explicitly accepts degraded fidelity. Default off.

---

## 4. Observer pool

Same pattern as mutator pool but selection happens at OBSERVER FIRE cadence
(every N iters), so fewer samples per arm. Recommendations:

- Default selector for observers: **UCB1** with a larger exploration
  constant (`c = 2.0` instead of `sqrt(2)`) to compensate for the low-sample
  regime. (We considered Thompson here but rejected it for the same
  reward-distribution-assumption reasons listed above in §3.3.)
- Reward for observer arm: `score_delta_in_next_K_iters` where K=5 (did the
  rules the observer produced lead to improvements in the following K
  iterations?).
- Warm prior: round-robin until each observer arm has fired at least twice
  before bandit takes over.

### 4.1 Observer-mutator independence

The bandit over observers uses a SEPARATE policy from the bandit over
mutators. They don't coordinate. (Future work: contextual bandit coupling
the two.)

### 4.2 Per-arm ACE playbook (decision 2026-04-20)

Each mutator arm gets its OWN playbook (CLAUDE.md for claude-code arms,
AGENTS.md for opencode / codex arms, both for arms where we're unsure).
Playbooks are isolated from one another — an observer fire on arm X reads
arm X's recent failures and arm X's current playbook, then writes only to
arm X's playbook.

**Why per-arm, not shared.** Different models have different failure modes.
claude-code's sonnet may consistently forget to import `scipy.signal` while
opencode's gpt-5.4 may consistently emit markdown fences. A shared playbook
would accumulate rules that apply to only one mutator AND rules that are
contradictory across mutators. A per-arm playbook lets ACE curate rules
that actually match the arm's failure distribution.

**Why seeded from a SHARED start, not empty.** At run start, copy the seed
`CLAUDE.md` (the one Tim authored for the drone task) into each arm's
playbook file. Every arm gets the same task-level guidance on iter 1, then
drifts as its observer fires modify only that arm's file. Empty-start would
force each arm to re-derive task constraints from scratch via trial and
error, burning budget.

**Layout in the workdir.**

```
controllers/              ← mutation target (per iter)
.hone/run-<id>/
  playbooks/
    claude-code-sonnet.md       ← full CLAUDE.md for that arm
    opencode-gpt-5.4.md         ← full AGENTS.md for that arm (identical seed content)
    codex-gpt-5.4.md            ← ...
  playbook_versions/
    claude-code-sonnet/
      v0.md  (seeded at run start)
      v1.md  (after first observer fire on this arm)
      ...
```

**Dispatch flow per iter.**

1. Bandit picks arm X (a mutator spec).
2. Optimizer reads `playbooks/<X-hash>.md`.
3. When invoking the mutator:
   - For `harness:claude-code:*` arms → write that playbook to
     `<workdir>/CLAUDE.md` only.
   - For `harness:opencode:*` or `harness:codex:*` arms → write that
     playbook to `<workdir>/AGENTS.md` only.
   - Do NOT dual-write. Dual-writing was the v2 workaround for
     "we don't know which file the mutator reads"; in v3 we know because the
     mutator arm tells us (adapter name → file name).
4. Observer fire on arm X:
   - Reflector input: last `observer_window` iters from arm X's history
     only (filter `mutations.jsonl` by `arm == X`) + current
     `playbooks/<X-hash>.md`.
   - Curator writes updated content back to `playbooks/<X-hash>.md`.
   - Snapshot old version into `playbook_versions/<X>/v<n>.md`.

**Arm hash.** `<X-hash>` = short sha256 of the arm spec string, e.g.
`claude-code-sonnet-3f9a1b`. Keeps filenames readable while collision-safe
if two runs use overlapping arm labels.

**Deferred to v3.1 — Option C (shared base + per-arm delta).** A future
variation could split each playbook into a shared "task constraints" base
and a per-arm "behavioral corrections" delta, so universal rules stay in
sync across arms. Defer until we have empirical data from v3 on how much
per-arm playbook content is actually mutator-specific vs. universal. If v3
observer fires show 80%+ overlap in rule content across arms, Option C is
worth building; if arms diverge heavily, per-arm is clearly correct and
Option C adds complexity for no benefit.

---

## 5. Implementation

### 5.1 New files in `~/hone-v3/src/hone/`

```
selectors.py      — Selector ABC + UCB1, EpsGreedy, RoundRobin, Pareto
arm_stats.py      — ArmStats dataclass + serialization
mutator_pool.py   — MutatorPool: wraps dict[spec, Mutator] + Selector
observer_pool.py  — ObserverPool: same shape for observers
playbooks.py      — per-arm playbook I/O: arm_hash(spec), load/save,
                    snapshot to playbook_versions/
```

### 5.2 Changed files

```
cli.py            — parse comma-sep pools, construct pools, pass to optimize_dir
optimizer.py      — optimize_dir takes MutatorPool + ObserverPool instead of single Mutator/Observer
                  — per-iter: pool.pick() → mutator; after grade: pool.update()
                  — per-observer-fire: similar for observer pool
                  — summary.json gains per_arm_stats block
proposer.py       — propose_for_file accepts a specific Mutator (not hardcoded)
                  — writes ONE playbook file (CLAUDE.md xor AGENTS.md) based
                    on the chosen arm's adapter, not both (v2's dual-write
                    is retired since per-arm files know which adapter uses them)
observer.py       — ACE observer reads/writes a single arm's playbook
                    (path injected by optimizer). Window filtered to that arm's iters.
```

### 5.3 Changes to summary.json (v3 additions)

```json
{
  "mutator_pool": ["harness:claude-code:sonnet", "harness:opencode:openai/gpt-5.4"],
  "observer_pool": ["harness:claude-code:sonnet"],
  "selector": "ucb1",
  "reward_mode": "score_delta",
  "per_arm_playbook_path": ".hone/run-<id>/playbooks/",
  "per_arm_stats": {
    "harness:claude-code:sonnet": {
      "plays": 42, "total_reward": 3.14, "mean_reward": 0.075,
      "total_cost_usd": 12.34, "total_wall_s": 7800, "errors": 2
    },
    "harness:opencode:openai/gpt-5.4": {
      "plays": 58, "total_reward": 4.21, "mean_reward": 0.073,
      "total_cost_usd": 6.02, "total_wall_s": 9200, "errors": 8
    }
  },
  "best_arm_by_reward": "harness:claude-code:sonnet",
  "best_arm_by_rpd": "harness:opencode:openai/gpt-5.4"
}
```

### 5.4 Per-iter logging

Every `mutations.jsonl` row gains a full `bandit_state` block alongside
the existing fields. Without this we can't reconstruct "why was arm X
picked at iter 42" after the run.

```json
{
  "iter": 42,
  "target": "planner.py",
  "arm": "harness:opencode:openai/gpt-5.4",
  "bandit_state": {
    "window_size": 20,
    "window_start_iter": 22,
    "arms": {
      "harness:claude-code:sonnet": {
        "plays_in_window": 8,
        "mean_reward_in_window": 0.031,
        "ucb_score": 0.612
      },
      "harness:opencode:openai/gpt-5.4": {
        "plays_in_window": 11,
        "mean_reward_in_window": 0.054,
        "ucb_score": 0.629
      }
    },
    "picked_arm": "harness:opencode:openai/gpt-5.4",
    "picked_reason": "max_ucb"  // or "forced_exploration", "cold_start"
  },
  "reward": 0.017,
  "cost_usd": 0.12,
  ...
}
```

Scout flagged the absence of this as a category-H (operational /
engineering) pitfall. Treat the block as mandatory, not optional debug.

---

## 6. Open questions / design choices

### 6.1 Reward attribution under lineage branching

If GEPA branches (iter N's winner becomes two children via two different
mutators), both mutators get credit on their respective child. No lineage
collision because each iter has one mutator responsible for its direct
delta from parent.

### 6.2 Observer-mutator interaction

**Resolved by §4.2 (per-arm playbooks).** Prior drafts proposed a
"reflector must produce mutator-agnostic rules" constraint and a post-hoc
audit. Both are obsolete now that each arm has its own playbook — rules
CAN and SHOULD reference arm-specific tooling (e.g., "Edit tool" for
claude-code arms, "apply_patch" for codex arms). The observer writes only
to the relevant arm's playbook, so cross-arm contamination is impossible
by construction.

### 6.3 Stale arm beliefs after ACE rule changes

When the observer adds a rule, past mutator performance reflects behavior
BEFORE the rule. The arm's historical reward is stale. Options:
- **Discount old samples** with exponential decay (half-life = observer
  interval). Simple, effective.
- **Reset arms on observer fire.** Too aggressive — loses all bandit state.
- **Ignore** (POC). The bandit will adapt eventually; early bias is tolerable
  for 100-iter runs.

POC: ignore. Add exponential decay in v3.1 if we see stale-arm lock-in.

### 6.4 Cost heterogeneity across harnesses

Claude Code reports cost via JSON envelope. opencode reports via sqlite.
codex may not report. aider might. We need a consistent cost-per-call
source. For POC, use whatever harness.RunResult.cost_usd returns; if None,
estimate from tokens × published pricing table.

---

## 7. Smoke verification (before full run)

5-iter smoke with a 3-arm pool must show:

1. **All 3 arms played at least once** by iter 5 (via `explore_until = 2*3 = 6`
   would take 6 iters — use `explore_until = 3` for smoke).
2. **Per-arm stats in summary.json** are populated and sane.
3. **Bandit actually SELECTS** — if we use two arms and one is much better on
   synthetic data, the selector should prefer it in iters 4-5 after both
   were explored in 1-3.

Synthetic bandit test (unit-level, no LLM calls):
```python
# Mock mutator that deterministically returns score based on arm
# Run selector with 100 rounds; verify >70% pulls on best arm by iter 100.
```

---

## 8. Full-run config (what we actually run when this lands)

After smoke passes:

```bash
hone run --dir controllers/ \
    --grader ./grader.sh \
    --mutator-pool \
        harness:claude-code:sonnet,\
        harness:opencode:openai/gpt-5.4 \
    --observer-pool \
        harness:claude-code:sonnet,\
        harness:opencode:openai/gpt-5.4 \
    --selector ucb1 \
    --reward-mode score_delta \
    --scheduler diagnose \
    --scheduler-config ./scheduler.json \
    --budget 150 \
    --seed 0 \
    --output ./controllers.v3-honed
```

Budget 150 (not 100) because 2-arm pool + exploration needs more samples
for bandit to converge meaningfully.

(To evaluate cost-adjusted regret after the run, regenerate a derived
leaderboard with `reward_mode = score_per_dollar` from the raw
`mutations.jsonl` + per-iter `cost_usd` — the bandit doesn't need to
optimize on that signal for us to analyze on it later.)

### What we expect to learn

1. **Does one mutator dominate?** If after 30-40 iters UCB1 is pulling 80%+
   from one arm, we found the best mutator for this task.
2. **Is the observer choice orthogonal?** Does the observer's arm selection
   correlate with the mutator's arm selection? If claude-observer + opencode-
   mutator scores higher than either homogeneous combo, we found a cross-
   vendor win.
3. **Cost-optimal combo.** If opencode/gpt-5.4 is 4× cheaper per-iter but
   50% worse on score_delta, is `score_per_dollar` higher than claude-code?
4. **Robustness to error rates.** opencode may have different error modes
   than claude-code. How does each handle the 6-file workdir?

---

## 9. Integration with leaderboard

`summary.json` from a v3 run adds `per_arm_stats` block. The
`leaderboard.py` (from `harness-metric-design.md`) should:

- Sort arms across all runs, not just same-pool comparisons
- Flag when an arm appears in multiple runs and compute pooled mean
- Support "which arm was best on grader X?" queries

---

## 10. Novelty note (narrowed by scout findings 2026-04-20)

Earlier drafts of this spec claimed the "GEPA × ACE × bandit" triple-stack
was a new combination. That claim was wrong. Scout (`~/dev/hone-novelty/`)
found **ShinkaEvolve** (Sakana AI, arxiv 2509.19349, ICLR 2026), which
already runs UCB1 over a pool of LLMs for code-evolution search. The
bandit layer alone is NOT novel.

### What v3 genuinely contributes

Scout narrowed the defensible novelty claims to two:

1. **Harness-level arm granularity.** ShinkaEvolve's arms are raw LLM
   API endpoints. hone v3's arms are `(coding-CLI, model)` pairs —
   e.g., `harness:claude-code:sonnet`, `harness:opencode:gpt-5.4`,
   `harness:codex:gpt-5.4`, `harness:aider:sonnet`. The CLI matters
   because it determines tool access (Edit vs apply_patch vs shell),
   workspace discipline, and per-iter cost profile. As far as scout
   could find, no prior system has compared coding-CLI *agents* as
   bandit arms against a shared grader.
2. **Per-arm ACE playbook.** Each arm carries its own evolving
   CLAUDE.md / AGENTS.md, seeded from a shared start and updated only
   by observer fires on that arm. This is downstream of ACE (arxiv
   2510.04618) but the per-arm scoping and the coupling to the bandit's
   arm choice is new work.

### Positioning

Scout identifies the real competitor set as **OpenEvolve + ShinkaEvolve
+ DSPy/GEPA**, NOT orchestration stacks (LangGraph/AutoGen) or eval
harnesses (Braintrust). The niche is "coding-CLI-mutator entry in the
evolutionary-LLM-search space."

### What's publishable

**Workshop-publishable, not full-venue.** If the v3 run data shows (a)
the bandit meaningfully converges across coding-CLI arms, (b) per-arm
playbooks diverge in non-trivial ways, and (c) the winning arm beats
an equivalent v2-style solo run, that's a concrete empirical result for
an ICLR/ICML workshop submission. Full-venue novelty would require a
stronger claim than "we extended ShinkaEvolve with coding CLIs and
per-arm rules" — e.g., multi-grader cross-task transfer, or a proof
of the per-arm-playbook / bandit-arm coupling's regret bound.

### Credits

When v3 ships:
- README → "Credits" section citing ShinkaEvolve (arxiv 2509.19349),
  ACE (arxiv 2510.04618), GEPA/DSPy, and OpenEvolve as prior art.
- v3.md writeup → explicit "what we borrowed, what we added" section.

---

## 11. Implementation order (for drone-of-future)

1. `selectors.py` + synthetic bandit unit tests (no LLM calls). Must
   verify BOTH:
   - Classic UCB1 converges to best arm on a stationary 3-arm reward
     distribution with zero-inflated rewards (20% zeros, 80% normal
     positive).
   - Sliding-window UCB1 (W=20) adapts when the arm-reward mapping flips
     halfway through a 60-iter synthetic run (e.g., arm A is best for
     iters 0-29, arm B best for 30-59). Classic UCB should lock onto A
     and under-serve B; sliding-window should catch up by ~iter 45.
2. `arm_stats.py` (with ring-buffer reward history per arm, sized to
   window × safety factor) + `mutator_pool.py` + CLI parsing for
   `--bandit-window` (default 20).
3. `playbooks.py` — arm-hash helper, seed-from-shared CLAUDE.md, per-arm
   load/save, version-snapshot. Unit test: after N fake observer fires,
   arm X's playbook ≠ arm Y's playbook, both still contain the seed header.
4. Wire `MutatorPool` + per-arm playbook into `optimize_dir`. Smoke: 5
   iters with 2-arm pool, single-arm pool still produces identical behavior
   to v2.
5. `observer_pool.py` + observer-bandit wiring, scoped per-arm. Smoke: 20
   iters with 2 observer arms × 2 mutator arms, verify each mutator arm's
   playbook only gets modified when the observer fires ON that arm.
6. `summary.json` writes per-arm stats block + per_arm_playbook_path.
7. Full run per §8.
8. Writeup/v3.md: mutator arm winner, observer arm winner, per-arm playbook
   diff analysis (how much did the arms' rules diverge?), post-hoc
   cost-adjusted reward from mutations.jsonl.

### Baseline arm retargeted 2026-04-21 (cairn → drone)

Original plan: anthropic SDK direct for a "single API completion vs
agent-in-loop" control. Blocked on API billing (OAuth-only env). Replaced
with **claude-code single-shot (no-tools)**: harness:claude-code:sonnet
invoked via HarnessMutator.propose() with prompt scaffolding that forbids
Read / Edit / Bash tools. Contrast is narrower but tighter: "LLM-completion
via OAuth with tool access vs without." Runner at
`run_singleshot_baseline.py` (drone repo, not hone-v3). Arm label in
mutations.jsonl + summary.json: `harness:claude-code:sonnet:no-tools`.

Time estimate: 1-2 days from start to first full run. Smoke-able by end of
day 1.

---

## 12. What comes after v3.0 (scout findings 2026-04-20)

This section is forward-looking. **Do not rescope v3.0** — the sections
above are locked. Use §12 to decide what to queue *after* v3.0 ships.

### 12.1 Next (v3.1): multi-grader support

Scout's `~/dev/hone-novelty/MULTI-GRADER.md` argues that multi-grader is
hone's **killer use case**, not a nice-to-have. The wedge product story:
"optimize an agent orchestrator (spawn latency, message count, kill
reliability, task completion) across non-commensurable axes." DSPy,
ShinkaEvolve, and OpenEvolve all default to single-scalar; none of them
currently serve this. Multi-grader is where hone stops being "another
evolutionary-search framework" and becomes *the* coding-CLI-driven
multi-objective optimizer.

**Key design points (full spec in `writeup/v3.1-spec.md`):**

- `--grader` becomes repeatable (multi-occurrence accepted on CLI).
- `--grader-combine {pareto|weighted|lexicographic|epsilon}`;
  **default = Pareto** (scout's recommendation — avoids the
  non-commensurable-units tax of weighted-sum).
- `summary.json` gains per-grader-per-arm stats + Pareto-front
  candidates.
- Bandit reward for multi-grader Pareto: hypervolume contribution of the
  candidate's point on the current frontier (or for weighted-sum: the
  scalar).

Estimated cost: **2 person-weeks.** NOT scope creep per scout — the v3.0
pool + selectors infrastructure is most of the work; multi-grader is
mostly plumbing + one Pareto-bookkeeping module.

**Secondary v3.1 follow-up: `--scheduler-adaptive-file-weights` (opt-in).**
Run-2 (2026-04-20) showed that the `diagnose` scheduler routed 14 edits
to `world_model.py` and 3 to `attitude_ctrl.py` across two opencode-mutator
arms, with **zero accepted improvements** on those files. Every single
gain across all three arms was attributed to `planner.py`. One candidate
solution: weight the scheduler's fallback target distribution by each
file's cumulative accept rate, so files that have proven to be dead ends
get sampled less often. DEFERRED to v3.1 (not v3.0) because a single-task
datapoint isn't enough evidence — the pattern may be task-specific to
drone-racing. Revisit once we have data from 2+ reference problems
(SWE-bench Live, Stockfish). If adopted, keep it opt-in behind a flag so
the baseline scheduler behavior stays reproducible.

### 12.2 Strategic context: moat and obsolescence risk

Scout's `~/dev/hone-novelty/LANDSCAPE.md`:

- **Moat = MODERATE.** v1 reproducible in ~1 week by a skilled team;
  v3.0 reproducible in 6-10 person-weeks.
- **Strongest moat component = harness cross-CLI abstraction.** Being
  first to maintain a multi-CLI adapter library (claude-code + opencode
  + codex + aider) creates a first-mover + integration-complexity moat
  analogous to how `transformers` became the default model-adapter
  library.
- **Biggest obsolescence risk: DSPy ships a coding-CLI adapter for
  GEPA (<6mo probability non-trivial).** If that happens, hone v1's
  niche collapses. Scout's quoted estimate: "~1 day of work for anyone
  on the DSPy team."

**Defensive plays (ranked by scout):**

1. **Ship v3 fast.** Claim the multi-CLI bandit + per-arm ACE niche
   publicly before DSPy ships a single-CLI adapter.
2. **Consider contributing the harness library upstream to DSPy.**
   Becoming the de-facto adapter layer inside DSPy is a better outcome
   than being commoditized from outside.
3. **Workshop paper with v3.0 results + v3.1 multi-grader.** Plants a
   flag in the literature for "coding-CLI-mutator + per-arm ACE +
   multi-grader Pareto" as the distinguishing stack.

### 12.3 What to watch (weekly, not daily)

- DSPy changelog / PRs / issues mentioning "coding CLI", "shell",
  "agent", "claude-code", "codex adapter". Set a GitHub notification.
- Sakana AI / ShinkaEvolve extensions. If ShinkaEvolve itself ships
  coding-CLI arms, our novelty claim narrows further.
- OpenEvolve releases. Adjacent but not directly overlapping; watch
  for multi-grader features specifically.

### 12.4 v3.2+ (not yet specified)

Scout mentions (deferred, just flagging):
- Multi-grader cross-task transfer experiments (reference problems:
  SWE-bench Live Q3 2026, Stockfish Q4 2026, hone-on-hone meta
  Q1 2027).
- Contextual bandit coupling of mutator + observer arms.
- ACE playbook Option C (shared base + per-arm delta) if v3 shows
  high overlap in per-arm rule content.

For the full forward-look across ALL axes of choice (not just the scout-
sourced ones) — including the research directions that sit outside the
v3.x roadmap (hot/cold skills, subagent-template evolution, multi-repo
hone, ACE-on-ACE, per-rule attribution, offline counterfactual replay)
— see the unified design doc at `writeup/HONE-MODES.md`. That document
is organized by axis rather than by version; use it as the map, use
this spec as the v3.0 implementation contract.
