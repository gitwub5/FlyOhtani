from __future__ import annotations

import numpy as np


class ScriptedSwingController:
    """Distance-triggered swing controller for baseline validation."""

    def __init__(
        self,
        trigger_distance: float = 0.5,
        reset_angle: float = -0.65,
        swing_gain: float = 1.0,
    ) -> None:
        self.trigger_distance = trigger_distance
        self.reset_angle = reset_angle
        self.swing_gain = swing_gain

    def reset(self) -> None:
        pass

    def act(self, obs: np.ndarray) -> np.ndarray:
        ball_x = float(obs[0])
        ball_vx = float(obs[3])
        swing_angle = float(obs[6])

        approaching = ball_vx > 0.0
        distance_to_zone = abs(0.08 - ball_x)
        if approaching and distance_to_zone < self.trigger_distance:
            action = self.swing_gain
        else:
            action = -0.25 if swing_angle > self.reset_angle else 0.0
        return np.array([np.clip(action, -1.0, 1.0)], dtype=np.float32)
