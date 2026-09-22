# ADR 0004: Synthetic data with engineered causal signals

## Status

Accepted

## Context

The pipeline needs source data. Real product analytics data cannot be
published, and uniformly random data makes every downstream analysis
meaningless — a cohort analysis over noise returns noise, which makes the
project impossible to demo and its correctness impossible to eyeball.

## Decision

`scripts/generate_synthetic_data.py` generates all raw sources with explicit,
parameterized causal structure:

- **Feature adoption drives conversion.** Each feature has a configured
  `conversion_boost`; users who adopt more features convert more often and
  faster (`days_saved`).
- **Acquisition channel drives lead quality.** Each channel has a
  `conversion_mult` (referral 1.4x … outbound 0.7x) applied to the user's
  conversion probability. ~5% of signups are deliberately unattributed to
  force downstream joins to handle missing attribution.
- **Feature adoption drives retention.** In the subscription lifecycle
  simulation, each adopted feature multiplies the monthly churn hazard by
  0.88 (floored at 0.40), so retention analyses find a real signal.
- **Growth patterns look real.** Signups follow exponential growth with
  seasonality, weekend dips, and marketing bumps after feature releases.

Everything is seeded (`--seed`, default 42) for reproducibility, and the
generator prints a validation report quantifying each engineered signal so
pipeline outputs can be checked against known ground truth.

## Consequences

- Gold-layer outputs have known expected shapes (e.g. referral should show
  the highest conversion rate), which acts as an end-to-end sanity check.
- Signal strengths are configuration, so scenarios can be tuned without
  touching generation logic.
- The data is *plausible but synthetic*: absolute values (MRR ranges,
  adoption rates) are invented and should not be quoted as benchmarks.
