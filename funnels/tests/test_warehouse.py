from __future__ import annotations

from datetime import date

import pytest

from funnels.config import Params
from funnels.warehouse import build


def test_params_table_reflects_params(query):
    assert query(
        "select early_window_days, outcome_window_days, retained_from_day, retained_to_day,"
        " retained_min_active_days, habit_target_retention, min_group_size,"
        " usage_end, conversion_end from params"
    ) == [(14, 30, 28, 56, 2, 0.8, 30, date(2024, 6, 30), date(2024, 6, 30))]


def test_build_rejects_missing_raw_dir(tmp_path):
    with pytest.raises(FileNotFoundError):
        build(tmp_path / "nope", Params())


def test_build_accepts_raw_dir_with_a_quote_in_its_path(tmp_path):
    from funnels.tests.fixture_data import write_raw

    odd = tmp_path / "it's raw"
    write_raw(odd)
    con = build(odd, Params())
    con.close()


def test_wilson_interval_matches_known_values(query):
    low, high = query("select wilson_low(50, 100), wilson_high(50, 100)")[0]
    assert low == pytest.approx(0.4038, abs=1e-3)
    assert high == pytest.approx(0.5962, abs=1e-3)


def test_wilson_interval_edges(query):
    assert query("select wilson_low(0, 0), wilson_high(0, 0)") == [(None, None)]
    low, high = query("select wilson_low(0, 10), wilson_high(0, 10)")[0]
    assert low == pytest.approx(0.0, abs=1e-9)
    assert high == pytest.approx(0.2775, abs=1e-3)
    assert query("select wilson_high(10, 10)")[0][0] == 1.0


def test_safe_rate_is_null_for_empty_denominator(query):
    assert query("select safe_rate(3, 0), safe_rate(1, 4)") == [(None, 0.25)]


def test_diff_interval_is_null_when_either_side_is_empty(query):
    assert query("select diff_low(1, 0, 1, 5), diff_high(1, 5, 0, 0)") == [(None, None)]
    low, high = query("select diff_low(30, 100, 20, 100), diff_high(30, 100, 20, 100)")[0]
    assert low == pytest.approx(0.10 - 1.96 * (0.21 / 100 + 0.16 / 100) ** 0.5)
    assert high == pytest.approx(0.10 + 1.96 * (0.21 / 100 + 0.16 / 100) ** 0.5)


@pytest.mark.parametrize(
    "n, bucket, order",
    [(0, "0", 0), (1, "1", 1), (2, "2-3", 2), (3, "2-3", 2), (4, "4-6", 3),
     (6, "4-6", 3), (7, "7+", 4), (40, "7+", 4)],
)
def test_activity_bucket(query, n, bucket, order):
    assert query("select activity_bucket(?), activity_bucket_order(?)", n, n) == [(bucket, order)]
