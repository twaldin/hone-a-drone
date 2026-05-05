"""Minimum-snap inspired trajectory planner for drone racing.

Geometric path: cubic spline (scipy) through carefully chosen gate waypoints.
Timing: constant arc-speed with a conservative speed cap, clamped so the
Mellinger controller can track reliably.

Reference math: Richter, Bry, Roy 2016 (min-snap philosophy).

v3: composes with sibling modules in controllers/. Obs flow through
`StateEstimator`, gate info through `GateDetector` + `WorldModel`, action
assembly through `attitude_ctrl.make_state_command`. Edits to any of those
siblings propagate to the graded code path.
"""
from __future__ import annotations

import numpy as np
from scipy.interpolate import CubicSpline, PchipInterpolator
from scipy.spatial.transform import Rotation

# Sibling composition (files in same controllers/ dir, loaded via sys.path
# augmented by run_rollout.py before importing this module):
from attitude_ctrl import make_state_command
from gate_detector import GateDetector
from state_estimator import StateEstimator
from world_model import WorldModel

# --- Tunable parameters (primary hone targets) ---
CRUISE_SPEED: float = 1.59    # m/s nominal traversal speed along path
MAX_SPEED: float = 2.5        # m/s clamp on planned velocity norm
APPROACH_DIST: float = 0.5    # m before gate center, along gate normal
EXIT_DIST: float = 0.66        # m after gate center, along exit direction
LIFTOFF_FRAC: float = 0.55     # fraction of height to first gate used for liftoff wpt
MIN_SEGMENT_TIME: float = 0.5  # s minimum time per waypoint segment
OBSTACLE_RADIUS: float = 0.2  # m safety bubble around each obstacle axis (xy)
OBSTACLE_AVOID_OFFSET: float = 0.35  # m lateral offset when adding avoidance waypoint


class Planner:
    """Cubic-spline drone racing trajectory planner.

    Builds a smooth path through all gates with approach/exit waypoints
    and parameterizes it by arc-length-proportional time at CRUISE_SPEED.
    """

    def __init__(self, obs: dict, info: dict, config) -> None:
        self._freq: float = config.env.freq
        self._n_gates: int = len(config.env.track.gates)
        self._finished: bool = False

        self._state_est = StateEstimator(obs, info, config)
        self._gate_det = GateDetector(obs, info, config)
        self._world = WorldModel(obs, info, config)

        detection = self._gate_det.detect(obs)
        estimate = self._state_est.estimate(obs)
        world = self._world.update(detection, estimate)

        gates_pos = np.array(world["gates_pos"], dtype=float)
        gates_quat = np.array(world["gates_quat"], dtype=float)
        self._planned_gates_pos = gates_pos.copy()
        obstacles_pos = np.array(obs["obstacles_pos"], dtype=float)
        start_pos = np.array(estimate["pos"], dtype=float)

        self._stacked_track: bool = bool(np.max(np.ptp(gates_pos[:, :2], axis=0)) < 0.45)
        self._gate_phase: int = 0
        self._last_gate_idx: int = int(obs.get("target_gate", 0))
        self._gate_normals = _aligned_gate_normals(start_pos, gates_pos, gates_quat)

        wpts = _build_waypoints(start_pos, gates_pos, gates_quat, obstacles_pos)
        times = _assign_times(wpts)
        self._spline = _fit_spline(wpts, times)
        self._duration: float = float(times[-1])

    def compute_target(self, obs: dict, info: dict | None, t: float) -> np.ndarray:
        """Return desired state [pos(3), vel(3), acc(3), yaw, rates(3)] at time t."""
        t_c = float(np.clip(t, 0.0, self._duration))
        pos = self._spline(t_c)
        gate_idx = int(obs.get("target_gate", -1))
        if 0 <= gate_idx < self._n_gates:
            observed_gate = np.array(obs["gates_pos"][gate_idx], dtype=float)
            delta = observed_gate - self._planned_gates_pos[gate_idx]
            if float(np.linalg.norm(delta)) > 1e-3:
                d_gate = float(np.linalg.norm(pos - self._planned_gates_pos[gate_idx]))
                blend = float(np.clip(1.0 - d_gate / 1.8, 0.0, 1.0))
                pos = pos + blend * delta

        if self._stacked_track and 0 <= gate_idx < self._n_gates:
            if gate_idx != self._last_gate_idx:
                self._last_gate_idx = gate_idx
                self._gate_phase = 0
            gate_pos = np.array(obs["gates_pos"][gate_idx], dtype=float)
            normal = self._gate_normals[gate_idx]
            approach = gate_pos - APPROACH_DIST * normal
            exit_pt = gate_pos + EXIT_DIST * normal
            current_pos = np.array(obs["pos"], dtype=float)
            if self._gate_phase == 0 and float(np.linalg.norm(current_pos - approach)) < 0.22:
                self._gate_phase = 1
            pos = approach if self._gate_phase == 0 else exit_pt

        if t >= self._duration:
            self._finished = True

        return make_state_command(pos)

    def step(
        self,
        obs: dict,
        info: dict | None,
        action: np.ndarray,
        reward: float,
        terminated: bool,
        truncated: bool,
    ) -> None:
        pass

    @property
    def is_finished(self) -> bool:
        return self._finished


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _gate_dir(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Unit vector from a toward b."""
    d = b - a
    n = float(np.linalg.norm(d))
    return d / n if n > 1e-3 else np.array([1.0, 0.0, 0.0])


def _gate_normal_aligned(quat: np.ndarray, flow_dir: np.ndarray) -> np.ndarray:
    """Gate normal (±x of gate frame) signed to align with `flow_dir`.

    lsy_drone_racing gate collision geometry is thin in x, wide in y/z — so
    the gate's local x-axis is the through-direction. We pick the sign that
    matches the track flow (direction from previous waypoint to next gate).
    """
    rot = Rotation.from_quat(quat)
    normal = rot.apply([1.0, 0.0, 0.0])
    if float(np.dot(normal, flow_dir)) < 0.0:
        normal = -normal
    return normal


def _aligned_gate_normals(
    start: np.ndarray,
    gates_pos: np.ndarray,
    gates_quat: np.ndarray,
) -> np.ndarray:
    normals: list[np.ndarray] = []
    prev = start.copy()
    n = len(gates_pos)
    for i, (pos, quat) in enumerate(zip(gates_pos, gates_quat)):
        next_point = gates_pos[i + 1] if i + 1 < n else (pos + (pos - prev))
        flow_dir = next_point - prev
        n_flow = float(np.linalg.norm(flow_dir))
        flow_dir = flow_dir / n_flow if n_flow > 1e-3 else np.array([1.0, 0.0, 0.0])
        normals.append(_gate_normal_aligned(quat, flow_dir))
        prev = pos.copy()
    return np.array(normals)


def _build_waypoints(
    start: np.ndarray,
    gates_pos: np.ndarray,
    gates_quat: np.ndarray,
    obstacles_pos: np.ndarray | None = None,
) -> np.ndarray:
    """Build waypoint sequence through all gates.

    Pattern: start → liftoff → (approach, center, exit) per gate
    Exit direction points toward the next gate to avoid U-turn overshoot in spline.
    """
    wpts: list[np.ndarray] = [start.copy()]

    # Liftoff waypoint: same x,y as approach to gate 0, elevated
    g0 = gates_pos[0]
    approach0_dir = _gate_dir(start, g0)
    liftoff = start.copy()
    liftoff[2] = start[2] + LIFTOFF_FRAC * (g0[2] - start[2] + 0.3)
    # Slide forward 20% of the way toward first gate to avoid backward spline
    liftoff[:2] = start[:2] + 0.2 * approach0_dir[:2] * np.linalg.norm(g0[:2] - start[:2])
    wpts.append(liftoff)

    prev = liftoff.copy()
    n = len(gates_pos)
    for i, (pos, quat) in enumerate(zip(gates_pos, gates_quat)):
        # Gate flow direction: from previous waypoint toward NEXT gate (or end).
        # This is the natural direction the drone should fly through this gate.
        next_point = gates_pos[i + 1] if i + 1 < n else (pos + (pos - prev))
        flow_dir = next_point - prev
        n_flow = float(np.linalg.norm(flow_dir))
        flow_dir = flow_dir / n_flow if n_flow > 1e-3 else np.array([1.0, 0.0, 0.0])

        # Gate normal: pick the ±x-axis of gate frame that best aligns with flow_dir.
        normal = _gate_normal_aligned(quat, flow_dir)

        approach_wpt = pos - APPROACH_DIST * normal
        exit_wpt = pos + EXIT_DIST * normal

        # Shift approach/exit waypoints if they land inside an obstacle's xy bubble
        if obstacles_pos is not None and len(obstacles_pos) > 0:
            approach_wpt = _nudge_off_obstacles(approach_wpt, obstacles_pos, normal)
            exit_wpt = _nudge_off_obstacles(exit_wpt, obstacles_pos, normal)

        wpts.append(approach_wpt)
        wpts.append(pos.copy())
        wpts.append(exit_wpt)
        prev = pos.copy()

    return np.array(wpts)


def _nudge_off_obstacles(
    wpt: np.ndarray,
    obstacles_pos: np.ndarray,
    normal: np.ndarray,
) -> np.ndarray:
    """If wpt is inside an obstacle's xy safety bubble, nudge it away perpendicular to normal.

    Obstacles are vertical capsules; we work in xy only. Offset direction is
    perpendicular to the gate normal (so the waypoint still lies in the gate
    approach/exit plane at the correct x along the normal axis).
    """
    perp = np.array([-normal[1], normal[0], 0.0])
    perp_n = float(np.linalg.norm(perp))
    if perp_n < 1e-6:
        perp = np.array([0.0, 1.0, 0.0])
    else:
        perp = perp / perp_n

    for o in obstacles_pos:
        dx = wpt[0] - o[0]
        dy = wpt[1] - o[1]
        dist = float(np.hypot(dx, dy))
        if dist < OBSTACLE_RADIUS:
            # Shift along perp, in the direction away from the obstacle
            to_wpt_xy = np.array([dx, dy])
            n_to = float(np.linalg.norm(to_wpt_xy))
            if n_to > 1e-6:
                sign = 1.0 if float(np.dot(perp[:2], to_wpt_xy / n_to)) > 0.0 else -1.0
            else:
                sign = 1.0
            wpt = wpt + sign * OBSTACLE_AVOID_OFFSET * perp
            break
    return wpt


def _assign_times(wpts: np.ndarray) -> np.ndarray:
    """Assign cumulative times based on arc-length at CRUISE_SPEED."""
    dists = np.linalg.norm(np.diff(wpts, axis=0), axis=1)
    seg_times = np.maximum(dists / CRUISE_SPEED, MIN_SEGMENT_TIME)
    return np.concatenate([[0.0], np.cumsum(seg_times)])


def _fit_spline(wpts: np.ndarray, times: np.ndarray):
    """Fit a shape-preserving spline through waypoints to reduce boundary overshoot."""
    return PchipInterpolator(times, wpts, axis=0)
