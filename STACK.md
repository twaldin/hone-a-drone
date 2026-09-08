# STACK.md

This document preserves the proposed racing stack and its component research. It is not an inventory of implemented features or a verified dependency/license disclosure. See [README.md](README.md#current-controller-path) for the committed proxy seed: SciPy cubic-spline planning, simulator-observation adapters, a pass-through world model and a 13-component state-command adapter. CNN perception, VIO, map fusion, minimum-snap optimization, TOPP-RA timing and MPC are not implemented in that path.

## Philosophy

1. **Permissive licenses only** (MIT / BSD / Apache 2.0). GPL and AGPL are excluded by policy — not because they're bad, but because they create distribution obligations that conflict cleanly with Anduril §(c) Entry handling and complicate §(d) disclosure. Where the best-known package is GPL (e.g., Fast-Planner, rpg_mpc), we use the permissive equivalent and note it below.
2. **Competitive seeds, not educational ones (design goal).** The proposed full stack combines MPC-backed control, minimum-snap planning, VIO state estimation and learned gate detection. The committed proxy seed is simpler; these are proposed upgrades, not its starting capabilities.
3. **Module boundaries match mutation targets (design goal).** Each layer below has its own file. Candidate-directory grading lets the planner load sibling changes together; the legacy single-file demo does not make every module a standalone planner entry point.
4. **One framework per layer.** No dual-stacks, no abstraction layers "for future flexibility." Pick the one best thing, commit to it.

## Proposed architecture

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

## Proposed component picks

| Layer | Seed package | License | Source | Why |
|---|---|---|---|---|
| Simulator framework | `lsy_drone_racing` + `crazyflow` | MIT | utiasDSL | Already our env; JAX-backed; 4 difficulty levels as multi-task dataset |
| Perception | Custom lightweight CNN (U-Net corner detector à la arXiv:2012.04512), trained in PyTorch | BSD (torch) + MIT (our code) | Proposed training on UZH-FPV + TII-RATM | Sidesteps Ultralytics AGPL; corner regression > bbox for pose recovery |
| Time-optimal parameterization | TOPP-RA | MIT | hungpham2511/toppra | Millisecond-scale time-optimal parameterization of geometric paths |
| Trajectory generation | `mav_trajectory_generation` (math only, port ~150 LOC) | Apache 2.0 | ethz-asl | Canonical minimum-snap polynomial trajectories |
| Low-level attitude | `drone-controllers` (from lsy_drone_racing) | MIT | utiasDSL | Already in our env; retained as fixed baseline |
| Perception fine-tune datasets | UZH-FPV, TII-RATM, AirSim Drone Racing | Research / MIT (AirSim) | Public | All public, no redistribution |
| MPC solver | acados | BSD-2-Clause | acados/acados | Real-time nonlinear MPC; permissive; don't use rpg_mpc wrapper (GPL) |
| Geometric SE(3) control | `uav_geometric_control` | Apache 2.0 | fdcl-gwu | Reference SE(3) controller for extreme attitude maneuvers |
| State estimation (VIO) | OpenVINS | Apache 2.0 | rpng/open_vins | IROS 2019 FPV VIO competition winner; handles 23+ m/s; monocular-capable matches Anduril's single-camera spec |

## Exclusions and deferred alternatives

The license exclusions below are design constraints. The final row records deferred permissive alternatives, not a license exclusion. Research license labels here still need verification for any actual entry.

| Excluded | License | Replaced by |
|---|---|---|
| Ultralytics YOLO | AGPL-3.0 | Custom PyTorch detector or YOLOX (Apache) |
| VINS-Fusion, ORB-SLAM3 | GPL-3.0 | OpenVINS |
| Fast-Planner | GPL-3.0 | `mav_trajectory_generation` + TOPP-RA + acados MPC |
| cflib (Crazyflie radio) | GPL-3.0 | Not needed — Anduril runs our code in their sandbox |
| rpg_mpc, rpg_time_optimal | GPL-3.0 | acados + custom MPC formulation |
| CleanRL, Stable-Baselines3 | MIT | vwxyzjn, DLR-RM — only if a learned component is added later |

## Proposed module → hone rotation targets

The Makefile's legacy demo targets `planner.py`. The grader also accepts a candidate directory and the loader exposes its sibling modules, so directory candidates can include changes across the controller stack. The `diagnose` scheduler below is proposed, not a tracked command; see [ROADMAP.md](ROADMAP.md). Proposed rotation priority:

1. `planner.py` — highest leverage, largest search space, fastest convergence. Start here.
2. `world_model.py` — gate position estimation logic; often the real bottleneck once perception is OK.
3. `gate_detector.py` — NMS thresholds, confidence gating, temporal smoothing logic. Don't let hone retrain the CNN weights — evolve the post-processing code only.
4. `state_estimator.py` — tuning parameters and fusion logic around OpenVINS output. Don't evolve OpenVINS itself.
5. `attitude_ctrl.py` — last. Low-level control is usually close to optimal via classical methods; expected gains are small.

Files NOT in the rotation: `run_rollout.py`, `run_parallel.py`, `grader.sh`. These are infrastructure.

## Proposed dependency seed (not current pyproject.toml)

The actual [pyproject.toml](pyproject.toml) declares NumPy, SciPy, TOPP-RA and Gymnasium; PyTorch/torchvision and acados-template are optional extras. Simulator and hone installation is separate in the legacy Makefile. The block below preserves the broader design proposal rather than instructions to replace the current metadata.

```toml
[project]
dependencies = [
  "lsy-drone-racing",       # MIT — sim framework
  "crazyflow",              # MIT — sim backend
  "torch>=2.2",             # BSD — perception
  "torchvision",            # BSD
  "numpy",
  "scipy",
  "acados-template",        # BSD — MPC
  "toppra",                 # MIT — time-optimal param
]
```

Note: OpenVINS and `mav_trajectory_generation` are C++/ROS-native. The original proxy-work proposal was to port just the math needed:
- Minimum-snap polynomial coefficients (~150 LOC) into `planner.py` directly.
- Kalman filter / VIO residual math into `state_estimator.py` (or use `openvins-python` wrappers where available).

Full C++ stack integration was deferred to the DCL sim; this records the original dependency, not a claim about that simulator's current availability.

## Disclosure template (Anduril §(d))

Planning example only. The lists include proposed components and datasets and do not establish that they were used, ported, trained on or included in an entry. The former root `disclosure.md` was untracked in `8f956a3`; do not recreate it as a personal disclosure without the author's confirmation of the actual tools, software, datasets and applicable competition requirements.

```
Generative AI tools used in development:
  - hone (https://github.com/twaldin/hone) — prompt/code optimizer, MIT
  - GEPA (https://github.com/gepa-ai/gepa) — reflective optimization engine, MIT
  - Claude Code (Anthropic) — code mutation engine

Open-source software included in Entry:
  - lsy_drone_racing (MIT) — simulation framework during development only
  - crazyflow (MIT) — simulation backend during development only
  - OpenVINS (Apache 2.0) — visual-inertial odometry
  - mav_trajectory_generation (Apache 2.0) — polynomial trajectory synthesis math (ported)
  - TOPP-RA (MIT) — time-optimal path parameterization
  - acados (BSD-2-Clause) — MPC solver
  - uav_geometric_control (Apache 2.0) — geometric attitude control reference
  - PyTorch, torchvision (BSD) — perception CNN runtime

Datasets used for training perception components:
  - UZH-FPV Drone Racing Dataset (research license, properly attributed)
  - TII-RATM Dataset (research use, properly attributed)
```

For an actual submission, verify the applicable disclosure requirements and replace the planning example with the author's confirmed inventory. Review that inventory whenever a dependency is added or swapped; do not treat this template as proof of use or license compliance.
