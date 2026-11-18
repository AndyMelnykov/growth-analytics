from __future__ import annotations

import pytest

COLS = (
    "signups, viewed, activated, shared, multi_feature, converted_in_window,"
    " median_days_to_first_use"
)


def seg(query, dimension, segment):
    return query(
        f"select {COLS} from gold_activation_funnel"
        f" where dimension = '{dimension}' and segment = '{segment}'"
    )


def test_all_segment_excludes_unobserved_signups(query):
    # 9 observed users (u8 excluded). activated = u1, u2, u5, u9
    assert seg(query, "all", "all") == [(9, 2, 4, 1, 1, 3, 0.0)]


def test_channel_segment(query):
    # referral = u1, u2, u6: viewed u1+u6, activated u1+u2 (days 1 and 0), shared u2, converted u1
    assert seg(query, "acquisition_channel", "referral") == [(3, 2, 2, 1, 0, 1, 0.5)]


def test_segment_without_activation_has_null_median(query):
    assert seg(query, "acquisition_channel", "paid_search") == [(2, 0, 0, 0, 0, 2, None)]


def test_every_dimension_covers_the_whole_cohort(query):
    totals = query(
        "select dimension, sum(signups) from gold_activation_funnel group by dimension"
        " order by dimension"
    )
    assert totals == [
        ("acquisition_channel", 9),
        ("all", 9),
        ("company_size", 9),
        ("industry", 9),
    ]


def test_rates_and_intervals(query):
    rate, low, high, multi_rate, conv_rate = query(
        "select activation_rate, activation_ci_low, activation_ci_high,"
        " multi_feature_rate_of_activated, conversion_rate"
        " from gold_activation_funnel where dimension = 'all'"
    )[0]
    assert rate == pytest.approx(4 / 9)
    assert low < rate < high
    assert multi_rate == pytest.approx(1 / 4)
    assert conv_rate == pytest.approx(3 / 9)


def test_multi_feature_rate_is_null_when_nobody_activated(query):
    assert query(
        "select activation_rate, multi_feature_rate_of_activated from gold_activation_funnel"
        " where dimension = 'acquisition_channel' and segment = 'paid_search'"
    ) == [(0.0, None)]


def test_small_segments_are_flagged(query):
    assert query("select bool_and(low_n) from gold_activation_funnel") == [(True,)]
