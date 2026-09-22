# ADR 0001: Medallion architecture on Delta Lake + Spark

## Status

Accepted

## Context

The project models a SaaS product-led-growth analytics platform: several raw
event/entity feeds must become trustworthy business marts. The pipeline needs
clear contracts between stages, safe re-runs, and historical analysis
(point-in-time questions), while staying runnable on a laptop.

## Decision

A three-layer **medallion architecture** on **Delta Lake**, transformed by
**PySpark**:

- **Bronze** — raw sources landed as-is (plus `ingestion_timestamp`), append
  mode. Bronze is the replayable system of record; nothing is cleaned here,
  so bugs downstream never require re-extracting sources.
- **Silver** — cleaned, conformed entities: dimensions (SCD Type 2 feature
  states, the user dimension), periodized subscription intervals, and usage
  facts. Silver reads only bronze.
- **Gold** — business marts shaped for consumption (cohort impact, MRR
  waterfall, channel performance, weekly engagement). Overwrite mode makes
  every gold rebuild idempotent.

Delta Lake (not plain parquet) because the pipeline exercises real lakehouse
mechanics: ACID writes, `MERGE` for SCD Type 2 upserts, schema enforcement/
evolution, and a transaction log that lets other engines (delta-rs/DuckDB in
the serving layer) resolve the exact current snapshot.

Spark (not pandas/duckdb for transformation) because the code is written the
way it would ship at data-warehouse scale — window functions, MERGE, and
partitioned writes carry over unchanged to a real cluster; only the paths and
session config would change.

## Consequences

- Layer discipline gives every table a single upstream contract, which the
  lineage graph and Airflow Datasets mirror one-to-one.
- Append-mode bronze plus deterministic silver/gold rebuilds make the
  pipeline safely re-runnable end-to-end (`make pipeline`).
- Spark's JVM startup dominates local runtimes (~minutes for the full
  pipeline); acceptable for a portfolio project, and the serving layer
  (DuckDB) keeps interactive queries fast.
