from __future__ import annotations

from datetime import date

from funnels.warehouse import build


def test_feature_states_close_old_versions_and_open_current(query):
    assert query(
        "select feature_name, version, effective_from, effective_to, is_current, is_enabled"
        " from silver_feature_states order by feature_id, effective_from"
    ) == [
        ("real_time_collab", "v1.0", date(2024, 1, 1), date(2024, 3, 1), False, True),
        ("real_time_collab", "v2.0", date(2024, 3, 1), date(9999, 12, 31), True, True),
        ("ai_insights", "v1.0", date(2024, 2, 1), date(9999, 12, 31), True, True),
    ]


def test_feature_state_record_hash_is_md5_of_name_and_version(query):
    assert query(
        "select record_hash = md5('ai_insights|v1.0') from silver_feature_states"
        " where feature_name = 'ai_insights'"
    ) == [(True,)]


def test_user_dim_has_one_row_per_signup(query):
    assert query("select count(*), count(distinct user_id) from silver_user_dim") == [(10, 10)]


def test_user_without_attribution_is_unattributed(query):
    assert query(
        "select acquisition_channel, acquisition_campaign from silver_user_dim where user_id = 5"
    ) == [("unattributed", "unattributed")]


def test_user_dim_current_state_from_latest_subscription_event(query):
    rows = dict(
        (u, (p, m))
        for u, p, m in query(
            "select user_id, current_plan, current_mrr from silver_user_dim"
        )
    )
    assert rows[1] == ("churned", 0)  # cancelled
    assert rows[2] == ("free", 0)  # never converted
    assert rows[3] == ("pro", 300)  # downgraded from enterprise
    assert rows[5] == ("pro", 150)


def test_same_day_subscription_events_are_ordered_by_event_id(query):
    # user 4 has seats_expanded (id 6, $250) then seats_contracted (id 7, $220) on one date
    assert query("select current_plan, current_mrr from silver_user_dim where user_id = 4") == [
        ("pro", 220)
    ]


def test_usage_events_drop_orphans_and_add_day_index(query):
    assert query("select count(*) from silver_usage_events") == [(23,)]
    assert query("select count(*) from silver_usage_events where user_id = 999") == [(0,)]
    assert query(
        "select list(day_index order by event_timestamp) from silver_usage_events where user_id = 1"
    ) == [([0, 1, 2, 55],)]


def test_extent_uses_param_overrides(query):
    assert query("select usage_end, conversion_end from silver_extent") == [
        (date(2024, 6, 30), date(2024, 6, 30))
    ]


def test_extent_defaults_to_latest_dates_in_the_data(raw_dir):
    con = build(raw_dir)  # default Params: no overrides
    try:
        assert con.execute("select usage_end, conversion_end from silver_extent").fetchall() == [
            (date(2024, 3, 5), date(2024, 3, 12))
        ]
    finally:
        con.close()
