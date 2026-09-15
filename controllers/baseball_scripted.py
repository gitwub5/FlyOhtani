from __future__ import annotations

import numpy as np


class BaseballScriptedSwing:
    """Time-to-arrival triggered bat swing for ENV-002 B0 baseline validation.

    Unlike envs/fly_batter_env.py's limb, the bat's horizontal swing (about a
    vertical hinge axis) is not torqued by gravity -- zero_torque holds
    prep_angle on its own (see docs/records/VALIDATION_LOG.md). The prep-hold
    correction here is a light safety margin, not a drift compensator.
    """

    def __init__(
        self,
        prep_angle: float = 1.0,
        actuator_correction_time_s: float = 0.30,
        hold_gain: float = 0.5,
        swing_ctrl: float = -1.0,
    ) -> None:
        self.prep_angle = prep_angle
        self.actuator_correction_time_s = actuator_correction_time_s
        self.hold_gain = hold_gain
        self.swing_ctrl = swing_ctrl
        self._swinging = False

    def reset(self) -> None:
        self._swinging = False

    def act(self, obs: np.ndarray) -> np.ndarray:
        ball_vx = float(obs[3])
        bat_angle = float(obs[6])
        predicted_time_to_target = float(obs[8])

        approaching = ball_vx < 0.0  # ball travels -x in ENV-002's coordinates
        if (
            not self._swinging
            and approaching
            and 0.0 < predicted_time_to_target <= self.actuator_correction_time_s
        ):
            self._swinging = True

        if self._swinging:
            action = self.swing_ctrl
        else:
            action = self.hold_gain * (self.prep_angle - bat_angle)
        return np.array([np.clip(action, -1.0, 1.0)], dtype=np.float32)
