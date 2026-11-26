"""Hand-built clean raw snapshot used by every data_checks test.

Four users, two features. It passes every check under FIXTURE_CONFIG; tests make
one edit to it and assert that exactly the targeted check notices. The usage rows
are deliberately not in time order, because the real file is not either.
"""
from __future__ import annotations

import copy
import json
from datetime import date
from pathlib import Path

from data_checks.config import CheckConfig
from data_checks.model import CheckResult
from data_checks.registry import get_check
from data_checks.snapshot import METADATA_FILE, SOURCE_FILES, Snapshot

CLEAN: dict[str, list[dict]] = {
    "user_signups": [
        {"user_id": 1, "email": "user1@example.com", "signup_date": "2024-01-10", "company_size": "1-10", "industry": "technology"},
        {"user_id": 2, "email": "user2@example.com", "signup_date": "2024-01-10", "company_size": "11-50", "industry": "finance"},
        {"user_id": 3, "email": "user3@example.com", "signup_date": "2024-02-01", "company_size": "51-200", "industry": "retail"},
        {"user_id": 4, "email": "user4@example.com", "signup_date": "2024-02-01", "company_size": "1-10", "industry": "education"},
    ],
    # user 4 is unattributed on purpose
    "marketing_attribution": [
        {"user_id": 1, "channel": "referral", "campaign": "user_invite", "first_touch_date": "2024-01-05"},
        {"user_id": 2, "channel": "paid_search", "campaign": "google_brand", "first_touch_date": "2024-01-10"},
        {"user_id": 3, "channel": "organic_search", "campaign": "seo_blog", "first_touch_date": "2024-01-20"},
    ],
    "conversions": [
        {"user_id": 1, "conversion_date": "2024-01-20", "plan": "pro", "mrr": 49, "signup_date": "2024-01-10", "days_to_convert": 10, "used_real_time_collab": True},
        {"user_id": 2, "conversion_date": "2024-03-10", "plan": "enterprise", "mrr": 2000, "signup_date": "2024-01-10", "days_to_convert": 60, "used_real_time_collab": False},
    ],
    "subscription_events": [
        {"event_id": 1, "user_id": 1, "event_date": "2024-01-20", "event_type": "subscription_started", "plan": "pro", "mrr": 49, "previous_plan": None, "previous_mrr": None},
        {"event_id": 2, "user_id": 2, "event_date": "2024-03-10", "event_type": "subscription_started", "plan": "enterprise", "mrr": 2000, "previous_plan": None, "previous_mrr": None},
        {"event_id": 3, "user_id": 1, "event_date": "2024-03-01", "event_type": "seats_expanded", "plan": "pro", "mrr": 98, "previous_plan": "pro", "previous_mrr": 49},
        {"event_id": 4, "user_id": 1, "event_date": "2024-05-01", "event_type": "plan_upgraded", "plan": "enterprise", "mrr": 500, "previous_plan": "pro", "previous_mrr": 98},
        {"event_id": 5, "user_id": 2, "event_date": "2024-06-01", "event_type": "subscription_cancelled", "plan": None, "mrr": 0, "previous_plan": "enterprise", "previous_mrr": 2000},
    ],
    "feature_usage_events": [
        {"timestamp": "2024-03-05 09:00:00", "user_id": 1, "feature_id": 2, "feature_name": "ai_insights", "event_type": "use"},
        {"timestamp": "2024-01-18 10:00:00", "user_id": 1, "feature_id": 1, "feature_name": "real_time_collab", "event_type": "view"},
        {"timestamp": "2024-02-02 12:00:00", "user_id": 3, "feature_id": 1, "feature_name": "real_time_collab", "event_type": "use"},
        {"timestamp": "2024-03-02 08:00:00", "user_id": 2, "feature_id": 2, "feature_name": "ai_insights", "event_type": "share"},
    ],
    "feature_releases": [
        {"id": 1, "name": "real_time_collab", "release_date": "2024-01-15", "version": "v1.0"},
        {"id": 2, "name": "ai_insights", "release_date": "2024-03-01", "version": "v1.0"},
        {"id": 1, "name": "real_time_collab", "release_date": "2024-07-01", "version": "v2.0"},
    ],
}

CLEAN_METADATA: dict = {
    "users_with_real_time_collab": [1, 3],
    "percentage": 0.5,
    "total_users": 4,
    "per_feature_adoption": {"real_time_collab": 2, "ai_insights": 2},
}

FIXTURE_CONFIG = CheckConfig(
    as_of=date(2024, 12, 31),
    max_gap_days=30,
    unattributed_share_band=(0.0, 0.5),
    best_channel=None,
    worst_channels=None,
)

_DEFAULT = object()


def make_snapshot(metadata: object = _DEFAULT, **sources: list[dict]) -> Snapshot:
    """Clean snapshot with any source (or the metadata) replaced."""
    unknown = set(sources) - set(SOURCE_FILES)
    if unknown:
        raise ValueError(f"unknown sources: {sorted(unknown)}")
    records = {name: copy.deepcopy(sources.get(name, CLEAN[name])) for name in SOURCE_FILES}
    meta = copy.deepcopy(CLEAN_METADATA) if metadata is _DEFAULT else metadata
    return Snapshot(records=records, metadata=meta)


def edit(source: str, index: int, **changes: object) -> list[dict]:
    """Deep copy of a clean source with row `index` updated."""
    rows = copy.deepcopy(CLEAN[source])
    rows[index].update(changes)
    return rows


def append(source: str, row: dict) -> list[dict]:
    rows = copy.deepcopy(CLEAN[source])
    rows.append(copy.deepcopy(row))
    return rows


def remove(source: str, index: int) -> list[dict]:
    rows = copy.deepcopy(CLEAN[source])
    del rows[index]
    return rows


def write_raw(
    path: Path,
    records: dict[str, list[dict]] | None = None,
    metadata: dict | None = CLEAN_METADATA,
) -> Path:
    """Write the sources in raw-file format (JSONL, releases as a JSON array)."""
    path.mkdir(parents=True, exist_ok=True)
    data = {name: (records or {}).get(name, CLEAN[name]) for name in SOURCE_FILES}
    for name, file_name in SOURCE_FILES.items():
        rows = data[name]
        if file_name.endswith(".jsonl"):
            text = "".join(json.dumps(row) + "\n" for row in rows)
        else:
            text = json.dumps(rows, indent=2)
        (path / file_name).write_text(text, encoding="utf-8")
    if metadata is not None:
        (path / METADATA_FILE).write_text(json.dumps(metadata), encoding="utf-8")
    return path


def run(check_id: str, snap: Snapshot, cfg: CheckConfig = FIXTURE_CONFIG) -> CheckResult:
    return get_check(check_id).evaluate(snap, cfg)
