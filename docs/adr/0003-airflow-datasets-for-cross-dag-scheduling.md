# ADR 0003: One DAG per table, wired with Airflow Datasets

## Status

Accepted

## Context

With per-table jobs (ADR 0002), orchestration could be one monolithic DAG
with task-level dependencies, or many small DAGs. A monolith couples every
table's schedule and failure domain: one slow bronze feed blocks unrelated
marts, and adding a table means editing a shared file every time.

## Decision

**One DAG per table** (14 DAGs), each with the same three-task chain
(`assert_input_quality >> process >> assert_output_quality`), connected by
**Airflow Datasets** instead of explicit cross-DAG dependencies:

- Bronze DAGs run `@daily` and declare their output Dataset
  (`delta://bronze/<table>`) as the `process` task's outlet.
- Silver and gold DAGs have no time schedule at all — their `schedule` is the
  *list of upstream Datasets*. Airflow triggers them exactly when all their
  inputs have been refreshed.

The dependency graph therefore lives in data-space ("this DAG consumes
`delta://bronze/subscription_events`"), not in orchestration-space
("trigger DAG X after DAG Y"). A governance test asserts this wiring matches
the `upstreams` declared in the data contracts, so the lineage documentation,
the DAGs, and the contracts cannot drift apart.

## Consequences

- Independent failure domains and natural backfills: re-running one bronze
  DAG cascades through exactly the marts that depend on it.
- Adding a table touches only its own DAG file plus the shared `config.py`
  constants — no central graph edit.
- Dataset triggers fire on *producer success*, not on data content; the
  in-DAG validation gates (ADR 0002) are what protect consumers from bad
  data.
- 14 small files instead of one big one is more surface area to skim, but
  every file is the same 60-line pattern.
