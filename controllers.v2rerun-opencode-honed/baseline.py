"""Baseline controller: assembles Planner + attitude_ctrl into a runnable Controller.

Imports Planner from controllers/planner.py and makes_state_command from
attitude_ctrl.py. Also supports loading a planner from an arbitrary file path
(used by run_rollout.py to evaluate hone-generated candidates from temp files).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from lsy_drone_racing.control import Controller

if TYPE_CHECKING:
    from numpy.typing import NDArray


def _load_planner_cls(path: Path):
    spec = importlib.util.spec_from_file_location("_planner_candidate", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not hasattr(mod, "Planner"):
        raise ImportError(f"No Planner class found in {path}")
    return mod.Planner


class BaselineController(Controller):
    """Orchestrates Planner → attitude_ctrl → Mellinger (sim) pipeline."""

    def __init__(
        self,
        obs: dict,
        info: dict,
        config,
        planner_path: Path | str | None = None,
    ) -> None:
        super().__init__(obs, info, config)
        self._freq: float = config.env.freq
        self._tick: int = 0
        self._finished: bool = False

        if planner_path is not None:
            PlannerCls = _load_planner_cls(Path(planner_path))
        else:
            # Add project root to path so `controllers.planner` is importable
            project_root = str(Path(__file__).parent.parent)
            if project_root not in sys.path:
                sys.path.insert(0, project_root)
            from controllers.planner import Planner as PlannerCls  # noqa: PLC0415

        self._planner = PlannerCls(obs, info, config)

    def compute_control(
        self, obs: dict[str, NDArray[np.floating]], info: dict | None = None
    ) -> NDArray[np.float32]:
        t = self._tick / self._freq
        return self._planner.compute_target(obs, info, t)

    def step_callback(
        self,
        action: NDArray[np.floating],
        obs: dict,
        reward: float,
        terminated: bool,
        truncated: bool,
        info: dict,
    ) -> bool:
        self._planner.step(obs, info, action, reward, terminated, truncated)
        self._tick += 1
        self._finished = getattr(self._planner, "is_finished", False)
        return self._finished

    def episode_callback(self) -> None:
        self._tick = 0
        self._finished = False

    def episode_reset(self) -> None:
        self._tick = 0
        self._finished = False
