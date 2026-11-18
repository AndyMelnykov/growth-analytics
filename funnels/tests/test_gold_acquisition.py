from __future__ import annotations

from datetime import date

import pytest

CHANNEL_SQL = (
    "select acquisition_channel, signups, observed_signups, activated, converted_in_window,"
    " avg_days_to_convert, new_mrr from gold_acquisition_funnel where level = 'channel'"
    " order by acquisition_channel"
)


def test_channel_rows_use_only_observed_users_for_stage_counts(query):
    assert query(CHANNEL_SQL) == [
        ("organic_search", 3, 2, 0, 0, None, 0),  # u8 is not observed
        ("paid_search", 2, 2, 0, 2, 17.0, 1200),  # u4's first use is day 15
        ("paid_social", 1, 1, 1, 0, None, 0),
        ("referral", 3, 3, 2, 1, 5.0, 100),
        ("unattributed", 1, 1, 1, 0, None, 0),  # u5 converted on day 40: outside the 30-day window
    ]


def test_total_row_reconciles_with_signups_and_channels(query):
    assert query(
        "select level, acquisition_channel, acquisition_campaign, signups, observed_signups,"
        " activated, converted_in_window, avg_days_to_convert, new_mrr"
        " from gold_acquisition_funnel where level = 'total'"
    ) == [("total", "(all)", "(all)", 10, 9, 4, 3, 13.0, 1300)]
    assert query(
        "select sum(signups) from gold_acquisition_funnel where level = 'channel'"
    ) == [(10,)]


def test_campaign_rows(query):
    assert query(
        "select acquisition_channel, acquisition_campaign, signups, converted_in_window"
        " from gold_acquisition_funnel where level = 'campaign' and acquisition_channel = 'referral'"
        " order by acquisition_campaign"
    ) == [("referral", "affiliate", 1, 0), ("referral", "user_invite", 2, 1)]


def test_rates_denominator_is_observed_signups_not_all_signups(query):
    rate, low, high = query(
        "select conversion_rate, conversion_ci_low, conversion_ci_high"
        " from gold_acquisition_funnel where level = 'total'"
    )[0]
    assert rate == pytest.approx(3 / 9)
    assert low < rate < high


def test_enterprise_share_and_avg_mrr(query):
    assert query(
        "select enterprise_share, avg_new_mrr from gold_acquisition_funnel"
        " where level = 'channel' and acquisition_channel = 'paid_search'"
    ) == [(0.5, 600.0)]


def test_rates_are_null_not_errors_when_no_one_converted(query):
    assert query(
        "select conversion_rate, avg_days_to_convert, avg_new_mrr, enterprise_share"
        " from gold_acquisition_funnel where level = 'channel' and acquisition_channel = 'paid_social'"
    ) == [(0.0, None, None, None)]


def test_small_groups_are_flagged(query):
    assert query("select bool_and(low_n) from gold_acquisition_funnel") == [(True,)]


def test_cohorts_by_signup_month(query):
    assert query(
        "select signup_month, acquisition_channel, signups, observed_signups, converted_in_window"
        " from gold_acquisition_cohorts where signup_month = date '2024-01-01'"
        " order by acquisition_channel"
    ) == [
        (date(2024, 1, 1), "paid_search", 2, 2, 2),
        (date(2024, 1, 1), "paid_social", 1, 1, 0),
        (date(2024, 1, 1), "referral", 2, 2, 1),
    ]
    # u8 (June) is unobserved: counted in signups, excluded from the denominator
    assert query(
        "select signups, observed_signups from gold_acquisition_cohorts"
        " where signup_month = date '2024-06-01'"
    ) == [(1, 0)]
    assert query(
        "select conversion_rate, conversion_ci_low from gold_acquisition_cohorts"
        " where signup_month = date '2024-06-01'"
    ) == [(None, None)]
