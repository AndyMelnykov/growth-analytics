from __future__ import annotations

import pytest

# Landmark members: u2, u3, u4, u5, u6, u9, u10 (u1 converted on day 5; u7, u8 outcome window open).
# Converted after landmark: u3 (day 14), u4 (day 20), u5 (day 40).


def feature_cohorts(query, feature):
    return query(
        "select cohort, users, converted from gold_aha_features"
        f" where feature_name = '{feature}' order by cohort"
    )


def test_real_time_collab_cohorts(query):
    assert feature_cohorts(query, "real_time_collab") == [
        ("available_not_used", 3, 2),  # u3, u4 (used only on day 15+), u6 (view only)
        ("not_available", 1, 0),  # u10 signed up before the 2024-01-01 release
        ("used_feature", 3, 1),  # u2, u5, u9
    ]


def test_ai_insights_cohorts_distinguish_not_released_from_not_used(query):
    assert feature_cohorts(query, "ai_insights") == [
        ("available_not_used", 1, 0),  # u6 signed up on the release date
        ("not_available", 5, 2),  # January signups could not have used it
        ("used_feature", 1, 1),  # u5
    ]


def test_cohorts_partition_the_landmark_cohort(query):
    assert query(
        "select feature_name, sum(users) from gold_aha_features group by feature_name"
        " order by feature_name"
    ) == [("ai_insights", 7), ("real_time_collab", 7)]


def test_user_converted_before_landmark_is_in_no_cohort(query):
    # u1 used real_time_collab early but converted on day 5: it must not inflate used_feature
    assert query(
        "select users from gold_aha_features"
        " where feature_name = 'real_time_collab' and cohort = 'used_feature'"
    ) == [(3,)]


def test_feature_lift(query):
    row = query(
        "select used_users, used_converted, baseline_users, baseline_converted,"
        " rate_diff, lift_ratio, ci_excludes_zero, low_n"
        " from gold_aha_feature_lift where feature_name = 'real_time_collab'"
    )[0]
    assert row[:4] == (3, 1, 3, 2)
    assert row[4] == pytest.approx(-1 / 3)
    assert row[5] == pytest.approx(0.5)
    assert row[6] is False
    assert row[7] is True


def test_lift_view_has_one_row_per_feature_with_both_cohorts(query):
    assert query("select feature_name from gold_aha_feature_lift order by feature_name") == [
        ("ai_insights",),
        ("real_time_collab",),
    ]


def test_behavior_features_used(query):
    assert query(
        "select level, users, converted from gold_aha_behaviors"
        " where behavior = 'early_features_used' order by level_order"
    ) == [("0", 4, 2), ("1", 2, 0), ("2", 1, 1)]


def test_behavior_active_days_omits_empty_buckets(query):
    assert query(
        "select level, users, converted from gold_aha_behaviors"
        " where behavior = 'early_active_days' order by level_order"
    ) == [("0", 3, 2), ("1", 1, 0), ("2-3", 2, 1), ("7+", 1, 0)]


def test_behavior_shared(query):
    assert query(
        "select level, users, converted from gold_aha_behaviors"
        " where behavior = 'early_shared' order by level_order"
    ) == [("no", 6, 3), ("yes", 1, 0)]


def test_behavior_rates_have_intervals(query):
    rate, low, high = query(
        "select conversion_rate, conversion_ci_low, conversion_ci_high from gold_aha_behaviors"
        " where behavior = 'early_features_used' and level = '0'"
    )[0]
    assert rate == pytest.approx(0.5)
    assert low < rate < high
