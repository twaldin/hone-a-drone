"""Single-rollout runner. Prints ONE JSON line to stdout.

Usage:
    python run_rollout.py --planner <path> --level <0-3> --seed <int> [--timeout <s>]

Hard-fails (non-zero exit) on import errors from planner or lsy_drone_racing.
The grader treats non-zero exit as score=0 via hone's GraderResult contract.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np

SIM_PATH = str(Path(__file__).parent / "sim" / "lsy_drone_racing")
PROJECT_ROOT = str(Path(__file__).parent)


def _load_planner_cls(path: str):
    # Force SourceFileLoader so non-.py suffixes (e.g., hone's /tmp/*.prompt) work.
    from importlib.machinery import SourceFileLoader

    loader = SourceFileLoader("_planner_candidate", path)
    spec = importlib.util.spec_from_loader("_planner_candidate", loader)
    if spec is None:
        print(json.dumps({"error": "spec_none", "path": path}), flush=True)
        sys.exit(1)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as e:
        print(json.dumps({"error": f"planner_import_error: {e}", "path": path}), flush=True)
        sys.exit(1)
    if not hasattr(mod, "Planner"):
        print(json.dumps({"error": "no_Planner_class", "path": path}), flush=True)
        sys.exit(1)
    return mod.Planner


def _crash_reason(obs: dict, pos_low: np.ndarray, pos_high: np.ndarray, truncated: bool) -> str:
    if obs["target_gate"] == -1:
        return "completed"
    if truncated:
        return "timeout"
    pos = np.array(obs["pos"])
    if np.any(pos < pos_low) or np.any(pos > pos_high):
        return "out_of_bounds"
    return "collision"


def _approach_angle(vel: np.ndarray, gate_quat: np.ndarray) -> float:
    from scipy.spatial.transform import Rotation

    speed = float(np.linalg.norm(vel))
    if speed < 0.05:
        return float("nan")
    vel_unit = vel / speed
    rot = Rotation.from_quat(gate_quat)
    gate_normal = rot.apply([1.0, 0.0, 0.0])
    cos_ang = float(np.clip(abs(np.dot(vel_unit, gate_normal)), 0.0, 1.0))
    return float(np.degrees(np.arccos(cos_ang)))


def run(planner_path: str, level: int, seed: int, timeout_secs: float) -> dict:
    if SIM_PATH not in sys.path:
        sys.path.insert(0, SIM_PATH)

    try:
        import gymnasium
        from gymnasium.wrappers.jax_to_numpy import JaxToNumpy
        from lsy_drone_racing.utils import load_config
    except ImportError as e:
        print(json.dumps({"error": f"sim_import_error: {e}"}), flush=True)
        sys.exit(1)

    PlannerCls = _load_planner_cls(planner_path)

    config_path = Path(SIM_PATH) / "config" / f"level{level}.toml"
    config = load_config(config_path)
    config.sim.render = False
    config.env.seed = seed

    env = gymnasium.make(
        config.env.id,
        freq=config.env.freq,
        sim_config=config.sim,
        sensor_range=config.env.sensor_range,
        control_mode=config.env.control_mode,
        track=config.env.track,
        disturbances=config.env.get("disturbances"),
        randomizations=config.env.get("randomizations"),
        seed=config.env.seed,
    )
    env = JaxToNumpy(env)

    n_gates = len(config.env.track.gates)
    limits = config.env.track.safety_limits
    pos_low = np.array(limits.pos_limit_low)
    pos_high = np.array(limits.pos_limit_high)

    obs, info = env.reset(seed=seed)

    try:
        planner = PlannerCls(obs, info, config)
    except Exception as e:
        env.close()
        print(json.dumps({"error": f"planner_init_error: {e}", "level": level, "seed": seed}), flush=True)
        sys.exit(1)

    freq = config.env.freq
    max_steps = int(timeout_secs * freq)
    gate_times: list[float] = []
    approach_angles: list[float] = []
    velocities: list[float] = []
    loop_latencies: list[float] = []
    prev_gate = int(obs["target_gate"])
    crash_reason = "dnf"

    for i in range(max_steps):
        t = i / freq

        t0 = time.perf_counter()
        action = planner.compute_target(obs, info, t)
        loop_latencies.append((time.perf_counter() - t0) * 1000.0)

        obs, reward, terminated, truncated, info = env.step(action)

        try:
            planner.step(obs, info, action, float(reward), bool(terminated), bool(truncated))
        except Exception:
            pass

        velocities.append(float(np.linalg.norm(obs["vel"])))

        curr_gate = int(obs["target_gate"])
        if curr_gate != prev_gate:
            gate_idx = n_gates - 1 if curr_gate == -1 else prev_gate
            if 0 <= gate_idx < n_gates:
                gate_times.append(round(t, 3))
                ang = _approach_angle(np.array(obs["vel"]), np.array(obs["gates_quat"][gate_idx]))
                approach_angles.append(round(ang, 2) if not np.isnan(ang) else None)
            prev_gate = curr_gate

        if terminated or truncated:
            crash_reason = _crash_reason(obs, pos_low, pos_high, bool(truncated))
            break

    env.close()

    lap_time = round((min(i + 1, max_steps)) / freq, 3)
    gates_passed = n_gates if obs["target_gate"] == -1 else int(obs["target_gate"])
    crashed = crash_reason not in ("completed", "timeout", "dnf")

    lat = np.array(loop_latencies) if loop_latencies else np.array([0.0])
    result = {
        "level": level,
        "seed": seed,
        "gates_passed": gates_passed,
        "n_gates": n_gates,
        "lap_time": lap_time,
        "crashed": crashed,
        "crash_reason": crash_reason,
        "max_velocity": round(float(max(velocities)) if velocities else 0.0, 3),
        "gate_times": gate_times,
        "approach_angles": [a for a in approach_angles if a is not None],
        "loop_latency_p50": round(float(np.percentile(lat, 50)), 3),
        "loop_latency_p99": round(float(np.percentile(lat, 99)), 3),
    }
    print(json.dumps(result), flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run one drone racing episode.")
    parser.add_argument("--planner", required=True, help="Path to planner.py (may be a temp file)")
    parser.add_argument("--level", type=int, default=0, choices=[0, 1, 2, 3])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--timeout", type=float, default=35.0, help="Max episode wall seconds")
    args = parser.parse_args()
    run(args.planner, args.level, args.seed, args.timeout)
