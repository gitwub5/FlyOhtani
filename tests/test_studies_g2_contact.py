"""G2 regression tests.

Two kinds, kept apart:

  * Code correctness against closed-form answers (effective mass, momentum
    conservation). These would fail on a bug in the measurement, whatever
    the contact parameters are.
  * Guards on the pre-registration: the constants in g2_contact.py must stay
    the ones committed in docs/records/G2-CONTACT.md before the gate ran.
"""
from __future__ import annotations

import math

import mujoco
import pytest

from flyohtani.studies import g2_contact as g2

CAND = g2.Candidate(1e-6, 0.3, "default")
DT = CAND.timeconst_s / g2.V1.production_divisor


def _bat_transverse_inertia(mass: float) -> float:
    cfg = g2.Config("bat", 1000.0, 0.0, mass, 0.0)
    model = mujoco.MjModel.from_xml_string(g2._xml(cfg, CAND, DT, "Euler"))
    body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "target")
    return float(max(model.body_inertia[body]))


class TestEffectiveMassMatchesClosedForm:
    def test_fixed_block_effective_mass_is_the_ball(self):
        r = g2.run_contact(g2.Config("block", 1000.0, 0.0, None, 0.0), CAND, DT)
        assert r.m_eff_g == pytest.approx(g2.BALL_MASS_G, rel=1e-9)

    @pytest.mark.parametrize("bat_mass", g2.BAT_MASSES_G)
    def test_centre_hit_on_free_bat_is_the_reduced_mass(self, bat_mass):
        r = g2.run_contact(g2.Config("bat", 1000.0, 0.0, bat_mass, 0.0), CAND, DT)
        expected = 1.0 / (1.0 / g2.BALL_MASS_G + 1.0 / bat_mass)
        assert r.m_eff_g == pytest.approx(expected, rel=1e-9)

    def test_eccentric_hit_adds_the_rotational_term(self):
        mass, z = g2.BAT_MASSES_G[0], 1.5
        r = g2.run_contact(g2.Config("bat", 1000.0, 0.0, mass, z), CAND, DT)
        inv = 1.0 / g2.BALL_MASS_G + 1.0 / mass + z**2 / _bat_transverse_inertia(mass)
        assert r.m_eff_g == pytest.approx(1.0 / inv, rel=1e-6)


class TestConservation:
    @pytest.mark.parametrize("angle", g2.BAT_IMPACT_ANGLES_DEG)
    def test_linear_momentum_is_conserved_to_roundoff(self, angle):
        """Contact forces are equal and opposite and nothing else acts. A
        residual above roundoff means a double step or a spurious impulse."""
        r = g2.run_contact(g2.Config("bat", 1000.0, angle, g2.BAT_MASSES_G[0], 1.5), CAND, DT)
        assert r.momentum_residual < 1e-12

    def test_energy_check_is_exact_for_one_dimensional_impacts(self):
        """Stated limitation of C5, pinned: for a head-on hit the check is an
        identity, because COR and kinetic energy come from the same
        velocities. It only has teeth for eccentric or oblique impacts."""
        r = g2.run_contact(g2.Config("block", 1000.0, 0.0, None, 0.0), CAND, DT)
        assert r.energy_residual < 1e-12

    def test_energy_check_is_not_trivially_zero_for_oblique_impacts(self):
        r = g2.run_contact(g2.Config("bat", 1000.0, 35.0, g2.BAT_MASSES_G[0], 1.5), CAND, DT)
        assert r.energy_residual > 1e-9


class TestMeasurementMechanics:
    def test_an_impact_separates_and_does_not_flip(self):
        r = g2.run_contact(g2.Config("bat", 500.0, 20.0, g2.BAT_MASSES_G[1], 1.5), CAND, DT)
        assert r.separated
        assert not r.chatter
        assert not r.normal_flip
        assert math.isfinite(r.cor)

    def test_refuses_a_timestep_that_would_trigger_the_silent_clamp(self):
        """MuJoCo raises timeconst to 2*dt without saying so. The gate must
        never run in that regime, so the runner refuses it outright."""
        with pytest.raises(ValueError, match="timeconst"):
            g2.run_contact(g2.Config("block", 1000.0, 0.0, None, 0.0), CAND, CAND.timeconst_s)


class TestPreRegistrationIsIntact:
    """These values were committed in docs/records/G2-CONTACT.md before the
    gate ever ran (commit ea7dff9). A change here is a change to the
    experiment and must be recorded as one."""

    def test_acceptance_criteria(self):
        assert g2.MAX_PENETRATION_MM == pytest.approx(0.015)
        assert g2.COR_BAND == (0.3, 0.7)
        assert g2.REL_TOL == 0.02
        assert g2.COR_ABS_TOL == 0.01
        assert g2.PEN_ABS_TOL == pytest.approx(0.00015)
        assert g2.MAX_ENERGY_RESIDUAL == 0.05
        assert g2.MAX_MOMENTUM_RESIDUAL == 0.01

    def test_grid(self):
        assert len(g2.all_candidates()) == 40
        assert len(g2.all_configs()) == 65
        assert max(g2.IMPACT_SPEEDS_MM_S) == 4500.0

    def test_v1_ladder_is_the_one_that_ran(self):
        """Section 3 of the record, commit ea7dff9."""
        assert g2.V1.dt_divisors == (2, 4, 8, 16)
        assert g2.V1.production_divisor == 4
        assert not g2.V1.use_holdout

    def test_v2_ladder_is_the_one_registered_in_section_9(self):
        assert g2.V2.dt_divisors == (64, 128, 256, 512)
        assert g2.V2.production_divisor == 128
        assert g2.V2.use_holdout

    def test_v2_changes_only_the_ladder(self):
        """Section 9.1: criteria, candidates and fixed setup are shared, so a
        v2 pass cannot come from a quietly relaxed threshold."""
        assert g2.V1.evidence_name != g2.V2.evidence_name
        # criteria are module-level, not per-protocol -- there is nowhere for
        # v2 to hold a different threshold.
        assert not hasattr(g2.V2, "max_penetration_mm")

    def test_holdout_values_are_absent_from_the_main_grid(self):
        """Section 9.3: hold-out means values nothing has been tuned on."""
        assert set(g2.HOLDOUT_SPEEDS_MM_S).isdisjoint(g2.IMPACT_SPEEDS_MM_S)
        assert set(g2.HOLDOUT_ANGLES_DEG).isdisjoint(g2.BAT_IMPACT_ANGLES_DEG)
        assert set(g2.HOLDOUT_HIT_HEIGHTS_MM).isdisjoint(g2.HIT_HEIGHTS_MM)
        assert len(g2.holdout_configs()) == 10

    @pytest.mark.parametrize("protocol", [g2.V1, g2.V2])
    def test_every_timestep_in_the_grid_is_clamp_safe(self, protocol):
        for cand in g2.all_candidates():
            for k in protocol.dt_divisors:
                assert cand.timeconst_s / k <= cand.timeconst_s / 2

    def test_a_protocol_cannot_be_built_with_a_clamping_step(self):
        with pytest.raises(ValueError, match="clamp"):
            g2.Protocol("bad", (1, 2), 2, use_holdout=False, evidence_name="x")


class TestEvidenceWriter:
    def test_evidence_is_gzipped_and_byte_stable_regardless_of_filename(self, tmp_path, monkeypatch):
        """The first attempt at this passed `mtime` to gzip.open (not
        accepted) and, once fixed, still embedded the output filename in the
        header -- same data, different bytes. Pinned end to end through
        main()."""
        import gzip
        import json
        import sys

        fake = {"gate": "G2", "verdict": "FAIL", "selected": None,
                "n_passing_before_cross_check": 0, "n_candidates": 40, "n_configs": 65}
        monkeypatch.setattr(g2, "evaluate", lambda protocol=None, workers=None: dict(fake))
        monkeypatch.setattr(g2, "datetime", _FixedDatetime)

        outputs = []
        for name in ("a.json.gz", "completely-different-name.json.gz"):
            out = tmp_path / name
            monkeypatch.setattr(sys, "argv", ["g2", "--protocol", "v1", "--out", str(out)])
            g2.main()
            outputs.append(out.read_bytes())

        assert outputs[0] == outputs[1]
        assert json.loads(gzip.decompress(outputs[0]))["verdict"] == "FAIL"


class _FixedDatetime:
    """main() stamps the run date; freeze it so the byte comparison above
    tests the writer, not the calendar."""

    @staticmethod
    def now(tz=None):
        import datetime as _dt

        return _dt.datetime(2026, 9, 17, tzinfo=tz)
