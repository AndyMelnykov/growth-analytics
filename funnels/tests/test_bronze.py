from __future__ import annotations

from datetime import date, datetime


def test_row_counts(query):
    counts = {
        "user_signups": 10,
        "marketing_attribution": 9,
        "conversions": 4,
        "subscription_events": 8,
        "feature_usage_events": 24,  # 23 real + 1 orphan
        "feature_releases": 3,
    }
    for view, expected in counts.items():
        assert query(f"select count(*) from {view}") == [(expected,)], view


def test_column_types_are_typed_not_strings(query):
    assert query(
        "select typeof(signup_date) from user_signups limit 1"
    ) == [("DATE",)]
    assert query(
        "select typeof(event_timestamp), typeof(event_date) from feature_usage_events limit 1"
    ) == [("TIMESTAMP", "DATE")]
    assert query("select typeof(mrr) from conversions limit 1") == [("INTEGER",)]


def test_usage_view_renames_timestamp_and_derives_date(query):
    assert query(
        "select event_timestamp, event_date from feature_usage_events"
        " where user_id = 1 order by event_timestamp limit 1"
    ) == [(datetime(2024, 1, 10, 9, 0), date(2024, 1, 10))]


def test_release_view_renames_id_and_name(query):
    assert query(
        "select feature_id, feature_name, release_date, version from feature_releases"
        " order by feature_id, release_date"
    ) == [
        (1, "real_time_collab", date(2024, 1, 1), "v1.0"),
        (1, "real_time_collab", date(2024, 3, 1), "v2.0"),
        (2, "ai_insights", date(2024, 2, 1), "v1.0"),
    ]


def test_null_subscription_fields_stay_null(query):
    assert query(
        "select plan, mrr, previous_plan, previous_mrr from subscription_events"
        " where event_type = 'subscription_cancelled'"
    ) == [(None, 0, "pro", 100)]
