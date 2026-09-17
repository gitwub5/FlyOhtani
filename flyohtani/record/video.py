"""Turns a simulation into something a person can watch: an mp4 and a sheet
of stills, each frame showing the scene from two cameras, what the fly's two
eyes see, and a caption panel.

Everything here is for HUMAN viewers. The text, rings and layout never reach
the policy, which only ever gets `batter.render_eyes` output (D28).

Rendering never changes the simulation: `capture` reads `data` and nothing
else, so a run recorded and a run not recorded produce the same physics.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Self

import mujoco
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from flyohtani.world import batter as B

_FONT_CANDIDATES = (
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
)


def _font(size: int) -> ImageFont.ImageFont:
    """A font that can draw Korean if the machine has one; PIL's built-in
    bitmap font otherwise (Latin only -- captions then degrade, the video
    still gets written)."""
    for path in _FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


@dataclass
class View:
    label: str
    camera: mujoco.MjvCamera | str


def free_camera(lookat: Sequence[float], distance: float, azimuth: float, elevation: float) -> mujoco.MjvCamera:
    cam = mujoco.MjvCamera()
    cam.type = mujoco.mjtCamera.mjCAMERA_FREE
    cam.lookat[:] = lookat
    cam.distance, cam.azimuth, cam.elevation = distance, azimuth, elevation
    return cam


INK = (24, 27, 22)
MUTED = (110, 116, 104)
PANEL = (246, 247, 243)
ACCENT = (153, 87, 31)
RING = (225, 45, 45)


class Recorder:
    """Composites one frame per `capture` call:

        +-------------------+-------------------+
        |  view 0           |  view 1           |
        +---------+---------+-------------------+
        | eye L   | eye R   |  caption panel    |
        +---------+---------+-------------------+
    """

    def __init__(self, model: mujoco.MjModel, views: Sequence[View], *,
                 view_size: tuple[int, int] = (640, 360), eye_px: int = 180) -> None:
        if len(views) != 2:
            raise ValueError("the layout has room for exactly two scene views")
        self.model = model
        self.views = list(views)
        self.vw, self.vh = view_size
        self.eye_px = eye_px
        self.width = 2 * self.vw
        self.height = self.vh + eye_px + 20
        self._scene = mujoco.Renderer(model, height=self.vh, width=self.vw)
        self._eyes = mujoco.Renderer(model, height=B.EYE_RESOLUTION, width=B.EYE_RESOLUTION)
        self._opt = mujoco.MjvOption()
        for g in range(5):
            self._opt.geomgroup[g] = 1
        self._opt.geomgroup[5] = 0  # hidden collision stand-ins
        self.frames: list[np.ndarray] = []
        self.times: list[float] = []
        self._title = _font(22)
        self._body = _font(17)
        self._small = _font(14)

    def close(self) -> None:
        self._scene.close()
        self._eyes.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _eye_tile(self, gray: np.ndarray, label: str, ball_px: tuple[float, float] | None) -> Image.Image:
        s = self.eye_px // B.EYE_RESOLUTION
        img = Image.fromarray(gray).resize((B.EYE_RESOLUTION * s, B.EYE_RESOLUTION * s), Image.NEAREST).convert("RGB")
        tile = Image.new("RGB", (self.eye_px, self.eye_px + 20), PANEL)
        tile.paste(img, (0, 0))
        draw = ImageDraw.Draw(tile)
        if ball_px is not None:
            cx, cy = (ball_px[0] + 0.5) * s, (ball_px[1] + 0.5) * s
            draw.ellipse((cx - 11, cy - 11, cx + 11, cy + 11), outline=RING, width=2)
        draw.text((4, self.eye_px + 1), label, font=self._small, fill=MUTED)
        return tile

    def _ball_pixel(self, data: mujoco.MjData, camera: str) -> tuple[float, float] | None:
        """Where the ball is in an eye image, for the explanatory ring only."""
        ball = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, "ball")
        if ball < 0:
            return None
        cam = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_CAMERA, camera)
        mat = data.cam_xmat[cam].reshape(3, 3)
        rel = mat.T @ (data.xpos[ball] - data.cam_xpos[cam])
        if rel[2] >= 0:
            return None
        f = (B.EYE_RESOLUTION / 2) / np.tan(np.radians(self.model.cam_fovy[cam]) / 2)
        u = B.EYE_RESOLUTION / 2 + f * rel[0] / -rel[2] - 0.5
        v = B.EYE_RESOLUTION / 2 - f * rel[1] / -rel[2] - 0.5
        if not (0 <= u < B.EYE_RESOLUTION and 0 <= v < B.EYE_RESOLUTION):
            return None
        return float(u), float(v)

    def capture(self, data: mujoco.MjData, *, title: str, lines: Sequence[str] = (),
                ring_ball: bool = True) -> np.ndarray:
        canvas = Image.new("RGB", (self.width, self.height), PANEL)
        draw = ImageDraw.Draw(canvas)
        for i, view in enumerate(self.views):
            self._scene.update_scene(data, camera=view.camera, scene_option=self._opt)
            canvas.paste(Image.fromarray(self._scene.render()), (i * self.vw, 0))
            draw.rectangle((i * self.vw + 8, 8, i * self.vw + 16 + 9 * len(view.label) + 40, 34), fill=(0, 0, 0))
            draw.text((i * self.vw + 14, 10), view.label, font=self._small, fill=(255, 255, 255))
        eyes = B.render_eyes(self.model, data, self._eyes)
        x = 0
        for side, label in (("L", "왼쪽 눈 (투수 쪽)"), ("R", "오른쪽 눈 (포수 쪽)")):
            px = self._ball_pixel(data, f"eye_{side}") if ring_ball else None
            canvas.paste(self._eye_tile(eyes[side], label, px), (x, self.vh))
            x += self.eye_px
        tx, ty = x + 20, self.vh + 12
        draw.text((tx, ty), title, font=self._title, fill=INK)
        for k, line in enumerate(lines):
            draw.text((tx, ty + 34 + k * 24), line, font=self._body, fill=INK if k == 0 else MUTED)
        draw.text((self.width - 330, self.height - 22),
                  "빨간 원: 설명용 표시 (파리가 보는 화면에는 없음)", font=self._small, fill=MUTED)
        frame = np.asarray(canvas)
        self.frames.append(frame)
        self.times.append(float(data.time))
        return frame

    def write_video(self, path: Path, fps: int = 30) -> Path:
        import imageio.v2 as imageio

        path.parent.mkdir(parents=True, exist_ok=True)
        with imageio.get_writer(path, fps=fps, codec="libx264", quality=8,
                                macro_block_size=1, ffmpeg_log_level="error") as w:
            for f in self.frames:
                w.append_data(f)
        return path

    def write_sheet(self, path: Path, picks: Sequence[int] | None = None, columns: int = 2,
                    scale: float = 0.5) -> Path:
        """Contact sheet of selected frames (evenly spaced by default)."""
        if not self.frames:
            raise ValueError("nothing captured")
        if picks is None:
            n = min(8, len(self.frames))
            picks = [round(i * (len(self.frames) - 1) / max(n - 1, 1)) for i in range(n)]
        tw, th = int(self.width * scale), int(self.height * scale)
        rows = (len(picks) + columns - 1) // columns
        sheet = Image.new("RGB", (columns * tw + (columns - 1) * 8, rows * th + (rows - 1) * 8), (255, 255, 255))
        for k, i in enumerate(picks):
            tile = Image.fromarray(self.frames[i]).resize((tw, th), Image.LANCZOS)
            sheet.paste(tile, ((k % columns) * (tw + 8), (k // columns) * (th + 8)))
        path.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(path)
        return path

    def write_still(self, path: Path, index: int) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(self.frames[index]).save(path)
        return path
