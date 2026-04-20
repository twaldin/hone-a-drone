"""Fixed low-level attitude control interface.

Wraps lsy_drone_racing's Mellinger controller (MIT, drone-controllers package)
which runs inside crazyflow's sim. This module assembles the 13-component
state command vector; the sim's onboard Mellinger controller handles SE(3) tracking.

Not a hone rotation target — kept fixed while planner.py is evolved.
"""
from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


def make_state_command(
    pos: NDArray[np.floating],
    vel: NDArray[np.floating] | None = None,
    acc: NDArray[np.floating] | None = None,
    yaw: float = 0.0,
    angular_rates: NDArray[np.floating] | None = None,
) -> NDArray[np.float32]:
    """Assemble a 13-component state command for the Mellinger controller.

    Returns [x, y, z, vx, vy, vz, ax, ay, az, yaw, roll_rate, pitch_rate, yaw_rate].
    Uses a position-and-yaw command by default; feedforward terms are kept at
    zero because the sim's onboard controller tracks those more reliably.
    """
    _pos = np.asarray(pos, dtype=np.float32).reshape(3)
    _zeros = np.zeros(3, dtype=np.float32)
    return np.array([*_pos, *_zeros, *_zeros, np.float32(yaw), *_zeros], dtype=np.float32)
