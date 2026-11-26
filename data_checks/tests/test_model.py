from __future__ import annotations

import pytest

from data_checks.model import Check, Finding, Severity, SkipCheck, Status
from data_checks.registry import all_checks, check
from data_checks.tests.fixture_data import FIXTURE_CONFIG, make_snapshot


def test_evaluate_pass_fail_samples_and_metric():
    c = Check("Z1", "t", Severity.WARN, lambda s, cfg: Finding([f"v{i}" for i in range(7)], metric=0.5))
    r = c.evaluate(make_snapshot(), FIXTURE_CONFIG)
    assert (r.status, r.violation_count, r.samples, r.metric) == (
        Status.FAIL,
        7,
        ("v0", "v1", "v2", "v3", "v4"),
        0.5,
    )
    ok = Check("Z2", "t", Severity.ERROR, lambda s, cfg: Finding([]))
    assert ok.evaluate(make_snapshot(), FIXTURE_CONFIG).status == Status.PASS


def test_evaluate_skip_and_crash_never_raise():
    def skip(s, cfg):
        raise SkipCheck("no baseline")

    def boom(s, cfg):
        raise KeyError("x")

    r1 = Check("Z3", "t", Severity.WARN, skip).evaluate(make_snapshot(), FIXTURE_CONFIG)
    r2 = Check("Z4", "t", Severity.ERROR, boom).evaluate(make_snapshot(), FIXTURE_CONFIG)
    assert (r1.status, r1.detail) == (Status.SKIPPED, "no baseline")
    assert r2.status == Status.ERRORED and r2.detail.startswith("KeyError")


@pytest.mark.skipif(
    not any(c.check_id == "A1" for c in all_checks()), reason="A1 lands in Task 2"
)
def test_duplicate_check_id_is_rejected():
    with pytest.raises(ValueError):
        check("A1", "dup", Severity.ERROR)(lambda s, cfg: Finding([]))
