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
from scipy.interpolate import PchipInterpolator
from scipy.spatial.transform import Rotation

# Sibling composition (files in same controllers/ dir, loaded via sys.path
# augmented by run_rollout.py before importing this module):
from attitude_ctrl import make_state_command
from gate_detector import GateDetector
from state_estimator import StateEstimator
from world_model import WorldModel

# --- Tunable parameters (primary hone targets) ---
CRUISE_SPEED: float = 1.35    # m/s nominal traversal speed along path
MAX_SPEED: float = 2.5        # m/s clamp on planned velocity norm
APPROACH_DIST: float = 0.55   # m before gate center, along gate normal
EXIT_DIST: float = 0.6        # m after gate center, along exit direction
LIFTOFF_FRAC: float = 0.4     # fraction of height to first gate used for liftoff wpt
MIN_SEGMENT_TIME: float = 0.5  # s minimum time per waypoint segment
OBSTACLE_RADIUS: float = 0.2  # m safety bubble around each obstacle axis (xy)
OBSTACLE_AVOID_OFFSET: float = 0.35  # m lateral offset when adding avoidance waypoint
MAX_LIFTOFF_XY_SHIFT: float = 0.18  # m limit on initial xy slide toward first gate
STRAIGHTEN_DIST: float = 0.28  # m extra waypoint after gate before allowing a turn
TURN_SHARP_COS: float = 0.35  # add straightening waypoint when turn is sharper than this
LAST_EXIT_DIST: float = 0.42  # m just enough to clear the final gate frame


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
        obstacles_pos = np.array(obs["obstacles_pos"], dtype=float)
        start_pos = np.array(estimate["pos"], dtype=float)

        wpts = _build_waypoints(start_pos, gates_pos, gates_quat, obstacles_pos)
        times = _assign_times(wpts)
        self._spline = _fit_spline(wpts, times)
        self._duration: float = float(times[-1])

    def compute_target(self, obs: dict, info: dict | None, t: float) -> np.ndarray:
        """Return desired state [pos(3), vel(3), acc(3), yaw, rates(3)] at time t."""
        t_c = float(np.clip(t, 0.0, self._duration))
        pos = self._spline(t_c)

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

    # Liftoff waypoint: mostly vertical, but with a small capped xy bias toward the
    # first gate so the initial spline does not kink into a large lateral sweep.
    g0 = gates_pos[0]
    approach0_dir = _gate_dir(start, g0)
    liftoff = start.copy()
    liftoff[2] = start[2] + LIFTOFF_FRAC * (g0[2] - start[2] + 0.3)
    # Randomized starts are most fragile right after takeoff. Keep liftoff nearly
    # vertical, but allow a small lead-in toward the first gate to reduce the
    # curvature spike between liftoff and the first approach waypoint.
    liftoff[:2] = start[:2] + MAX_LIFTOFF_XY_SHIFT * approach0_dir[:2]
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

        if i + 1 < n:
            next_gate = gates_pos[i + 1]
            gate_spacing = float(np.linalg.norm(next_gate - pos))
        else:
            gate_spacing = float(np.linalg.norm(pos - prev))

        approach_dist = min(APPROACH_DIST, 0.35 * gate_spacing)
        exit_dist = min(EXIT_DIST, 0.4 * gate_spacing)
        if i + 1 == n:
            exit_dist = min(exit_dist, LAST_EXIT_DIST)
        approach_wpt = pos - approach_dist * normal
        exit_wpt = pos + max(exit_dist, 0.41) * normal
        straighten_wpt = None

        if i + 1 < n:
            next_gate = gates_pos[i + 1]
            desired_after_gate = _gate_dir(pos, next_gate)
            turn_cos = float(np.dot(normal, desired_after_gate))
            if turn_cos < TURN_SHARP_COS:
                straighten_dist = min(STRAIGHTEN_DIST, 0.2 * gate_spacing)
                straighten_wpt = pos + max(exit_dist, 0.41) * normal + straighten_dist * normal

        # Shift approach/exit waypoints if they land inside an obstacle's xy bubble
        if obstacles_pos is not None and len(obstacles_pos) > 0:
            approach_wpt = _nudge_off_obstacles(approach_wpt, obstacles_pos, normal)
            exit_wpt = _nudge_off_obstacles(exit_wpt, obstacles_pos, normal)
            if straighten_wpt is not None:
                straighten_wpt = _nudge_off_obstacles(straighten_wpt, obstacles_pos, normal)

        wpts.append(approach_wpt)
        wpts.append(pos.copy())
        wpts.append(exit_wpt)
        if straighten_wpt is not None:
            wpts.append(straighten_wpt)
        prev = straighten_wpt if straighten_wpt is not None else exit_wpt

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


def _fit_spline(wpts: np.ndarray, times: np.ndarray) -> PchipInterpolator:
    """Fit a shape-preserving spline through waypoints.

    Randomized tracks can make unconstrained cubic splines swing wide outside the
    corridor between gates. PCHIP is less smooth but strongly reduces overshoot,
    which improves robustness on level 2/3.
    """
    return PchipInterpolator(times, wpts, axis=0)
