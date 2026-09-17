"""LIT-01 regression tests.

The velocity numbers in docs/records/LIT-01-FLY-LEG-LIMITS.md are re-derived
here from the vendored recording rather than asserted as literals, so the
document and the code cannot drift apart silently.
"""
from __future__ import annotations

import numpy as np
import pytest

from flyohtani import units
from flyohtani.body import limits
from flyohtani.body.minimal_body import ACTIVE_JOINTS, LOCKED_DOFS


@pytest.fixture(scope="module")
def speeds():
    return limits.walking_joint_speeds()


class TestMeasuredFromTheRecording:
    def test_the_recording_is_what_its_provenance_says(self):
        prov = limits.walking_provenance()
        assert prov["source"]["pypi_version"] == "1.2.1"
        assert prov["source"]["license"] == "Apache-2.0"
        assert prov["conversion"]["lossless"].startswith("verified")
        assert "one fly" in prov["recording"]["caveat"].lower()

        data = np.load(limits.WALKING_NPZ, allow_pickle=False)
        assert data["joint_angles_rad"].shape == (42, 2000)
        assert float(data["timestep_s"]) == pytest.approx(5e-4)

    def test_all_six_legs_and_seven_dofs_are_present(self, speeds):
        assert len(speeds) == 42
        for leg in ("LF", "LM", "LH", "RF", "RM", "RH"):
            for dof in units.ACTIVE_FORELEG_JOINTS:
                assert f"joint_{leg}{dof}" in speeds

    def test_walking_speeds_reproduce_the_documented_values(self, speeds):
        """LIT-01 section 1's table, recomputed. Loose tolerances -- the
        point is that the document was not written from a different run."""
        assert speeds["joint_RFTibia"].max_abs == pytest.approx(98.6, rel=0.01)
        assert speeds["joint_RFTibia"].p95_abs == pytest.approx(65.2, rel=0.01)
        assert speeds["joint_RFFemur"].max_abs == pytest.approx(78.2, rel=0.01)
        fastest = max(speeds.values(), key=lambda s: s.max_abs)
        assert fastest.name == "joint_LFTarsus1"
        assert fastest.max_abs == pytest.approx(231.1, rel=0.01)

    def test_the_dofs_we_drive_stay_under_a_hundred_rad_per_second(self, speeds):
        """Walking never gets our five driven DOFs past ~100 rad/s. This is
        the "normal behaviour" reference the chosen ceiling sits above."""
        driven = [speeds[name].max_abs for name in ACTIVE_JOINTS]
        assert max(driven) < 100.0

    def test_locked_roll_dofs_do_move_in_a_real_fly(self, speeds):
        """Locking them is a modelling compromise, not a claim that a fly
        holds them still. If this ever passes trivially, the compromise has
        been forgotten."""
        for dof in LOCKED_DOFS:
            assert speeds[f"joint_RF{dof}"].range_of_motion_rad > 0.5
            assert speeds[f"joint_RF{dof}"].max_abs > 50.0


class TestTheChosenCeiling:
    def test_ceiling_sits_inside_the_derived_jump_range(self):
        low, high = limits.JUMP_JOINT_SPEED_RANGE_RAD_S
        assert low < limits.MAX_JOINT_SPEED_RAD_S < high

    def test_ceiling_is_above_measured_walking_not_below_it(self, speeds):
        """Batting is maximal effort; a ceiling under strolling speed would
        be the wrong bound."""
        walking_max = max(speeds[name].max_abs for name in ACTIVE_JOINTS)
        assert limits.MAX_JOINT_SPEED_RAD_S > walking_max

    def test_g1s_best_run_is_flagged_as_unphysiological(self):
        """The whole reason LIT-01 exists."""
        assert limits.exceeds_biological_speed(1682.0)
        assert not limits.exceeds_biological_speed(280.0)

    def test_derived_jump_range_follows_from_the_published_numbers(self):
        """The range must be takeoff_speed / radius, not a typed-in pair."""
        low, high = limits.JUMP_JOINT_SPEED_RANGE_RAD_S
        assert low == pytest.approx(limits.JUMP_TAKEOFF_SPEED_MM_S / 2.00, rel=0.01)
        assert high == pytest.approx(limits.JUMP_TAKEOFF_SPEED_MM_S / 0.93, rel=0.01)


class TestForceWasNeverTheProblem:
    def test_model_torque_limit_is_the_same_order_as_the_measured_jump_force(self):
        """At a 1 mm moment arm, flygym's +/-65 uN*mm and Zumstein's 101 uN
        are within a factor of two. LIT-01 section 4's conclusion."""
        model_torque = units.POSITION_CONTROL_FORCERANGE[1]
        published_at_1mm = limits.JUMP_PEAK_LEG_FORCE_UN * 1.0
        assert 0.4 < model_torque / published_at_1mm < 1.0


class TestBatTipCeiling:
    def test_bat_tip_ceiling_is_consistent_with_the_g1_evidence(self):
        """Re-read from the G1 evidence file: the fastest stable run under
        the chosen joint ceiling. Keeps limits.py honest if G1 is re-run."""
        import json
        from pathlib import Path

        path = Path(__file__).resolve().parent.parent / "docs" / "records" / "evidence" / "G1-swing-sweep.json"
        runs = json.loads(path.read_text())["all_runs"]
        eligible = [
            r for r in runs
            if r["stable"] and r["peak_joint_speed_rad_s"] <= limits.MAX_JOINT_SPEED_RAD_S
        ]
        assert eligible, "no G1 run survives the chosen ceiling"
        best = max(r["peak_tip_speed_mm_s"] for r in eligible)
        assert limits.MAX_BAT_TIP_SPEED_MM_S == pytest.approx(best, rel=0.01)

    def test_the_grid_cannot_resolve_the_ceiling_it_is_asked_about(self):
        """Documented limitation, pinned so it is not quietly forgotten: the
        coarsest target angle already exceeds 280 rad/s, so a 300 and a 520
        rad/s ceiling pick the same run."""
        import json
        from pathlib import Path

        path = Path(__file__).resolve().parent.parent / "docs" / "records" / "evidence" / "G1-swing-sweep.json"
        runs = json.loads(path.read_text())["all_runs"]

        def best_under(cap):
            ok = [r["peak_tip_speed_mm_s"] for r in runs if r["stable"] and r["peak_joint_speed_rad_s"] <= cap]
            return max(ok) if ok else None

        assert best_under(300.0) == best_under(520.0)
