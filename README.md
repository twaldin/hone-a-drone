# hone-a-drone

Drone-racing controller experiments using the [utiasDSL lsy_drone_racing simulator](https://github.com/utiasDSL/lsy_drone_racing). The recorded experiments used hone's GEPA-backed mutation loop; the committed `controllers/` directory is the proxy-simulator seed, not a complete camera-based racing stack or the best output of every run.

## Setup and command status

The scripts expect a repository-local `.venv/bin/python` and a simulator checkout at `sim/lsy_drone_racing`. The Makefile selects Python 3.11 and uses [uv](https://github.com/astral-sh/uv); `pyproject.toml` declares Python >=3.11, NumPy, SciPy, TOPP-RA and Gymnasium, with optional perception and MPC dependencies.

**The original setup and optimizer demo are legacy commands, not a verified fresh-clone quickstart.** `make setup` clones the simulator without a pinned revision, creates `.venv`, installs the simulator's `[sim]` extra, installs hone from its unpinned GitHub repository, then installs TOPP-RA. Current upstream interfaces have changed:

- The [simulator package metadata](https://github.com/utiasDSL/lsy_drone_racing/blob/main/pyproject.toml) no longer declares a `[sim]` Python extra. Check upstream setup requirements before preparing a compatible simulation environment.
- [Current hone](https://github.com/twaldin/hone) uses a Node-based capsule CLI, not the Python `hone run <file> --grader ... --mutator ... --budget ...` interface used here. `make setup` and `make demo` have not been migrated to that interface.

The repository does not pin a known-compatible historical hone/simulator pair. Restoring a reproducible setup is a separate implementation task; do not assume installing upstream HEAD recreates the recorded experiments.

| Target | What the committed Makefile requests |
|---|---|
| `make setup` | Legacy environment setup described above; installs dependencies and accesses the network |
| `make demo` | Legacy hone run targeting `controllers/planner.py`, Claude Code Sonnet mutator, budget 5; mutates code and runs simulations, not a lightweight smoke test |
| `make baseline` | Evaluate the committed planner across levels 0–3 and seeds 1–3 (12 rollouts); no optimizer |

With a compatible simulator and dependencies already installed, the baseline entry point is:

```sh
make baseline
```

Commands here were checked statically against the Makefile and runners, not by installing dependencies or running simulations.

## Current controller path

At initialization, `Planner` reads simulator observations through `StateEstimator` and `GateDetector`. `WorldModel` passes the gate detection through unchanged. The planner builds approach/center/exit waypoints, nudges approach and exit points away from obstacles, and fits a SciPy `CubicSpline`. Segment times use waypoint distance divided by `CRUISE_SPEED`, bounded below by `MIN_SEGMENT_TIME`.

At each control step, the planner samples that precomputed spline and calls `make_state_command(pos)`. It returns 13 floats: position, velocity, acceleration, yaw and angular rates. The current caller supplies only position; the other components are zero-filled. Low-level tracking belongs to the simulator, not a local MPC implementation.

There is no camera detector, VIO, gate-map fusion, minimum-snap solver or TOPP-RA parameterization in the current controller path. [STACK.md](STACK.md) preserves the proposed architecture and component rationale separately from this implemented seed.

## Files

| File | Purpose |
|---|---|
| `controllers/planner.py` | Cubic-spline waypoint planner and controller entry point |
| `controllers/gate_detector.py` | Passes through simulator gate positions, orientations and visited flags, with unit confidence |
| `controllers/state_estimator.py` | Passes through simulator position, velocity, orientation and angular velocity |
| `controllers/world_model.py` | Returns detector output unchanged; no fusion yet |
| `controllers/attitude_ctrl.py` | Assembles the 13-component state command |
| `run_rollout.py` | Loads a candidate's `Planner` and runs one episode; prints a JSON result |
| `run_parallel.py` | Fans out rollouts, scores results and writes one aggregate CSV |
| `grader.sh` | Accepts a planner file or a directory containing `planner.py`; evaluates levels 0–3 with five seeds each |
| [STACK.md](STACK.md) | Architecture proposal, component research and disclosure template |
| [ROADMAP.md](ROADMAP.md) | Historical multi-module rotation proposal and design constraints |
| [experiments/hone-vs-autoresearch/](experiments/hone-vs-autoresearch/) | Preserved comparison policies, seed controllers and results |
| [posts/](posts/) | Dated experiment write-ups; not current setup instructions |

## Results and scoring

`make baseline` writes one timestamped CSV to `runs/` for the entire invocation, with one row per rollout, not per timestep. Columns include `level`, `seed`, `gates_passed`, `n_gates`, `lap_time`, `crashed`, `crash_reason`, `max_velocity`, `gate_times`, `approach_angles`, `loop_latency_p50`, `loop_latency_p99` and `rollout_score`; error results can also contain `error`.

`run_parallel.py` prints one JSON result per rollout and the aggregate score on the last stdout line. Human-readable rollout and score summaries go to stderr; it does not create per-run `.log` files automatically.

Higher scores are better. A completed rollout scores `1 + 10 / lap_time`; a crash scores half the fraction of gates passed; other unfinished rollouts score the fraction passed. Scores are averaged across seeds within each level, then combined with weights L0=1, L1=1.5, L2=2 and L3=3, normalized by the total weight.

The dated posts and experiment notes retain their original results and local artifact paths. Some referenced `.hone/` runs, validation logs and output snapshots are not tracked; a public checkout is not a complete reproduction bundle. Preserve local runs, spikes and experiment worktrees rather than treating them as disposable documentation clutter.

## Motivation

The Anduril Grand Prix motivated these proxy-simulator experiments: use measured controller performance to guide code mutation before integrating a full racing stack. The research and future component choices are recorded in STACK.md and ROADMAP.md; they are not claims of a completed competition entry.

## Disclosure

`disclosure.md` was removed from the tracked tree in commit `8f956a3` and is ignored as scratch material. The [disclosure template in STACK.md](STACK.md#disclosure-template-anduril-d) is a planning checklist, not a verified statement of tools, dependencies or datasets used in a submitted entry. Any actual disclosure needs the author's confirmation against the entry being submitted.
