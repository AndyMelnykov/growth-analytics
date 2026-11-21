"""Invariants and sanity checks against the real data/raw snapshot.

Skipped when the snapshot is not present. The sanity checks encode the signals
engineered into the synthetic data (docs/adr/0004): they check direction and
rank, not exact values.
"""
from __future__ import annotations

import pytest

from funnels.config import DEFAULT_RAW_DIR
from funnels.warehouse import build

pytestmark = pytest.mark.skipif(
    not (DEFAULT_RAW_DIR / "user_signups.jsonl").exists(), reason="data/raw not present"
)


@pytest.fixture(scope="module")
def real():
    con = build(DEFAULT_RAW_DIR)
    yield con
    con.close()


def scalar(con, sql):
    return con.execute(sql).fetchone()[0]


def test_bronze_row_counts(real):
    expected = {
        "user_signups": 5000,
        "marketing_attribution": 4774,
        "conversions": 1526,
        "subscription_events": 2651,
        "feature_usage_events": 48666,
        "feature_releases": 8,
    }
    for view, count in expected.items():
        assert scalar(real, f"select count(*) from {view}") == count, view


def test_keys_are_unique(real):
    assert scalar(real, "select count(*) - count(distinct user_id) from user_signups") == 0
    assert scalar(real, "select count(*) - count(distinct user_id) from marketing_attribution") == 0
    assert scalar(real, "select count(*) - count(distinct user_id) from conversions") == 0


def test_every_conversion_matches_one_subscription_start(real):
    assert scalar(
        real,
        "select count(*) from conversions c join subscription_events s"
        " on s.user_id = c.user_id and s.event_type = 'subscription_started'"
        " and s.event_date = c.conversion_date and s.mrr = c.mrr",
    ) == 1526


def test_denormalized_days_to_convert_agrees_with_dates(real):
    assert scalar(
        real,
        "select count(*) from conversions c join user_signups s using (user_id)"
        " where date_diff('day', s.signup_date, c.conversion_date) <> c.days_to_convert",
    ) == 0


def test_no_usage_before_signup_or_before_the_feature_existed(real):
    assert scalar(real, "select count(*) from silver_usage_events") == 48666  # no orphans
    assert scalar(real, "select count(*) from silver_usage_events where day_index < 0") == 0
    assert scalar(
        real,
        "select count(*) from silver_usage_events e join silver_feature_states s"
        " on s.feature_id = e.feature_id and s.version = 'v1.0'"
        " where e.event_date < s.effective_from",
    ) == 0


def test_silver_and_gold_reconcile_with_signups(real):
    assert scalar(real, "select count(*) from silver_user_dim") == 5000
    assert scalar(real, "select count(*) from silver_user_journey") == 5000
    assert scalar(
        real, "select signups from gold_acquisition_funnel where level = 'total'"
    ) == 5000
    assert scalar(
        real, "select sum(signups) from gold_acquisition_funnel where level = 'channel'"
    ) == 5000
    assert scalar(
        real, "select count(*) from silver_user_dim where acquisition_channel = 'unattributed'"
    ) == 226


def test_observation_ends_come_from_the_data(real):
    assert str(real.execute("select usage_end, conversion_end from silver_extent").fetchone()) == (
        "(datetime.date(2024, 12, 30), datetime.date(2024, 11, 2))"
    )


def test_every_signup_has_an_elapsed_30_day_conversion_window(real):
    # latest signup 2024-09-15 + 30 days < 2024-11-02, so nobody is dropped from the funnel
    assert scalar(
        real, "select observed_signups from gold_acquisition_funnel where level = 'total'"
    ) == 5000


def test_funnel_stages_are_ordered(real):
    row = real.execute(
        "select signups, activated, multi_feature, converted_in_window"
        " from gold_activation_funnel where dimension = 'all'"
    ).fetchone()
    signups, activated, multi_feature, converted = row
    assert signups == 5000
    assert 0 < multi_feature < activated < signups
    assert 0 < converted < signups


def test_engineered_channel_signal_referral_best_outbound_and_paid_social_worst(real):
    rates = dict(
        real.execute(
            "select acquisition_channel, conversion_rate from gold_acquisition_funnel"
            " where level = 'channel' and acquisition_channel <> 'unattributed'"
        ).fetchall()
    )
    ranked = sorted(rates, key=rates.get, reverse=True)
    assert ranked[0] == "referral"
    assert set(ranked[-2:]) == {"outbound", "paid_social"}


def test_habit_curve_rises_with_early_activity(real):
    rates = [
        r[0]
        for r in real.execute(
            "select retained_rate from gold_habit_curve where cohort = 'all_users'"
            " and not low_n order by bucket_order"
        ).fetchall()
    ]
    assert len(rates) >= 3
    assert rates == sorted(rates)
    assert rates[-1] - rates[0] > 0.5


def test_habit_threshold_is_found_for_all_users(real):
    bucket = scalar(
        real, "select threshold_bucket from gold_habit_threshold where cohort = 'all_users'"
    )
    assert bucket in {"1", "2-3", "4-6"}


def test_aha_cohort_excludes_everyone_who_converted_before_the_landmark(real):
    assert scalar(
        real,
        "select count(*) from silver_user_journey"
        " where landmark_member and converted and days_to_convert < 14",
    ) == 0
    # and the aha cohorts partition the landmark cohort for every feature
    members = scalar(real, "select count(*) from silver_user_journey where landmark_member")
    per_feature = real.execute(
        "select feature_name, sum(users) from gold_aha_features group by feature_name"
    ).fetchall()
    assert len(per_feature) == 6
    assert all(total == members for _, total in per_feature)
