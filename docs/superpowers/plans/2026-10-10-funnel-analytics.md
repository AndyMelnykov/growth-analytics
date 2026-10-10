# Funnel Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build acquisition, activation, aha-moment and habit-moment analytics over the raw SaaS snapshot in `data/raw`, as SQL views a person can read, query and re-parameterize.

**Architecture:** A small Python package (`funnels/`) opens an in-memory DuckDB, reads the raw JSON/JSONL files directly through typed views (Bronze), builds four Silver tables (user dimension, feature version history, enriched usage events, and a one-row-per-user journey table), and exposes nine Gold views (acquisition, activation, aha, habit, usage retention). Every window and threshold lives in one `Params` dataclass. A CLI prints all Gold views. No Spark, Delta, Airflow, Parquet layers or services.

**Tech Stack:** Python >= 3.10, DuckDB (`duckdb>=1.1,<2`, developed against 1.5.6), pytest. No pandas.

**Spec:** No separate design doc. Requirements come from the conversation that produced this plan (acquisition funnel, activation funnel, aha moments, habit moment, on the existing dataset; "right-sized, not fancy") and from [docs/data_dictionary.md](../../data_dictionary.md), whose Silver table and column names are reused where they exist. [ADR 0009](../../adr/0009-right-sized-funnel-analytics-on-duckdb.md) (Task 1) records the engine decision.

## Why this shape (read first)

The whole raw folder is 62,617 rows (48,666 of them usage events, ~8 MB). ADR 0001/0002 describe PySpark + Delta + per-table jobs; at this size that is pure overhead (JVM start-up alone exceeds the time DuckDB needs to answer every query here). The plan keeps the **medallion vocabulary and the data-dictionary table names** but implements each layer as DuckDB SQL.

Facts about the data, measured on 2026-10-10 and relied on by this plan:

| Fact | Consequence for the design |
|---|---|
| Keys are clean: 5,000 unique `user_id`; attribution unique per user; no duplicate events; every conversion has exactly one matching `subscription_started` (same date, same MRR); no event precedes signup or its feature's release. | Joins need no de-duplication. Tests assert these as invariants so a changed snapshot fails loudly. |
| Converters have **3,011 usage events before conversion and 15,861 after**. | "Used the feature before converting" is biased (immortal time, reverse causation). Aha analysis uses a **landmark design**: behavior in the first 14 days, only for users still free at day 14, outcome = conversion in the next 30 days. |
| Signups end 2024-09-15, conversions end 2024-11-02, usage ends 2024-12-30, `days_to_convert` reaches 95. | Recent cohorts have not had time to convert. Every windowed metric excludes users whose window has not fully elapsed (they are not counted as non-converters). |
| The first event is a `view` for 1,638 users, a `use` for 1,864, a `share` for 602. | "Activation" is defined on `use` events, not on the first event. |
| With the landmark design, early behavior vs later conversion is weak and non-monotonic (conversion 15.0% for 0 early active days, 22.2% for 1, 20.4% for 2-3, 16.7% for 4-6; no feature lift except a *negative* one for `team_analytics`, n = 82). Early activity vs usage 4-8 weeks later is strong (retained: 9% -> 53% -> 71% -> 87% for 0 / 1 / 2-3 / 4-6 active days). | Expect **habit** to be a clear signal and **aha** to be modest. The plan reports confidence intervals and a `low_n` flag everywhere and never claims causation. These are the numbers the finished views produce on the committed data (verified by running the plan's code). |
| Data is synthetic with engineered signals (ADR 0004): referral converts best (41%), outbound and paid_social worst (~22%). | Task 10 asserts these as end-to-end sanity checks. |

## Global Constraints

- Python `>=3.10` (from `pyproject.toml`); runtime dependency only `duckdb>=1.1,<2`, declared as the optional extra `funnels`; dev dependency `pytest>=8`.
- `data/raw/` is read-only input. The pipeline never writes into it.
- Windows, thresholds and observation ends are defined only in `funnels/config.py::Params`. SQL reads them from the one-row `params` table; no literal `14`, `30`, `28`, `56` windows in SQL.
- Silver/Gold table and column names follow [docs/data_dictionary.md](../../data_dictionary.md) where a table exists there (`silver_user_dim`, `silver_feature_states`); new tables are documented in `docs/funnel_metrics.md`.
- Every reported rate has its numerator and denominator beside it; rates that matter also carry a 95% Wilson interval and a `low_n` flag (`n < Params.min_group_size`).
- A window metric only counts users whose window has fully elapsed by the observation end. Unobserved users are excluded from denominators, never counted as non-converters.
- Python run commands use `-o addopts=""` so pytest does not rewrite the tracked `docs/test-reports/junit.xml`.
- Console output is ASCII only (Windows terminals).
- No Claude co-author trailer in commit messages (user preference). Commit messages follow the repo style (`feat(funnels): ...`, `docs: ...`, `test: ...`).
- Work happens on a new branch `feat/funnel-analytics` created from `origin/main` (local `main` is stale).

## Review Focus

The inputs most likely to bite a person using this software, with the behavior a reasonable person expects. Each line is pinned by a test in the task named in brackets.

1. **User converted before the landmark** (fixture `u1`, converted day 5; also events after conversion). Expected: excluded from the aha cohort, never counted as "still free"; post-conversion events never feed the aha outcome. [Task 4, Task 7]
2. **Window not yet elapsed** (fixture `u7`, `u8`). Expected: excluded from the denominators of the metric whose window is open; still counted in raw `signups`; never shown as a non-converter. [Task 4, Task 5, Task 8]
3. **Empty or tiny groups.** Expected: `n = 0` gives NULL rates and NULL intervals (never a division error); a bucket with no users is simply absent; groups under `min_group_size` carry `low_n = true`. [Task 1, Task 5, Task 7]
4. **Users with no usage events at all** (fixture `u3`, `u7`, `u10`). Expected: kept (LEFT JOINs), counted in the zero-activity buckets, so Silver and Gold totals still reconcile with the 5,000 signups. [Task 4, Task 6]
5. **Feature not released when the user signed up** (fixture `u10`, and `ai_insights` for January signups). Expected: `not_available`, never "available but did not use it". [Task 7]
6. **Boundary day.** A user converting on exactly day 14 (fixture `u3`) is still free at the landmark and converts in the outcome window; a `use` on day 13 is early, on day 14 is not. [Task 4]
7. **Signups with no attribution row** (fixture `u5`). Expected: channel and campaign `unattributed`, present in every channel total. [Task 3, Task 5]
8. **Same-day subscription events.** Latest state is decided by `(event_date, event_id)`, not by arrival order (fixture `u4`). [Task 3]
9. **Orphan usage events** (a `user_id` not in signups, fixture `999`). Expected: dropped from Silver, not an error. [Task 3]

---

## File Structure

```
funnels/
  __init__.py
  config.py                 # Params dataclass, default raw dir
  warehouse.py              # build(): params table + run sql/*.sql in order
  report.py                 # GOLD_VIEWS, format_table(), render()
  __main__.py               # python -m funnels
  sql/
    00_macros.sql           # wilson_low/high, diff_low/high, safe_rate, activity_bucket*
    01_bronze.sql           # typed views over data/raw (dictionary names)
    02_silver_core.sql      # silver_feature_states, silver_user_dim, silver_usage_events, silver_extent
    03_silver_journey.sql   # silver_user_journey (one row per user)
    04_gold_acquisition.sql # gold_acquisition_funnel, gold_acquisition_cohorts
    05_gold_activation.sql  # gold_activation_funnel
    06_gold_aha.sql         # gold_aha_features, gold_aha_feature_lift, gold_aha_behaviors
    07_gold_habit.sql       # gold_habit_curve, gold_habit_threshold, gold_usage_retention
  tests/
    __init__.py
    fixture_data.py         # 10 hand-built users; every expected number below is derived from it
    conftest.py             # session fixtures: raw_dir, con, query
    test_warehouse.py       # Task 1
    test_bronze.py          # Task 2
    test_silver_core.py     # Task 3
    test_silver_journey.py  # Task 4
    test_gold_acquisition.py  # Task 5
    test_gold_activation.py   # Task 6
    test_gold_aha.py          # Task 7
    test_gold_habit.py        # Task 8
    test_report.py            # Task 9
    test_real_data.py         # Task 10
docs/adr/0009-right-sized-funnel-analytics-on-duckdb.md   # Task 1
docs/funnel_metrics.md                                    # Task 10
docs/funnel_report.txt                                    # Task 10 (generated snapshot)
```

Modified: `pyproject.toml`, `.gitignore`, `README.md`.

**Fixture design (used by Tasks 2-8).** `fixture_data.py` writes six raw files for 10 users and two features, with observation ends fixed by `Params(usage_end=2024-06-30, conversion_end=2024-06-30)`. Day indexes below are days since signup.

| user | signup | channel / campaign | size / industry | conversion | usage events (day index) |
|---|---|---|---|---|---|
| u1 | 2024-01-10 | referral / user_invite | 1-10 / technology | day 5, pro, $100; cancelled 2024-04-01 | f1 view d0; f1 use d1, d2, d55 |
| u2 | 2024-01-10 | referral / user_invite | 11-50 / finance | never | f1 use d0; f1 share d3 |
| u3 | 2024-01-10 | paid_search / google_brand | 1-10 / technology | day 14, enterprise, $1000; downgraded to pro $300 on 2024-03-01 | none |
| u4 | 2024-01-10 | paid_search / google_brand | 11-50 / retail | day 20, pro, $200; two events 2024-02-10 (ids 6, 7) ending at $220 | f1 use d15, d30 |
| u5 | 2024-02-01 | none (unattributed) | 1-10 / technology | day 40, pro, $150 | f1 use d0; f2 use d1; f1 use d2, d30, d33 |
| u6 | 2024-02-01 | referral / affiliate | 11-50 / finance | never | f1 view d0 |
| u7 | 2024-05-30 | organic_search / seo_blog | 1-10 / retail | never | none |
| u8 | 2024-06-20 | organic_search / seo_blog | 1-10 / retail | never | none |
| u9 | 2024-01-10 | paid_social / linkedin_cold | 201-1000 / manufacturing | never | f1 use d0-d6, d30, d40 |
| u10 | 2023-12-20 | organic_search / seo_docs | 1-10 / education | never | none |

Plus one orphan event for `user_id` 999. Features: `f1 real_time_collab` v1.0 on 2024-01-01 and v2.0 on 2024-03-01; `f2 ai_insights` v1.0 on 2024-02-01.

---

### Task 1: Scaffold, engine decision, params, macros, build runner

**Files:**
- Create: `docs/adr/0009-right-sized-funnel-analytics-on-duckdb.md`
- Create: `funnels/__init__.py`, `funnels/config.py`, `funnels/warehouse.py`, `funnels/sql/00_macros.sql`
- Create: `funnels/tests/__init__.py`, `funnels/tests/fixture_data.py`, `funnels/tests/conftest.py`
- Test: `funnels/tests/test_warehouse.py`
- Modify: `pyproject.toml`, `.gitignore`

**Interfaces:**
- Produces: `funnels.config.Params` (frozen dataclass: `early_window_days=14`, `outcome_window_days=30`, `retained_from_day=28`, `retained_to_day=56`, `retained_min_active_days=2`, `habit_target_retention=0.80`, `min_group_size=30`, `usage_end: date | None`, `conversion_end: date | None`); `funnels.config.DEFAULT_RAW_DIR: Path`; `funnels.warehouse.build(raw_dir=DEFAULT_RAW_DIR, params=None, db_path=None) -> duckdb.DuckDBPyConnection` which creates table `params` and runs `funnels/sql/*.sql` in filename order, replacing the token `{{RAW_DIR}}` with the raw directory (forward slashes, single quotes escaped); SQL macros `wilson_low(k,n)`, `wilson_high(k,n)`, `diff_low(k1,n1,k2,n2)`, `diff_high(k1,n1,k2,n2)`, `safe_rate(k,n)`, `activity_bucket(n)`, `activity_bucket_order(n)`.
- Test helpers produced here and used by every later task: fixture `raw_dir`, `con`, `query(sql, *params) -> list[tuple]` in `conftest.py`; `FIXTURE_PARAMS` and `write_raw(directory)` in `fixture_data.py`.

- [ ] **Step 1: Create the branch and install dependencies**

Use a separate worktree so the current checkout (which may hold local edits such as `.vscode/settings.json` and an untracked copy of `data/raw_data_overview.md` that `origin/main` already contains) is not disturbed:

```bash
git fetch origin
git worktree add ../growth-analytics-funnels -b feat/funnel-analytics origin/main
cp docs/superpowers/plans/2026-10-10-funnel-analytics.md ../growth-analytics-funnels/docs/superpowers/plans/
cd ../growth-analytics-funnels
python -m pip install -e ".[funnels,dev]"
```

Expected: pip installs `duckdb` and `pytest`; `python -c "import duckdb; print(duckdb.__version__)"` prints a `1.x` version. Run every later command from `../growth-analytics-funnels`. Include the plan file in the Task 1 commit (`git add docs/superpowers/plans/2026-10-10-funnel-analytics.md`).

- [ ] **Step 2: Edit `pyproject.toml`**

Replace the `[project.optional-dependencies]` block through `[tool.pytest.ini_options]`'s `testpaths` line so it reads exactly:

```toml
[project.optional-dependencies]
graph = ["neo4j>=6.3,<6.4"]
funnels = ["duckdb>=1.1,<2"]
dev = ["pytest>=8"]

[tool.setuptools.packages.find]
include = ["graph*", "funnels*"]

[tool.setuptools.package-data]
funnels = ["sql/*.sql"]

[tool.pytest.ini_options]
testpaths = ["graph/tests", "funnels/tests"]
```

Leave the existing `addopts` and `markers` lines below it unchanged. Then append to `.gitignore`:

```
# funnel analytics warehouse (python -m funnels --db ...)
*.duckdb
```

- [ ] **Step 3: Write the ADR**

Write `docs/adr/0009-right-sized-funnel-analytics-on-duckdb.md`:

````markdown
# ADR 0009: Right-sized funnel analytics on DuckDB

## Status

Accepted. Supersedes ADR 0001 and ADR 0002 for the current repository scale;
those ADRs remain the reference shape if the data grows by orders of magnitude.

## Context

ADR 0001 and 0002 specify PySpark, Delta Lake and per-table job modules with
validation gates. Nothing of that was built. The raw snapshot is 62,617 rows
(48,666 usage events, 5,000 users) in about 8 MB. The questions to answer are
acquisition, activation, aha-moment and habit-moment funnels.

At this size a Spark session's start-up time exceeds the time DuckDB needs to
answer every query, and the Delta transaction log, Airflow Datasets and
per-table `main.py` files would be more code than the analytics themselves.

## Decision

- One Python package, `funnels/`, with one dependency: DuckDB.
- **Bronze** = typed SQL views directly over `data/raw/*.json[l]`. Nothing is
  copied or persisted; the raw files remain the system of record.
- **Silver** = DuckDB tables built from Bronze (`silver_user_dim`,
  `silver_feature_states`, `silver_usage_events`, `silver_user_journey`).
  Table and column names follow `docs/data_dictionary.md` where a table exists.
- **Gold** = SQL views over Silver, one file per analysis, each at a fixed
  documented grain, carrying counts, rates and Wilson confidence intervals.
- All windows and thresholds are fields of one `Params` dataclass.
- The warehouse is rebuilt in memory on every run (about a second). An optional
  `--db` flag writes a `.duckdb` file for ad-hoc querying.
- Tests build the same SQL against a 10-user hand-computed fixture, plus
  invariant and sanity checks on the real snapshot.

## Consequences

- Anyone can read the logic: each analysis is one SQL file.
- Re-running is idempotent and needs no services.
- No point-in-time storage or incremental loads. If the snapshot grows past a
  few million rows, or needs multiple writers, revisit: DuckDB can read Parquet
  and Delta, so the SQL ports forward before any Spark migration is justified.
- ADR 0006's DuckDB serving idea is consistent with this; the semantic layer
  and chatbot can later query the same Gold views.
````

- [ ] **Step 4: Write the fixture, conftest and failing tests**

Write `funnels/tests/__init__.py` (empty file), then:

Write `funnels/tests/fixture_data.py`:

```python
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
```

Write `funnels/tests/conftest.py`:

```python
from __future__ import annotations

import pytest

from funnels.tests.fixture_data import FIXTURE_PARAMS, write_raw
from funnels.warehouse import build


@pytest.fixture(scope="session")
def raw_dir(tmp_path_factory):
    path = tmp_path_factory.mktemp("raw")
    write_raw(path)
    return path


@pytest.fixture(scope="session")
def con(raw_dir):
    connection = build(raw_dir, FIXTURE_PARAMS)
    yield connection
    connection.close()


@pytest.fixture(scope="session")
def query(con):
    def run(sql, *params):
        return con.execute(sql, list(params)).fetchall()

    return run
```

Write `funnels/tests/test_warehouse.py`:

```python
from __future__ import annotations

from datetime import date

import pytest

from funnels.config import Params
from funnels.warehouse import build


def test_params_table_reflects_params(query):
    assert query(
        "select early_window_days, outcome_window_days, retained_from_day, retained_to_day,"
        " retained_min_active_days, habit_target_retention, min_group_size,"
        " usage_end, conversion_end from params"
    ) == [(14, 30, 28, 56, 2, 0.8, 30, date(2024, 6, 30), date(2024, 6, 30))]


def test_build_rejects_missing_raw_dir(tmp_path):
    with pytest.raises(FileNotFoundError):
        build(tmp_path / "nope", Params())


def test_build_accepts_raw_dir_with_a_quote_in_its_path(tmp_path):
    from funnels.tests.fixture_data import write_raw

    odd = tmp_path / "it's raw"
    write_raw(odd)
    con = build(odd, Params())
    con.close()


def test_wilson_interval_matches_known_values(query):
    low, high = query("select wilson_low(50, 100), wilson_high(50, 100)")[0]
    assert low == pytest.approx(0.4038, abs=1e-3)
    assert high == pytest.approx(0.5962, abs=1e-3)


def test_wilson_interval_edges(query):
    assert query("select wilson_low(0, 0), wilson_high(0, 0)") == [(None, None)]
    low, high = query("select wilson_low(0, 10), wilson_high(0, 10)")[0]
    assert low == pytest.approx(0.0, abs=1e-9)
    assert high == pytest.approx(0.2775, abs=1e-3)
    assert query("select wilson_high(10, 10)")[0][0] == 1.0


def test_safe_rate_is_null_for_empty_denominator(query):
    assert query("select safe_rate(3, 0), safe_rate(1, 4)") == [(None, 0.25)]


def test_diff_interval_is_null_when_either_side_is_empty(query):
    assert query("select diff_low(1, 0, 1, 5), diff_high(1, 5, 0, 0)") == [(None, None)]
    low, high = query("select diff_low(30, 100, 20, 100), diff_high(30, 100, 20, 100)")[0]
    assert low == pytest.approx(0.10 - 1.96 * (0.21 / 100 + 0.16 / 100) ** 0.5)
    assert high == pytest.approx(0.10 + 1.96 * (0.21 / 100 + 0.16 / 100) ** 0.5)


@pytest.mark.parametrize(
    "n, bucket, order",
    [(0, "0", 0), (1, "1", 1), (2, "2-3", 2), (3, "2-3", 2), (4, "4-6", 3),
     (6, "4-6", 3), (7, "7+", 4), (40, "7+", 4)],
)
def test_activity_bucket(query, n, bucket, order):
    assert query("select activity_bucket(?), activity_bucket_order(?)", n, n) == [(bucket, order)]
```

- [ ] **Step 5: Run the tests to verify they fail**

Run: `python -m pytest funnels/tests/test_warehouse.py -o addopts="" -q`
Expected: collection error `ModuleNotFoundError: No module named 'funnels.config'`.

- [ ] **Step 6: Write the implementation**

Write `funnels/__init__.py`:

```python
"""Funnel analytics over the raw growth snapshot (DuckDB + SQL)."""
```

Write `funnels/config.py`:

```python
"""Tunable definitions for the funnel analytics.

Every window and threshold the SQL uses lives here, so changing a definition is
a one-line edit and tests can override it. Day indexes count days since signup:
day 0 is the signup date.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RAW_DIR = REPO_ROOT / "data" / "raw"


@dataclass(frozen=True)
class Params:
    # "Early behavior" is what a user did on day 0 .. early_window_days - 1.
    early_window_days: int = 14
    # Conversion outcome horizon, both from signup and from the landmark.
    outcome_window_days: int = 30
    # Habit outcome: active on >= retained_min_active_days distinct days in
    # [retained_from_day, retained_to_day).
    retained_from_day: int = 28
    retained_to_day: int = 56
    retained_min_active_days: int = 2
    # Habit moment = smallest early-activity bucket whose retention interval
    # lower bound reaches this level.
    habit_target_retention: float = 0.80
    # Groups smaller than this are flagged low_n.
    min_group_size: int = 30
    # Observation ends. None means "use the latest event / conversion date in
    # the data". Windows that extend past these dates are treated as unobserved.
    usage_end: date | None = None
    conversion_end: date | None = None
```

Write `funnels/warehouse.py`:

```python
"""Build the analytics warehouse: params table + the SQL files in order."""
from __future__ import annotations

from pathlib import Path

import duckdb

from funnels.config import DEFAULT_RAW_DIR, Params

SQL_DIR = Path(__file__).parent / "sql"
RAW_DIR_TOKEN = "{{RAW_DIR}}"


def _create_params_table(con: duckdb.DuckDBPyConnection, p: Params) -> None:
    con.execute(
        """
        create or replace table params as select
            cast(? as INTEGER) as early_window_days,
            cast(? as INTEGER) as outcome_window_days,
            cast(? as INTEGER) as retained_from_day,
            cast(? as INTEGER) as retained_to_day,
            cast(? as INTEGER) as retained_min_active_days,
            cast(? as DOUBLE)  as habit_target_retention,
            cast(? as INTEGER) as min_group_size,
            cast(? as DATE)    as usage_end,
            cast(? as DATE)    as conversion_end
        """,
        [
            p.early_window_days,
            p.outcome_window_days,
            p.retained_from_day,
            p.retained_to_day,
            p.retained_min_active_days,
            p.habit_target_retention,
            p.min_group_size,
            p.usage_end,
            p.conversion_end,
        ],
    )


def build(
    raw_dir: Path | str = DEFAULT_RAW_DIR,
    params: Params | None = None,
    db_path: Path | str | None = None,
) -> duckdb.DuckDBPyConnection:
    """Return a connection with every Bronze/Silver/Gold object created.

    The warehouse is in memory unless db_path is given. Raw files are only read.
    """
    raw = Path(raw_dir)
    if not raw.is_dir():
        raise FileNotFoundError(f"raw data directory not found: {raw}")
    raw_posix = raw.resolve().as_posix().replace("'", "''")

    con = duckdb.connect(str(db_path) if db_path else ":memory:")
    _create_params_table(con, params or Params())
    for sql_file in sorted(SQL_DIR.glob("*.sql")):
        con.execute(sql_file.read_text(encoding="utf-8").replace(RAW_DIR_TOKEN, raw_posix))
    return con
```

Write `funnels/sql/00_macros.sql`:

```sql
-- Shared helpers. Wilson 95% interval for a proportion k/n (z = 1.96, z^2 = 3.8416).
-- NULL when n = 0 so empty groups never raise a division error.
create or replace macro wilson_low(k, n) as
    case when n > 0 then
        greatest(0.0, (k + 1.9208 - 1.96 * sqrt(k * (n - k) / n + 0.9604)) / (n + 3.8416))
    end;

create or replace macro wilson_high(k, n) as
    case when n > 0 then
        least(1.0, (k + 1.9208 + 1.96 * sqrt(k * (n - k) / n + 0.9604)) / (n + 3.8416))
    end;

create or replace macro safe_rate(k, n) as
    case when n > 0 then k::double / n end;

-- 95% Wald interval for the difference of two proportions k1/n1 - k2/n2.
create or replace macro diff_low(k1, n1, k2, n2) as
    case when n1 > 0 and n2 > 0 then
        (k1::double / n1 - k2::double / n2)
        - 1.96 * sqrt((k1::double / n1) * (1 - k1::double / n1) / n1
                    + (k2::double / n2) * (1 - k2::double / n2) / n2)
    end;

create or replace macro diff_high(k1, n1, k2, n2) as
    case when n1 > 0 and n2 > 0 then
        (k1::double / n1 - k2::double / n2)
        + 1.96 * sqrt((k1::double / n1) * (1 - k1::double / n1) / n1
                    + (k2::double / n2) * (1 - k2::double / n2) / n2)
    end;

-- Buckets of "number of active days", shared by the aha and habit analyses.
create or replace macro activity_bucket(n) as
    case when n = 0 then '0' when n = 1 then '1' when n <= 3 then '2-3'
         when n <= 6 then '4-6' else '7+' end;

create or replace macro activity_bucket_order(n) as
    case when n = 0 then 0 when n = 1 then 1 when n <= 3 then 2
         when n <= 6 then 3 else 4 end;
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python -m pytest funnels/tests/test_warehouse.py -o addopts="" -q`
Expected: all tests pass (`15 passed`).

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml .gitignore docs/adr/0009-right-sized-funnel-analytics-on-duckdb.md docs/superpowers/plans/2026-10-10-funnel-analytics.md funnels
git commit -m "feat(funnels): scaffold DuckDB funnel analytics with params, macros and ADR 0009"
```

---

### Task 2: Bronze views over the raw files

**Files:**
- Create: `funnels/sql/01_bronze.sql`
- Test: `funnels/tests/test_bronze.py`

**Interfaces:**
- Consumes: `build()`, `con`, `query` from Task 1.
- Produces six views named as in the data dictionary: `user_signups(user_id, email, signup_date, company_size, industry)`, `marketing_attribution(user_id, channel, campaign, first_touch_date)`, `conversions(user_id, conversion_date, plan, mrr, signup_date, days_to_convert, used_real_time_collab)`, `subscription_events(event_id, user_id, event_date, event_type, plan, mrr, previous_plan, previous_mrr)`, `feature_usage_events(user_id, feature_id, feature_name, event_type, event_timestamp, event_date)`, `feature_releases(feature_id, feature_name, release_date, version)`. Dates are `DATE`, `event_timestamp` is `TIMESTAMP`. Differences from the raw files, intentional: raw `timestamp` becomes `event_timestamp` plus `event_date`; raw `id`/`name` become `feature_id`/`feature_name`; no `ingestion_timestamp`/`event_id` (views, not loads).

- [ ] **Step 1: Write the failing test**

Write `funnels/tests/test_bronze.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest funnels/tests/test_bronze.py -o addopts="" -q`
Expected: FAIL with `Catalog Error: Table with name user_signups does not exist`.

- [ ] **Step 3: Write the Bronze SQL**

Write `funnels/sql/01_bronze.sql`:

```sql
-- Bronze: typed views directly over the raw files. Nothing is copied.
-- {{RAW_DIR}} is replaced by funnels.warehouse.build().

create or replace view user_signups as
select user_id, email, signup_date, company_size, industry
from read_json(
    '{{RAW_DIR}}/user_signups.jsonl', format = 'newline_delimited',
    columns = {'user_id': 'INTEGER', 'email': 'VARCHAR', 'signup_date': 'DATE',
               'company_size': 'VARCHAR', 'industry': 'VARCHAR'});

create or replace view marketing_attribution as
select user_id, channel, campaign, first_touch_date
from read_json(
    '{{RAW_DIR}}/marketing_attribution.jsonl', format = 'newline_delimited',
    columns = {'user_id': 'INTEGER', 'channel': 'VARCHAR', 'campaign': 'VARCHAR',
               'first_touch_date': 'DATE'});

create or replace view conversions as
select user_id, conversion_date, plan, mrr, signup_date, days_to_convert,
       used_real_time_collab
from read_json(
    '{{RAW_DIR}}/conversions.jsonl', format = 'newline_delimited',
    columns = {'user_id': 'INTEGER', 'conversion_date': 'DATE', 'plan': 'VARCHAR',
               'mrr': 'INTEGER', 'signup_date': 'DATE', 'days_to_convert': 'INTEGER',
               'used_real_time_collab': 'BOOLEAN'});

create or replace view subscription_events as
select event_id, user_id, event_date, event_type, plan, mrr, previous_plan, previous_mrr
from read_json(
    '{{RAW_DIR}}/subscription_events.jsonl', format = 'newline_delimited',
    columns = {'event_id': 'INTEGER', 'user_id': 'INTEGER', 'event_date': 'DATE',
               'event_type': 'VARCHAR', 'plan': 'VARCHAR', 'mrr': 'INTEGER',
               'previous_plan': 'VARCHAR', 'previous_mrr': 'INTEGER'});

-- The raw column is called "timestamp"; the data dictionary calls it event_timestamp.
create or replace view feature_usage_events as
select user_id, feature_id, feature_name, event_type,
       "timestamp" as event_timestamp,
       cast("timestamp" as date) as event_date
from read_json(
    '{{RAW_DIR}}/feature_usage_events.jsonl', format = 'newline_delimited',
    columns = {'timestamp': 'TIMESTAMP', 'user_id': 'INTEGER', 'feature_id': 'INTEGER',
               'feature_name': 'VARCHAR', 'event_type': 'VARCHAR'});

-- The raw file is a JSON array with id / name.
create or replace view feature_releases as
select id as feature_id, name as feature_name, release_date, version
from read_json(
    '{{RAW_DIR}}/feature_releases.json', format = 'array',
    columns = {'id': 'INTEGER', 'name': 'VARCHAR', 'release_date': 'DATE',
               'version': 'VARCHAR'});
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest funnels/tests -o addopts="" -q`
Expected: all tests in `test_warehouse.py` and `test_bronze.py` pass.

- [ ] **Step 5: Commit**

```bash
git add funnels/sql/01_bronze.sql funnels/tests/test_bronze.py
git commit -m "feat(funnels): add typed Bronze views over the raw files"
```

---

### Task 3: Silver core tables (user dimension, feature states, usage events, extent)

**Files:**
- Create: `funnels/sql/02_silver_core.sql`
- Test: `funnels/tests/test_silver_core.py`

**Interfaces:**
- Consumes: Bronze views (Task 2), `params` table.
- Produces:
  - `silver_feature_states(feature_id, feature_name, version, is_enabled, effective_from, effective_to, is_current, record_hash)` as in the data dictionary (SCD Type 2; `effective_to = 9999-12-31` for current).
  - `silver_user_dim(user_id, signup_date, company_size, industry, acquisition_channel, acquisition_campaign, current_plan, current_mrr)` as in the data dictionary (`current_plan` in free/pro/enterprise/churned).
  - `silver_usage_events(user_id, feature_id, feature_name, event_type, event_timestamp, event_date, day_index)` where `day_index = event_date - signup_date` in days; orphan events dropped.
  - `silver_extent(usage_end DATE, conversion_end DATE)`: one row, parameter override else latest event / conversion date in the data.

- [ ] **Step 1: Write the failing test**

Write `funnels/tests/test_silver_core.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest funnels/tests/test_silver_core.py -o addopts="" -q`
Expected: FAIL with `Catalog Error: Table with name silver_feature_states does not exist`.

- [ ] **Step 3: Write the Silver core SQL**

Write `funnels/sql/02_silver_core.sql`:

```sql
-- Silver core: conformed entities. Names and columns follow docs/data_dictionary.md.

-- SCD Type 2 feature version history: a new release closes the previous version.
create or replace table silver_feature_states as
with ordered as (
    select feature_id, feature_name, version, release_date as effective_from,
           lead(release_date) over (partition by feature_id order by release_date) as next_release
    from feature_releases
)
select feature_id, feature_name, version,
       true as is_enabled,
       effective_from,
       coalesce(next_release, date '9999-12-31') as effective_to,
       next_release is null as is_current,
       md5(feature_name || '|' || version) as record_hash
from ordered;

-- One row per user: firmographics + first-touch attribution + current commercial state.
-- Same-day events are ordered by event_id so the latest state is deterministic.
create or replace table silver_user_dim as
with ranked as (
    select *,
           row_number() over (partition by user_id order by event_date desc, event_id desc) as rn
    from subscription_events
),
latest as (
    select user_id, event_type, plan, mrr from ranked where rn = 1
)
select s.user_id,
       s.signup_date,
       s.company_size,
       s.industry,
       coalesce(a.channel, 'unattributed') as acquisition_channel,
       coalesce(a.campaign, 'unattributed') as acquisition_campaign,
       case when l.user_id is null then 'free'
            when l.event_type = 'subscription_cancelled' then 'churned'
            else l.plan end as current_plan,
       case when l.user_id is null or l.event_type = 'subscription_cancelled' then 0
            else l.mrr end as current_mrr
from user_signups s
left join marketing_attribution a using (user_id)
left join latest l using (user_id);

-- Usage events with their position on the user's own timeline (day 0 = signup date).
-- The inner join drops orphan events whose user never signed up.
create or replace table silver_usage_events as
select e.user_id, e.feature_id, e.feature_name, e.event_type,
       e.event_timestamp, e.event_date,
       date_diff('day', u.signup_date, e.event_date) as day_index
from feature_usage_events e
join user_signups u using (user_id);

-- Observation ends: the parameter wins, otherwise the latest date seen in the data.
create or replace table silver_extent as
select coalesce(p.usage_end, (select max(event_date) from feature_usage_events)) as usage_end,
       coalesce(p.conversion_end, (select max(conversion_date) from conversions)) as conversion_end
from params p;
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest funnels/tests -o addopts="" -q`
Expected: all tests so far pass.

- [ ] **Step 5: Commit**

```bash
git add funnels/sql/02_silver_core.sql funnels/tests/test_silver_core.py
git commit -m "feat(funnels): add Silver user dimension, feature states, usage events and extent"
```

---

### Task 4: Silver user journey (one row per user, with window flags)

**Files:**
- Create: `funnels/sql/03_silver_journey.sql`
- Test: `funnels/tests/test_silver_journey.py`

**Interfaces:**
- Consumes: `silver_user_dim`, `silver_usage_events`, `silver_extent`, `conversions`, `params`.
- Produces `silver_user_journey` with exactly these columns (all Gold views depend on these names):
  `user_id, signup_date, signup_month, company_size, industry, acquisition_channel, acquisition_campaign, converted, days_to_convert, conversion_plan, conversion_mrr, first_view_day, first_use_day, first_share_day, second_feature_day, early_events, early_active_days, early_features_used, early_shares, late_active_days, early_window_observed, conversion_window_observed, retention_window_observed, converted_in_window, free_at_landmark, landmark_member, converted_after_landmark`.
  - `first_*_day` / `second_feature_day`: day index of the first view / use / share, and of the first `use` of a second distinct feature; NULL if never.
  - `early_*`: counts over day index `[0, early_window_days)`; `late_active_days`: distinct active days over `[retained_from_day, retained_to_day)`; all `0` (not NULL) when the user has no events.
  - `early_window_observed = signup + early_window_days <= usage_end`; `conversion_window_observed = signup + outcome_window_days <= conversion_end`; `retention_window_observed = signup + retained_to_day <= usage_end`.
  - `converted_in_window`: converted with `days_to_convert < outcome_window_days`.
  - `free_at_landmark`: never converted, or `days_to_convert >= early_window_days`.
  - `landmark_member`: `free_at_landmark` and `signup + early_window_days + outcome_window_days <= conversion_end` (the aha cohort).
  - `converted_after_landmark`: `early_window_days <= days_to_convert < early_window_days + outcome_window_days`.

- [ ] **Step 1: Write the failing test**

Write `funnels/tests/test_silver_journey.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest funnels/tests/test_silver_journey.py -o addopts="" -q`
Expected: FAIL with `Catalog Error: Table with name silver_user_journey does not exist`.

- [ ] **Step 3: Write the journey SQL**

Write `funnels/sql/03_silver_journey.sql`:

```sql
-- One row per user: attribution, outcome, first-milestone days, early/late behavior,
-- and which measurement windows have fully elapsed by the observation end.
create or replace table silver_user_journey as
with
p as (select * from params),
x as (select * from silver_extent),
milestones as (
    select user_id,
           min(day_index) filter (where event_type = 'view')  as first_view_day,
           min(day_index) filter (where event_type = 'use')   as first_use_day,
           min(day_index) filter (where event_type = 'share') as first_share_day
    from silver_usage_events
    group by user_id
),
first_use_by_feature as (
    select user_id, feature_id, min(day_index) as day_index
    from silver_usage_events
    where event_type = 'use'
    group by user_id, feature_id
),
second_feature as (
    select user_id, day_index as second_feature_day
    from (
        select *, row_number() over (partition by user_id order by day_index, feature_id) as rn
        from first_use_by_feature
    )
    where rn = 2
),
early as (
    select e.user_id,
           count(*) as early_events,
           count(distinct e.day_index) as early_active_days,
           count(distinct e.feature_id) filter (where e.event_type = 'use') as early_features_used,
           count(*) filter (where e.event_type = 'share') as early_shares
    from silver_usage_events e, p
    where e.day_index < p.early_window_days
    group by e.user_id
),
late as (
    select e.user_id, count(distinct e.day_index) as late_active_days
    from silver_usage_events e, p
    where e.day_index >= p.retained_from_day and e.day_index < p.retained_to_day
    group by e.user_id
),
base as (
    select d.user_id, d.signup_date,
           date_trunc('month', d.signup_date)::date as signup_month,
           d.company_size, d.industry, d.acquisition_channel, d.acquisition_campaign,
           c.user_id is not null as converted,
           date_diff('day', d.signup_date, c.conversion_date) as days_to_convert,
           c.plan as conversion_plan,
           c.mrr as conversion_mrr,
           m.first_view_day, m.first_use_day, m.first_share_day,
           sf.second_feature_day,
           coalesce(e.early_events, 0) as early_events,
           coalesce(e.early_active_days, 0) as early_active_days,
           coalesce(e.early_features_used, 0) as early_features_used,
           coalesce(e.early_shares, 0) as early_shares,
           coalesce(l.late_active_days, 0) as late_active_days
    from silver_user_dim d
    left join conversions c on c.user_id = d.user_id
    left join milestones m on m.user_id = d.user_id
    left join second_feature sf on sf.user_id = d.user_id
    left join early e on e.user_id = d.user_id
    left join late l on l.user_id = d.user_id
)
select b.*,
       b.signup_date + p.early_window_days <= x.usage_end as early_window_observed,
       b.signup_date + p.outcome_window_days <= x.conversion_end as conversion_window_observed,
       b.signup_date + p.retained_to_day <= x.usage_end as retention_window_observed,
       coalesce(b.days_to_convert < p.outcome_window_days, false) as converted_in_window,
       (not b.converted or b.days_to_convert >= p.early_window_days) as free_at_landmark,
       ((not b.converted or b.days_to_convert >= p.early_window_days)
           and b.signup_date + p.early_window_days + p.outcome_window_days <= x.conversion_end
       ) as landmark_member,
       coalesce(b.days_to_convert >= p.early_window_days
                and b.days_to_convert < p.early_window_days + p.outcome_window_days,
                false) as converted_after_landmark
from base b
cross join p
cross join x;
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest funnels/tests -o addopts="" -q`
Expected: all tests so far pass.

- [ ] **Step 5: Commit**

```bash
git add funnels/sql/03_silver_journey.sql funnels/tests/test_silver_journey.py
git commit -m "feat(funnels): add per-user Silver journey table with window-elapsed flags"
```

---

### Task 5: Gold acquisition funnel and cohorts

**Files:**
- Create: `funnels/sql/04_gold_acquisition.sql`
- Test: `funnels/tests/test_gold_acquisition.py`

**Interfaces:**
- Consumes: `silver_user_journey`, `params`, macros.
- Produces:
  - `gold_acquisition_funnel(level, acquisition_channel, acquisition_campaign, signups, observed_signups, activated, activation_rate, converted_in_window, conversion_rate, conversion_ci_low, conversion_ci_high, avg_days_to_convert, new_mrr, avg_new_mrr, enterprise_share, low_n)`. `level` is `'campaign'`, `'channel'` (campaign shown as `(all)`) or `'total'` (both shown as `(all)`). `signups` counts everyone; every other count uses only **observed** users (`early_window_observed and conversion_window_observed`). `activated` = first `use` before `early_window_days`. `avg_days_to_convert`, `new_mrr`, `avg_new_mrr`, `enterprise_share` cover users converted inside the window.
  - `gold_acquisition_cohorts(signup_month, acquisition_channel, signups, observed_signups, converted_in_window, conversion_rate, conversion_ci_low, conversion_ci_high, low_n)`.

- [ ] **Step 1: Write the failing test**

Write `funnels/tests/test_gold_acquisition.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest funnels/tests/test_gold_acquisition.py -o addopts="" -q`
Expected: FAIL with `Catalog Error: Table with name gold_acquisition_funnel does not exist`.

- [ ] **Step 3: Write the SQL**

Write `funnels/sql/04_gold_acquisition.sql`:

```sql
-- Acquisition: which channels / campaigns bring users who activate and convert.
-- Stage counts only include users whose early and conversion windows have elapsed.
create or replace view gold_acquisition_funnel as
with cohort as (
    select j.*, (j.early_window_observed and j.conversion_window_observed) as observed
    from silver_user_journey j
),
agg as (
    select
        acquisition_channel,
        acquisition_campaign,
        count(*) as signups,
        count(*) filter (where observed) as observed_signups,
        count(*) filter (where observed and first_use_day < p.early_window_days) as activated,
        count(*) filter (where observed and converted_in_window) as converted_in_window,
        avg(days_to_convert) filter (where observed and converted_in_window) as avg_days_to_convert,
        coalesce(sum(conversion_mrr) filter (where observed and converted_in_window), 0) as new_mrr,
        count(*) filter (
            where observed and converted_in_window and conversion_plan = 'enterprise'
        ) as enterprise_conversions
    from cohort
    cross join params p
    group by grouping sets ((acquisition_channel, acquisition_campaign), (acquisition_channel), ())
)
select
    case when acquisition_channel is null then 'total'
         when acquisition_campaign is null then 'channel'
         else 'campaign' end as level,
    coalesce(acquisition_channel, '(all)') as acquisition_channel,
    coalesce(acquisition_campaign, '(all)') as acquisition_campaign,
    signups,
    observed_signups,
    activated,
    safe_rate(activated, observed_signups) as activation_rate,
    converted_in_window,
    safe_rate(converted_in_window, observed_signups) as conversion_rate,
    wilson_low(converted_in_window, observed_signups) as conversion_ci_low,
    wilson_high(converted_in_window, observed_signups) as conversion_ci_high,
    avg_days_to_convert,
    new_mrr,
    safe_rate(new_mrr, converted_in_window) as avg_new_mrr,
    safe_rate(enterprise_conversions, converted_in_window) as enterprise_share,
    observed_signups < (select min_group_size from params) as low_n
from agg
order by
    case when acquisition_channel is null then 0 when acquisition_campaign is null then 1 else 2 end,
    acquisition_channel, acquisition_campaign;

-- Same conversion measure per signup month and channel, for trend lines.
create or replace view gold_acquisition_cohorts as
with cohort as (
    select j.*, (j.early_window_observed and j.conversion_window_observed) as observed
    from silver_user_journey j
),
agg as (
    select
        signup_month,
        acquisition_channel,
        count(*) as signups,
        count(*) filter (where observed) as observed_signups,
        count(*) filter (where observed and converted_in_window) as converted_in_window
    from cohort
    group by signup_month, acquisition_channel
)
select
    signup_month,
    acquisition_channel,
    signups,
    observed_signups,
    converted_in_window,
    safe_rate(converted_in_window, observed_signups) as conversion_rate,
    wilson_low(converted_in_window, observed_signups) as conversion_ci_low,
    wilson_high(converted_in_window, observed_signups) as conversion_ci_high,
    observed_signups < (select min_group_size from params) as low_n
from agg
order by signup_month, acquisition_channel;
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest funnels/tests -o addopts="" -q`
Expected: all tests so far pass.

- [ ] **Step 5: Commit**

```bash
git add funnels/sql/04_gold_acquisition.sql funnels/tests/test_gold_acquisition.py
git commit -m "feat(funnels): add acquisition funnel and monthly cohort views"
```

---

### Task 6: Gold activation funnel

**Files:**
- Create: `funnels/sql/05_gold_activation.sql`
- Test: `funnels/tests/test_gold_activation.py`

**Interfaces:**
- Consumes: `silver_user_journey`, `params`, macros.
- Produces `gold_activation_funnel(dimension, segment, signups, viewed, activated, shared, multi_feature, converted_in_window, activation_rate, activation_ci_low, activation_ci_high, multi_feature_rate_of_activated, conversion_rate, median_days_to_first_use, low_n)`. `dimension` is `'all'`, `'acquisition_channel'`, `'company_size'` or `'industry'`. Cohort = observed users (early and conversion windows elapsed). `viewed` / `activated` / `shared` = first view / use / share before `early_window_days`; `multi_feature` = second distinct feature used before `early_window_days`. These are milestone reach counts, **not** a strictly nested funnel (a user can share without a view).

- [ ] **Step 1: Write the failing test**

Write `funnels/tests/test_gold_activation.py`:

```python
from __future__ import annotations

import pytest

COLS = (
    "signups, viewed, activated, shared, multi_feature, converted_in_window,"
    " median_days_to_first_use"
)


def seg(query, dimension, segment):
    return query(
        f"select {COLS} from gold_activation_funnel"
        f" where dimension = '{dimension}' and segment = '{segment}'"
    )


def test_all_segment_excludes_unobserved_signups(query):
    # 9 observed users (u8 excluded). activated = u1, u2, u5, u9
    assert seg(query, "all", "all") == [(9, 2, 4, 1, 1, 3, 0.0)]


def test_channel_segment(query):
    # referral = u1, u2, u6: viewed u1+u6, activated u1+u2 (days 1 and 0), shared u2, converted u1
    assert seg(query, "acquisition_channel", "referral") == [(3, 2, 2, 1, 0, 1, 0.5)]


def test_segment_without_activation_has_null_median(query):
    assert seg(query, "acquisition_channel", "paid_search") == [(2, 0, 0, 0, 0, 2, None)]


def test_every_dimension_covers_the_whole_cohort(query):
    totals = query(
        "select dimension, sum(signups) from gold_activation_funnel group by dimension"
        " order by dimension"
    )
    assert totals == [
        ("acquisition_channel", 9),
        ("all", 9),
        ("company_size", 9),
        ("industry", 9),
    ]


def test_rates_and_intervals(query):
    rate, low, high, multi_rate, conv_rate = query(
        "select activation_rate, activation_ci_low, activation_ci_high,"
        " multi_feature_rate_of_activated, conversion_rate"
        " from gold_activation_funnel where dimension = 'all'"
    )[0]
    assert rate == pytest.approx(4 / 9)
    assert low < rate < high
    assert multi_rate == pytest.approx(1 / 4)
    assert conv_rate == pytest.approx(3 / 9)


def test_multi_feature_rate_is_null_when_nobody_activated(query):
    assert query(
        "select activation_rate, multi_feature_rate_of_activated from gold_activation_funnel"
        " where dimension = 'acquisition_channel' and segment = 'paid_search'"
    ) == [(0.0, None)]


def test_small_segments_are_flagged(query):
    assert query("select bool_and(low_n) from gold_activation_funnel") == [(True,)]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest funnels/tests/test_gold_activation.py -o addopts="" -q`
Expected: FAIL with `Catalog Error: Table with name gold_activation_funnel does not exist`.

- [ ] **Step 3: Write the SQL**

Write `funnels/sql/05_gold_activation.sql`:

```sql
-- Activation: what share of new signups reach each product milestone in their first
-- early_window_days, overall and per segment. Milestones are reach counts, not a
-- strictly nested funnel.
create or replace view gold_activation_funnel as
with cohort as (
    select * from silver_user_journey
    where early_window_observed and conversion_window_observed
),
segmented as (
    select 'all' as dimension, 'all' as segment, * from cohort
    union all select 'acquisition_channel', acquisition_channel, * from cohort
    union all select 'company_size', company_size, * from cohort
    union all select 'industry', industry, * from cohort
),
agg as (
    select
        dimension,
        segment,
        count(*) as signups,
        count(*) filter (where first_view_day < p.early_window_days) as viewed,
        count(*) filter (where first_use_day < p.early_window_days) as activated,
        count(*) filter (where first_share_day < p.early_window_days) as shared,
        count(*) filter (where second_feature_day < p.early_window_days) as multi_feature,
        count(*) filter (where converted_in_window) as converted_in_window,
        median(first_use_day) filter (where first_use_day < p.early_window_days)
            as median_days_to_first_use
    from segmented
    cross join params p
    group by dimension, segment
)
select
    dimension,
    segment,
    signups,
    viewed,
    activated,
    shared,
    multi_feature,
    converted_in_window,
    safe_rate(activated, signups) as activation_rate,
    wilson_low(activated, signups) as activation_ci_low,
    wilson_high(activated, signups) as activation_ci_high,
    safe_rate(multi_feature, activated) as multi_feature_rate_of_activated,
    safe_rate(converted_in_window, signups) as conversion_rate,
    median_days_to_first_use,
    signups < (select min_group_size from params) as low_n
from agg
order by case dimension when 'all' then 0 else 1 end, dimension, segment;
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest funnels/tests -o addopts="" -q`
Expected: all tests so far pass.

- [ ] **Step 5: Commit**

```bash
git add funnels/sql/05_gold_activation.sql funnels/tests/test_gold_activation.py
git commit -m "feat(funnels): add activation funnel view with segment breakdowns"
```

---

### Task 7: Gold aha-moment views (landmark design)

**Files:**
- Create: `funnels/sql/06_gold_aha.sql`
- Test: `funnels/tests/test_gold_aha.py`

**Interfaces:**
- Consumes: `silver_user_journey` (`landmark_member`, `converted_after_landmark`, early metrics), `silver_usage_events`, `silver_feature_states`, `params`, macros.
- Produces (all use only `landmark_member` users: still free at day `early_window_days`, with the full outcome window observed):
  - `gold_aha_features(feature_name, cohort, users, converted, conversion_rate, conversion_ci_low, conversion_ci_high, low_n)`. `cohort` is `used_feature` (a `use` event on day index `< early_window_days`), `available_not_used` (feature released on or before signup, no early use) or `not_available` (released after signup and not used early). `converted` counts `converted_after_landmark`.
  - `gold_aha_feature_lift(feature_name, used_users, used_converted, used_rate, baseline_users, baseline_converted, baseline_rate, rate_diff, rate_diff_ci_low, rate_diff_ci_high, lift_ratio, ci_excludes_zero, low_n)`: `used_feature` vs `available_not_used`; a feature missing either cohort is omitted.
  - `gold_aha_behaviors(behavior, level, level_order, users, converted, conversion_rate, conversion_ci_low, conversion_ci_high, low_n)` for behaviors `early_features_used` (levels `0`, `1`, `2`, `3+`), `early_active_days` (buckets from `activity_bucket`) and `early_shared` (`no`, `yes`).

- [ ] **Step 1: Write the failing test**

Write `funnels/tests/test_gold_aha.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest funnels/tests/test_gold_aha.py -o addopts="" -q`
Expected: FAIL with `Catalog Error: Table with name gold_aha_features does not exist`.

- [ ] **Step 3: Write the SQL**

Write `funnels/sql/06_gold_aha.sql`:

```sql
-- Aha moment, landmark design. Cohort = users still free at the end of the early window
-- whose outcome window has fully elapsed. Predictor = behavior inside the early window.
-- Outcome = converted in the following outcome_window_days. Users who converted before
-- the landmark are excluded, so post-conversion usage can never explain conversion.

create or replace view gold_aha_features as
with members as (
    select user_id, signup_date, converted_after_landmark
    from silver_user_journey
    where landmark_member
),
features as (
    select feature_id, feature_name, min(effective_from) as released_on
    from silver_feature_states
    group by feature_id, feature_name
),
early_use as (
    select e.user_id, e.feature_id
    from silver_usage_events e, params p
    where e.event_type = 'use' and e.day_index < p.early_window_days
    group by e.user_id, e.feature_id
),
cohorted as (
    select f.feature_name,
           m.converted_after_landmark,
           case when eu.user_id is not null then 'used_feature'
                when f.released_on <= m.signup_date then 'available_not_used'
                else 'not_available' end as cohort
    from members m
    cross join features f
    left join early_use eu on eu.user_id = m.user_id and eu.feature_id = f.feature_id
),
agg as (
    select feature_name, cohort,
           count(*) as users,
           count(*) filter (where converted_after_landmark) as converted
    from cohorted
    group by feature_name, cohort
)
select feature_name, cohort, users, converted,
       safe_rate(converted, users) as conversion_rate,
       wilson_low(converted, users) as conversion_ci_low,
       wilson_high(converted, users) as conversion_ci_high,
       users < (select min_group_size from params) as low_n
from agg
order by feature_name, cohort;

-- used_feature vs available_not_used: difference in conversion rate with a 95% interval.
-- Six features are compared, so treat an interval that excludes zero as a lead, not proof.
create or replace view gold_aha_feature_lift as
select
    u.feature_name,
    u.users as used_users,
    u.converted as used_converted,
    u.conversion_rate as used_rate,
    b.users as baseline_users,
    b.converted as baseline_converted,
    b.conversion_rate as baseline_rate,
    u.conversion_rate - b.conversion_rate as rate_diff,
    diff_low(u.converted, u.users, b.converted, b.users) as rate_diff_ci_low,
    diff_high(u.converted, u.users, b.converted, b.users) as rate_diff_ci_high,
    case when b.conversion_rate > 0 then u.conversion_rate / b.conversion_rate end as lift_ratio,
    coalesce(
        diff_low(u.converted, u.users, b.converted, b.users) > 0
        or diff_high(u.converted, u.users, b.converted, b.users) < 0,
        false) as ci_excludes_zero,
    least(u.users, b.users) < (select min_group_size from params) as low_n
from gold_aha_features u
join gold_aha_features b
  on b.feature_name = u.feature_name and b.cohort = 'available_not_used'
where u.cohort = 'used_feature'
order by u.feature_name;

-- Behavior thresholds: how conversion changes with the amount of early activity.
create or replace view gold_aha_behaviors as
with members as (
    select * from silver_user_journey where landmark_member
),
leveled as (
    select 'early_features_used' as behavior,
           case when early_features_used >= 3 then '3+'
                else cast(early_features_used as varchar) end as level,
           least(early_features_used, 3) as level_order,
           converted_after_landmark
    from members
    union all
    select 'early_active_days',
           activity_bucket(early_active_days),
           activity_bucket_order(early_active_days),
           converted_after_landmark
    from members
    union all
    select 'early_shared',
           case when early_shares > 0 then 'yes' else 'no' end,
           case when early_shares > 0 then 1 else 0 end,
           converted_after_landmark
    from members
),
agg as (
    select behavior, level, level_order,
           count(*) as users,
           count(*) filter (where converted_after_landmark) as converted
    from leveled
    group by behavior, level, level_order
)
select behavior, level, level_order, users, converted,
       safe_rate(converted, users) as conversion_rate,
       wilson_low(converted, users) as conversion_ci_low,
       wilson_high(converted, users) as conversion_ci_high,
       users < (select min_group_size from params) as low_n
from agg
order by behavior, level_order;
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest funnels/tests -o addopts="" -q`
Expected: all tests so far pass.

- [ ] **Step 5: Commit**

```bash
git add funnels/sql/06_gold_aha.sql funnels/tests/test_gold_aha.py
git commit -m "feat(funnels): add landmark-based aha-moment views"
```

---

### Task 8: Gold habit curve, habit threshold and usage retention

**Files:**
- Create: `funnels/sql/07_gold_habit.sql`
- Test: `funnels/tests/test_gold_habit.py`

**Interfaces:**
- Consumes: `silver_user_journey`, `silver_usage_events`, `silver_extent`, `params`, macros (`activity_bucket`, `activity_bucket_order`).
- Produces:
  - `gold_habit_curve(cohort, early_active_days_bucket, bucket_order, users, retained_users, retained_rate, retained_ci_low, retained_ci_high, low_n)`. Base = users whose early window **and** retention window have elapsed. `retained` = at least `retained_min_active_days` distinct active days in `[retained_from_day, retained_to_day)`. `cohort` is `all_users` or `free_at_landmark` (removes users who had already converted, so conversion does not explain the retention).
  - `gold_habit_threshold(cohort, target_retention, threshold_bucket)`: the smallest bucket (by `bucket_order`) whose `retained_ci_low >= habit_target_retention`; NULL if none qualifies.
  - `gold_usage_retention(signup_month, week_n, cohort_users, active_users, retention_rate, retention_ci_low, retention_ci_high)` for `week_n` 0..12 (week n = day index `7n .. 7n+6`). `cohort_users` only includes users whose week `n` has fully elapsed, so recent months stop at an earlier week instead of showing false drop-offs.

- [ ] **Step 1: Write the failing test**

Write `funnels/tests/test_gold_habit.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest funnels/tests/test_gold_habit.py -o addopts="" -q`
Expected: FAIL with `Catalog Error: Table with name gold_habit_curve does not exist`.

- [ ] **Step 3: Write the SQL**

Write `funnels/sql/07_gold_habit.sql`:

```sql
-- Habit moment: how much early activity predicts still using the product weeks later.
-- Caveat (documented in docs/funnel_metrics.md): activity persists, so a strong curve
-- shows where retention jumps, not that the early usage caused it.
create or replace view gold_habit_curve as
with base as (
    select j.*, (j.late_active_days >= p.retained_min_active_days) as retained
    from silver_user_journey j
    cross join params p
    where j.early_window_observed and j.retention_window_observed
),
cohorts as (
    select 'all_users' as cohort, * from base
    union all
    select 'free_at_landmark', * from base where free_at_landmark
),
agg as (
    select cohort,
           activity_bucket(early_active_days) as early_active_days_bucket,
           activity_bucket_order(early_active_days) as bucket_order,
           count(*) as users,
           count(*) filter (where retained) as retained_users
    from cohorts
    group by cohort, early_active_days_bucket, bucket_order
)
select cohort, early_active_days_bucket, bucket_order, users, retained_users,
       safe_rate(retained_users, users) as retained_rate,
       wilson_low(retained_users, users) as retained_ci_low,
       wilson_high(retained_users, users) as retained_ci_high,
       users < (select min_group_size from params) as low_n
from agg
order by cohort, bucket_order;

-- The habit moment candidate: the smallest early-activity bucket whose retention interval
-- lower bound reaches habit_target_retention. Using the lower bound keeps tiny buckets
-- from qualifying by luck.
create or replace view gold_habit_threshold as
select c.cohort,
       p.habit_target_retention as target_retention,
       arg_min(c.early_active_days_bucket, c.bucket_order)
           filter (where c.retained_ci_low >= p.habit_target_retention) as threshold_bucket
from gold_habit_curve c
cross join params p
group by c.cohort, p.habit_target_retention
order by c.cohort;

-- Weekly usage retention by signup month. A cell only exists once week n has fully
-- elapsed for that user, so recent cohorts end earlier instead of showing a false drop.
create or replace view gold_usage_retention as
with weeks as (
    select cast(unnest(range(0, 13)) as integer) as week_n  -- weeks 0..12; INTEGER so date + 7n works
),
active as (
    select distinct user_id, day_index // 7 as week_n
    from silver_usage_events
    where day_index >= 0
),
grid as (
    select j.signup_month, j.user_id, w.week_n
    from silver_user_journey j
    cross join weeks w
    cross join silver_extent x
    where j.signup_date + 7 * (w.week_n + 1) <= x.usage_end
),
agg as (
    select g.signup_month, g.week_n,
           count(*) as cohort_users,
           count(a.user_id) as active_users
    from grid g
    left join active a on a.user_id = g.user_id and a.week_n = g.week_n
    group by g.signup_month, g.week_n
)
select signup_month, week_n, cohort_users, active_users,
       safe_rate(active_users, cohort_users) as retention_rate,
       wilson_low(active_users, cohort_users) as retention_ci_low,
       wilson_high(active_users, cohort_users) as retention_ci_high
from agg
order by signup_month, week_n;
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest funnels/tests -o addopts="" -q`
Expected: all tests so far pass.

- [ ] **Step 5: Commit**

```bash
git add funnels/sql/07_gold_habit.sql funnels/tests/test_gold_habit.py
git commit -m "feat(funnels): add habit curve, habit threshold and usage retention views"
```

---

### Task 9: Report CLI

**Files:**
- Create: `funnels/report.py`, `funnels/__main__.py`
- Test: `funnels/tests/test_report.py`

**Interfaces:**
- Consumes: `build()`, `DEFAULT_RAW_DIR`, all nine Gold views.
- Produces: `funnels.report.GOLD_VIEWS: list[str]` (the nine Gold view names, in the order the report prints them); `format_table(columns: list[str], rows: list[tuple]) -> str` (ASCII, left-aligned, floats to 3 decimals, `None` as `-`); `render(con, views=GOLD_VIEWS) -> str`; `funnels.__main__.main(argv=None) -> int` with options `--raw-dir PATH`, `--db PATH`, `--view NAME` (repeatable, restricted to `GOLD_VIEWS`).

- [ ] **Step 1: Write the failing test**

Write `funnels/tests/test_report.py`:

```python
from __future__ import annotations

import pytest

from funnels.__main__ import main
from funnels.report import GOLD_VIEWS, format_table, render


def test_format_table_aligns_columns_and_formats_values():
    text = format_table(["name", "rate"], [("a", 0.5), ("longer", None), ("c", 3)])
    assert text.splitlines() == [
        "name    rate",
        "------  -----",
        "a       0.500",
        "longer  -",
        "c       3",
    ]


def test_format_table_with_no_rows_still_prints_headers():
    assert format_table(["x", "y"], []).splitlines() == ["x  y", "-  -"]


def test_render_prints_a_section_per_view(con):
    text = render(con)
    for view in GOLD_VIEWS:
        assert f"## {view}" in text


def test_render_single_view(con):
    text = render(con, ["gold_habit_threshold"])
    assert text.startswith("## gold_habit_threshold")
    assert "gold_acquisition_funnel" not in text


def test_gold_views_all_exist_and_are_queryable(query):
    for view in GOLD_VIEWS:
        query(f"select * from {view}")


def test_cli_prints_report(raw_dir, capsys):
    assert main(["--raw-dir", str(raw_dir)]) == 0
    out = capsys.readouterr().out
    assert "## gold_acquisition_funnel" in out
    assert "referral" in out


def test_cli_view_filter(raw_dir, capsys):
    assert main(["--raw-dir", str(raw_dir), "--view", "gold_activation_funnel"]) == 0
    out = capsys.readouterr().out
    assert "## gold_activation_funnel" in out
    assert "## gold_habit_curve" not in out


def test_cli_rejects_unknown_view(raw_dir):
    with pytest.raises(SystemExit):
        main(["--raw-dir", str(raw_dir), "--view", "users; drop table params"])


def test_cli_can_persist_the_warehouse(raw_dir, tmp_path, capsys):
    db = tmp_path / "wh.duckdb"
    assert main(["--raw-dir", str(raw_dir), "--db", str(db), "--view", "gold_habit_threshold"]) == 0
    capsys.readouterr()
    assert db.exists()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest funnels/tests/test_report.py -o addopts="" -q`
Expected: collection error `ModuleNotFoundError: No module named 'funnels.__main__'` (or `funnels.report`).

- [ ] **Step 3: Write the implementation**

Write `funnels/report.py`:

```python
"""Plain-text rendering of the Gold views."""
from __future__ import annotations

import duckdb

GOLD_VIEWS = [
    "gold_acquisition_funnel",
    "gold_acquisition_cohorts",
    "gold_activation_funnel",
    "gold_aha_features",
    "gold_aha_feature_lift",
    "gold_aha_behaviors",
    "gold_habit_curve",
    "gold_habit_threshold",
    "gold_usage_retention",
]


def _fmt(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def format_table(columns: list[str], rows: list[tuple]) -> str:
    cells = [[_fmt(v) for v in row] for row in rows]
    widths = [max([len(col)] + [len(r[i]) for r in cells]) for i, col in enumerate(columns)]

    def line(parts: list[str]) -> str:
        return "  ".join(p.ljust(w) for p, w in zip(parts, widths)).rstrip()

    return "\n".join(
        [line(list(columns)), line(["-" * w for w in widths]), *[line(r) for r in cells]]
    )


def render(con: duckdb.DuckDBPyConnection, views: list[str] | None = None) -> str:
    blocks = []
    for view in views or GOLD_VIEWS:
        if view not in GOLD_VIEWS:  # view names are interpolated into SQL below
            raise ValueError(f"unknown view: {view}")
        cursor = con.execute(f"select * from {view}")
        columns = [d[0] for d in cursor.description]
        blocks.append(f"## {view}\n{format_table(columns, cursor.fetchall())}")
    return "\n\n".join(blocks)
```

Write `funnels/__main__.py`:

```python
"""python -m funnels: build the warehouse and print the Gold views."""
from __future__ import annotations

import argparse
from pathlib import Path

from funnels.config import DEFAULT_RAW_DIR
from funnels.report import GOLD_VIEWS, render
from funnels.warehouse import build


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m funnels",
        description="Build the funnel analytics warehouse and print the Gold views.",
    )
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR,
                        help="directory with the raw files (default: data/raw)")
    parser.add_argument("--db", type=Path, default=None,
                        help="also persist the warehouse to this DuckDB file")
    parser.add_argument("--view", action="append", choices=GOLD_VIEWS,
                        help="print only this view (repeatable)")
    args = parser.parse_args(argv)

    con = build(args.raw_dir, db_path=args.db)
    try:
        print(render(con, args.view))
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest funnels/tests -o addopts="" -q`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add funnels/report.py funnels/__main__.py funnels/tests/test_report.py
git commit -m "feat(funnels): add report renderer and python -m funnels CLI"
```

---

### Task 10: Real-data invariants, sanity checks, documentation

**Files:**
- Test: `funnels/tests/test_real_data.py`
- Create: `docs/funnel_metrics.md`, `docs/funnel_report.txt`
- Modify: `README.md`

**Interfaces:**
- Consumes: everything above, and the real `data/raw`.
- Produces: tests that fail loudly if the snapshot or the SQL drifts; a metric-definition document; a committed text snapshot of the report.

- [ ] **Step 1: Write the real-data tests**

Write `funnels/tests/test_real_data.py`:

```python
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
```

- [ ] **Step 2: Run the real-data tests**

Run: `python -m pytest funnels/tests/test_real_data.py -o addopts="" -q`
Expected: all pass. If `test_engineered_channel_signal...` or `test_habit_curve...` fails, do **not** loosen the assertion blindly: run `python -m funnels --view gold_acquisition_funnel --view gold_habit_curve`, read the numbers, and decide whether the SQL or the assertion is wrong; record the decision in the commit message.

- [ ] **Step 3: Generate the report snapshot and inspect it**

```bash
python -m funnels > docs/funnel_report.txt
```

Open `docs/funnel_report.txt` and compare with the values the plan's author got on the committed data (about 42 KB, runtime under a second):

| View | Expected |
|---|---|
| `gold_acquisition_funnel`, total | 5000 signups, 5000 observed, 2427 activated (48.5%), 1345 converted within 30 days (26.9%, interval 25.7%-28.1%), 13.8 average days to convert |
| `gold_acquisition_funnel`, channels | referral highest (36.1%); paid_social (18.9%) and outbound (19.5%) lowest; 226 `unattributed` users at 30.5% |
| `gold_activation_funnel`, all | 2261 viewed, 2427 activated, 1103 shared, 534 multi-feature; median 5 days to first use; technology (57.0%) and education (55.3%) activate most, manufacturing (31.9%) and healthcare (37.9%) least |
| `gold_aha_feature_lift` | five features (custom_workflows is released too late to have a baseline cohort); only `team_analytics` has `ci_excludes_zero = true`, and it is negative (-9.1 points, 82 users); it is released on 2024-09-01, so its "available" users are only late signups, which makes it a confounded comparison, not evidence that the feature hurts |
| `gold_aha_behaviors` | conversion after the landmark is 15%-22% at every well-populated level with no monotonic trend (0 early active days 15.0%, 1 day 22.2%, 2-3 days 20.4%, 4-6 days 16.7%): there is no clean aha threshold in this snapshot, and the snapshot must not be reported as having one |
| `gold_habit_curve`, `all_users` | retained 9.4% / 52.8% / 70.8% / 87.0% / 100% (7+ bucket is `low_n`) for 0 / 1 / 2-3 / 4-6 / 7+ early active days |
| `gold_habit_threshold` | `4-6` for both cohorts |

If a number differs by more than rounding, stop and find out why before committing the snapshot.

- [ ] **Step 4: Write the metrics document**

Write `docs/funnel_metrics.md`:

````markdown
# Funnel metrics

How the acquisition, activation, aha-moment and habit-moment analytics are
defined, and how to read them. Implementation: the `funnels/` package
([ADR 0009](adr/0009-right-sized-funnel-analytics-on-duckdb.md)). Output
snapshot for the committed data: [funnel_report.txt](funnel_report.txt).

## Run it

```bash
python -m pip install -e ".[funnels]"
python -m funnels                              # print every Gold view
python -m funnels --view gold_habit_curve      # one view
python -m funnels --db data/warehouse.duckdb   # also keep a queryable file
python -m pytest funnels/tests -o addopts=""   # tests
```

All windows and thresholds are fields of `funnels.config.Params`.

## Definitions

Day index = days since the user's signup date (day 0 = signup date).

| Term | Definition (defaults) |
|---|---|
| Early window | day index 0..13 (`early_window_days = 14`) |
| Activated | at least one `use` event in the early window |
| Multi-feature | `use` events on at least 2 distinct features in the early window |
| Converted in window | free-to-paid conversion with `days_to_convert < 30` (`outcome_window_days`) |
| Observed | the relevant window has fully elapsed by the data's observation end (latest event date / latest conversion date, or `Params.usage_end` / `conversion_end`) |
| Landmark | the end of the early window. The aha cohort is users **still free at the landmark** whose next 30 days are observed |
| Converted after landmark | `14 <= days_to_convert < 44` |
| Retained | at least 2 distinct active days in day index 28..55 |
| Habit moment | smallest early-active-days bucket whose retention 95% interval **lower bound** is at least 0.80 |

## Views

| View | Grain | Question |
|---|---|---|
| `gold_acquisition_funnel` | channel x campaign, channel, total | Which channels and campaigns bring users who activate and convert, how fast, at what MRR? |
| `gold_acquisition_cohorts` | signup month x channel | Is channel quality stable over time? |
| `gold_activation_funnel` | segment (all, channel, company size, industry) | What share reach view / use / share / multi-feature in 14 days? How long to first use? |
| `gold_aha_features` | feature x cohort | After 14 days, how do users who used a feature convert vs those who could have but did not vs those who could not? |
| `gold_aha_feature_lift` | feature | Difference in later conversion, with a 95% interval |
| `gold_aha_behaviors` | behavior x level | Does conversion change with the number of features used, active days, or sharing in the first 14 days? |
| `gold_habit_curve` | cohort x early-active-days bucket | How does early activity relate to still using the product in weeks 5-8? |
| `gold_habit_threshold` | cohort | Smallest bucket that clears the target |
| `gold_usage_retention` | signup month x week | Weekly usage retention triangle |

Silver tables: `silver_user_dim` and `silver_feature_states` (as in the
[data dictionary](data_dictionary.md)), `silver_usage_events` (adds
`day_index`, drops orphan events) and `silver_user_journey` (one row per user,
every Gold view reads from it).

## How to read the numbers

- **Windows are honest.** Users whose window has not elapsed are excluded from
  that metric's denominator. They still count in `signups`.
- **Every rate has a 95% Wilson interval** (differences use a Wald interval) and
  a `low_n` flag for groups under 30 users. Do not rank rows whose intervals overlap.
- **Aha uses a landmark, not "used before converting".** Converters have far more
  usage after converting (15,861 events) than before (3,011), so comparing
  "used the feature before converting" against non-users is biased.
- **Habit curve is descriptive.** People who are active early tend to stay active.
  The `free_at_landmark` cohort removes users who had already paid, but neither
  cohort shows that early usage *causes* retention.
- **Six features are compared in `gold_aha_feature_lift`.** An interval that excludes
  zero is a lead to test with an experiment, not a finding.
- **Activation steps are reach counts, not a strict funnel.** A user can share
  without a recorded view.
- **Synthetic data.** Signals were engineered (ADR 0004). Absolute values are not
  benchmarks.

## Differences from the data dictionary

- Bronze objects are views over `data/raw`, with `timestamp` exposed as
  `event_timestamp` plus `event_date`, and feature `id`/`name` as
  `feature_id`/`feature_name`. There is no `ingestion_timestamp` or generated
  `event_id`.
- `silver_feature_usage_facts` and the Gold marts `gold_channel_performance`,
  `gold_feature_conversion_impact`, `gold_mrr_waterfall` and
  `gold_weekly_engagement` are not built here. The acquisition, aha and habit
  views replace the first two with window-aware, landmark-based versions.
````

- [ ] **Step 5: Update the README**

In `README.md`, replace the sentence `but no graph model or data has been loaded.` with:

```
but no graph model or data has been loaded.

Funnel analytics (acquisition, activation, aha moment, habit moment) run today
on DuckDB straight from the raw files: `python -m funnels`. See
[docs/funnel_metrics.md](docs/funnel_metrics.md) and
[ADR 0009](docs/adr/0009-right-sized-funnel-analytics-on-duckdb.md).
```

In the `## Documentation` list, insert before the line `- [Project references](references.md): related open-source projects and tools.`:

```
- [Funnel metrics](docs/funnel_metrics.md): definitions, views and caveats for
  the acquisition, activation, aha-moment and habit-moment analytics;
  [funnel_report.txt](docs/funnel_report.txt) is the output on the committed data.
```

- [ ] **Step 6: Run the whole suite**

Run: `python -m pytest funnels/tests -o addopts="" -q`
Expected: all tests pass. Then `python -m pytest graph/tests/test_connection_unit.py -o addopts="" -q` still passes (the new package must not break the existing one).

- [ ] **Step 7: Commit**

```bash
git add funnels/tests/test_real_data.py docs/funnel_metrics.md docs/funnel_report.txt README.md
git commit -m "docs: add funnel metrics, real-data checks and report snapshot"
```

---

## Self-Review

**1. Spec coverage** (requirements from the conversation):
- Acquisition funnel -> Task 5 (`gold_acquisition_funnel`, `gold_acquisition_cohorts`).
- Activation funnel -> Task 6 (`gold_activation_funnel`, segmented by channel, company size, industry).
- Aha moments -> Task 7 (`gold_aha_features`, `gold_aha_feature_lift`, `gold_aha_behaviors`; landmark design for the pre-conversion bias).
- Habit moment -> Task 8 (`gold_habit_curve`, `gold_habit_threshold`, `gold_usage_retention`).
- "Workable for this amount of data" -> Task 1 ADR 0009 and the whole architecture (no Spark/Delta/Airflow).
- Use `docs/data_dictionary.md` -> table names in Tasks 2-3 follow it; deviations listed in `docs/funnel_metrics.md` (Task 10).
- Gaps found: none. Out of scope on purpose: MRR waterfall, subscription survival, journey/graph layers, chatbot, synthetic data generator, Airflow.

**2. Placeholder scan:** every step contains the actual code, SQL, command and expected result; no TBD.

**3. Type and name consistency:** `silver_user_journey` columns are listed once in Task 4 and used by name in Tasks 5-8 (`converted_in_window`, `landmark_member`, `converted_after_landmark`, `free_at_landmark`, `early_*`, `late_active_days`, `*_window_observed`). Macros are defined in Task 1 and used with the same signatures in Tasks 5-8. `GOLD_VIEWS` (Task 9) lists the nine views produced in Tasks 5-8.

**4. Review Focus:** items 1-9 above each name the task whose tests pin them.

## Open questions for the owner

1. **Retention definition.** "Active on 2+ days in days 28-55" is a judgment call; it is a one-line `Params` change. If a stricter or looser definition is wanted, change `retained_min_active_days` and re-read `gold_habit_threshold`.
2. **Observation end for conversions.** The plan derives it from the data (latest conversion date, 2024-11-02). If the real extract date is later, set `Params.conversion_end`, which only matters for cohorts signed up within 30 days of 2024-11-02.
3. **Persisting results.** Gold views are recomputed on every run (about a second). If a dashboard or the graph layer needs stable tables, add a `--materialize` option later; it is deliberately not in this plan.
