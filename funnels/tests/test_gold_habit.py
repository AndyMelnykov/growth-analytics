from __future__ import annotations

from datetime import date

import pytest

# Base (early and retention windows elapsed): u1..u6, u9, u10. u7 and u8 are excluded.
# Retained (>= 2 active days in days 28..55): u5 (d30, d33) and u9 (d30, d40).


def curve(query, cohort):
    return query(
        "select early_active_days_bucket, users, retained_users from gold_habit_curve"
        f" where cohort = '{cohort}' order by bucket_order"
    )


def test_habit_curve_all_users(query):
    assert curve(query, "all_users") == [("0", 3, 0), ("1", 1, 0), ("2-3", 3, 1), ("7+", 1, 1)]


def test_habit_curve_free_at_landmark_drops_users_converted_early(query):
    # u1 converted on day 5 and falls out of the '2-3' bucket
    assert curve(query, "free_at_landmark") == [("0", 3, 0), ("1", 1, 0), ("2-3", 2, 1), ("7+", 1, 1)]


def test_habit_curve_rates_and_low_n(query):
    rate, low, high, low_n = query(
        "select retained_rate, retained_ci_low, retained_ci_high, low_n from gold_habit_curve"
        " where cohort = 'all_users' and early_active_days_bucket = '2-3'"
    )[0]
    assert rate == pytest.approx(1 / 3)
    assert low < rate < high
    assert low_n is True


def test_threshold_is_null_when_no_bucket_reaches_the_target(query):
    # with so few users no Wilson lower bound reaches 0.80
    assert query(
        "select cohort, target_retention, threshold_bucket from gold_habit_threshold order by cohort"
    ) == [("all_users", 0.8, None), ("free_at_landmark", 0.8, None)]


def test_usage_retention_counts_users_active_in_each_week(query):
    # January 2024 signups: u1, u2, u3, u4, u9
    weeks = {
        w: (n, a)
        for w, n, a in query(
            "select week_n, cohort_users, active_users from gold_usage_retention"
            " where signup_month = date '2024-01-01'"
        )
    }
    assert weeks[0] == (5, 3)  # u1, u2, u9 active in days 0..6
    assert weeks[4] == (5, 2)  # u4 (d30), u9 (d30)
    assert weeks[7] == (5, 1)  # u1 (d55)
    # February 2024 signups: u5, u6
    assert query(
        "select week_n, cohort_users, active_users from gold_usage_retention"
        " where signup_month = date '2024-02-01' and week_n in (0, 4) order by week_n"
    ) == [(0, 2, 2), (4, 2, 1)]


def test_usage_retention_stops_at_the_last_fully_elapsed_week(query):
    # u7 signed up 2024-05-30; 2024-06-30 is 31 days later, so weeks 0..3 have elapsed
    assert query(
        "select max(week_n) from gold_usage_retention where signup_month = date '2024-05-01'"
    ) == [(3,)]


def test_user_with_no_events_stays_in_the_denominator(query):
    # u10 (December 2023 signup, no events at all) is the only user in its month
    assert query(
        "select cohort_users, active_users, retention_rate from gold_usage_retention"
        " where signup_month = date '2023-12-01' and week_n = 0"
    ) == [(1, 0, 0.0)]


def test_retention_rate_and_interval(query):
    rate, low, high = query(
        "select retention_rate, retention_ci_low, retention_ci_high from gold_usage_retention"
        " where signup_month = date '2024-01-01' and week_n = 0"
    )[0]
    assert rate == pytest.approx(0.6)
    assert low < rate < high


def test_signup_months_are_dates(query):
    assert query("select min(signup_month) from gold_usage_retention") == [(date(2023, 12, 1),)]
