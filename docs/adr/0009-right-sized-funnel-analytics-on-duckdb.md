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
