from __future__ import annotations

import numpy as np
from scipy.interpolate import CubicSpline
from scipy.spatial.transform import Rotation

CRUISE_SPEED: float = 2.2
MAX_SPEED: float = 3.0
APPROACH_DIST: float = 0.5
EXIT_DIST: float = 0.6
LIFTOFF_FRAC: float = 0.5
MIN_SEGMENT_TIME: float = 0.25
OBSTACLE_RADIUS: float = 0.2
OBSTACLE_AVOID_OFFSET: float = 0.35
LOOKAHEAD_TIME: float = 0.35
N_CACHED: int = 600


class Planner:
    def __init__(self, obs: dict, info: dict, config) -> None:
        self._freq: float = config.env.freq
        self._n_gates: int = len(config.env.track.gates)
        self._finished: bool = False

        gates_pos = np.array(obs["gates_pos"], dtype=float)
        gates_quat = np.array(obs["gates_quat"], dtype=float)
        obstacles_pos = np.array(obs["obstacles_pos"], dtype=float)
        start_pos = np.array(obs["pos"], dtype=float)

        wpts = _build_waypoints(start_pos, gates_pos, gates_quat, obstacles_pos, do_liftoff=True)
        times = _assign_times(wpts)
        self._spline = _fit_spline(wpts, times)
        self._duration: float = float(times[-1])

        self._ts = np.linspace(0.0, self._duration, N_CACHED)
        self._cached_pts = self._spline(self._ts)
        self._t_track: float = 0.0

        self._last_target_gate: int = int(obs["target_gate"])
        self._need_replan: bool = False

    def _do_replan(self, obs: dict) -> None:
        target_gate = int(obs["target_gate"])
        if target_gate < 0:
            return

        gates_pos = np.array(obs["gates_pos"], dtype=float)
        gates_quat = np.array(obs["gates_quat"], dtype=float)
        obstacles_pos = np.array(obs["obstacles_pos"], dtype=float)
        pos_cur = np.array(obs["pos"], dtype=float)

        remaining_pos = gates_pos[target_gate:]
        remaining_quat = gates_quat[target_gate:]

        if len(remaining_pos) == 0:
            return

        wpts = _build_waypoints(pos_cur, remaining_pos, remaining_quat, obstacles_pos, do_liftoff=False)
        times = _assign_times(wpts)
        self._spline = _fit_spline(wpts, times)
        self._duration = float(times[-1])
        self._ts = np.linspace(0.0, self._duration, N_CACHED)
        self._cached_pts = self._spline(self._ts)
        self._t_track = 0.0

    def compute_target(self, obs: dict, info: dict | None, t: float) -> np.ndarray:
        if self._need_replan:
            self._do_replan(obs)
            self._need_replan = False

        pos_cur = np.array(obs["pos"], dtype=float)

        search_lo = max(0.0, self._t_track - 0.2)
        search_hi = min(self._duration, self._t_track + 2.5)

        i_lo = int(np.searchsorted(self._ts, search_lo))
        i_hi = int(np.searchsorted(self._ts, search_hi)) + 1
        i_hi = min(i_hi, len(self._ts))

        if i_lo < i_hi:
            window = self._cached_pts[i_lo:i_hi]
            dists = np.sum((window - pos_cur) ** 2, axis=1)
            best = int(np.argmin(dists))
            self._t_track = float(self._ts[i_lo + best])

        t_target = min(self._t_track + LOOKAHEAD_TIME, self._duration)
        pos = self._spline(t_target)

        if self._t_track >= self._duration - 0.15:
            self._finished = True

        return np.array([*pos, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)

    def step(
        self,
        obs: dict,
        info: dict | None,
        action: np.ndarray,
        reward: float,
        terminated: bool,
        truncated: bool,
    ) -> None:
        target_gate = int(obs["target_gate"])
        if target_gate != self._last_target_gate and target_gate >= 0:
            self._last_target_gate = target_gate
            self._need_replan = True

    @property
    def is_finished(self) -> bool:
        return self._finished


def _gate_dir(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    d = b - a
    n = float(np.linalg.norm(d))
    return d / n if n > 1e-3 else np.array([1.0, 0.0, 0.0])


def _gate_normal_aligned(quat: np.ndarray, flow_dir: np.ndarray) -> np.ndarray:
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
    do_liftoff: bool = True,
) -> np.ndarray:
    wpts: list[np.ndarray] = [start.copy()]

    if do_liftoff and len(gates_pos) > 0:
        g0 = gates_pos[0]
        approach0_dir = _gate_dir(start, g0)
        liftoff = start.copy()
        liftoff[2] = start[2] + LIFTOFF_FRAC * (g0[2] - start[2] + 0.3)
        liftoff[:2] = start[:2] + 0.2 * approach0_dir[:2] * np.linalg.norm(g0[:2] - start[:2])
        wpts.append(liftoff)

    prev = wpts[-1].copy()
    n = len(gates_pos)
    for i, (pos, quat) in enumerate(zip(gates_pos, gates_quat)):
        next_point = gates_pos[i + 1] if i + 1 < n else (pos + (pos - prev))
        flow_dir = next_point - prev
        n_flow = float(np.linalg.norm(flow_dir))
        flow_dir = flow_dir / n_flow if n_flow > 1e-3 else np.array([1.0, 0.0, 0.0])

        normal = _gate_normal_aligned(quat, flow_dir)

        approach_wpt = pos - APPROACH_DIST * normal
        exit_wpt = pos + EXIT_DIST * normal

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
        if dist < OBSTACLE_AVOID_OFFSET:
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
    dists = np.linalg.norm(np.diff(wpts, axis=0), axis=1)
    seg_times = np.maximum(dists / CRUISE_SPEED, MIN_SEGMENT_TIME)
    return np.concatenate([[0.0], np.cumsum(seg_times)])


def _fit_spline(wpts: np.ndarray, times: np.ndarray) -> CubicSpline:
    return CubicSpline(times, wpts, bc_type="not-a-knot")