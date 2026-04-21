"""World model stub — passes through detector output during proxy development.

Real implementation: fuses gate detector output with VIO state estimate to
maintain a consistent map of gate positions in world frame across occlusions.
Not implemented until DCL sim ships in May.
"""
from __future__ import annotations
import numpy as np


class WorldModel:
    def __init__(self, obs: dict, info: dict, config) -> None:
        pass

    def update(self, detection: dict, estimate: dict) -> dict:
        """Return world-frame gate positions (pass-through for now)."""
        return detection
