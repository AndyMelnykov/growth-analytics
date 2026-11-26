from __future__ import annotations

from datetime import date, datetime

import pytest

from data_checks.snapshot import (
    as_date,
    as_int,
    as_timestamp,
    event_date,
    load_snapshot,
    row_counts,
)
from data_checks.tests.fixture_data import CLEAN_METADATA, write_raw


def test_loads_every_source_from_a_valid_dir(tmp_path):
    snap = load_snapshot(write_raw(tmp_path))
    assert row_counts(snap) == {
        "user_signups": 4,
        "marketing_attribution": 3,
        "conversions": 2,
        "subscription_events": 5,
        "feature_usage_events": 4,
        "feature_releases": 3,
    }
    assert snap.missing_files == () and snap.parse_errors == {}
    assert snap.metadata == CLEAN_METADATA


def test_missing_file_is_recorded_not_raised(tmp_path):
    raw = write_raw(tmp_path)
    (raw / "conversions.jsonl").unlink()
    snap = load_snapshot(raw)
    assert snap.missing_files == ("conversions.jsonl",) and snap.records["conversions"] == []


def test_bad_line_is_recorded_and_other_lines_kept(tmp_path):
    raw = write_raw(tmp_path)
    with open(raw / "user_signups.jsonl", "a", encoding="utf-8") as f:
        f.write("\nnot json\n[1, 2]\n")
    snap = load_snapshot(raw)
    assert len(snap.records["user_signups"]) == 4  # blank line skipped
    assert len(snap.parse_errors["user_signups"]) == 2  # non-JSON and non-object
    assert snap.parse_errors["user_signups"][0].startswith("line 6:")


def test_releases_must_be_a_json_array(tmp_path):
    raw = write_raw(tmp_path)
    (raw / "feature_releases.json").write_text('{"id": 1}')
    snap = load_snapshot(raw)
    assert snap.records["feature_releases"] == [] and len(snap.parse_errors["feature_releases"]) == 1


def test_absent_metadata_is_none(tmp_path):
    assert load_snapshot(write_raw(tmp_path, metadata=None)).metadata is None


def test_raw_dir_that_does_not_exist_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_snapshot(tmp_path / "nope")


def test_value_parsers_are_strict():
    assert as_int(5) == 5 and as_int(True) is None and as_int("5") is None
    assert as_date("2024-01-10") == date(2024, 1, 10)
    assert as_date("2024-1-10") is None and as_date(None) is None
    assert as_timestamp("2024-01-18 10:00:00") == datetime(2024, 1, 18, 10)
    assert as_timestamp("2024-01-18T10:00:00") is None
    assert event_date("2024-01-18 10:00:00") == date(2024, 1, 18)
    assert event_date("2024-01-18") == date(2024, 1, 18)
