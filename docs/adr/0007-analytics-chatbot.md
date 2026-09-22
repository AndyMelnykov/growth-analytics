# ADR 0007: Analytics chatbot — Claude tool use over the semantic layer

## Status

Accepted

## Context

The gold marts answer known questions; business users ask new ones. The goal
is a chat interface where "which channel brings the best customers?" turns
into governed queries and a sourced answer — without giving a language model
free rein over the data.

## Decision

A small agent (`chatbot/agent.py`) drives Claude (`claude-opus-4-8`, adaptive
thinking) with exactly two tools:

1. **`query_metric`** — the preferred path. Requests are validated and
   compiled by the semantic layer, so aggregations are correct by definition
   and limited to the governed metric catalog.
2. **`run_sql`** — the escape hatch for detail questions (top-N, joins,
   point-in-time lookups). Statements pass the engine's read-only guard and
   run in DuckDB against the current Delta snapshot; errors return to the
   model as tool results so it can self-correct.

Grounding is generated, not hand-written: the system prompt embeds the data
contracts (tables, grain, column semantics) and the metric catalog — the same
sources that produce the data dictionary, kept honest by the contract tests.
The prompt is a stable prefix with a cache breakpoint, so multi-turn chats
reuse the cached grounding.

The agent loop is written manually (not the SDK tool runner) for one reason:
**transparency**. Every executed query — the compiled metric request or the
SQL text — is captured and rendered in the UI next to the answer, so an
analyst can audit exactly how a number was produced.

Two frontends share the agent: a Streamlit chat app (`make chatbot`) with a
data-model browser in the sidebar, and a terminal CLI (`python -m
chatbot.cli`). Without an API key, the app still serves as a data-catalog
browser and says clearly what is missing.

## Safety posture

- Read-only by construction: the DuckDB session holds views over parquet
  files; the guard rejects anything but a single SELECT/WITH.
- The model sees schema metadata and query *results* the user could already
  read; there is no write path and no credential in the container.
- Filter values in metric queries are escaped; SQL is displayed verbatim to
  the user.

## Consequences

- New tables/metrics become chatbot-visible by writing a contract/metric
  definition — no prompt editing.
- Answer quality is bounded by the metric catalog and contracts; ambiguous
  questions rely on the model stating its assumptions (instructed).
- The Claude API dependency is isolated to `chatbot/`; the rest of the
  platform runs fully offline.
