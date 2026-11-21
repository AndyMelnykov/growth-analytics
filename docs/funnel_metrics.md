# Funnel metrics

How the acquisition, activation, aha-moment and habit-moment analytics are
defined, and how to read them. Implementation: the `funnels/` package
([ADR 0009](adr/0009-right-sized-funnel-analytics-on-duckdb.md)). Output
snapshot for the committed data: [funnel_report.txt](funnel_report.txt).

## Run it

```bash
python -m pip install -e ".[funnels]"
python -m funnels                              # print every Gold view
python -m funnels --view gold_habit_curve      # one view
python -m funnels --db data/warehouse.duckdb   # also keep a queryable file
python -m pytest funnels/tests -o addopts=""   # tests
```

All windows and thresholds are fields of `funnels.config.Params`.

## Definitions

Day index = days since the user's signup date (day 0 = signup date).

| Term | Definition (defaults) |
|---|---|
| Early window | day index 0..13 (`early_window_days = 14`) |
| Activated | at least one `use` event in the early window |
| Multi-feature | `use` events on at least 2 distinct features in the early window |
| Converted in window | free-to-paid conversion with `days_to_convert < 30` (`outcome_window_days`) |
| Observed | the relevant window has fully elapsed by the data's observation end (latest event date / latest conversion date, or `Params.usage_end` / `conversion_end`) |
| Landmark | the end of the early window. The aha cohort is users **still free at the landmark** whose next 30 days are observed |
| Converted after landmark | `14 <= days_to_convert < 44` |
| Retained | at least 2 distinct active days in day index 28..55 |
| Habit moment | smallest early-active-days bucket (not `low_n`) whose retention 95% interval **lower bound** is at least 0.80 |

## Views

| View | Grain | Question |
|---|---|---|
| `gold_acquisition_funnel` | channel x campaign, channel, total | Which channels and campaigns bring users who activate and convert, how fast, at what MRR? |
| `gold_acquisition_cohorts` | signup month x channel | Is channel quality stable over time? |
| `gold_activation_funnel` | segment (all, channel, company size, industry) | What share reach view / use / share / multi-feature in 14 days? How long to first use? |
| `gold_aha_features` | feature x cohort | After 14 days, how do users who used a feature convert vs those who could have but did not vs those who could not? |
| `gold_aha_feature_lift` | feature | Difference in later conversion, with a 95% interval |
| `gold_aha_behaviors` | behavior x level | Does conversion change with the number of features used, active days, or sharing in the first 14 days? |
| `gold_habit_curve` | cohort x early-active-days bucket | How does early activity relate to still using the product in weeks 5-8? |
| `gold_habit_threshold` | cohort | Smallest bucket that clears the target |
| `gold_usage_retention` | signup month x week | Weekly usage retention triangle |

Silver tables: `silver_user_dim` and `silver_feature_states` (as in the
[data dictionary](data_dictionary.md)), `silver_usage_events` (adds
`day_index`, drops orphan events) and `silver_user_journey` (one row per user,
every Gold view reads from it).

## How to read the numbers

- **Windows are honest.** Users whose window has not elapsed are excluded from
  that metric's denominator. They still count in `signups`.
- **Every rate has a 95% Wilson interval** (differences use a Wald interval) and
  a `low_n` flag for groups under 30 users. Do not rank rows whose intervals overlap.
- **Aha uses a landmark, not "used before converting".** Converters have far more
  usage on or after their conversion date (15,861 events) than before it (3,011),
  so comparing "used the feature before converting" against non-users is biased.
- **Habit curve is descriptive.** People who are active early tend to stay active.
  The `free_at_landmark` cohort removes users who had already paid, but neither
  cohort shows that early usage *causes* retention.
- **Five features are compared in `gold_aha_feature_lift`** (`custom_workflows` is
  released too late to have a baseline cohort). An interval that excludes zero is
  a lead to test with an experiment, not a finding. The only one in this snapshot
  is `team_analytics`, and it is negative: it was released on 2024-09-01, so its
  "available" users are only late signups, which makes the comparison confounded.
- **There is no clean aha threshold in this snapshot.** Conversion after the
  landmark is 15%-22% at every well-populated `gold_aha_behaviors` level with no
  monotonic trend. Habit, by contrast, is a clear signal.
- **Activation steps are reach counts, not a strict funnel.** A user can share
  without a recorded view.
- **Synthetic data.** Signals were engineered (ADR 0004). Absolute values are not
  benchmarks.

## Differences from the data dictionary

- Bronze objects are views over `data/raw`, with `timestamp` exposed as
  `event_timestamp` plus `event_date`, and feature `id`/`name` as
  `feature_id`/`feature_name`. There is no `ingestion_timestamp` or generated
  `event_id`.
- `silver_feature_usage_facts` and the Gold marts `gold_channel_performance`,
  `gold_feature_conversion_impact`, `gold_mrr_waterfall` and
  `gold_weekly_engagement` are not built here. The acquisition, aha and habit
  views replace the first two with window-aware, landmark-based versions.
