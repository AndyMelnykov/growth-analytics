from __future__ import annotations

import pytest

COLUMNS = (
    "converted, days_to_convert, conversion_plan, conversion_mrr, first_view_day, first_use_day,"
    " first_share_day, second_feature_day, early_events, early_active_days, early_features_used,"
    " early_shares, late_active_days"
)


def journey(query, user_id):
    return query(f"select {COLUMNS} from silver_user_journey where user_id = {user_id}")[0]


def flags(query, user_id):
    return query(
        "select early_window_observed, conversion_window_observed, retention_window_observed,"
        " converted_in_window, free_at_landmark, landmark_member, converted_after_landmark"
        f" from silver_user_journey where user_id = {user_id}"
    )[0]


def test_one_row_per_user_even_without_events(query):
    assert query("select count(*), count(distinct user_id) from silver_user_journey") == [(10, 10)]


def test_converter_with_early_use_and_late_event(query):
    # u1: converted day 5; f1 view d0, use d1, d2, and a use on d55 (late window is [28, 56))
    assert journey(query, 1) == (True, 5, "pro", 100, 0, 1, None, None, 3, 3, 1, 0, 1)


def test_non_converter_with_use_and_share(query):
    assert journey(query, 2) == (False, None, None, None, None, 0, 3, None, 2, 2, 1, 1, 0)


def test_user_with_no_events_keeps_zero_counts_not_nulls(query):
    assert journey(query, 3) == (True, 14, "enterprise", 1000, None, None, None, None, 0, 0, 0, 0, 0)
    assert journey(query, 10) == (False, None, None, None, None, None, None, None, 0, 0, 0, 0, 0)


def test_use_on_day_15_is_not_early(query):
    # u4: uses on d15 and d30 only
    assert journey(query, 4) == (True, 20, "pro", 200, None, 15, None, None, 0, 0, 0, 0, 1)


def test_second_feature_day_is_first_use_of_a_second_distinct_feature(query):
    # u5: f1 use d0, f2 use d1 -> second feature on day 1; late events d30, d33
    assert journey(query, 5) == (True, 40, "pro", 150, None, 0, None, 1, 3, 3, 2, 0, 2)


def test_view_only_user_has_no_first_use_and_no_features_used(query):
    assert journey(query, 6) == (False, None, None, None, 0, None, None, None, 1, 1, 0, 0, 0)


def test_seven_early_active_days(query):
    assert journey(query, 9) == (False, None, None, None, None, 0, None, None, 7, 7, 1, 0, 2)


def test_window_flags_converted_on_day_5_is_not_free_at_landmark(query):
    # (early, conv, retention observed, converted_in_window, free_at_landmark, member, after)
    assert flags(query, 1) == (True, True, True, True, False, False, False)


def test_window_flags_converted_exactly_on_day_14_is_still_free_and_converts_after(query):
    assert flags(query, 3) == (True, True, True, True, True, True, True)


def test_window_flags_converted_on_day_40_is_after_landmark_not_in_30_day_window(query):
    assert flags(query, 5) == (True, True, True, False, True, True, True)


def test_recent_signup_with_closed_retention_and_landmark_windows(query):
    # u7 signed up 2024-05-30: 14 and 30 day windows elapsed, 44 and 56 day windows not
    assert flags(query, 7) == (True, True, False, False, True, False, False)


def test_newest_signup_has_no_elapsed_windows(query):
    # u8 signed up 2024-06-20, 10 days before the observation end
    assert flags(query, 8) == (False, False, False, False, True, False, False)


@pytest.mark.parametrize("user_id", [2, 3, 4, 5, 6, 9, 10])
def test_landmark_members(query, user_id):
    assert flags(query, user_id)[5] is True


@pytest.mark.parametrize("user_id", [1, 7, 8])
def test_not_landmark_members(query, user_id):
    assert flags(query, user_id)[5] is False
