# drone-pi55-round3-fair hone mutator playbook

Goal: improve the drone racing controller from the same Round 2 H05 validation-winner seed used by autoresearch lanes.

Editable scope in the candidate directory:
- `planner.py`
- `world_model.py`
- `state_estimator.py`
- `gate_detector.py`
- `attitude_ctrl.py`
- `baseline.py` only if necessary

Do not edit scorer/evaluation substrate. In this hone candidate directory those files are not present; if you see or create evaluation scripts, remove/revert them.

Controller contract:
- Preserve module-level `Planner` class in `planner.py`.
- `Planner.__init__(obs, info, config)`, `compute_target(obs, info, t)`, and `step(...)` must remain compatible.
- `compute_target` returns exactly 13 float-ish values: `[x,y,z,vx,vy,vz,ax,ay,az,yaw,roll_rate,pitch_rate,yaw_rate]`.
- Keep `compute_target` fast and deterministic. No logging from controller methods.

Round 3 information-matched context:
- All lanes start from Round 2 heldout winner H05, validation aggregate `1.0026100374804507` on seeds 31-40.
- Round 3 train split is seeds 41-50; heldout validation is seeds 51-60.
- Round 2 showed high train score can overfit badly: AR04/AR05 got ~1.148 train but validated below 0.89.
- H05 won by transfer/robustness, not train-best. Prefer robust L0/L1/L2 transfer over narrow train gains.
- L3 remains mostly unsolved; do not destroy L0/L1/L2 chasing L3 unless scorer evidence is strong.

Mutation style:
- Make one coherent edit per iteration, not a giant rewrite.
- Use scorer traces, submetrics, and recent attempts to avoid repeating bad changes.
- If changing constants, keep the diff obvious and localized.
- If changing logic, preserve the seed controller's successful behavior.
- Do not hardcode seed numbers, validation tracks, or scorer-specific artifacts.
