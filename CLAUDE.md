<!-- flt:start -->
# Fleet Agent: drone
You are a managed agent in a fleet orchestrated by flt.
Parent: cairn | CLI: claude-code | Model: opus[1m]

## IMPORTANT: Nobody reads your terminal output.
Your terminal has no human viewer. The ONLY way to communicate is:
```
flt send parent "your message here"
```
Use this for: progress updates, questions, completion reports, blockers.
Do NOT just print to stdout — it goes nowhere.

## Other commands
- Message sibling: flt send <name> "<message>"
- List fleet: flt list
- View agent output: flt logs <name>

## Protocol
- Report completion to parent when your task is done
- Report blockers immediately — don't spin
- Do not modify this fleet instruction block

<!-- flt:end -->

# Mutator instructions (for hone iterations on controllers/planner.py)

You are evolving the `Planner` class in `controllers/planner.py`. The hone
harness handles the output-shape contract (plain Python, no fences, no prose);
the notes below are what you actually need to know about the task.

## Hard constraints (violating these wastes the iteration)

1. **Only modify `controllers/planner.py`.** The grader loads exactly this file
   via `importlib`. Other files (`attitude_ctrl.py`, `baseline.py`, `run_rollout.py`,
   `grader.sh`) are infrastructure — editing them does nothing for scoring and
   may break the loader.
2. **Preserve the `Planner` class interface exactly:**
   - `class Planner:` at module scope (not renamed, not removed).
   - `__init__(self, obs: dict, info: dict, config)` — reads initial obs.
   - `compute_target(self, obs, info, t) -> np.ndarray` — MUST return a
     numpy array of **13 float32 values** in order:
     `[x, y, z, vx, vy, vz, ax, ay, az, yaw, roll_rate, pitch_rate, yaw_rate]`.
     Wrong shape → the env rejects and the drone crashes instantly.
   - `step(self, obs, info, action, reward, terminated, truncated)` — callback,
     keep the signature even if the body is `pass`.
     (`is_finished` property is optional.)
3. **Imports must be self-contained.** Only use `numpy`, `scipy`, and `toppra`.
   No `from controllers.*` or `from lsy_drone_racing.*` — the file is executed
   as a temp module during grading, not as a package member.
4. **Do not import from or reference `attitude_ctrl.py`, `baseline.py`, or
   anything else in the repo.** Any cross-file logic belongs inside planner.py.
5. **Obs keys are fixed by the sim:** `pos` (3,), `vel` (3,), `quat` (4, xyzw),
   `ang_vel` (3,), `target_gate` (int, -1 when all passed), `gates_pos`
   `(n_gates, 3)`, `gates_quat` `(n_gates, 4)`, `obstacles_pos` `(n_obstacles, 3)`.
   Obstacles are vertical capsules (ignore z — treat as xy circles).

## What to optimize

Read the stderr feedback carefully — it contains per-rollout diagnostics for
4 difficulty levels × 5 seeds:
- `gates=P/N` — how many gates the drone cleared (higher = better)
- `lap_time` — time when the episode ended (lower = better when completed)
- `crash_reason` — `completed`, `timeout`, `out_of_bounds`, or `collision`
- `gate_times` — per-gate crossing times (irregular spacing = bad pacing)
- `approach_angles` — angle between drone velocity and gate normal at crossing
  (smaller = cleaner approach; > 25° usually precedes a failed gate next time)
- `max_velocity` — peak 3D speed
- `latency_p50`, `latency_p99` — `compute_target` runtime (< 1ms p99 required)

**Level weights for the aggregate score: L0=1.0, L1=1.5, L2=2.0, L3=3.0.**
Level 3 (random tracks) dominates — prioritize robustness to unseen gate
layouts over raw L0 lap-time improvements once L0 is clean.

## Level semantics

- **level0.toml** — deterministic track, no randomization. Baseline sanity check.
- **level1.toml** — randomized inertial properties (drone mass/drag).
- **level2.toml** — randomized obstacle & gate poses (same layout template).
- **level3.toml** — randomized tracks (different gate sequences per seed).
  This is the generalization test. Do NOT hardcode gate positions.

## Common failure modes to avoid

- **Wrong gate-normal axis.** Gate collision geometry is thin in local x, wide
  in y/z — the "through" direction is gate's local x-axis
  (`Rotation.from_quat(q).apply([1,0,0])`).
- **Exit waypoint inside the gate frame thickness.** Gate frame extends ~0.36m
  radially from center; exit waypoint must be > 0.4m along the gate normal to clear it.
- **Approach waypoint colliding with an obstacle.** The planner must check
  `obs["obstacles_pos"]` and nudge any waypoint that lands inside an obstacle's
  xy safety bubble (~0.2m radius).
- **Aggressive velocity / acceleration.** Mellinger low-level ctrl in crazyflow
  can't track beyond ~3 m/s or ~8 m/s² reliably. Faster targets → crashes.
- **Non-zero velocity/acceleration in the action vector.** Empirically the
  simpler position-only command tracks better than feeding spline derivatives
  as feedforward. Keep vel/acc in the action to `0.0` unless you have a specific
  reason to do otherwise.

## Do not

- Do not reformulate the class as a `Controller` subclass. Planner is standalone.
- Do not train a neural network or load weights.
- Do not add a new pip dependency — only numpy/scipy/toppra are guaranteed.
- Do not print/log to stdout or stderr from inside Planner methods. The grader
  captures stderr; polluting it confuses future iterations.
- Do not edit this CLAUDE.md.
