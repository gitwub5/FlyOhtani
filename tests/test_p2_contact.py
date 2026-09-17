"""VM-01 P2 regression tests (docs/records/VM01-P2-CONTACT.md): the thin
plate's ball-diameter-exceeds-plate-thickness tunneling/normal-flip finding
must not silently regress, and the fixed (thick_block/flat_plane) geometry
must keep giving a POSITIVE, non-flipping restitution. Single-dt only (not
the full 3-dt convergence sweep scripts/p2_contact_diagnosis.py runs) to
keep this fast as a regression check, not a re-validation.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import p2_contact_diagnosis as p2


class TestThinPlateTunneling:
    def test_thin_plate_ball_ends_up_past_the_far_face(self):
        r = p2.run_frontal("thin_plate", p2.DT_CANDIDATES[0], log_trajectory=True)
        assert r["trajectory"][-1]["ball_x"] > 5.01

    def test_thin_plate_shows_a_contact_normal_sign_flip(self):
        r = p2.run_frontal("thin_plate", p2.DT_CANDIDATES[0])
        assert r["normal_sign_flip_observed"]
        assert r["cor"] < 0


class TestFixedGeometryGivesCleanRestitution:
    def test_thick_block_no_normal_flip_positive_cor(self):
        r = p2.run_frontal("thick_block", p2.DT_CANDIDATES[0])
        assert not r["normal_sign_flip_observed"]
        assert r["cor"] > 0

    def test_flat_plane_no_normal_flip_positive_cor(self):
        r = p2.run_frontal("flat_plane", p2.DT_CANDIDATES[0])
        assert not r["normal_sign_flip_observed"]
        assert r["cor"] > 0

    def test_thick_block_and_flat_plane_agree_closely(self):
        r_block = p2.run_frontal("thick_block", p2.DT_CANDIDATES[0])
        r_plane = p2.run_frontal("flat_plane", p2.DT_CANDIDATES[0])
        assert abs(r_block["cor"] - r_plane["cor"]) < 0.05


class TestObliqueDoesNotExcuseFrontal:
    def test_oblique_cor_along_normal_stays_similar_to_frontal(self):
        """The user's explicit instruction: a decent oblique result must
        not be used to wave away the frontal failure. Regression-check
        that this remains true numerically (oblique COR stays in the same
        ballpark as frontal, not dramatically better)."""
        frontal = p2.run_frontal("thick_block", p2.DT_CANDIDATES[0])
        oblique = p2.run_oblique_free_bat(p2.DT_CANDIDATES[0], angle_deg=35)
        assert oblique["cor_along_normal"] is not None
        assert abs(oblique["cor_along_normal"] - frontal["cor"]) < 0.15
