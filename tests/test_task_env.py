"""The environment and the contract it hands a policy.

Two things are being held here. That the env's physics is the physics
`world.rollout` already validated against `run_pitch` -- an env that quietly
simulates something else is worse than no env. And that the observation
carries the pitch ONLY through the eye, which is the whole premise of the
project.
"""
from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pytest

from flyohtani.task import env as E
from flyohtani.task.observation import FORBIDDEN_FIELD_NAMES, BatObservation
from flyohtani.world import batter as B
from flyohtani.world import rollout as R

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def env() -> E.BattingEnv:
    e = E.BattingEnv()
    yield e
    e.close()


def _trigger_time_s(env: E.BattingEnv, frame: int) -> float:
    return frame / env.eye_rate_hz


def _matching_rollout(env: E.BattingEnv, frame: int) -> R.Rollout:
    """`rollout.run` with the pitch shifted so its scripted swing starts at
    the same instant the env's policy triggered."""
    t_star, p_star = R.dry_swing(env.scene, env.swing_duration_s, env.swing_follow)
    m = R.compiled(env.scene)
    r_ball = float(m.geom_size[__import__("mujoco").mj_name2id(
        m, __import__("mujoco").mjtObj.mjOBJ_GEOM, "ball")][0])
    strike = p_star + np.array([r_ball + B.BAT_BARREL_RADIUS_MM * env.scene.scale, 0.0, 0.0])
    _, _, flight = B.pitch_geometry(strike, env.scene.scale)
    return R.run((flight - t_star - _trigger_time_s(env, frame)) * 1e3)


class TestObservationContract:
    def test_no_forbidden_fields(self):
        assert FORBIDDEN_FIELD_NAMES.isdisjoint(BatObservation.__dataclass_fields__)

    def test_the_forbidden_list_covers_the_clock_as_well_as_the_ball(self):
        for name in ("ball_pos", "ball_vel", "time_s", "frame_index", "time_to_contact_s"):
            assert name in FORBIDDEN_FIELD_NAMES

    def test_the_observation_module_cannot_reach_the_simulator(self):
        """AST, not grep: the module a policy imports must not be able to
        read world state even by accident."""
        tree = ast.parse((REPO / "flyohtani" / "task" / "observation.py").read_text())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        bad = [m for m in imported
               if m.startswith(("flyohtani.world", "flyohtani.task.env", "flyohtani.sense.evaluator"))]
        assert not bad, bad

    def test_shapes_are_checked(self):
        with pytest.raises(ValueError):
            BatObservation(np.zeros((4, 5), np.uint8), np.zeros((4, 4), np.uint8),
                           np.zeros(5), np.zeros(5), False)
        with pytest.raises(ValueError):
            BatObservation(np.zeros((4, 4), np.uint8), np.zeros((4, 4), np.uint8),
                           np.zeros(5), np.zeros(4), False)


class TestEpisode:
    def test_reset_gives_an_eye_image_and_the_arm_at_ready(self, env):
        obs = env.reset()
        assert obs.eye_left.shape == (B.EYE_RESOLUTION, B.EYE_RESOLUTION)
        assert obs.eye_right.shape == (B.EYE_RESOLUTION, B.EYE_RESOLUTION)
        assert obs.joint_angle_rad.shape == (5,)
        assert not obs.swing_started
        ready = np.array([B.READY_POSE[j] for j in B.ACTIVE_JOINTS])
        assert obs.joint_angle_rad == pytest.approx(ready, abs=1e-6)

    def test_watching_without_swinging_ends_the_episode(self, env):
        env.reset()
        done = False
        frames = 0
        while not done and frames < 200:
            _, _, done, _ = env.step(E.Action(swing=False))
            frames += 1
        assert done and frames < 200
        assert not env.outcome.swung and not env.outcome.contact

    def test_stepping_after_the_end_is_an_error(self, env):
        env.reset()
        done = False
        while not done:
            _, _, done, _ = env.step(False)
        with pytest.raises(RuntimeError):
            env.step(False)

    def test_swinging_sets_the_flag_and_ends_the_episode(self, env):
        env.reset()
        obs, reward, done, info = env.step(E.Action(swing=True))
        assert done and obs.swing_started and reward == 0.0
        assert info["outcome"] is env.outcome
        assert env.outcome.swung and env.outcome.swing_frame == 0

    def test_the_reward_is_not_invented_here(self, env):
        """Phase 5 versions the reward; until then every step scores zero and
        the outcome goes to the caller."""
        env.reset()
        _, reward, _, _ = env.step(False)
        assert reward == 0.0


class TestItIsTheSamePhysics:
    @pytest.mark.parametrize("frame", [19, 20, 21])
    def test_outcome_matches_the_validated_rollout(self, env, frame):
        got = E.swing_at_frame(env, frame)
        want = _matching_rollout(env, frame)
        assert got.contact == want.contact, frame
        if not want.contact:
            return
        assert abs(got.exit_speed_mm_s - want.exit_speed_mm_s) / want.exit_speed_mm_s \
            <= R.MAX_EXIT_SPEED_REL
        assert abs(got.launch_angle_deg - want.launch_angle_deg) <= R.MAX_ANGLE_ERROR_DEG
        assert abs(got.carry_mm - want.carry_mm) / want.carry_mm <= R.MAX_CARRY_REL
        assert got.fair == want.fair


class TestOnlyTheEyeCarriesThePitch:
    def test_two_different_pitches_look_different_but_feel_the_same(self, env):
        """The leak test with teeth: change only the pitch, and every channel
        except the eye must be byte-identical. If the ball's state reached
        proprioception, this fails."""
        a = env.reset(E.PitchSpec(timing_ms=0.0))
        env.step(False)
        obs_a = env.step(False)[0]
        b = env.reset(E.PitchSpec(timing_ms=6.0))
        env.step(False)
        obs_b = env.step(False)[0]
        assert np.array_equal(obs_a.joint_angle_rad, obs_b.joint_angle_rad)
        assert np.array_equal(obs_a.joint_vel_rad_s, obs_b.joint_vel_rad_s)
        assert not np.array_equal(obs_a.eye_left, obs_b.eye_left), "the eye saw no difference"
        assert np.array_equal(a.joint_angle_rad, b.joint_angle_rad)


class TestPolicies:
    """The wiring from eye to action. What it achieves is a measurement and
    lives in docs/records/BRAIN-CIRCUIT.md, not in an assertion here."""

    def test_the_fixed_frame_policy_swings_when_told_and_sees_nothing(self, env):
        from flyohtani.task.policy import FixedFramePolicy, run_episode
        out = run_episode(env, FixedFramePolicy(frame=4))
        assert out.swung and out.swing_frame == 4

    def test_the_circuit_policy_runs_end_to_end_and_records_its_own_trace(self, env):
        from flyohtani.task.policy import CircuitPolicy, run_episode
        policy = CircuitPolicy()
        out = run_episode(env, policy)
        assert policy.trace, "no trace"
        assert {"t_s", "lc_spikes", "dn_spikes", "swing"} <= set(policy.trace[0])
        assert out.frames_seen == len(policy.trace)

    def test_the_motor_delay_shifts_the_swing_by_exactly_that_many_frames(self, env):
        """The measured offset between this circuit's commit and the frame
        that connects is a constant, so the parameter that fixes it has to
        behave like one."""
        from flyohtani.task.policy import CircuitPolicy, run_episode
        base = run_episode(env, CircuitPolicy(motor_delay_frames=0))
        delayed = run_episode(env, CircuitPolicy(motor_delay_frames=2))
        assert base.swung and delayed.swung
        assert delayed.swing_frame == base.swing_frame + 2

    def test_a_policy_that_never_commits_ends_the_episode_without_swinging(self, env):
        from flyohtani.task.policy import CircuitPolicy, run_episode
        out = run_episode(env, CircuitPolicy(spikes_to_swing=10_000))
        assert not out.swung and not out.contact
