from __future__ import annotations

import numpy as np


class ScriptedSwingController:
    """Time-to-arrival triggered swing controller for baseline validation.

    Holds near `prep_angle` (a light proportional correction, not a hard
    teleport -- see the separate held_pose diagnostic for that) until the
    ball's predicted remaining time to the target x-coordinate drops to
    `actuator_correction_time_s` (the measured time to swing from prep to the
    interception alignment angle; see docs/design/ENV-001-calibration.json),
    then swings at full torque. Uses only the current-step observation, never
    the hidden planned-arrival time or RNG state.
    """

    def __init__(
        self,
        prep_angle: float = 0.50,
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
        swing_angle = float(obs[6])
        predicted_time_to_target = float(obs[8])

        approaching = ball_vx > 0.0
        if (
            not self._swinging
            and approaching
            and 0.0 < predicted_time_to_target <= self.actuator_correction_time_s
        ):
            self._swinging = True

        if self._swinging:
            action = self.swing_ctrl
        else:
            action = self.hold_gain * (self.prep_angle - swing_angle)
        return np.array([np.clip(action, -1.0, 1.0)], dtype=np.float32)


class ConstantAngleController:
    """Actively drives toward and holds one fixed target angle (proportional control).

    This is a real actuated policy (unlike the held_pose diagnostic, which
    teleports qpos directly) -- it exercises the actuator the same way any
    other controller does. Used for the `best_constant_angle` baseline: a
    dev-seed-selected fixed angle, to show whether a single static setpoint
    already solves the fixed-target task.
    """

    def __init__(self, target_angle: float, gain: float = 1.0) -> None:
        self.target_angle = target_angle
        self.gain = gain

    def reset(self) -> None:
        pass

    def act(self, obs: np.ndarray) -> np.ndarray:
        swing_angle = float(obs[6])
        action = self.gain * (self.target_angle - swing_angle)
        return np.array([np.clip(action, -1.0, 1.0)], dtype=np.float32)
