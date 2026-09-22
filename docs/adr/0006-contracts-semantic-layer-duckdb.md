# ADR 0006: Data contracts, a YAML semantic layer, and DuckDB serving

## Status

Accepted

## Context

The lakehouse now has 14 tables. Three consumers need to understand them:
humans (data dictionary), machines (lineage tooling), and an LLM analytics
chatbot (schema grounding + safe query execution). Maintaining three separate
descriptions guarantees drift. And none of these consumers should need a
running Spark cluster to ask a question.

## Decision

**One source of truth: YAML contracts** (`contracts/<layer>/<table>.yml`),
one per table, declaring description, grain, owner, columns with types and
descriptions, and `upstreams`. Everything else derives from them:

- `docs/data_dictionary.md` and `docs/lineage.md` (+ an OpenLineage-style
  `lineage.json`) are *generated* (`make docs`), never hand-edited.
- The chatbot's schema context is rendered from the same objects.
- **Contract tests keep the contracts honest**: one suite asserts every
  contract matches the Spark job's authoritative `StructType`
  (names, order, types); another asserts declared `upstreams` match the
  Airflow Dataset wiring (triggers and outlets) exactly. Drift fails CI.

**Semantic layer** (`semantic/metrics.yml`): governed metrics defined as SQL
*aggregate expressions* over exactly one table, with an allow-list of
dimensions. Ratio metrics (conversion rate, NRR) are ratios of sums, so any
regrouping stays correct — the classic "average of averages" bug is
impossible by construction. A small compiler validates metric/dimension/
filter requests and emits SQL.

**Serving via DuckDB, resolving Delta snapshots with delta-rs**: the engine
asks `deltalake` for each table's *current* file list and registers DuckDB
views over those files. Reading `*.parquet` globs naively would resurrect
tombstoned files from previous overwrites; going through the Delta log makes
DuckDB see exactly what Spark committed. Queries are guarded read-only
(single SELECT/WITH statement, keyword deny-list).

## Alternatives considered

- **dbt docs / dbt semantic layer**: the transformation layer here is
  PySpark, not dbt models; bolting dbt on only for docs would duplicate the
  schema definitions instead of deriving them.
- **A metrics store service (Cube, MetricFlow)**: heavy operational footprint
  for a portfolio-scale lakehouse; the YAML-compiler approach demonstrates
  the same concepts in ~150 lines with zero services.
- **Spark for serving**: correct but slow to start and oversized for
  interactive/chatbot queries; DuckDB answers in milliseconds on the same
  files.

## Consequences

- Adding a table = adding a contract + schema + job; CI fails until all
  three agree, and docs regenerate from the contract.
- The chatbot can only run read-only SQL against governed views, and its
  understanding of the schema is exactly what the dictionary documents.
- The engine reads a static snapshot per session; long-lived processes
  should re-instantiate `LakehouseEngine` to pick up new Delta commits.
