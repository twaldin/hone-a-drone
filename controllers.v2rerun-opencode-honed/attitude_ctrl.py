"""Fixed low-level attitude control interface.

Wraps lsy_drone_racing's Mellinger controller (MIT, drone-controllers package)
which runs inside crazyflow's sim. This module assembles the 13-component
state command vector; the sim's onboard Mellinger controller handles SE(3) tracking.

Not a hone rotation target — kept fixed while planner.py is evolved.
"""
from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


def _as_vec3(value: NDArray[np.floating] | None) -> NDArray[np.float32]:
    if value is None:
        return np.zeros(3, dtype=np.float32)

    vec = np.asarray(value, dtype=np.float32).reshape(-1)
    if vec.size != 3:
        raise ValueError(f"Expected a 3-vector, got shape {np.shape(value)!r}")
    return np.nan_to_num(vec, nan=0.0, posinf=0.0, neginf=0.0)


def make_state_command(
    pos: NDArray[np.floating],
    vel: NDArray[np.floating] | None = None,
    acc: NDArray[np.floating] | None = None,
    yaw: float = 0.0,
    angular_rates: NDArray[np.floating] | None = None,
) -> NDArray[np.float32]:
    """Assemble a 13-component state command for the Mellinger controller.

    Returns [x, y, z, vx, vy, vz, ax, ay, az, yaw, roll_rate, pitch_rate, yaw_rate].
    Zero-fills optional components when not provided.
    """
    _pos = _as_vec3(pos)
    _vel = _as_vec3(vel)
    _acc = _as_vec3(acc)
    _rates = _as_vec3(angular_rates)
    _yaw = float(np.nan_to_num(yaw, nan=0.0, posinf=0.0, neginf=0.0))
    return np.array([*_pos, *_vel, *_acc, _yaw, *_rates], dtype=np.float32)
