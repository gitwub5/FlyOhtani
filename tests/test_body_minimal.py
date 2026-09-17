"""Phase 1 body regression tests.

The point of most of these is narrow: the body must keep coming from the
vendored NeuroMechFly file, not from numbers someone typed in. So several
tests re-read the source MJCF and compare against it rather than asserting a
literal, which is what would catch a well-meaning "cleanup" that replaces a
measured mass or joint axis with a rounder one.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

import mujoco
import numpy as np
import pytest

from flyohtani import units
from flyohtani.body.minimal_body import (
    ACTIVE_JOINTS,
    LOCKED_DOFS,
    SOURCE_MJCF,
    BatSpec,
    BuildOptions,
    build_minimal_body_xml,
)

SOURCE_TIMESTEP = 1e-4
"""flygym's own default, and what the source MJCF's <option> says."""

BAT = BatSpec(mass_g=2e-6, length_mm=2.0)
FAST_OPTS = BuildOptions(include_visual_body=False)


@pytest.fixture(scope="module")
def model() -> mujoco.MjModel:
    return mujoco.MjModel.from_xml_string(build_minimal_body_xml(bat=BAT, opts=FAST_OPTS))


@pytest.fixture(scope="module")
def source_root() -> ET.Element:
    return ET.parse(SOURCE_MJCF).getroot()


def _body(root: ET.Element, name: str) -> ET.Element:
    return next(b for b in root.iter("body") if b.get("name") == name)


class TestBuiltFromSource:
    def test_segment_masses_match_the_source_mjcf_exactly(self, source_root):
        """Not 'close to' -- the same float. A mass that drifts is a mass
        someone retyped."""
        xml = build_minimal_body_xml(bat=None, opts=FAST_OPTS)
        built = ET.fromstring(xml)
        for name in ("RFCoxa", "RFFemur", "RFTibia", "RFTarsus1"):
            src_mass = _body(source_root, name).find("geom").get("mass")
            built_mass = _body(built, name).find("geom").get("mass")
            assert built_mass == src_mass, name

    def test_joint_axes_match_the_source_mjcf_exactly(self, source_root):
        built = ET.fromstring(build_minimal_body_xml(bat=None, opts=FAST_OPTS))
        built_axes = {j.get("name"): j.get("axis") for j in built.iter("joint")}
        for name, axis in built_axes.items():
            src = next(j for j in source_root.iter("joint") if j.get("name") == name)
            assert axis == src.get("axis"), name

    def test_segment_positions_match_the_source_mjcf_exactly(self, source_root):
        built = ET.fromstring(build_minimal_body_xml(bat=None, opts=FAST_OPTS))
        for name in ("RFCoxa", "RFFemur", "RFTibia", "RFTarsus1"):
            assert _body(built, name).get("pos") == _body(source_root, name).get("pos"), name


class TestDegreesOfFreedom:
    def test_five_actuated_dofs_and_nothing_else_moves(self, model):
        """nv == nu == 5: the thorax is welded (no free joint), the head is
        static, and the roll DOFs are locked. Any extra DOF here means
        something got loose."""
        assert model.nv == 5
        assert model.nu == 5
        assert model.njnt == 5

    def test_roll_dofs_are_absent_not_merely_unactuated(self, model):
        """A locked DOF that is still a joint would still wobble. It must not
        exist in the compiled model at all."""
        names = {mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, i) for i in range(model.njnt)}
        for dof in LOCKED_DOFS:
            assert f"joint_RF{dof}" not in names
        assert names == set(ACTIVE_JOINTS)

    def test_active_joints_are_the_source_models_own_actuated_names(self):
        """flygym's all_leg_dofs builds names as joint_{side}{pos}{dof}. If
        this drifts, the actuators silently attach to nothing."""
        expected = {f"joint_RF{d}" for d in units.ACTIVE_FORELEG_JOINTS} - {
            f"joint_RF{d}" for d in LOCKED_DOFS
        }
        assert set(ACTIVE_JOINTS) == expected

    def test_every_active_joint_has_exactly_one_position_actuator(self, model):
        driven = [model.actuator_trnid[i][0] for i in range(model.nu)]
        assert sorted(driven) == sorted(set(driven))
        assert len(driven) == len(ACTIVE_JOINTS)

    def test_actuator_force_limit_is_the_source_models(self, model):
        lo, hi = units.POSITION_CONTROL_FORCERANGE
        assert np.allclose(model.actuator_forcerange[:, 0], lo)
        assert np.allclose(model.actuator_forcerange[:, 1], hi)


class TestRollDofDegeneracy:
    @staticmethod
    def _dt_limits(*, lock_roll_dofs: bool, bat: BatSpec | None) -> dict[str, float]:
        """Largest timestep at which a kp=45 position controller on each DOF
        is integrable, from that DOF's own diagonal inertia."""
        model = mujoco.MjModel.from_xml_string(
            build_minimal_body_xml(
                bat=bat,
                opts=BuildOptions(include_visual_body=False, lock_roll_dofs=lock_roll_dofs),
            )
        )
        data = mujoco.MjData(model)
        mujoco.mj_forward(model, data)
        full = np.zeros((model.nv, model.nv))
        mujoco.mj_fullM(model, data, full)
        out = {}
        for i in range(model.njnt):
            name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, i)
            adr = model.jnt_dofadr[i]
            out[name] = 2.0 / float(np.sqrt(units.POSITION_CONTROL_KP / full[adr, adr]))
        return out

    def test_roll_dofs_cannot_be_integrated_at_the_source_models_own_timestep(self):
        """This, not "the inertia is small", is the actual reason they are
        locked. With the model's own kp (45), the position controller's
        natural frequency on these DOFs implies a stability limit finer than
        the model's own dt -- the published settings cannot drive the
        published joints under a saturating command.

        The same measurement on the UNMODIFIED published model (Coxa_roll
        2.914e-08, Femur_roll 1.784e-08 g*mm^2) is in
        docs/records/G1-FORELEG-SWING.md; it needs mesh files this repo
        deliberately does not vendor, so it cannot run offline here.
        """
        limits = self._dt_limits(lock_roll_dofs=False, bat=BAT)
        for dof in LOCKED_DOFS:
            assert limits[f"joint_RF{dof}"] < SOURCE_TIMESTEP, dof

    def test_g1s_configuration_is_integrable_at_the_timestep_g1_uses(self):
        """The operational claim: with the rolls locked and a bat fitted,
        every driven DOF is integrable at the sweep's own timestep."""
        from flyohtani.body.g1_sweep import DEFAULT_TIMESTEP

        limits = self._dt_limits(lock_roll_dofs=True, bat=BAT)
        assert set(limits) == set(ACTIVE_JOINTS)
        for name, limit in limits.items():
            assert limit > DEFAULT_TIMESTEP, f"{name}: needs dt < {limit:.2e}"

    def test_an_unloaded_tarsus_is_marginal_at_the_source_timestep(self):
        """Recorded because it is counter-intuitive and easy to trip over:
        the BAT stabilises the wrist. With no tool fitted, Tarsus1's own
        inertia is small enough that it too fails at the source model's
        default dt. Any future no-bat run must pick its timestep knowing
        this."""
        limits = self._dt_limits(lock_roll_dofs=True, bat=None)
        assert limits["joint_RFTarsus1"] < SOURCE_TIMESTEP
        assert self._dt_limits(lock_roll_dofs=True, bat=BAT)["joint_RFTarsus1"] > SOURCE_TIMESTEP


class TestGeometry:
    def test_foreleg_reach_is_sub_two_millimetres(self, model):
        """Real fly scale. If this ever reads ~1.8 METRES, someone has
        reintroduced v1's enlarged rig."""
        data = mujoco.MjData(model)
        mujoco.mj_forward(model, data)
        grip = data.site_xpos[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, "grip")]
        coxa = data.xpos[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "RFCoxa")]
        assert 1.5 < float(np.linalg.norm(grip - coxa)) < 2.0

    def test_eye_camera_is_carried_by_the_head_body(self, model):
        cam = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, "eye_cam")
        head = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "Head")
        assert cam >= 0
        assert model.cam_bodyid[cam] == head

    def test_bat_is_welded_to_the_tarsus(self, model):
        bat = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "bat")
        tarsus = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "RFTarsus1")
        assert model.body_parentid[bat] == tarsus
        assert model.body_jntnum[bat] == 0


class TestBatSpec:
    @pytest.mark.parametrize("kwargs", [
        {"mass_g": 0, "length_mm": 1.0},
        {"mass_g": 1e-6, "length_mm": -1.0},
        {"mass_g": 1e-6, "length_mm": 1.0, "radius_mm": 0},
    ])
    def test_rejects_non_positive_dimensions(self, kwargs):
        with pytest.raises(ValueError):
            BatSpec(**kwargs)

    def test_model_builds_without_a_bat(self):
        m = mujoco.MjModel.from_xml_string(build_minimal_body_xml(bat=None, opts=FAST_OPTS))
        assert mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "bat") < 0
        assert m.nv == 5


class TestSwingBehaviour:
    def test_a_saturating_step_command_stays_stable(self):
        from flyohtani.body.g1_sweep import _run_one

        result = _run_one(BAT, target_rad=3.0, sign=-1)
        assert result.stable
        assert result.warnings == {}
        assert result.peak_tip_speed_mm_s > 0

    def test_a_heavier_bat_swings_slower(self):
        """The load has to actually load the arm. If mass stops mattering,
        something has decoupled the bat from the joints."""
        from flyohtani.body.g1_sweep import _run_one

        light = _run_one(BatSpec(2e-6, 4.0), target_rad=3.0, sign=-1)
        heavy = _run_one(BatSpec(2e-5, 4.0), target_rad=3.0, sign=-1)
        assert light.stable and heavy.stable
        assert heavy.peak_tip_speed_mm_s < light.peak_tip_speed_mm_s

    def test_mass_clamping_is_detected_and_reported(self):
        """boundmass silently raises light bodies. The sweep has to say so
        rather than quietly reporting a bat heavier than requested."""
        from flyohtani.body.g1_sweep import _run_one

        clamped = _run_one(BatSpec(5e-7, 2.0), target_rad=1.0, sign=1, boundmass=1e-6)
        assert clamped.mass_was_clamped
        assert clamped.compiled_bat_mass_g == pytest.approx(1e-6)

        exact = _run_one(BatSpec(5e-7, 2.0), target_rad=1.0, sign=1, boundmass=1e-9)
        assert not exact.mass_was_clamped
        assert exact.compiled_bat_mass_g == pytest.approx(5e-7)
