# Raw Data Consistency Checks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A library of Python consistency checks over the six raw files in `data/raw`. A daily cron job or an integration pipeline can call it to catch data discrepancies before Silver and Gold are built.

**Architecture:** A new top-level package, `data_checks/`, uses only the standard library. `load_snapshot(raw_dir)` reads the raw files into plain dicts and never raises on bad content. Each check is a small function registered under a stable ID (A1 to G6) with a severity (`error` or `warn`). `Check.evaluate(snapshot, config)` wraps the function and always returns a `CheckResult`, even when the check is skipped or crashes. Thresholds live in one `CheckConfig` dataclass, and the expected schema and value lists live in `contract.py`.

**Tech Stack:** Python >= 3.10, standard library only, pytest >= 8.

**Spec:** No separate design doc. The checks are the list reviewed in the conversation that produced this plan (IDs A1 to G6, severities and "today" results). The user's direction: "implement it as python code consistency checks done on daily basis using cron or as part of integration pipeline - do not write code to run these checks - just checks themselves". The facts about the data below were measured on 2026-11-26 against the committed snapshot.

## Why this shape (read first)

| Fact | Consequence |
|---|---|
| The DuckDB Bronze views in `funnels/sql/01_bronze.sql` turn a **renamed** JSON key into an all-NULL column and silently drop **new** keys (verified with DuckDB on 2026-11-26). Only a wrong type fails loudly. | The checks read the raw JSON themselves, with no DuckDB, so A2 can see the exact set of keys in each record. |
| The existing invariants in `funnels/tests/test_real_data.py` are pytest tests with hard-coded row counts (5000, 48666, ...). | Those stay as they are. The new checks use bands and an optional baseline (G1) instead of exact counts, so a legitimate daily refresh does not trip them. |
| Every hard check passes on today's snapshot. | The real-data test (Task 8) asserts that every check is PASS (G1 is SKIPPED because it has no baseline). Any future failure is a real change in the data. |
| `used_real_time_collab` means "ever used". 148 of 1,526 converters (0.0970) are flagged `true` but first used the feature after converting. | D4 locks in the "ever used" meaning as an error. D5 measures the after-conversion share as a warning, with a maximum of 0.15. |
| 133 of 1,526 converters (0.0872) have no usage events at all. 115 of 253 cancelled users (0.4545) used the product after cancelling. 226 of 5,000 signups (0.0452) are unattributed. | G4, G5 and G3 are measurement checks (warn), with bands of max 0.15, max 0.60 and 0.03 to 0.07. |
| Signups and usage have no empty day inside their date range; the largest daily spike is 2.9x the median. Conversions (longest gap 7 days) and subscription events (3 days) are naturally sparse. | G2 covers only `user_signups` and `feature_usage_events`, with a maximum gap of 2 days and a spike factor of 5.0. |
| The reviewed check F4 (start MRR + sum of MRR changes = latest MRR) is implied by F1: the sum telescopes once each `previous_mrr` equals the prior `mrr`. | F4 is dropped. Its ID is not reused. |
| `feature_usage_events.jsonl` is not sorted (19,450 adjacent pairs for the same user are out of time order). | No check may depend on the order of rows in a file. The fixture's usage rows are deliberately unsorted. |

## Global Constraints

- Python `>=3.10`. **No new dependencies**: `data_checks` imports only the standard library.
- **Out of scope:** any code that runs the checks. That means no CLI, no `__main__`, no loop over all checks that turns results into an exit code, no cron or CI config, no persisted baseline and no notifications. The package only provides `load_snapshot`, `all_checks()`, `Check.evaluate` and `row_counts`. `docs/data_checks.md` describes, in prose, how a runner should call them.
- `data/raw/` is read-only. The checks never write files.
- `Check.evaluate` never raises. A check that hits an exception returns `Status.ERRORED`, so one broken check cannot hide the others.
- Each check reports only its own concern. A value that cannot be parsed (a bad date, a non-int MRR, a null) is A3's or A4's job. Every other check skips that value and does not fail on it.
- Checks must not depend on the order of rows in a file. Subscription events are ordered by `(event_date, event_id)`.
- Test command: `../growth-analytics/.venv/Scripts/python.exe -m pytest data_checks/tests -o addopts="" -q`. The `-o addopts=""` stops pytest from rewriting the tracked `docs/test-reports/junit.xml`.
- Commit messages follow the repo style (`feat(data-checks): ...`, `test: ...`, `docs: ...`) and have **no** Claude co-author trailer (user preference, as recorded in `docs/superpowers/plans/2026-10-10-funnel-analytics.md`).
- Work on a new branch, `feat/data-consistency-checks`, in a worktree created from `origin/main`. The current checkout is on a stale branch.

## Review Focus

1. **Malformed values in any field** (wrong type, null, garbage string). Expected: only A3 or A4 fail, and no check is ERRORED. Covered by `test_no_check_crashes_on_garbage`, which is parametrized over every registered check. [Task 2]
2. **Missing or empty files.** Expected: A1 fails, and the other checks pass or skip but never crash. A measurement check whose denominator is 0 is SKIPPED. Covered by `test_no_check_crashes_on_empty_snapshot`. [Task 2]
3. **Rows in arbitrary file order.** Expected: the same results as sorted input. The clean fixture's usage rows are unsorted, and `test_subscription_checks_ignore_file_order` reverses the subscription events. [Task 1 fixture, Task 6]
4. **Two subscription events on the same day.** Expected: they are ordered by `event_id`, and the sequence checks still pass. Covered by `test_same_day_events_ordered_by_event_id`. [Task 6]
5. **Optional inputs absent** (no `_feature_users_metadata.json`, no baseline, no expected-signal channels configured). Expected: D6, G1 and G6 are SKIPPED, never FAIL. [Task 4, Task 7]

---

## File Structure

```
data_checks/
  __init__.py          # public API re-exports; imports data_checks.checks to register everything
  model.py             # Severity, Status, Finding, CheckResult, SkipCheck, Check(.evaluate)
  registry.py          # @check decorator, all_checks(), get_check()
  snapshot.py          # SOURCE_FILES, Snapshot, load_snapshot, as_int/as_date/as_timestamp, row_counts
  config.py            # CheckConfig (every threshold), DEFAULT_RAW_DIR
  contract.py          # FIELDS, NULL_ALLOWED, value domains, CAMPAIGNS_BY_CHANNEL
  checks/
    __init__.py        # imports each check module (registration side effect)
    schema.py          # A1-A5
    integrity.py       # B1-B4, C1-C3
    cross_file.py      # D1-D6
    temporal.py        # E1-E4
    subscriptions.py   # F1, F2, F3, F5
    drift.py           # G1-G6
  tests/
    __init__.py
    fixture_data.py    # clean 4-user snapshot + edit helpers + FIXTURE_CONFIG + run()
    test_snapshot.py
    test_model.py
    test_all_checks.py # parametrized over all_checks(): clean -> expected status; garbage/empty -> no ERRORED
    test_schema.py
    test_integrity.py
    test_cross_file.py
    test_temporal.py
    test_subscriptions.py
    test_drift.py
    test_real_data.py
docs/data_checks.md     # check catalogue + runner contract (prose)
pyproject.toml          # add data_checks to packages and testpaths
README.md               # one line under Documentation
```

---

### Task 1: Worktree, core model, snapshot loader, config, fixture

**Files:**
- Create: `data_checks/__init__.py`, `data_checks/model.py`, `data_checks/registry.py`, `data_checks/snapshot.py`, `data_checks/config.py`, `data_checks/checks/__init__.py` (empty for now), `data_checks/tests/__init__.py`, `data_checks/tests/fixture_data.py`, `data_checks/tests/test_snapshot.py`, `data_checks/tests/test_model.py`
- Modify: `pyproject.toml` (`[tool.setuptools.packages.find] include` add `"data_checks*"`; `[tool.pytest.ini_options] testpaths` add `"data_checks/tests"`)
- Add: this plan file to `docs/superpowers/plans/`

**Interfaces:**
- Produces (`model.py`):
  - `class Severity(str, Enum): ERROR = "error"; WARN = "warn"`
  - `class Status(str, Enum): PASS = "pass"; FAIL = "fail"; SKIPPED = "skipped"; ERRORED = "errored"`
  - `class SkipCheck(Exception)`: a check raises `SkipCheck(reason)` when it cannot apply.
  - `@dataclass(frozen=True) class Finding: violations: list[str]; metric: float | None = None`
  - `@dataclass(frozen=True) class CheckResult: check_id: str; title: str; severity: Severity; status: Status; violation_count: int; samples: tuple[str, ...]; metric: float | None; detail: str`
  - `@dataclass(frozen=True) class Check: check_id: str; title: str; severity: Severity; fn: Callable[[Snapshot, CheckConfig], Finding]` with `def evaluate(self, snap: Snapshot, cfg: CheckConfig) -> CheckResult`
- Produces (`registry.py`): `def check(check_id: str, title: str, severity: Severity) -> Callable[[F], F]` (registers, returns `fn` unchanged, `ValueError` on a duplicate ID); `def all_checks() -> list[Check]` (sorted by ID); `def get_check(check_id: str) -> Check` (`KeyError` if unknown)
- Produces (`snapshot.py`):
  - `SOURCE_FILES: dict[str, str]` = `{"user_signups": "user_signups.jsonl", "marketing_attribution": "marketing_attribution.jsonl", "conversions": "conversions.jsonl", "subscription_events": "subscription_events.jsonl", "feature_usage_events": "feature_usage_events.jsonl", "feature_releases": "feature_releases.json"}`
  - `METADATA_FILE = "_feature_users_metadata.json"`
  - `@dataclass(frozen=True) class Snapshot: records: dict[str, list[dict]]; missing_files: tuple[str, ...] = (); parse_errors: dict[str, tuple[str, ...]] = field(default_factory=dict); metadata: dict | None = None`. `records` always has every key in `SOURCE_FILES`.
  - `def load_snapshot(raw_dir: Path | str) -> Snapshot`
  - `def as_int(v: object) -> int | None` (`bool` is not an int), `def as_date(v: object) -> date | None` (strict `YYYY-MM-DD`), `def as_timestamp(v: object) -> datetime | None` (strict `%Y-%m-%d %H:%M:%S`), `def event_date(v: object) -> date | None` (`as_date` or the date part of `as_timestamp`)
  - `def row_counts(snap: Snapshot) -> dict[str, int]`
- Produces (`config.py`): `DEFAULT_RAW_DIR = <repo root>/data/raw` and `@dataclass(frozen=True) class CheckConfig` with these fields and defaults:

  | Field | Default | Used by |
  |---|---|---|
  | `window_start: date` | `date(2023, 12, 1)` | E4 |
  | `window_end: date` | `date(2024, 12, 31)` | E4 |
  | `as_of: date \| None` | `None` (means `date.today()`) | E4 |
  | `max_touch_lag_days: int` | `30` | E1 |
  | `plan_mrr_bands: Mapping[str, tuple[int, int]]` | `{"pro": (29, 1986), "enterprise": (199, 9957)}` | F5 |
  | `baseline_row_counts: Mapping[str, int] \| None` | `None` | G1 |
  | `row_count_tolerance: float` | `0.20` | G1 |
  | `dense_sources: tuple[str, ...]` | `("user_signups", "feature_usage_events")` | G2 |
  | `max_gap_days: int` | `2` | G2 |
  | `spike_factor: float` | `5.0` | G2 |
  | `unattributed_share_band: tuple[float, float]` | `(0.03, 0.07)` | G3 |
  | `max_converters_without_usage_share: float` | `0.15` | G4 |
  | `max_usage_after_cancel_share: float` | `0.60` | G5 |
  | `max_rtc_first_use_after_conversion_share: float` | `0.15` | D5 |
  | `best_channel: str \| None` | `"referral"` | G6 |
  | `worst_channels: tuple[str, ...] \| None` | `("outbound", "paid_social")` | G6 |
  | `sample_size: int` | `5` | evaluate |

  Mappings use `field(default_factory=...)`.
- Produces (`tests/fixture_data.py`): `CLEAN: dict[str, list[dict]]`, `CLEAN_METADATA: dict`, `FIXTURE_CONFIG: CheckConfig`, `make_snapshot(metadata=<CLEAN_METADATA copy>, **sources) -> Snapshot` (sources that are not passed come from `CLEAN`, deep-copied), `edit(source, index, **changes) -> list[dict]`, `append(source, row) -> list[dict]`, `remove(source, index) -> list[dict]` (all return deep copies of the clean list), `write_raw(path: Path, records: dict | None = None, metadata: dict | None = CLEAN_METADATA) -> Path` (writes the files in raw format: JSONL, plus a JSON array for releases), `run(check_id: str, snap: Snapshot, cfg: CheckConfig = FIXTURE_CONFIG) -> CheckResult`

**The clean fixture.** All later tests mutate this data. It must pass every check under `FIXTURE_CONFIG`.

`user_signups` (email is `user{id}@example.com`):

| idx | user_id | signup_date | company_size | industry |
|---|---|---|---|---|
| 0 | 1 | 2024-01-10 | 1-10 | technology |
| 1 | 2 | 2024-01-10 | 11-50 | finance |
| 2 | 3 | 2024-02-01 | 51-200 | retail |
| 3 | 4 | 2024-02-01 | 1-10 | education |

`marketing_attribution` (user 4 is unattributed on purpose):

| idx | user_id | channel | campaign | first_touch_date |
|---|---|---|---|---|
| 0 | 1 | referral | user_invite | 2024-01-05 |
| 1 | 2 | paid_search | google_brand | 2024-01-10 |
| 2 | 3 | organic_search | seo_blog | 2024-01-20 |

`conversions`:

| idx | user_id | conversion_date | plan | mrr | signup_date | days_to_convert | used_real_time_collab |
|---|---|---|---|---|---|---|---|
| 0 | 1 | 2024-01-20 | pro | 49 | 2024-01-10 | 10 | true |
| 1 | 2 | 2024-03-10 | enterprise | 2000 | 2024-01-10 | 60 | false |

`subscription_events`:

| idx | event_id | user_id | event_date | event_type | plan | mrr | previous_plan | previous_mrr |
|---|---|---|---|---|---|---|---|---|
| 0 | 1 | 1 | 2024-01-20 | subscription_started | pro | 49 | null | null |
| 1 | 2 | 2 | 2024-03-10 | subscription_started | enterprise | 2000 | null | null |
| 2 | 3 | 1 | 2024-03-01 | seats_expanded | pro | 98 | pro | 49 |
| 3 | 4 | 1 | 2024-05-01 | plan_upgraded | enterprise | 500 | pro | 98 |
| 4 | 5 | 2 | 2024-06-01 | subscription_cancelled | null | 0 | enterprise | 2000 |

`feature_usage_events` (deliberately not in time order):

| idx | timestamp | user_id | feature_id | feature_name | event_type |
|---|---|---|---|---|---|
| 0 | 2024-03-05 09:00:00 | 1 | 2 | ai_insights | use |
| 1 | 2024-01-18 10:00:00 | 1 | 1 | real_time_collab | view |
| 2 | 2024-02-02 12:00:00 | 3 | 1 | real_time_collab | use |
| 3 | 2024-03-02 08:00:00 | 2 | 2 | ai_insights | share |

`feature_releases`: `[{id 1, real_time_collab, 2024-01-15, v1.0}, {id 2, ai_insights, 2024-03-01, v1.0}, {id 1, real_time_collab, 2024-07-01, v2.0}]` (index 0, 1, 2)

`CLEAN_METADATA = {"users_with_real_time_collab": [1, 3], "percentage": 0.5, "total_users": 4, "per_feature_adoption": {"real_time_collab": 2, "ai_insights": 2}}`

`FIXTURE_CONFIG = CheckConfig(as_of=date(2024, 12, 31), max_gap_days=30, unattributed_share_band=(0.0, 0.5), best_channel=None, worst_channels=None)`

- [ ] **Step 1: Create the worktree and branch**

```bash
cd /c/Projects/analytics/growth-analytics
git fetch origin
git worktree add ../growth-analytics-checks -b feat/data-consistency-checks origin/main
cp docs/superpowers/plans/2026-11-26-data-consistency-checks.md ../growth-analytics-checks/docs/superpowers/plans/
cd ../growth-analytics-checks
```

Every later command runs from `../growth-analytics-checks`.

- [ ] **Step 2: Write the failing tests**

`data_checks/tests/test_snapshot.py`:

```python
def test_loads_every_source_from_a_valid_dir(tmp_path):
    snap = load_snapshot(write_raw(tmp_path))
    assert row_counts(snap) == {"user_signups": 4, "marketing_attribution": 3, "conversions": 2,
                                "subscription_events": 5, "feature_usage_events": 4, "feature_releases": 3}
    assert snap.missing_files == () and snap.parse_errors == {}
    assert snap.metadata == CLEAN_METADATA

def test_missing_file_is_recorded_not_raised(tmp_path):
    raw = write_raw(tmp_path); (raw / "conversions.jsonl").unlink()
    snap = load_snapshot(raw)
    assert snap.missing_files == ("conversions.jsonl",) and snap.records["conversions"] == []

def test_bad_line_is_recorded_and_other_lines_kept(tmp_path):
    raw = write_raw(tmp_path)
    with open(raw / "user_signups.jsonl", "a", encoding="utf-8") as f:
        f.write("\nnot json\n[1, 2]\n")
    snap = load_snapshot(raw)
    assert len(snap.records["user_signups"]) == 4          # blank line skipped
    assert len(snap.parse_errors["user_signups"]) == 2     # non-JSON and non-object
    assert snap.parse_errors["user_signups"][0].startswith("line 6:")

def test_releases_must_be_a_json_array(tmp_path):
    raw = write_raw(tmp_path); (raw / "feature_releases.json").write_text('{"id": 1}')
    snap = load_snapshot(raw)
    assert snap.records["feature_releases"] == [] and len(snap.parse_errors["feature_releases"]) == 1

def test_absent_metadata_is_none(tmp_path):
    assert load_snapshot(write_raw(tmp_path, metadata=None)).metadata is None

def test_raw_dir_that_does_not_exist_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_snapshot(tmp_path / "nope")

def test_value_parsers_are_strict():
    assert as_int(5) == 5 and as_int(True) is None and as_int("5") is None
    assert as_date("2024-01-10") == date(2024, 1, 10) and as_date("2024-1-10") is None and as_date(None) is None
    assert as_timestamp("2024-01-18 10:00:00") == datetime(2024, 1, 18, 10) and as_timestamp("2024-01-18T10:00:00") is None
    assert event_date("2024-01-18 10:00:00") == date(2024, 1, 18) and event_date("2024-01-18") == date(2024, 1, 18)
```

`data_checks/tests/test_model.py` registers throwaway checks in a local `Check(...)` (not with `@check`, so the global registry stays clean):

```python
def test_evaluate_pass_fail_samples_and_metric():
    c = Check("Z1", "t", Severity.WARN, lambda s, cfg: Finding([f"v{i}" for i in range(7)], metric=0.5))
    r = c.evaluate(make_snapshot(), FIXTURE_CONFIG)
    assert (r.status, r.violation_count, r.samples, r.metric) == (Status.FAIL, 7, ("v0", "v1", "v2", "v3", "v4"), 0.5)
    assert Check("Z2", "t", Severity.ERROR, lambda s, cfg: Finding([])).evaluate(make_snapshot(), FIXTURE_CONFIG).status == Status.PASS

def test_evaluate_skip_and_crash_never_raise():
    def skip(s, cfg): raise SkipCheck("no baseline")
    def boom(s, cfg): raise KeyError("x")
    r1 = Check("Z3", "t", Severity.WARN, skip).evaluate(make_snapshot(), FIXTURE_CONFIG)
    r2 = Check("Z4", "t", Severity.ERROR, boom).evaluate(make_snapshot(), FIXTURE_CONFIG)
    assert (r1.status, r1.detail) == (Status.SKIPPED, "no baseline")
    assert r2.status == Status.ERRORED and r2.detail.startswith("KeyError")

def test_duplicate_check_id_is_rejected():
    with pytest.raises(ValueError):
        check("A1", "dup", Severity.ERROR)(lambda s, cfg: Finding([]))
```

The duplicate-ID test only passes once A1 exists, so mark it `@pytest.mark.skipif(not any(c.check_id == "A1" for c in all_checks()), reason="A1 lands in Task 2")`.

- [ ] **Step 3: Run the tests and confirm they fail**

Run: `../growth-analytics/.venv/Scripts/python.exe -m pytest data_checks/tests -o addopts="" -q`
Expected: collection errors (`ModuleNotFoundError: data_checks`).

- [ ] **Step 4: Implement `model.py`, `registry.py`, `snapshot.py`, `config.py`, `fixture_data.py`, update `pyproject.toml`**

`load_snapshot` reads each file as UTF-8. For JSONL, blank lines are skipped, and a line that is not a JSON object is recorded as `"line N: <reason>"`. For the releases file, any top-level value that is not an array of objects is a single parse error. A file that is missing goes into `missing_files` (file name) and its list is `[]`. If the metadata file is missing, `metadata` is `None`. If it is present but unparseable, `metadata` is also `None` and `parse_errors["_metadata"]` holds the error. `evaluate` builds `detail` from the `SkipCheck` reason, from `f"{type(e).__name__}: {e}"` for a crash, and is otherwise `""`.

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `../growth-analytics/.venv/Scripts/python.exe -m pytest data_checks/tests -o addopts="" -q`
Expected: all pass; one skipped (the duplicate-ID test).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml data_checks docs/superpowers/plans/2026-11-26-data-consistency-checks.md
git commit -m "feat(data-checks): add check model, registry, snapshot loader and config"
```

---

### Task 2: Contract and schema checks A1 to A5, plus the all-checks safety net

**Files:**
- Create: `data_checks/contract.py`, `data_checks/checks/schema.py`, `data_checks/tests/test_schema.py`, `data_checks/tests/test_all_checks.py`
- Modify: `data_checks/checks/__init__.py` (import `schema`), `data_checks/__init__.py` (re-export public API, `import data_checks.checks`)

**Interfaces:**
- Consumes: Task 1 (all of it).
- Produces (`contract.py`):
  - `FIELDS: dict[str, dict[str, str]]`: per source, field to kind (`"int" | "str" | "date" | "timestamp" | "bool"`):
    - `user_signups`: user_id int, email str, signup_date date, company_size str, industry str
    - `marketing_attribution`: user_id int, channel str, campaign str, first_touch_date date
    - `conversions`: user_id int, conversion_date date, plan str, mrr int, signup_date date, days_to_convert int, used_real_time_collab bool
    - `subscription_events`: event_id int, user_id int, event_date date, event_type str, plan str, mrr int, previous_plan str, previous_mrr int
    - `feature_usage_events`: timestamp timestamp, user_id int, feature_id int, feature_name str, event_type str
    - `feature_releases`: id int, name str, release_date date, version str
  - `NULL_ALLOWED: dict[tuple[str, str], frozenset[str]]`: `("subscription_events", "previous_plan")` and `("subscription_events", "previous_mrr")` allow null on `{"subscription_started"}`; `("subscription_events", "plan")` allows null on `{"subscription_cancelled"}`. Nothing else may be null.
  - `COMPANY_SIZES = {"1-10", "11-50", "51-200", "201-1000", "1000+"}`; `INDUSTRIES = {"technology", "retail", "finance", "healthcare", "education", "manufacturing"}`; `PLANS = {"pro", "enterprise"}`; `SUBSCRIPTION_EVENT_TYPES = {"subscription_started", "plan_upgraded", "plan_downgraded", "seats_expanded", "seats_contracted", "subscription_cancelled"}`; `USAGE_EVENT_TYPES = {"view", "use", "share"}`; `RELEASE_VERSIONS = {"v1.0", "v2.0"}`
  - `CAMPAIGNS_BY_CHANNEL: dict[str, frozenset[str]]`: organic_search {seo_docs, seo_blog, seo_landing}; paid_search {google_generic, google_competitor, google_brand}; paid_social {linkedin_retargeting, linkedin_cold, meta_lookalike}; content_marketing {ebook_plg, webinar_series, newsletter}; referral {user_invite, affiliate}; outbound {sdr_sequence_q1, sdr_sequence_q2}; partner {integration_slack, marketplace_aws}
- Produces (checks; violations are one string per offending item, formatted `"<source> row <n>: <what>"` with 1-based `n`):

| ID | Sev | Title / rule | One violation per |
|---|---|---|---|
| A1 | error | Files present, non-empty, parseable: every `missing_files` entry, every `parse_errors` entry, every source file present with 0 records | missing file / bad line / empty file |
| A2 | error | Exact field set: record keys == `FIELDS[source]` keys | record with any missing or extra key (message names both) |
| A3 | error | Field kinds and formats: every non-null value matches its kind (`as_int`, `as_date`, `as_timestamp`, `isinstance(v, bool)`, non-empty `str`) | bad value |
| A4 | error | Nulls only where allowed (`NULL_ALLOWED`, keyed on the record's `event_type`) | null value |
| A5 | error | Values in their domains: company_size, industry, channel in `CAMPAIGNS_BY_CHANNEL`, campaign in its channel's set, conversions and subscription `plan` (non-null) in `PLANS`, event types, release version. Feature names are covered by C2/B3. | bad value |

- [ ] **Step 1: Write the failing tests**

`data_checks/tests/test_schema.py`: a parametrized table of `(check_id, snapshot_factory, expected_count)`, each asserting `r.status == Status.FAIL and r.violation_count == expected_count` with `r = run(check_id, factory())`:

```python
CASES = [
    ("A2", lambda: make_snapshot(user_signups=_rename(edit("user_signups", 0), 0, "signup_date", "signup_dt")), 1),
    ("A2", lambda: make_snapshot(conversions=edit("conversions", 0, extra_field=1)), 1),
    ("A3", lambda: make_snapshot(conversions=edit("conversions", 0, mrr="49")), 1),
    ("A3", lambda: make_snapshot(feature_usage_events=edit("feature_usage_events", 0, timestamp="2024-03-05T09:00:00")), 1),
    ("A3", lambda: make_snapshot(conversions=edit("conversions", 0, used_real_time_collab="true")), 1),
    ("A4", lambda: make_snapshot(user_signups=edit("user_signups", 1, industry=None)), 1),
    ("A4", lambda: make_snapshot(subscription_events=edit("subscription_events", 2, previous_plan=None)), 1),
    ("A5", lambda: make_snapshot(user_signups=edit("user_signups", 0, company_size="10-50")), 1),
    ("A5", lambda: make_snapshot(marketing_attribution=edit("marketing_attribution", 0, campaign="google_brand")), 1),
    ("A5", lambda: make_snapshot(feature_usage_events=edit("feature_usage_events", 0, event_type="click")), 1),
]
```

`_rename(rows, i, old, new)` is a local test helper. A1 is tested on files, because it reads `missing_files` and `parse_errors`:

```python
def test_a1_missing_file_bad_line_and_empty_file(tmp_path):
    raw = write_raw(tmp_path)
    (raw / "conversions.jsonl").unlink()
    (raw / "marketing_attribution.jsonl").write_text("")
    with open(raw / "user_signups.jsonl", "a", encoding="utf-8") as f: f.write("not json\n")
    r = run("A1", load_snapshot(raw))
    assert (r.status, r.violation_count) == (Status.FAIL, 3)
```

`data_checks/tests/test_all_checks.py` is the safety net that grows with each later task:

```python
EXPECTED_ON_CLEAN = {"G1": Status.SKIPPED, "G6": Status.SKIPPED}   # everything else PASS

@pytest.mark.parametrize("chk", all_checks(), ids=lambda c: c.check_id)
def test_clean_fixture(chk):
    assert chk.evaluate(make_snapshot(), FIXTURE_CONFIG).status == EXPECTED_ON_CLEAN.get(chk.check_id, Status.PASS)

@pytest.mark.parametrize("chk", all_checks(), ids=lambda c: c.check_id)
def test_no_check_crashes_on_garbage(chk):
    assert chk.evaluate(garbage_snapshot(), FIXTURE_CONFIG).status != Status.ERRORED

@pytest.mark.parametrize("chk", all_checks(), ids=lambda c: c.check_id)
def test_no_check_crashes_on_empty_snapshot(chk):
    empty = make_snapshot(metadata=None, **{s: [] for s in SOURCE_FILES})
    assert chk.evaluate(empty, FIXTURE_CONFIG).status != Status.ERRORED
```

Add `garbage_snapshot() -> Snapshot` to `fixture_data.py`. It takes the clean data, sets every field of row 0 in every source to `"?"`, appends a usage row whose fields are all `None`, and sets `metadata={"users_with_real_time_collab": "?"}`.

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `../growth-analytics/.venv/Scripts/python.exe -m pytest data_checks/tests -o addopts="" -q`
Expected: `test_schema.py` fails with `KeyError` from `get_check`.

- [ ] **Step 3: Implement `contract.py` and `checks/schema.py`, and wire up the registration imports**

- [ ] **Step 4: Run the tests and confirm they pass**

Run the same command. Expected: all pass, including the duplicate-ID test from Task 1, which now runs.

- [ ] **Step 5: Commit**

```bash
git add data_checks
git commit -m "feat(data-checks): add raw contract and schema checks A1-A5"
```

---

### Task 3: Keys and links between files (B1 to B4, C1 to C3)

**Files:**
- Create: `data_checks/checks/integrity.py`, `data_checks/tests/test_integrity.py`
- Modify: `data_checks/checks/__init__.py` (import `integrity`)

**Interfaces:**
- Consumes: Task 1 (`Snapshot`, `as_int`), `@check`.
- Produces:

| ID | Sev | Rule | One violation per |
|---|---|---|---|
| B1 | error | `user_id` unique in user_signups, marketing_attribution, conversions; `email` unique in user_signups | duplicated value per source (counted once per extra occurrence) |
| B2 | error | `subscription_events.event_id` unique | extra occurrence |
| B3 | error | releases: `(id, version)` unique, and each `id` has exactly one `name` | duplicated pair / id with >1 name |
| B4 | warn | usage: no exact duplicates of `(timestamp, user_id, feature_id, event_type)` | extra occurrence |
| C1 | error | every `user_id` in attribution, conversions, subscription_events, usage exists in signups | orphan row |
| C2 | error | usage `feature_id` exists in releases, and `feature_name` equals that id's release name | bad row |
| C3 | error | users in conversions == users with a `subscription_started` event, with exactly one start each | user breaking the rule |

- [ ] **Step 1: Write the failing tests**

Use the same `CASES` table pattern as Task 2, with `(check_id, factory, expected_count)`:

```python
CASES = [
    ("B1", lambda: make_snapshot(user_signups=append("user_signups", {**CLEAN["user_signups"][3], "email": "user5@example.com"})), 1),
    ("B1", lambda: make_snapshot(user_signups=edit("user_signups", 1, email="user1@example.com")), 1),
    ("B2", lambda: make_snapshot(subscription_events=edit("subscription_events", 4, event_id=4)), 1),
    ("B3", lambda: make_snapshot(feature_releases=append("feature_releases", dict(CLEAN["feature_releases"][1]))), 1),
    ("B3", lambda: make_snapshot(feature_releases=edit("feature_releases", 2, name="rtc")), 1),
    ("B4", lambda: make_snapshot(feature_usage_events=append("feature_usage_events", dict(CLEAN["feature_usage_events"][0]))), 1),
    ("C1", lambda: make_snapshot(feature_usage_events=edit("feature_usage_events", 0, user_id=99)), 1),
    ("C1", lambda: make_snapshot(conversions=edit("conversions", 1, user_id=99)), 1),
    ("C2", lambda: make_snapshot(feature_usage_events=edit("feature_usage_events", 0, feature_id=9)), 1),
    ("C2", lambda: make_snapshot(feature_usage_events=edit("feature_usage_events", 3, feature_name="real_time_collab")), 1),
    ("C3", lambda: make_snapshot(subscription_events=remove("subscription_events", 1)), 1),
    ("C3", lambda: make_snapshot(subscription_events=append("subscription_events", {**CLEAN["subscription_events"][0], "event_id": 6})), 1),
]
```

- [ ] **Step 2: Run the tests and confirm they fail** (`KeyError: 'B1'`)
- [ ] **Step 3: Implement `checks/integrity.py`**
- [ ] **Step 4: Run the whole suite and confirm it passes** (`test_all_checks.py` now also covers B and C)
- [ ] **Step 5: Commit:** `git add data_checks && git commit -m "feat(data-checks): add key and link checks B1-B4, C1-C3"`

---

### Task 4: Copied fields agree across files (D1 to D6)

**Files:**
- Create: `data_checks/checks/cross_file.py`, `data_checks/tests/test_cross_file.py`
- Modify: `data_checks/checks/__init__.py` (import `cross_file`)

**Interfaces:**
- Consumes: Task 1 (`as_date`, `event_date`, `as_int`), `CheckConfig.max_rtc_first_use_after_conversion_share`.
- Produces ("RTC" = the feature named `real_time_collab` in releases; if it is not in releases, D4 and D5 raise `SkipCheck`):

| ID | Sev | Rule | Metric |
|---|---|---|---|
| D1 | error | `conversions.signup_date` == the user's `user_signups.signup_date` | - |
| D2 | error | `days_to_convert` == `(conversion_date - signup_date).days`, using the conversion row's own dates | - |
| D3 | error | the user's `subscription_started` has the same `event_date`, `plan` and `mrr` as the conversion | - |
| D4 | error | `used_real_time_collab` == (the user has at least one RTC usage event) | - |
| D5 | warn | share of converters whose flag is true and whose first RTC usage date is after `conversion_date`. FAIL when the share exceeds `max_rtc_first_use_after_conversion_share`; violations then list those users. SkipCheck when there are 0 converters. | the share |
| D6 | warn | metadata agrees with usage: `users_with_real_time_collab` == the set of RTC users; `per_feature_adoption` keys == the release names, with each count == distinct users of that feature; `total_users` == number of signups; `percentage` == `round(len(list) / total_users, 4)`. SkipCheck when `metadata is None`. Malformed metadata (wrong types) counts as one violation. | - |

- [ ] **Step 1: Write the failing tests**

```python
CASES = [
    ("D1", lambda: make_snapshot(conversions=edit("conversions", 0, signup_date="2024-01-11", days_to_convert=9)), 1),
    ("D2", lambda: make_snapshot(conversions=edit("conversions", 1, days_to_convert=59)), 1),
    ("D3", lambda: make_snapshot(subscription_events=edit("subscription_events", 0, plan="enterprise")), 1),
    ("D3", lambda: make_snapshot(subscription_events=edit("subscription_events", 1, event_date="2024-03-11")), 1),
    ("D4", lambda: make_snapshot(conversions=edit("conversions", 1, used_real_time_collab=True)), 1),
    ("D6", lambda: make_snapshot(metadata={**CLEAN_METADATA, "users_with_real_time_collab": [1], "percentage": 0.25}), 1),
    ("D6", lambda: make_snapshot(metadata={**CLEAN_METADATA, "per_feature_adoption": {"real_time_collab": 2, "ai_insights": 3}}), 1),
]

def test_d5_measures_flag_set_by_post_conversion_use():
    snap = make_snapshot(feature_usage_events=edit("feature_usage_events", 1, timestamp="2024-02-01 10:00:00"))
    r = run("D5", snap)
    assert (r.status, r.metric, r.violation_count) == (Status.FAIL, 0.5, 1)
    assert run("D5", make_snapshot()).metric == 0.0

def test_d6_skipped_without_metadata():
    assert run("D6", make_snapshot(metadata=None)).status == Status.SKIPPED
```

- [ ] **Step 2: Run the tests and confirm they fail** (`KeyError: 'D1'`)
- [ ] **Step 3: Implement `checks/cross_file.py`**
- [ ] **Step 4: Run the whole suite and confirm it passes**
- [ ] **Step 5: Commit:** `git add data_checks && git commit -m "feat(data-checks): add cross-file agreement checks D1-D6"`

---

### Task 5: Dates and order (E1 to E4)

**Files:**
- Create: `data_checks/checks/temporal.py`, `data_checks/tests/test_temporal.py`
- Modify: `data_checks/checks/__init__.py` (import `temporal`)

**Interfaces:**
- Consumes: Task 1, plus `CheckConfig.window_start`, `window_end`, `as_of`, `max_touch_lag_days`.
- Produces: `def user_event_chains(snap: Snapshot) -> dict[object, list[dict]]` in `temporal.py`. It maps `user_id` to that user's subscription events sorted by `(event_date, event_id)`, and skips events whose `event_date` or `event_id` cannot be parsed. Task 6 reuses it. Checks:

| ID | Sev | Rule | One violation per |
|---|---|---|---|
| E1 | error | `first_touch_date <= signup_date`, and `(signup_date - first_touch_date).days <= max_touch_lag_days` | attribution row |
| E2 | error | `conversion_date >= user's signup_date`; usage `event_date >= user's signup_date`; usage `event_date >=` the feature's v1.0 `release_date` | offending row (a row breaking two rules counts once) |
| E3 | error | per user, with events sorted by `(event_date, event_id)`: the first is `subscription_started`; nothing follows `subscription_cancelled`; `event_id` increases along that order | user and rule |
| E4 | error | every date in the date fields (signup_date, first_touch_date, conversion_date, conversions.signup_date, event_date, the date of the usage timestamp, release_date) lies in `[window_start, min(window_end, as_of or today)]`; for each release `id`, v2.0 `release_date` > v1.0 `release_date` | bad value / bad id |

- [ ] **Step 1: Write the failing tests**

```python
CASES = [
    ("E1", lambda: make_snapshot(marketing_attribution=edit("marketing_attribution", 0, first_touch_date="2024-01-11")), 1),
    ("E1", lambda: make_snapshot(marketing_attribution=edit("marketing_attribution", 0, first_touch_date="2023-12-01")), 1),   # 40-day lag
    ("E2", lambda: make_snapshot(conversions=edit("conversions", 0, conversion_date="2024-01-05")), 1),
    ("E2", lambda: make_snapshot(feature_usage_events=edit("feature_usage_events", 1, timestamp="2024-01-12 10:00:00")), 1),  # before RTC release
    ("E2", lambda: make_snapshot(feature_usage_events=edit("feature_usage_events", 2, timestamp="2024-01-20 12:00:00")), 1),  # before user 3 signup
    ("E3", lambda: make_snapshot(subscription_events=append("subscription_events", {"event_id": 6, "user_id": 2, "event_date": "2024-07-01", "event_type": "seats_expanded", "plan": "enterprise", "mrr": 2100, "previous_plan": "enterprise", "previous_mrr": 2000})), 1),
    ("E3", lambda: make_snapshot(subscription_events=edit("subscription_events", 2, event_id=9)), 1),
    ("E4", lambda: make_snapshot(user_signups=edit("user_signups", 3, signup_date="2025-01-05")), 1),
    ("E4", lambda: make_snapshot(feature_releases=edit("feature_releases", 2, release_date="2024-01-01")), 1),
]

def test_e4_future_dates_judged_against_as_of():
    snap = make_snapshot(user_signups=edit("user_signups", 3, signup_date="2024-06-01"))
    assert run("E4", snap, replace(FIXTURE_CONFIG, as_of=date(2024, 5, 31))).violation_count >= 1
```

- [ ] **Step 2: Run the tests and confirm they fail** (`KeyError: 'E1'`)
- [ ] **Step 3: Implement `checks/temporal.py`**
- [ ] **Step 4: Run the whole suite and confirm it passes**
- [ ] **Step 5: Commit:** `git add data_checks && git commit -m "feat(data-checks): add date and order checks E1-E4"`

---

### Task 6: Subscription event sequence and MRR (F1, F2, F3, F5)

**Files:**
- Create: `data_checks/checks/subscriptions.py`, `data_checks/tests/test_subscriptions.py`
- Modify: `data_checks/checks/__init__.py` (import `subscriptions`)

**Interfaces:**
- Consumes: Task 1, `CheckConfig.plan_mrr_bands`, and `user_event_chains` from `data_checks/checks/temporal.py` (Task 5), so the per-user order is the same as E3's.
- Produces (F4 is dropped; see "Why this shape"):

| ID | Sev | Rule | One violation per |
|---|---|---|---|
| F1 | error | for each consecutive pair in a user's chain: `b.previous_mrr == a.mrr` and `b.previous_plan == a.plan` | broken pair |
| F2 | error | event type matches the change: `plan_upgraded` pro->enterprise with mrr up; `plan_downgraded` enterprise->pro with mrr down; `seats_expanded` same plan, mrr up; `seats_contracted` same plan, mrr down; `subscription_cancelled` mrr == 0 and plan is null; `subscription_started` previous_plan and previous_mrr are null | event |
| F3 | error | `mrr > 0` on every non-cancellation event | event |
| F5 | warn | the mrr of every non-cancellation event lies within `plan_mrr_bands[plan]` (inclusive) | event |

- [ ] **Step 1: Write the failing tests**

```python
CASES = [
    ("F1", lambda: make_snapshot(subscription_events=edit("subscription_events", 3, previous_mrr=97)), 1),
    ("F1", lambda: make_snapshot(subscription_events=edit("subscription_events", 3, previous_plan="enterprise")), 1),
    ("F2", lambda: make_snapshot(subscription_events=_chain_edit(2, mrr=40)), 1),              # seats_expanded with mrr down
    ("F2", lambda: make_snapshot(subscription_events=edit("subscription_events", 4, mrr=10)), 1),
    ("F2", lambda: make_snapshot(subscription_events=edit("subscription_events", 3, event_type="plan_downgraded")), 1),
    ("F3", lambda: make_snapshot(subscription_events=_chain_edit(2, mrr=0)), 1),
    ("F5", lambda: make_snapshot(subscription_events=_chain_edit(2, mrr=2500)), 1),
]

def test_subscription_checks_ignore_file_order():
    snap = make_snapshot(subscription_events=list(reversed(CLEAN["subscription_events"])))
    assert all(run(i, snap).status == Status.PASS for i in ("E3", "F1", "F2", "F3", "F5"))

def test_same_day_events_ordered_by_event_id():
    rows = edit("subscription_events", 2, event_date="2024-01-20")      # expansion on the start day, id 3 > id 1
    assert all(run(i, make_snapshot(subscription_events=rows)).status == Status.PASS for i in ("E3", "F1", "F2"))
```

`_chain_edit(index, mrr)` edits row `index`'s `mrr` and also sets the next event's `previous_mrr` to match, so that only the target check fails. For row 2, the next event is row 3.

- [ ] **Step 2: Run the tests and confirm they fail** (`KeyError: 'F1'`)
- [ ] **Step 3: Implement `checks/subscriptions.py`**
- [ ] **Step 4: Run the whole suite and confirm it passes**
- [ ] **Step 5: Commit:** `git add data_checks && git commit -m "feat(data-checks): add subscription sequence and MRR checks F1-F3, F5"`

---

### Task 7: Volume and distribution drift (G1 to G6)

**Files:**
- Create: `data_checks/checks/drift.py`, `data_checks/tests/test_drift.py`
- Modify: `data_checks/checks/__init__.py` (import `drift`)

**Interfaces:**
- Consumes: Task 1 (`row_counts`, `event_date`), the `CheckConfig` fields marked G1 to G6.
- Produces (all **warn**; every measurement check sets `metric` even when it passes; a measurement check with a zero denominator raises `SkipCheck`):

| ID | Rule | Metric |
|---|---|---|
| G1 | For each source in `baseline_row_counts`: `abs(count - base) / base <= row_count_tolerance`. SkipCheck when the baseline is None. Sources with a baseline of 0 or no baseline entry are ignored. | largest relative change |
| G2 | For each source in `dense_sources`, over the days from its own min to max event date: any run of consecutive zero-row days longer than `max_gap_days` is a violation, and any day whose count is greater than `spike_factor` x the median of non-zero daily counts is a violation | - |
| G3 | unattributed share = signups with no attribution row / signups; FAIL outside `unattributed_share_band` (inclusive) | the share |
| G4 | share of converters with zero usage events; FAIL above `max_converters_without_usage_share` | the share |
| G5 | share of cancelled users with any usage `event_date` after their cancellation `event_date`; FAIL above `max_usage_after_cancel_share` | the share |
| G6 | Conversion rate per attributed channel (converters / signups, excluding unattributed). `best_channel`'s rate is >= every other channel's rate, and every channel in `worst_channels` has a rate <= every channel not in that list. SkipCheck when `best_channel` and `worst_channels` are both None, or when a named channel has no signups. | - |

- [ ] **Step 1: Write the failing tests**

```python
def test_g1_skips_without_baseline_and_flags_large_change():
    assert run("G1", make_snapshot()).status == Status.SKIPPED
    ok = replace(FIXTURE_CONFIG, baseline_row_counts={"user_signups": 4})
    bad = replace(FIXTURE_CONFIG, baseline_row_counts={"user_signups": 10, "conversions": 0})
    assert run("G1", make_snapshot(), ok).status == Status.PASS
    r = run("G1", make_snapshot(), bad)
    assert (r.status, r.violation_count, r.metric) == (Status.FAIL, 1, 0.6)

def test_g2_gap():
    rows = edit("user_signups", 2, signup_date="2024-03-15"); rows[3]["signup_date"] = "2024-03-15"
    r = run("G2", make_snapshot(user_signups=rows))
    assert (r.status, r.violation_count) == (Status.FAIL, 1)                 # 64-day gap > 30

def test_g2_spike():
    days = ["2024-01-10", "2024-01-11"] + ["2024-01-12"] * 5
    signups = [{**CLEAN["user_signups"][0], "user_id": i + 1, "email": f"user{i+1}@example.com", "signup_date": d} for i, d in enumerate(days)]
    r = run("G2", make_snapshot(user_signups=signups), replace(FIXTURE_CONFIG, spike_factor=4.0))
    assert (r.status, r.violation_count) == (Status.FAIL, 1)

def test_g3_default_band_flags_fixture_share():
    r = run("G3", make_snapshot(), replace(FIXTURE_CONFIG, unattributed_share_band=(0.03, 0.07)))
    assert (r.status, r.metric) == (Status.FAIL, 0.25)

def test_g4_converter_without_usage():
    r = run("G4", make_snapshot(feature_usage_events=remove("feature_usage_events", 3)))
    assert (r.status, r.metric) == (Status.FAIL, 0.5)

def test_g5_usage_after_cancellation():
    late = {"timestamp": "2024-06-10 10:00:00", "user_id": 2, "feature_id": 2, "feature_name": "ai_insights", "event_type": "use"}
    r = run("G5", make_snapshot(feature_usage_events=append("feature_usage_events", late)))
    assert (r.status, r.metric) == (Status.FAIL, 1.0)

def test_g6_signal_direction():
    assert run("G6", make_snapshot()).status == Status.SKIPPED
    assert run("G6", make_snapshot(), replace(FIXTURE_CONFIG, best_channel="referral", worst_channels=("organic_search",))).status == Status.PASS
    assert run("G6", make_snapshot(), replace(FIXTURE_CONFIG, best_channel="organic_search")).status == Status.FAIL
```

- [ ] **Step 2: Run the tests and confirm they fail** (`KeyError: 'G1'`)
- [ ] **Step 3: Implement `checks/drift.py`**
- [ ] **Step 4: Run the whole suite and confirm it passes**
- [ ] **Step 5: Commit:** `git add data_checks && git commit -m "feat(data-checks): add volume and distribution drift checks G1-G6"`

---

### Task 8: Real-data test, documentation

**Files:**
- Create: `data_checks/tests/test_real_data.py`, `docs/data_checks.md`
- Modify: `README.md` (one bullet under "Documentation": `[Data consistency checks](docs/data_checks.md): raw-data checks for a daily cron job or CI gate.`)

**Interfaces:**
- Consumes: everything above, plus `DEFAULT_RAW_DIR`.

- [ ] **Step 1: Write the real-data test.** Skip it when `DEFAULT_RAW_DIR / "user_signups.jsonl"` does not exist. Use `CheckConfig(as_of=date(2026, 11, 26))`.

```python
EXPECTED_IDS = {"A1","A2","A3","A4","A5","B1","B2","B3","B4","C1","C2","C3","D1","D2","D3","D4","D5","D6",
                "E1","E2","E3","E4","F1","F2","F3","F5","G1","G2","G3","G4","G5","G6"}

def test_registry_is_exactly_the_reviewed_list():
    assert {c.check_id for c in all_checks()} == EXPECTED_IDS

def test_every_check_passes_on_the_committed_snapshot(results):
    assert {i: r.status for i, r in results.items() if r.status != Status.PASS} == {"G1": Status.SKIPPED}

def test_measured_metrics_match_the_2026_11_26_profile(results):
    assert results["D5"].metric == pytest.approx(148 / 1526, abs=1e-4)
    assert results["G3"].metric == pytest.approx(226 / 5000, abs=1e-4)
    assert results["G4"].metric == pytest.approx(133 / 1526, abs=1e-4)
    assert results["G5"].metric == pytest.approx(115 / 253, abs=1e-4)

def test_baseline_from_row_counts_round_trips(snap):
    cfg = CheckConfig(as_of=date(2026, 11, 26), baseline_row_counts=row_counts(snap))
    assert get_check("G1").evaluate(snap, cfg).status == Status.PASS
```

The module-scoped fixtures `snap` (`load_snapshot(DEFAULT_RAW_DIR)`) and `results` (`{c.check_id: c.evaluate(snap, cfg) for c in all_checks()}`) live in this test file. They are test fixtures, not a runner.

- [ ] **Step 2: Run it.** Command: `../growth-analytics/.venv/Scripts/python.exe -m pytest data_checks/tests/test_real_data.py -o addopts="" -q`. Expected: PASS. If a check fails here, stop and report it: either the check has a bug or the data has a real discrepancy. Do not loosen a threshold to make it pass.

- [ ] **Step 3: Write `docs/data_checks.md`**, with these sections:
  1. *Purpose*: one paragraph.
  2. *Check catalogue*: one table with ID, severity, rule, default threshold and the 2026-11-26 result, copied from the tables in Tasks 2 to 7, plus a note that F4 was dropped because F1 implies it.
  3. *Configuration*: the `CheckConfig` table from Task 1, and which values were calibrated on the 2024 snapshot.
  4. *Runner contract*, in prose only. A runner (a cron job or CI step, not part of this package) calls `load_snapshot(raw_dir)` and then `evaluate` on each check from `all_checks()`. A run is **failed** when any `ERROR`-severity result has status `FAIL` or `ERRORED`. `WARN` results and `SKIPPED` are reported but do not fail the run. An `ERRORED` warn check should be reported as a problem with the checks themselves. After a successful run, the runner stores `row_counts(snapshot)` and passes it as `baseline_row_counts` on the next run (G1). Set `as_of` to the run date.
  5. *Adding a check*: add a function decorated with `@check` in the right module, add one failing-case test, and confirm that `test_all_checks.py` and `test_real_data.py` still pass.

- [ ] **Step 4: Run the full repo test suite**

Run: `../growth-analytics/.venv/Scripts/python.exe -m pytest -o addopts="" -q`
Expected: all of `graph/tests`, `funnels/tests` and `data_checks/tests` pass. The graph and funnels tests need their extras; if the venv lacks `duckdb` or `igraph`, run only `data_checks/tests` and say so in the hand-off.

- [ ] **Step 5: Commit**

```bash
git add data_checks/tests/test_real_data.py docs/data_checks.md README.md
git commit -m "docs: add data consistency check catalogue and real-data test"
```
