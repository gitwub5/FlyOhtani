"""VM-01 V1: the EVALUATOR-ONLY ground-truth projection (docs/design/
VISION-01.md section 4's "평가(evaluator) 전용" -- "정책 코드 경로와 평가
코드 경로를 물리적으로 분리해 구현한다... 평가자 모듈이 정책 모듈을
import하되 역방향은 금지"). This module DOES read the simulator's true
ball position (env.data) -- that is its entire purpose: computing where
the ball ACTUALLY is in pixel space, to score vision/ball_detector.py and
vision/tracker.py's estimates against.

vision/ball_detector.py, vision/tracker.py, and vision/observation.py must
NEVER import this module (checked by
tests/test_vision_v1.py::test_evaluator_not_imported_by_policy_path).
"""
from __future__ import annotations

from dataclasses import dataclass

import mujoco
import numpy as np


@dataclass(frozen=True)
class GroundTruthProjection:
    visible_in_frame: bool
    pixel_xy: tuple[float, float] | None
    distance_m: float
    behind_camera: bool


def project_world_point(
    world_point: np.ndarray,
    cam_pos: np.ndarray,
    cam_mat: np.ndarray,
    fovy_deg: float,
    width: int,
    height: int,
) -> GroundTruthProjection:
    """Standard pinhole projection using the SAME camera basis convention
    mujoco itself uses (cam_mat's columns are [right, up, backward] in
    world coordinates; forward = -backward). Verified against an actual
    rendered frame in tests/test_vision_v1.py (a bright synthetic marker's
    rendered pixel location matches this function's prediction within a
    few pixels), not trusted from the formula alone."""
    right = cam_mat[:, 0]
    up = cam_mat[:, 1]
    backward = cam_mat[:, 2]
    rel = world_point - cam_pos
    x_cam = float(np.dot(rel, right))
    y_cam = float(np.dot(rel, up))
    z_cam = float(np.dot(rel, backward))  # positive = behind camera
    distance_m = float(np.linalg.norm(rel))

    if z_cam >= 0:
        return GroundTruthProjection(visible_in_frame=False, pixel_xy=None, distance_m=distance_m, behind_camera=True)

    depth_in_front = -z_cam
    f_px = (height / 2.0) / np.tan(np.radians(fovy_deg) / 2.0)
    u = width / 2.0 + f_px * (x_cam / depth_in_front)
    v = height / 2.0 - f_px * (y_cam / depth_in_front)
    visible = (0.0 <= u < width) and (0.0 <= v < height)
    return GroundTruthProjection(visible_in_frame=visible, pixel_xy=(u, v), distance_m=distance_m, behind_camera=False)


def ball_ground_truth_pixel(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    ball_body_id: int,
    camera_name: str,
    width: int,
    height: int,
) -> GroundTruthProjection:
    cam_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, camera_name)
    cam_pos = data.cam_xpos[cam_id].copy()
    cam_mat = data.cam_xmat[cam_id].reshape(3, 3).copy()
    fovy_deg = float(model.cam_fovy[cam_id])
    ball_pos = data.xpos[ball_body_id].copy()
    return project_world_point(ball_pos, cam_pos, cam_mat, fovy_deg, width, height)
