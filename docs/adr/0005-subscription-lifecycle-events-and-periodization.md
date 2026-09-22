# ADR 0005: Subscription lifecycle as events, periodized in silver

## Status

Accepted

## Context

The original model stopped at the conversion moment: one `conversions` record
per user, with a static plan and MRR. That cannot answer the questions a SaaS
business actually asks — MRR growth decomposition, net revenue retention,
churn, expansion vs contraction — because revenue *changes after* conversion.

Two common modeling options:

1. **Snapshot table** (monthly subscription state per user): simple to query
   but loses intra-month changes and bloats linearly with months x customers.
2. **Event log** (one row per lifecycle change): compact, lossless, and the
   natural shape in which billing systems (Stripe, Chargebee) emit this data.

## Decision

Source of truth is an **event log**: `subscription_events` with
`subscription_started`, `plan_upgraded`, `plan_downgraded`, `seats_expanded`,
`seats_contracted`, `subscription_cancelled`, each carrying `mrr` and
`previous_mrr`.

The silver layer **periodizes** the log into `silver_subscription_periods`
(one validity interval per state, `period_start`/`period_end`/`is_active`)
using a window `lead()` — the same query pattern as the SCD Type 2
`feature_states` table, so all point-in-time questions in the warehouse are
answered with one idiom: `WHERE date BETWEEN start AND end`.

Cancellations close the previous period without opening a new one, so a
churned customer simply has no active period.

The gold layer derives the **MRR waterfall** directly from the events: each
event maps to a movement (new / expansion / contraction / churn) via the
`mrr - previous_mrr` delta, and starting/ending MRR are a running sum of net
movements — which makes the waterfall internally consistent by construction
(`ending = starting + net_new`, every month).

## Consequences

- NRR, churn, and expansion analyses become simple aggregations.
- `silver_user_dim.current_plan` gains a `churned` state (derived from each
  user's latest event) instead of pretending cancelled customers are still
  paying.
- The event log is append-only, which matches the bronze layer's append
  ingestion mode; replays are idempotent at the silver layer because
  periodization is a full deterministic rebuild.
- Reactivation (win-back) events are deliberately out of scope for now; the
  periodization already supports them if added later.
