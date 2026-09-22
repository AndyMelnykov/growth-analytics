# ADR 0002: Per-table job modules with validation gates

## Status

Accepted

## Context

A single "run everything" script is easy to start with and painful to
operate: partial failures force full re-runs, tests can't target one
transformation, and orchestration can't schedule tables independently.

## Decision

Every table is its own Python module with a fixed internal anatomy:

```
spark/jobs/<layer>/<table>/
├── schema.py           # the authoritative StructType (input + output)
├── extract.py | transformation.py | aggregation.py   # the logic
├── validate.py         # input/output quality gates (CLI: --mode input|output)
└── main.py             # spark-submit / python -m entry point
```

- **Schemas are first-class artifacts.** Each job declares its output
  `StructType`; validation gates and the contract tests compare against it,
  and the data dictionary derives from it via the YAML contracts.
- **Validation is part of the job, not the orchestrator.** The shared
  framework (`spark/jobs/data_quality/validators.py`) checks existence,
  schema (names + types), and row counts. Airflow simply invokes
  `validate.py --mode input` before and `--mode output` after each `process`
  task: `assert_input_quality >> process >> assert_output_quality`.
- **Layer orchestrators** (`spark/jobs/<layer>/main.py`) exist for local
  `make pipeline` runs; production scheduling is per-table via Airflow.

The test tree mirrors this structure one-to-one (`tests/spark/jobs/...`), so
finding the tests for any job is mechanical.

## Consequences

- A schema change fails loudly in three places (validation gate, unit tests,
  contract tests) before it can corrupt downstream tables.
- Per-table modules make DAG-of-tables orchestration natural (see ADR 0003)
  and keep diffs local to the table being changed.
- Some boilerplate per table (4 small files); accepted as the cost of
  uniformity — every table looks the same, so nothing needs explaining twice.
