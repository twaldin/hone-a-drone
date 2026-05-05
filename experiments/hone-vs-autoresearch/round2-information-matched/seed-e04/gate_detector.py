"""Gate detector stub — passes through sim ground-truth during proxy development.

Real implementation: lightweight CNN corner detector (à la arXiv:2012.04512),
trained on UZH-FPV + TII-RATM. Not implemented until DCL sim ships in May.
"""
from __future__ import annotations
import numpy as np
from numpy.typing import NDArray


class GateDetector:
    def __init__(self, obs: dict, info: dict, config) -> None:
        pass

    def detect(self, obs: dict) -> dict:
        """Return gate positions and orientations from sim ground-truth."""
        return {
            "gates_pos": np.array(obs["gates_pos"]),
            "gates_quat": np.array(obs["gates_quat"]),
            "gates_visited": np.array(obs["gates_visited"]),
            "confidence": np.ones(len(obs["gates_pos"])),
        }
