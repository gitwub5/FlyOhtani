"""VM-01 V1 (docs/tasks/VISUOMOTOR-PIVOT.md, docs/design/VISION-01.md): the
head-mounted eye camera as a real, separate observation channel from the
env's own ball_pos/ball_vel state -- this module renders frames and reports
the camera's actual extrinsics/intrinsics/timing, and nothing else. It does
NOT read env.data for the ball's state; scripts/vm01_vision_metrics.py's
evaluator does that, in a physically separate module (vision/evaluator.py)
this module never imports.

Uses `camera="eye_cam"`, the real head-mounted camera added to
envs/assets/fly_visual_body.xml as a child of the Head body -- NOT the
world-fixed `fly_pov` camera in envs/assets/baseball_park_kc01a.xml, which
docs/design/VISION-01.md section 3 already flagged as not tracking
torso_yaw and not at the real Head position.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import mujoco
import numpy as np


@dataclass(frozen=True)
class CameraManifest:
    """Real (not assumed) camera extrinsics/intrinsics/timing, read directly
    from the model/data at the moment a frame is captured. Every field here
    is meant to be logged, not guessed -- docs/tasks/VISUOMOTOR-PIVOT.md V1
    item 3's explicit requirement."""

    camera_name: str
    resolution_wh: tuple[int, int]
    fovy_deg: float
    fps_hz: float
    world_pos: tuple[float, float, float]
    world_forward: tuple[float, float, float]
    world_up: tuple[float, float, float]
    world_right: tuple[float, float, float]
    head_body_world_pos: tuple[float, float, float]
    torso_yaw_rad: float
    capture_timestamp_s: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "camera_name": self.camera_name,
            "resolution_wh": list(self.resolution_wh),
            "fovy_deg": self.fovy_deg,
            "fps_hz": self.fps_hz,
            "world_pos": list(self.world_pos),
            "world_forward": list(self.world_forward),
            "world_up": list(self.world_up),
            "world_right": list(self.world_right),
            "head_body_world_pos": list(self.head_body_world_pos),
            "torso_yaw_rad": self.torso_yaw_rad,
            "capture_timestamp_s": self.capture_timestamp_s,
        }


@dataclass
class EyeCamera:
    """Wraps mujoco.Renderer for the `eye_cam` camera. `capture(env)` reads
    frames + a full CameraManifest from whatever env/model/data is passed in
    -- this class holds no simulation state of its own besides the
    renderer, so it can be reused across many episodes/environments without
    silently caching a stale camera pose.
    """

    model: mujoco.MjModel
    width: int = 128
    height: int = 128
    fps_hz: float = 60.0
    camera_name: str = "eye_cam"
    _renderer: mujoco.Renderer = field(init=False, repr=False)
    _cam_id: int = field(init=False, repr=False)
    _head_body_id: int = field(init=False, repr=False)
    _torso_joint_id: int = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._renderer = mujoco.Renderer(self.model, width=self.width, height=self.height)
        self._cam_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_CAMERA, self.camera_name)
        if self._cam_id < 0:
            raise ValueError(f"camera {self.camera_name!r} not found in model -- is fly_visual_body.xml up to date?")
        self._head_body_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, "Head")
        self._torso_joint_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, "torso_yaw")

    @property
    def fovy_deg(self) -> float:
        return float(self.model.cam_fovy[self._cam_id])

    def capture(self, data: mujoco.MjData, grayscale: bool = True) -> tuple[np.ndarray, CameraManifest]:
        """Renders the current `data` state from the eye camera. Caller is
        responsible for having called mujoco.mj_forward(model, data) first
        (this function does not step or forward the simulation -- it is a
        pure read, matching VISION-01's "read-only observation" contract).
        """
        self._renderer.update_scene(data, camera=self.camera_name)
        frame = self._renderer.render()
        if grayscale:
            frame = np.dot(frame[..., :3], [0.299, 0.587, 0.114]).astype(np.uint8)

        cam_pos = data.cam_xpos[self._cam_id].copy()
        cam_mat = data.cam_xmat[self._cam_id].reshape(3, 3)
        forward = -cam_mat[:, 2]
        up = cam_mat[:, 1]
        right = cam_mat[:, 0]
        head_pos = data.xpos[self._head_body_id].copy()
        torso_yaw = float(data.qpos[self.model.jnt_qposadr[self._torso_joint_id]]) if self._torso_joint_id >= 0 else float("nan")

        manifest = CameraManifest(
            camera_name=self.camera_name,
            resolution_wh=(self.width, self.height),
            fovy_deg=self.fovy_deg,
            fps_hz=self.fps_hz,
            world_pos=tuple(cam_pos.tolist()),
            world_forward=tuple(forward.tolist()),
            world_up=tuple(up.tolist()),
            world_right=tuple(right.tolist()),
            head_body_world_pos=tuple(head_pos.tolist()),
            torso_yaw_rad=torso_yaw,
            capture_timestamp_s=float(data.time),
        )
        return frame, manifest

    def close(self) -> None:
        self._renderer.close()
