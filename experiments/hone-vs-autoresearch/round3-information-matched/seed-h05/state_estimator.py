"""State estimator stub — passes through sim ground-truth during proxy development.

Real implementation: OpenVINS (Apache 2.0) visual-inertial odometry.
Not implemented until DCL sim ships in May.
"""
from __future__ import annotations
import numpy as np
from numpy.typing import NDArray


class StateEstimator:
    def __init__(self, obs: dict, info: dict, config) -> None:
        pass

    def estimate(self, obs: dict) -> dict:
        """Return drone pose and velocity from sim ground-truth."""
        return {
            "pos": np.array(obs["pos"]),
            "vel": np.array(obs["vel"]),
            "quat": np.array(obs["quat"]),
            "ang_vel": np.array(obs["ang_vel"]),
        }
