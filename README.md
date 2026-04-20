# hone-a-drone

Autonomous drone racing controller evolved by hone (GEPA + Claude Code mutator) against the utiasDSL lsy_drone_racing sim.

## Install

Requires Python 3.11 and [uv](https://github.com/astral-sh/uv).

```
make setup
```

## Demo

Smoke test (budget 5 hone iterations):

```
make demo
```

Full baseline (4 difficulty levels × 3 seeds each):

```
make baseline
```

## Architecture

```
┌────────────────────────────────────────────────────────────┐
│ FPV camera + IMU + motor RPM                               │
└────────────────────────┬───────────────────────────────────┘
                         ▼
┌────────────────────────────────────────────────────────────┐
│ [perception] gate_detector.py                              │
│ Input: camera frame. Output: gate corner pixels + conf.    │
└────────────────────────┬───────────────────────────────────┘
                         ▼
┌────────────────────────────────────────────────────────────┐
│ [state estimation] state_estimator.py                      │
│ Input: IMU + camera. Output: pose, vel, acc (drone frame). │
└────────────────────────┬───────────────────────────────────┘
                         ▼
┌────────────────────────────────────────────────────────────┐
│ [world model] world_model.py                               │
│ Fuses detector + pose into gate positions in world frame.  │
└────────────────────────┬───────────────────────────────────┘
                         ▼
┌────────────────────────────────────────────────────────────┐
│ [planner] planner.py                                       │
│ Input: pose + gate list. Output: reference trajectory.     │
└────────────────────────┬───────────────────────────────────┘
                         ▼
┌────────────────────────────────────────────────────────────┐
│ [controller] attitude_ctrl.py                              │
│ Input: reference. Output: thrust + attitude command.       │
└────────────────────────────────────────────────────────────┘
```

## Files

| File | Purpose |
|---|---|
| `controllers/planner.py` | Minimum-snap + TOPP-RA trajectory planner (primary hone target) |
| `controllers/gate_detector.py` | Gate perception; ground-truth pass-through until DCL sim |
| `controllers/state_estimator.py` | State estimation; ground-truth pass-through until DCL sim |
| `controllers/world_model.py` | Fuses detection + pose into world-frame gate map |
| `controllers/attitude_ctrl.py` | Low-level thrust + attitude controller |
| `run_parallel.py` | Parallel rollout runner across levels and seeds |
| `grader.sh` | Scores a rollout for hone reward signal |
| `STACK.md` | Full architecture reference and component rationale |

## Runs

`make baseline` writes one CSV per (level, seed) to `runs/`. Each row is a timestep. Columns: `t`, `x`, `y`, `z`, `gate_id`, `reward`. Aggregate with any CSV tool; `runs/*.log` holds per-run stdout.

## Motivation

The Anduril Grand Prix challenges teams to fly autonomous drones faster than human experts through tight gate sequences. hone-a-drone uses hone's GEPA-backed mutation loop to iterate the trajectory planner rapidly, targeting sub-second lap improvements per hone budget unit.

## Disclosure

See [disclosure.md](disclosure.md) for full AI tooling and open-source dependency disclosure per Anduril §(d).
