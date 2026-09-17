"""The selected contact parameters must be the ones G2 v2 actually selected.

Re-read from the committed evidence rather than trusted, so a re-run of G2
that picks something else cannot leave contact.py silently stale.
"""
from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from flyohtani.world import contact
from flyohtani.world import g2_contact as g2

EVIDENCE = Path(__file__).resolve().parent.parent / "docs" / "records" / "evidence"


@pytest.fixture(scope="module")
def v2():
    return json.loads(gzip.decompress((EVIDENCE / g2.V2.evidence_name).read_bytes()))


def test_g2_v2_passed(v2):
    assert v2["verdict"] == "PASS"
    assert v2["protocol"]["name"] == "v2"


def test_selected_parameters_match_the_evidence(v2):
    sel = v2["selected"]
    assert contact.SOLREF_TIMECONST_S == sel["timeconst_s"]
    assert contact.SOLREF_DAMPRATIO == sel["dampratio"]
    assert contact.SOLIMP == g2.SOLIMPS[sel["solimp"]]


def test_contact_timestep_is_the_registered_production_step(v2):
    assert contact.CONTACT_TIMESTEP_S == pytest.approx(v2["selected_production_timestep_s"])
    assert contact.CONTACT_TIMESTEP_S == pytest.approx(
        contact.SOLREF_TIMECONST_S / g2.V2.production_divisor)


def test_selection_survived_both_guards(v2):
    """RK4 cross-check and hold-out, both for the selected candidate."""
    sel = v2["selected"]
    rk4 = [c for c in v2["integrator_cross_checks"] if c["candidate"] == sel]
    hold = [c for c in v2["holdout_checks"] if c["candidate"] == sel]
    assert rk4 and rk4[0]["rk4_matches"]
    assert hold and hold[0]["passes"]


def test_expected_cor_range_covers_what_g2_measured(v2):
    sel = v2["selected"]
    cand = next(c for c in v2["candidates"] if c["candidate"] == sel)
    hold = next(c for c in v2["holdout_checks"] if c["candidate"] == sel)
    k = g2.V2.production_divisor
    cors = [r["cor"] for r in cand["runs"] if round(r["candidate"]["timeconst_s"] / r["timestep_s"]) == k]
    cors += [r["cor"] for r in hold["runs"] if round(r["candidate"]["timeconst_s"] / r["timestep_s"]) == k]
    lo, hi = contact.EXPECTED_COR_RANGE
    assert lo == pytest.approx(min(cors), abs=5e-4)
    assert hi == pytest.approx(max(cors), abs=5e-4)
    assert g2.COR_BAND[0] < lo < hi < g2.COR_BAND[1]


def test_validity_envelope_is_the_one_g2_tested():
    assert contact.MAX_VALIDATED_IMPACT_SPEED_MM_S == max(g2.IMPACT_SPEEDS_MM_S)
    assert contact.BALL_RADIUS_MM == g2.BALL_RADIUS_MM
    assert contact.BALL_MASS_G == g2.BALL_MASS_G
    assert contact.BAT_RADIUS_MM == g2.BAT_RADIUS_MM


def test_v1_still_records_its_failure():
    """v2 passing does not overwrite v1. Both verdicts stay on record."""
    v1 = json.loads(gzip.decompress((EVIDENCE / g2.V1.evidence_name).read_bytes()))
    assert v1["verdict"] == "FAIL"
    assert v1["n_passing_before_cross_check"] == 0
