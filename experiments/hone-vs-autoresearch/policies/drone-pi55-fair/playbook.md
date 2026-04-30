# drone-pi55-fair hone mutator playbook

Goal: improve the drone racing controller score from the exact same seed used by the long autoresearch lanes.

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

Known strong baseline idea to preserve unless traces demand otherwise:
- PCHIP path interpolation.
- Active observed-gate correction blend around radius `1.8`.
- Cruise near `1.59` from the seed.

Promising search directions from prior evidence:
- Asymmetric gate staging: approach around `0.5`, exit around `0.6`.
- Slightly higher liftoff / vertical staging (`LIFTOFF_FRAC` around `0.55`).
- Speed/exit/min-segment fine tuning around train-best variants, but validate via scorer feedback not guesswork.
- Smaller obstacle avoidance bubble/offset can lift L2, but may hurt validation.
- L3 stacked gates remain unresolved; prefer small robust changes that improve L3 failure mode without destroying L0/L1/L2.

Mutation style:
- Make one coherent edit per iteration, not a giant rewrite.
- Use the previous trace summary and recent attempts to avoid repeating bad changes.
- If changing constants, keep the diff obvious and localized.
- If changing logic, preserve the seed controller's successful L0/L1 behavior.
- Do not hardcode seed numbers or validation tracks.
