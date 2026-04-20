# Observations log — hone budget-100 primitive run

Timestamped observer notes during the run. Three categories:
- **MUTATOR-REPEAT** — mutator keeps introducing the same class of bug across iterations
- **STERR-IGNORED** — grader emits info that would have prevented a failure, but mutator doesn't read it
- **INFRA** — friction the observer notices that a machine could have caught

One entry per meaningful observation. Don't edit CLAUDE.md more often than every ~25 iterations.

---

## Setup context

- Start time: 2026-04-20T08:40:57Z (PID 84931)
- Budget: 100
- Mutator: claude-code:sonnet
- Grader: 4 levels × 5 seeds = 20 rollouts per candidate
- Seed planner score (from `runs/min_snap_seed_full.csv`): **0.8093**
  - L0: 5/5 completed @ 8.08s
  - L1: 5/5 completed @ 8.08s
  - L2: 0/5 completed, 2-3 gates typical
  - L3: 0/5 completed, 0-1 gates, mostly timeouts
- Baseline lsy state_controller (from `runs/baseline.csv`):
  - L0: 5/5 completed @ 13.86s
  - L1: 5/5 completed @ 13.86s
  - L2: 0/5 completed, best 3 gates
  - L3: 0/5 completed, 0 gates
- CLAUDE.md authored with: mutation-target constraints, Planner interface contract,
  level semantics, 5 known failure modes, 6 do-nots.
- Mutator workdir pinned to project root (via `runs/launcher.py`) so it reads CLAUDE.md.

## CLAUDE.md edits during run

### Edit #2 @ 2026-04-20 08:52, after observing first fix might still be ambiguous
**Trigger:** Tim's pushback — "maybe phrasing is confusing? return changes = no
tools? edit files is normal work?" — pointed out my CLAUDE.md fix still implicitly
conflicted with Claude Code's default mode (which is to edit files via tools, not
respond with text). The word "return" implies no tools, but editing files is
Claude Code's normal behavior, so the prior language created a conflict the
mutator might resolve incorrectly (respond with a change summary because a
summary is the natural text output when tools are used).

**Edit:** Restructured the top of the Mutator Instructions section to:
1. Open with "this is NOT a normal Claude Code session" framing.
2. Explicitly forbid Edit/Write/MultiEdit tools (they'd be wasted work since
   hone doesn't re-read the file).
3. Spell out the hone→temp-file→grader.sh→importlib pipeline so the mutator
   understands its response text LITERALLY becomes a Python file.
4. Add a "if you feel the urge to use a tool" section naming the two failure
   modes (tool use + summary response) by name.

**Human-judgment content:** Tim caught the conflict. An LLM observer reading
only the responses might have reached a similar conclusion, but the specific
framing ("edit files is normal work — of course it's confused") is easier for
a human who knows Claude Code's UX than an LLM observer pattern-matching on
output shape.

**For ACE:** A human-in-the-loop advantage — understanding the TOOL's default
mode, not just the output, was needed here. ACE would need the observer to
know what "normal" for the underlying mutator looks like. Probably doable with
a per-adapter "default behavior" note in hone's adapter config.

### Edit #1 @ 2026-04-20 08:47, after iter 2
**Trigger:** MUTATOR-REPEAT pattern confirmed on iters 1+2 (100% of output so far).
Mutator is returning natural-language "notes on what to change" instead of a
Python file. The "don't edit CLAUDE.md before iter 25" rule is meant to avoid
overreacting to noise — this isn't noise, it's every iteration bricked at score 0.

**Edit:** Rewrote top of Mutator Instructions section to explicitly call out:
- Hone's "improve the prompt" framing is ambiguous; ignore it
- Output is a Python source file, not a prose analysis
- Hard rules on first-line shape (must be docstring / import / comment)
- Self-check block: "read your output back"

**What an ACE observer would have needed to detect this:**
1. Parse each `runs/mutations.jsonl` entry's `response_head` and run `compile()`
   on the response_body. If it throws SyntaxError on iter 1 — observer fires.
2. That's a purely LLM-catchable signal — no human judgment needed.
3. Observer-interval default of 10 would have missed this; budget 2 would catch.
   Recommendation for ACE: observer should run at least every 3-5 iters in the
   early phase where the loop is still self-calibrating.

## Observations

### 2026-04-20 08:45 — iter 1+2
**Observation: Mutator returns natural-language analysis, NOT Python code.**

Iter 1 response (1881 chars, cost $0.129):
> "Drone racing cubic-spline planner. Score 0.809 — below identifies why and what to fix.
> SCORE BREAKDOWN (level weights L0=1.0 L1=1.5 L2=2.0 L3=3.0):
> L3 (random tracks) dominates total score..."

Ends with:
> "- APPROACH_DIST: 0.65–0.8 (raise from 0.5)
> - EXIT_DIST: 0.35–0.45 (lower from 0.5)
> ...Implement curvature-aware speed scaling in _assign_times..."

Iter 2 response (2583 chars, cost $0.134):
> "Drone racing planner scoring 0.809 at conservative 1.5 m/s cruise. The instruction
> docstring needs to guide the mutation agent toward specific, high-impact improvements..."

Both responses are PROSE describing what SHOULD be changed, not the updated Python.
When these get written to `/tmp/*.prompt` and loaded via `importlib`, they'll
crash with SyntaxError → rollout exits non-zero → subprocess returns score 0 →
every iteration dead-ends at 0.0.

**Root cause hypothesis:** hone's mutator prompt says "improving a prompt" and
"Return ONLY the improved prompt text." Claude-code + my CLAUDE.md says "return
Python code." The ambiguity of "prompt" is resolved by the mutator toward the
natural interpretation of the task framing, not the content type, and CLAUDE.md
either isn't being read (more likely — `claude -p --dangerously-skip-permissions`
may not load workdir CLAUDE.md) or is being overridden by hone's framing.

**Classification:** INFRA + CLAUDE.md gap, but ALSO a hone design tension —
hone assumes the component being optimized IS a prompt. We're bending it to
mutate code. The loop is currently structurally broken, not a CLAUDE.md
wording problem.

**Action:** Not editing CLAUDE.md yet — pattern is 2/2 so far, confirming.
Sending parent a real-time flt escalation now (this is the kind of observation
the task specifically asked for in real-time). Continuing to watch: do
iterations 3+ break the same way? If yes at iter 5+, run is effectively dead
and needs intervention.

### Diagnostic questions to verify at iter 3+
1. Does the grader return 0.0 for the iter 1 and iter 2 candidates (confirms
   the responses are non-executable)? **Confirmed yes** — hone log shows
   "New subsample score 0.0, skipping" for both.
2. Does claude-code actually load my workdir CLAUDE.md? Partial evidence at
   iter 3: response length jumped to 9396 chars and the body WAS Python code
   (docstring, imports, Planner class, the works) — but wrapped in ```python ...
   ``` markdown fences. So CLAUDE.md IS being read (or at least influencing
   behavior), just not fully followed.
3. Is the mutator reading stderr trace at all? Yes — all responses reference
   specifics from the trace ("L3 dominates", "1.5 m/s cruise", "0.809 score").

### 2026-04-20 08:52 — iter 3+4 update
- Iter 3 (after Edit #1): returned full valid Python **wrapped in ```python ...
  ``` markdown fences**. 9396 chars, cost $0.41. Still unparseable by importlib.
  Progress: mutator now believes it should return code. Regress: wrapping in
  markdown (which CLAUDE.md #1 explicitly forbade).
- Iter 4 (still under Edit #1): reverted to **prose** again, starting "Looking
  at the scoring (0.809) and the hone system's architecture, the 'prompt' is
  the module docstring...". 2317 chars, cost $0.15. Mutator behavior is
  **inconsistent** — alternating between prose and code-in-fences.
- Hypothesis: Claude Code's instinct to either (a) use Edit tools or (b)
  respond with a change summary is being suppressed by CLAUDE.md, but not
  robustly. A single directive has low prior weight against the adapter's
  default mode.

### 2026-04-20 08:54 — throughput & cost projection
- 4 iterations in 14 min = 3.5 min/iter avg.
- Grader is ~10-15s; mutator is ~60-90s.
- At this rate, budget 100 ≈ 5.8 hours.
- Cost so far: $0.13 + $0.13 + $0.41 + $0.15 = **$0.82** after 4 iters of 100.
  Projected: ~$20-25 for budget 100.

### 2026-04-20 09:00 — CLAUDE.md Edit #2 tested on iters 5–6, failed
- Iter 5 (08:55:34, after Edit #2): `"Looking at the current planner (score 0.809),
  I'll make three targeted improvements..."` — prose again.
- Iter 6 (09:00:38, clearly under Edit #2): `"Looking at the current planner
  (score 0.809), the main improvement areas are:\n1. Bug: obstacle avoidance
  break only handles the first coll..."` — prose again.
- Six iterations, six scores of 0.0. Neither CLAUDE.md edit flipped Claude Code
  out of "respond with an analytical summary" mode when the prompt framing
  called the artifact a "prompt".

### 2026-04-20 09:02 — RUN KILLED by cairn
**Final state:**
- PID 84931 terminated.
- 6 iterations, all scored 0.0. Best score unchanged from seed (0.8093).
- Cost: **$1.3885** (tokens in=16, out=58,857). Most wasted on iter 3 ($0.41,
  9396-char response that was valid code but wrapped in ```python ... ```
  fences — one `strip()` off the loop from parseable).
- Wall time: 22 min before kill.

**Root-cause conclusion:** hone's mutator prompt template ("You are improving a
prompt so it scores higher. Return ONLY the improved prompt text.") is broken
for code-seed components. claude-code resolves "prompt" toward
natural-language-prompt semantics. My two CLAUDE.md edits (Edit #1: forbid
markdown fences; Edit #2: "NOT a normal Claude Code session, your response IS
the file, do not use Edit tool") did not flip behavior — in 6/6 iterations
the response was prose or fenced code, never raw Python.

**The 6 fixes pushed to hone/harness** (via honefix agent spawned by cairn
after my flt-send-parent escalations):
1. `hone --component-kind {prompt|code:py|code:ts|...}` — explicit flag,
   plus auto-detect from seed filename extension.
2. hone post-validates mutator output — for code kinds, run the target
   language's parser; on parse failure, retry once with explicit error, don't
   charge the iteration to budget.
3. hone renames user-facing "prompt" → "component" / "artifact" when the
   kind is code.
4. harness verifies `claude -p --dangerously-skip-permissions` honors workdir
   CLAUDE.md walk-up; if not, pass `--append-system-prompt "$(cat CLAUDE.md)"`.
5. hone ships a **file-based mutator mode** (alternative to text-in-text-out):
   writes candidate to a worktree, invokes claude-code with Edit-tool
   freedom, reads back the resulting file as the new candidate. This
   matches claude-code's natural workflow and sidesteps the whole
   "response-text must parse as Python" fragility.
6. hone diff-visibility — show the mutator what it changed last iteration,
   so "improve this further" has proper continuity (currently each iteration
   the mutator re-reads the seed as if it were its first look).

**Resume plan:** hold run until the PRs land + Tim merges. On resume:
(a) prefer the file-based mutator mode (#5) if available, since it bypasses
the root cause entirely, (b) rerun from the same seed to keep comparability,
(c) document the before/after impact in first_run.md.

### 2026-04-20 09:12 — POST-MORTEM PROBE: does `claude -p` auto-load workdir CLAUDE.md?

Ran a direct probe using the harness API (not hone) with a prompt asking the
mutator to read CLAUDE.md and quote back the Mutator Instructions section.

**Result:** claude-code returned `num_turns: 2`, `cache_read_input_tokens:
38716`, and the result field contained the verbatim opening of Edit #2's
section: "Unusual invocation mode — read this carefully. This is NOT a normal
Claude Code session."

**Interpretation:** claude-code CAN read workdir CLAUDE.md (via the Read
tool) when the prompt tells it to, and the workdir-pin via `runs/launcher.py`
was correctly giving it access. BUT during actual mutator calls, the hone
prompt ("You are improving a prompt... return the improved prompt text") does
NOT ask the mutator to read CLAUDE.md, and claude-code in `-p` mode is
**purely reactive** — it only uses tools when the prompt implies they're
needed. One-turn response, no Read tool call, no CLAUDE.md ever consulted.

**So: my two CLAUDE.md edits had ~0 effect on the 6 mutator runs.** Iter 3's
brief flip into code-in-markdown-fences was sampling variance, not CLAUDE.md
influence. The entire CLAUDE.md-edit intervention was a no-op from the
mutator's perspective.

**Harness PR #4 implication:** this is NOT a "verify that claude-code walks
up for CLAUDE.md" bug. It's a "claude-code in print mode does not inject
CLAUDE.md as a system prompt; only exposes it via tools." The correct fix is
**mandatory**: the `claude-code` adapter should pass `--append-system-prompt
"$(cat workdir/CLAUDE.md)"` (if the flag exists) or equivalent — making the
project CLAUDE.md part of the mutator's system prompt every call, not
something the mutator would only discover if the user prompt nudges it.

**Implication for ace_case.md:** downgrades ACE further. Even a perfect ACE
observer editing CLAUDE.md in real-time would have been shouting into a void
under this run — the mutator never saw any of it. The harness-layer fix
precedes any observer-layer concern.

---
