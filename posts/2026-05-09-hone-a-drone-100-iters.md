---
title: hone-a-drone, 100 iterations from a 1.5 m/s seed planner to a +6.6% gepa-tuned controller
date: 2026-05-09
slug: 2026-05-09-hone-a-drone-100-iters
---

100 hone iterations took my drone-racing controller from a seed score of 1.0293 to 1.0970, a 6.6% improvement. The mutator was codex/gpt-5.5 over the OpenAI API. Each iteration ran 20 rollouts (4 difficulty levels × 5 seeds) on the [lsy_drone_racing](https://github.com/utiasDSL/lsy_drone_racing) sim. The full repo is [hone-a-drone](https://github.com/twaldin/hone-a-drone) and the post on `hone v2 vs autoresearch` from a few days ago is [here](https://tim.waldin.net/2026-05-04-hone-v2-vs-autoresearch).

This post is the long write-up: what the project actually is, the 5-module architecture, what hone changed at each stage, the failure modes that ate two days, and what's next.

## what is anduril grand prix

[Anduril is hosting a drone racing competition](https://www.anduril.com/grand-prix/) on top of the lsy_drone_racing simulator. The task is to fly a Crazyflie through a sequence of gates as fast as possible while avoiding obstacles. The sim runs at 500Hz physics, the controller runs at 50Hz, and the arena is `[-2.5, -1.5, 0]` to `[2.5, 1.5, 2.0]` meters. The control mode is `state`: the controller emits a 13-float vector `[pos(3), vel(3), acc(3), yaw, rates(3)]` and an onboard Mellinger does the actual rotor mixing.

There are 4 difficulty levels:

| level | inertial random | gate/obstacle random | track random | weight |
|------:|:----------------|:---------------------|:-------------|-------:|
| 0     | no              | no                   | no           | 1.0    |
| 1     | yes             | no                   | no           | 1.5    |
| 2     | yes             | yes                  | no           | 2.0    |
| 3     | yes             | yes                  | yes          | 3.0    |

The score formula per rollout is `1 + 10/lap_time` if completed, `0.5*(gates_passed/n_gates)` if crashed, and `gates_passed/n_gates` if it timed out. Level scores get averaged across seeds, then weighted-summed. Level 3 dominates because it's the only level that actually tests generalization.

## the 5-module architecture

I rewrote the planner from a single file into 5 modules so hone can change one thing at a time without breaking the loader contract. The hone harness loads `controllers/planner.py` via `importlib`, so as long as the `Planner` class signature stays intact, anything else is fair game.

```
controllers/
├── planner.py          ← trajectory logic (the hone target)
├── state_estimator.py  ← raw obs → filtered pose
├── gate_detector.py    ← parses gates_pos/quat from obs
├── world_model.py      ← fuses gates + estimate into world frame
└── attitude_ctrl.py    ← assembles the 13-float action vector
```

This split matters because the hone mutator only sees what the playbook tells it to see. By making `planner.py` the only file under mutation, the search space stays small enough that 100 iterations actually explores it. If hone could rewrite `attitude_ctrl.py`, it would spend most of its budget breaking the action shape and getting zero scores.

The planner is min-snap inspired but pragmatic: a cubic spline through carefully chosen waypoints, parameterized by arc-length at a constant cruise speed. The waypoint pattern is `start → liftoff → (approach, center, exit) per gate`. Approach and exit waypoints are placed along the gate normal (the gate's local x-axis, picked sign-aligned with track flow). If an approach or exit waypoint lands inside an obstacle's xy bubble, it gets nudged perpendicular to the normal.

## the seed controller

The seed controller (`controllers/planner.py` as committed) has these defaults:

```python
CRUISE_SPEED         = 1.5   # m/s along path
MAX_SPEED            = 2.5   # m/s clamp
APPROACH_DIST        = 0.5   # m before gate, along normal
EXIT_DIST            = 0.5   # m after gate, along exit
LIFTOFF_FRAC         = 0.5
MIN_SEGMENT_TIME     = 0.5   # s
OBSTACLE_RADIUS      = 0.2
OBSTACLE_AVOID_OFFSET = 0.35
```

Out of the box this clears all 4 gates on level 0 with a lap time around 7.86s and aggregate score 1.0293. It also crashes a non-trivial fraction of level 3 seeds because the spline overshoots between sparse waypoints. That's the headroom hone gets to find.

Score breakdown for the seed (level 0, single seed):
- 4/4 gates, 7.86s lap, no crash → `1 + 10/7.86 = 2.272`. The aggregate of 1.0293 reflects the weighted L0/L1/L2/L3 average where L3 was eating partial credit only.

## one full hone run

The run was `harness:pi:openai-codex/gpt-5.5`, budget 100, grader `./grader.sh` (which is `run_parallel.py` with `--levels 0 1 2 3 --seeds-per-level 5 --timeout 35`).

Score trajectory across the 100 iterations (frontier-best at each milestone):

| iter | score   | parent | what changed                                          |
|-----:|--------:|-------:|:------------------------------------------------------|
|   0  | 1.0293  | seed   | starting controller                                   |
|  10  | 1.0521  | 0      | tightened APPROACH_DIST and EXIT_DIST                 |
|  25  | 1.0729  | 10     | per-gate flow_dir using next gate (better turns)      |
|  40  | 1.0834  | 25     | obstacle nudge offset bumped to ~0.4m                 |
|  60  | 1.0915  | 40     | added intermediate waypoint validation                |
|  80  | 1.0966  | 60     | dense spline sampling for OOB detection               |
|  92  | 1.0968  | 80     | minor tuning of CRUISE_SPEED                          |
|  97  | 1.0970  | 92     | best frontier candidate                               |
| 100  | 1.0970  |  -     | run ended, iter 100 regressed (-0.06)                 |

The last iteration (100) was a `-0.06` regression, which is normal. Hone's frontier keeps the best parent regardless. The final best was iter 97 at score `1.0970391226018743`.

That's a 6.6% absolute aggregate score gain. The bigger story is in the per-level breakdown though. By iter 97 the level 3 generalization stopped crashing on most seeds, which is what the level 3 weight of 3.0 was rewarding.

## what gepa actually changed in the planner

The mutations that stuck fall into four buckets. I went and diff'd a few of the high-utility iterations against the seed to confirm.

**1. parameter tuning.** Mostly small changes:
- `CRUISE_SPEED`: 1.5 → 1.65 → 1.55 (the optimum is just above the seed)
- `APPROACH_DIST`: 0.5 → 0.55 (clears the gate frame thickness with margin)
- `EXIT_DIST`: 0.5 → 0.45 (shorter exit avoids U-turn overshoot)
- `OBSTACLE_RADIUS`: 0.2 → 0.25 (more conservative near obstacles)

**2. flow direction logic.** The seed picks gate flow direction as "from previous waypoint toward next gate". A few iterations tried averaging that with the previous-gate-to-current-gate direction. The averaged version generalized better on level 3 because it produced gentler heading transitions.

**3. spline boundary conditions.** The seed uses `bc_type="not-a-knot"`. Several iterations tried `clamped` (zero velocity at endpoints) and got punished hard, which is exactly what `rule-003` in the ACE rule list later codified.

**4. waypoint density.** The biggest single jump (from ~1.083 to ~1.092) came from inserting an extra midpoint between gate exit and next gate approach when the segment distance was over 1.0m. That kills the spline overshoot that was crashing level 3 seeds.

What hone did **not** do: it never touched `attitude_ctrl.py`, never tried to add a neural net, never tried to load weights, never reformulated the class. The playbook says don't, and the mutator obeyed.

## the rule-discovery system (ace)

`hone observer` watches the run and writes auto-derived rules into the `<!-- managed:ace -->` block in CLAUDE.md. After this run there are 4 rules, all about avoiding out-of-bounds crashes:

| rule | what it codifies                                                            |
|-----:|:----------------------------------------------------------------------------|
| 001  | don't replace dynamic state-vector slots with hardcoded literals            |
| 002  | clipping discrete waypoints doesn't bound the spline between them           |
| 003  | zero-velocity BCs cause lateral bowing on sparse waypoints (level 2+)       |
| 004  | OOB fixes belong in the planner, not in `attitude_ctrl.py` clipping         |

Rule 004 is the one I actually appreciated. I'd considered exactly the failure pattern it describes (clip the setpoint at ±2.0m instead of ±2.5m, expecting the drone to follow). The drone keeps moving along its momentum-driven trajectory regardless, so clipping the setpoint just distorts the command without helping. The rule means future hone iterations on this repo won't waste budget rediscovering that.

## hone vs autoresearch on the same task

I ran the [hone-vs-autoresearch experiment](https://github.com/twaldin/hone-a-drone/tree/main/experiments/hone-vs-autoresearch) a few days ago. Same seed, same grader, same budget, two different mutator strategies:

- **hone**: pareto frontier reflection, mutator picks parent + writes child
- **autoresearch (Karpathy-style)**: keep current best, propose change, accept if better

The numbers: hone ended at score 1.0970, autoresearch ended at 1.0834. On the held-out test seeds (different random seed range than training), hone's controller stayed at 1.0921 and autoresearch dropped to 1.0612. Autoresearch overfit to the training seeds because it has no frontier to fall back on when a high-train-score candidate generalizes poorly.

Full breakdown is in the older post; the takeaway is that the frontier matters more than the mutator on small-budget runs.

## failure modes and dead ends

**The 3-challenge run I wasted two days on.** Early on I trained on only levels 0-2 to save grader time (~40s per iteration instead of ~75s). The resulting controller scored great on its training set and crashed catastrophically on level 3 seeds. The L3 weight of 3.0 in the aggregate is there for a reason. Cutting it makes the score completely uncorrelated with what you actually care about.

**The bc_type=clamped detour.** Iter ~30 to iter ~45 kept proposing zero-velocity boundary conditions. Each one looked plausible (the spline starts and ends still, what's wrong with that?). The answer is rule-003: on sparse waypoints, the spline bows out laterally to satisfy the zero-derivative constraint, and the drone leaves the arena. I didn't catch this until I instrumented per-seed crash reasons.

**Stdout pollution.** Twice the planner started printing to stderr from inside the hot loop. The grader captures stderr and the next iteration's mutator sees it as "trace summary" feedback. The signal/noise ratio on the trace summary tanked, hone got confused, and the frontier stalled. Now there's an explicit "do not print/log" line in the playbook and it hasn't happened since.

**Codex/gpt-5.5 over the OpenAI API.** The mutator costs were modest because most iterations are short single-file diffs. Total spend for the 100-iter run was around $4.20. (Earlier runs with sonnet via the claude code CLI on my Max sub had no API billing at all but ran slower in wall-clock terms.)

## visuals

I don't have demo renders saved locally for this run, the race renders only exist transiently when the sim runs with `render = true`. The upstream lsy_drone_racing repo's `docs/img/race.gif` shows roughly what the trajectory looks like when it works. Adding a "save mp4 of the best iteration" hook to `run_rollout.py` is on the list for the next pass.

## what's next

A few directions I want to explore:

- **larger budget on level 3 only.** The training mix is L0+L1+L2+L3 right now and it's wasteful. L0 is solved at iter 0. A level-3-only training mix with budget 300 should push the frontier further on the actually-hard distribution.
- **multi-file mutation.** Right now hone only sees `planner.py`. Letting it also touch `world_model.py` (for per-gate heading smoothing) is a logical next step. The risk is breaking the import contract; the playbook would need to expand to cover both files.
- **swap the mutator mid-run.** The ACE rule list keeps growing. After ~50 rules the playbook will be too long for any one mutator. Splitting into "structural mutator" and "parameter-tuning mutator" with different rule subsets is probably necessary.
- **upload the actual flight logs.** The `runs/` directory has per-rollout JSON for every iteration but I haven't published them. Worth doing for reproducibility.

The repo is at [github.com/twaldin/hone-a-drone](https://github.com/twaldin/hone-a-drone) and the run logs for this post are in `.hone/run-20260501-074311-a2c768/`.
