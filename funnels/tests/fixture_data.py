"""Hand-built raw snapshot used by every unit test.

Ten users, two features, one orphan event. Every expected number asserted in
the Silver and Gold tests is derived by hand from this data; see the fixture
table in docs/superpowers/plans/2026-10-10-funnel-analytics.md.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from funnels.config import Params

# Both observation ends are pinned so that "window elapsed" is deterministic.
FIXTURE_PARAMS = Params(usage_end=date(2024, 6, 30), conversion_end=date(2024, 6, 30))

SIGNUPS = [
    # user_id, signup_date, company_size, industry
    (1, "2024-01-10", "1-10", "technology"),
    (2, "2024-01-10", "11-50", "finance"),
    (3, "2024-01-10", "1-10", "technology"),
    (4, "2024-01-10", "11-50", "retail"),
    (5, "2024-02-01", "1-10", "technology"),
    (6, "2024-02-01", "11-50", "finance"),
    (7, "2024-05-30", "1-10", "retail"),
    (8, "2024-06-20", "1-10", "retail"),
    (9, "2024-01-10", "201-1000", "manufacturing"),
    (10, "2023-12-20", "1-10", "education"),
]

# user 5 has no attribution row on purpose.
ATTRIBUTION = [
    (1, "referral", "user_invite"),
    (2, "referral", "user_invite"),
    (3, "paid_search", "google_brand"),
    (4, "paid_search", "google_brand"),
    (6, "referral", "affiliate"),
    (7, "organic_search", "seo_blog"),
    (8, "organic_search", "seo_blog"),
    (9, "paid_social", "linkedin_cold"),
    (10, "organic_search", "seo_docs"),
]

CONVERSIONS = [
    # user_id, conversion_date, plan, mrr, signup_date, days_to_convert
    (1, "2024-01-15", "pro", 100, "2024-01-10", 5),
    (3, "2024-01-24", "enterprise", 1000, "2024-01-10", 14),
    (4, "2024-01-30", "pro", 200, "2024-01-10", 20),
    (5, "2024-03-12", "pro", 150, "2024-02-01", 40),
]

SUBSCRIPTION_EVENTS = [
    # event_id, user_id, event_date, event_type, plan, mrr, previous_plan, previous_mrr
    (1, 1, "2024-01-15", "subscription_started", "pro", 100, None, None),
    (2, 3, "2024-01-24", "subscription_started", "enterprise", 1000, None, None),
    (3, 4, "2024-01-30", "subscription_started", "pro", 200, None, None),
    (4, 5, "2024-03-12", "subscription_started", "pro", 150, None, None),
    (5, 3, "2024-03-01", "plan_downgraded", "pro", 300, "enterprise", 1000),
    (6, 4, "2024-02-10", "seats_expanded", "pro", 250, "pro", 200),
    (7, 4, "2024-02-10", "seats_contracted", "pro", 220, "pro", 250),
    (8, 1, "2024-04-01", "subscription_cancelled", None, 0, "pro", 100),
]

USAGE = [
    # timestamp, user_id, feature_id, feature_name, event_type
    ("2024-01-10 09:00:00", 1, 1, "real_time_collab", "view"),
    ("2024-01-11 10:00:00", 1, 1, "real_time_collab", "use"),
    ("2024-01-12 10:00:00", 1, 1, "real_time_collab", "use"),
    ("2024-03-05 10:00:00", 1, 1, "real_time_collab", "use"),  # day 55, after conversion
    ("2024-01-10 11:00:00", 2, 1, "real_time_collab", "use"),
    ("2024-01-13 11:00:00", 2, 1, "real_time_collab", "share"),
    ("2024-01-25 09:00:00", 4, 1, "real_time_collab", "use"),  # day 15: not early
    ("2024-02-09 09:00:00", 4, 1, "real_time_collab", "use"),  # day 30
    ("2024-02-01 09:00:00", 5, 1, "real_time_collab", "use"),
    ("2024-02-02 09:00:00", 5, 2, "ai_insights", "use"),
    ("2024-02-03 09:00:00", 5, 1, "real_time_collab", "use"),
    ("2024-03-02 09:00:00", 5, 1, "real_time_collab", "use"),  # day 30
    ("2024-03-05 09:00:00", 5, 1, "real_time_collab", "use"),  # day 33
    ("2024-02-01 12:00:00", 6, 1, "real_time_collab", "view"),
    *[(f"2024-01-{10 + d:02d} 08:00:00", 9, 1, "real_time_collab", "use") for d in range(7)],
    ("2024-02-09 08:00:00", 9, 1, "real_time_collab", "use"),  # day 30
    ("2024-02-19 08:00:00", 9, 1, "real_time_collab", "use"),  # day 40
    ("2024-02-01 08:00:00", 999, 1, "real_time_collab", "use"),  # orphan: no such user
]

RELEASES = [
    (1, "real_time_collab", "2024-01-01", "v1.0"),
    (1, "real_time_collab", "2024-03-01", "v2.0"),
    (2, "ai_insights", "2024-02-01", "v1.0"),
]


def _jsonl(path: Path, keys: tuple[str, ...], rows: list[tuple]) -> None:
    lines = [json.dumps(dict(zip(keys, row))) for row in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_raw(directory: Path) -> None:
    """Write the six raw files, in the same shapes as data/raw."""
    directory.mkdir(parents=True, exist_ok=True)
    # The real signups file also has an email column.
    lines = [
        json.dumps(
            {"user_id": u, "email": f"user{u}@example.com", "signup_date": d,
             "company_size": s, "industry": i}
        )
        for u, d, s, i in SIGNUPS
    ]
    (directory / "user_signups.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    # first_touch_date is one day before signup for every attributed user.
    signup = {u: d for u, d, _, _ in SIGNUPS}
    attr_lines = []
    for u, ch, camp in ATTRIBUTION:
        y, m, d = (int(x) for x in signup[u].split("-"))
        touch = date.fromordinal(date(y, m, d).toordinal() - 1).isoformat()
        attr_lines.append(
            json.dumps({"user_id": u, "channel": ch, "campaign": camp, "first_touch_date": touch})
        )
    (directory / "marketing_attribution.jsonl").write_text(
        "\n".join(attr_lines) + "\n", encoding="utf-8"
    )
    conv_lines = [
        json.dumps(
            {"user_id": u, "conversion_date": cd, "plan": p, "mrr": m, "signup_date": sd,
             "days_to_convert": n, "used_real_time_collab": False}
        )
        for u, cd, p, m, sd, n in CONVERSIONS
    ]
    (directory / "conversions.jsonl").write_text("\n".join(conv_lines) + "\n", encoding="utf-8")
    _jsonl(
        directory / "subscription_events.jsonl",
        ("event_id", "user_id", "event_date", "event_type", "plan", "mrr",
         "previous_plan", "previous_mrr"),
        SUBSCRIPTION_EVENTS,
    )
    _jsonl(
        directory / "feature_usage_events.jsonl",
        ("timestamp", "user_id", "feature_id", "feature_name", "event_type"),
        USAGE,
    )
    releases = [
        {"id": i, "name": n, "release_date": d, "version": v} for i, n, d, v in RELEASES
    ]
    (directory / "feature_releases.json").write_text(
        json.dumps(releases, indent=2), encoding="utf-8"
    )
