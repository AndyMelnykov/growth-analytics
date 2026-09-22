# growth-analytics

This project explores how raw SaaS product-usage events can be transformed
into a graph of customer journeys, behavioral relationships, and product
metrics, then analyzed with AI to identify growth opportunities.

## Current status

The repository currently contains a synthetic raw-data snapshot and the design
documentation for the planned analytics platform. The raw data
supports the source entities described in the documentation, but the
transformation pipeline, graph model, AI chatbot, and materialized Bronze,
Silver, and Gold tables are not implemented in this repository yet.

## Repository layout

```text
data/raw/        Synthetic source files used as pipeline inputs
docs/            Data dictionary, lineage, and architecture decisions
references.md    Related project and technology references
```

### Raw data

The six files below are the source inputs represented in the lineage graph:

| File | Grain |
| --- | --- |
| `user_signups.jsonl` | One user signup |
| `feature_usage_events.jsonl` | One feature interaction |
| `feature_releases.json` | One feature release or version upgrade |
| `marketing_attribution.jsonl` | One first-touch attribution record |
| `conversions.jsonl` | One free-to-paid conversion |
| `subscription_events.jsonl` | One subscription lifecycle event |

`_feature_users_metadata.json` is an older auxiliary artifact from the
synthetic-data generation process. It is not part of the documented lineage
or table contracts and should not be treated as a pipeline source without
first documenting its schema and purpose.

The data is synthetic and intended for development and demonstration. It is
not a benchmark or a source of real-world SaaS performance assumptions.

## Documentation

- [Data dictionary](docs/data_dictionary.md): planned Bronze, Silver, and Gold
	schemas, grains, columns, and upstreams.
- [Data lineage](docs/lineage.md): planned flow from raw files to analytical
	marts. The machine-readable version is [lineage.json](docs/lineage.json).
- [Architecture decisions](docs/adr/): decisions covering the planned
	lakehouse, validation, orchestration, semantic layer, and chatbot.
- [Project references](references.md): related open-source projects and tools.

The dictionary and lineage describe the target architecture. They currently
refer to contracts, scripts, and generated outputs that have not been added to
the repository yet.

## Planned analytical model

The target design uses a medallion architecture:

- **Bronze**: raw sources landed with ingestion metadata.
- **Silver**: conformed user, feature, usage, and subscription entities.
- **Gold**: channel performance, feature-conversion impact, MRR waterfall,
	and weekly engagement marts.

The planned next implementation steps are to add the data contracts and
generation scripts, build the Spark/Delta transformations, add validation and
orchestration, and then expose governed metrics through the semantic layer
and chatbot.
