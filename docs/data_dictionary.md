# Data Dictionary

> Generated from the YAML data contracts in `contracts/` by
> `scripts/generate_data_dictionary.py`. Do not edit by hand —
> edit the contract and regenerate (`make docs`).

## Bronze layer

Raw sources landed as-is in Delta, plus an `ingestion_timestamp`.

### `conversions`

Raw conversion records ingested from conversions.jsonl. A conversion is the moment a free user becomes a paying customer; the ongoing subscription lifecycle after this moment lives in subscription_events.

- **Grain**: One row per free-to-paid conversion
- **Path**: `data/bronze/conversions`
- **Owner**: data-engineering
- **Source**: data/raw/conversions.jsonl (JSONL)

| Column | Type | Description |
|---|---|---|
| `user_id` | integer | User who converted |
| `conversion_date` | string | Conversion date, YYYY-MM-DD |
| `plan` | string | Plan purchased at conversion: pro or enterprise |
| `mrr` | integer | Monthly recurring revenue (USD) at conversion |
| `signup_date` | string | Denormalized signup date for convenience |
| `days_to_convert` | integer | Days between signup and conversion |
| `used_real_time_collab` | boolean | Legacy flag from the source system (superseded by usage facts) |
| `ingestion_timestamp` | timestamp | When the row was loaded into bronze |

### `feature_releases`

Raw product feature release log ingested from feature_releases.json. Contains initial releases and later version upgrades of the same feature, which feed the SCD Type 2 feature_states dimension.

- **Grain**: One row per feature release or version upgrade
- **Path**: `data/bronze/feature_releases`
- **Owner**: data-engineering
- **Source**: data/raw/feature_releases.json (JSON array)

| Column | Type | Description |
|---|---|---|
| `feature_id` | integer | Stable feature identifier (shared across version upgrades) |
| `feature_name` | string | Machine name of the feature (e.g. real_time_collab) |
| `release_date` | string | Release date of this version, YYYY-MM-DD |
| `version` | string | Version label (v1.0, v2.0, ...) |
| `ingestion_timestamp` | timestamp | When the row was loaded into bronze |

### `feature_usage_events`

Raw product telemetry ingested from feature_usage_events.jsonl, partitioned by event_date. Each row is a single user interaction (view/use/share) with a feature.

- **Grain**: One row per feature interaction event
- **Path**: `data/bronze/feature_usage_events`
- **Owner**: data-engineering
- **Source**: data/raw/feature_usage_events.jsonl (JSONL)
- **Partitioned by**: event_date

| Column | Type | Description |
|---|---|---|
| `event_id` | long | Surrogate event identifier generated at ingestion |
| `user_id` | integer | User who performed the interaction |
| `feature_id` | integer | Feature interacted with |
| `feature_name` | string | Denormalized feature machine name |
| `event_type` | string | Interaction type: view, use, or share |
| `event_timestamp` | timestamp | When the interaction happened |
| `event_date` | date | Calendar date of the interaction (partition column) |
| `ingestion_timestamp` | timestamp | When the row was loaded into bronze |

### `marketing_attribution`

First-touch marketing attribution ingested from marketing_attribution.jsonl. Roughly 5% of signups have no record (direct traffic, lost UTM parameters); downstream joins default those users to 'unattributed'.

- **Grain**: One row per attributed signup (first touch)
- **Path**: `data/bronze/marketing_attribution`
- **Owner**: data-engineering
- **Source**: data/raw/marketing_attribution.jsonl (JSONL)

| Column | Type | Description |
|---|---|---|
| `user_id` | integer | Attributed user |
| `channel` | string | Acquisition channel: organic_search, paid_search, paid_social, content_marketing, referral, partner, outbound |
| `campaign` | string | Campaign within the channel (e.g. google_brand, webinar_series) |
| `first_touch_date` | string | Date of the first tracked touch, YYYY-MM-DD (on or before signup) |
| `ingestion_timestamp` | timestamp | When the row was loaded into bronze |

### `subscription_events`

Append-only subscription lifecycle log ingested from subscription_events.jsonl — the shape billing systems (Stripe, Chargebee) emit. Every plan or seat change carries the MRR before and after, which makes revenue movement analysis a simple delta.

- **Grain**: One row per subscription lifecycle event
- **Path**: `data/bronze/subscription_events`
- **Owner**: data-engineering
- **Source**: data/raw/subscription_events.jsonl (JSONL)

| Column | Type | Description |
|---|---|---|
| `event_id` | integer | Unique event identifier (monotonic per generation run) |
| `user_id` | integer | Customer the event belongs to |
| `event_date` | string | Event date, YYYY-MM-DD |
| `event_type` | string | subscription_started, plan_upgraded, plan_downgraded, seats_expanded, seats_contracted, or subscription_cancelled |
| `plan` | string | Plan after the event (null for cancellations) |
| `mrr` | integer | MRR (USD) after the event; 0 for cancellations |
| `previous_plan` | string | Plan before the event (null for subscription_started) |
| `previous_mrr` | integer | MRR (USD) before the event (null for subscription_started) |
| `ingestion_timestamp` | timestamp | When the row was loaded into bronze |

### `user_signups`

Raw user registrations ingested from user_signups.jsonl, partitioned by signup_date. Firmographic attributes (company size, industry) come from the signup form.

- **Grain**: One row per user signup
- **Path**: `data/bronze/user_signups`
- **Owner**: data-engineering
- **Source**: data/raw/user_signups.jsonl (JSONL)
- **Partitioned by**: signup_date

| Column | Type | Description |
|---|---|---|
| `user_id` | integer | Unique user identifier |
| `email` | string | Signup email (synthetic; excluded from silver for privacy) |
| `signup_date` | string | Signup date, YYYY-MM-DD (partition column) |
| `company_size` | string | Company size bucket: 1-10, 11-50, 51-200, 201-1000, 1000+ |
| `industry` | string | Industry: technology, finance, healthcare, retail, education, manufacturing |
| `ingestion_timestamp` | timestamp | When the row was loaded into bronze |

## Silver layer

Cleaned, conformed, analysis-ready entities.

### `silver_feature_states`

Slowly Changing Dimension (Type 2) tracking feature version history. Version upgrades close the previous record (effective_to) and open a new current one. Point-in-time state is answered with WHERE date >= effective_from AND date < effective_to.

- **Grain**: One row per feature per version validity interval (SCD Type 2)
- **Path**: `data/silver/silver_feature_states`
- **Owner**: data-engineering
- **Upstreams**: `feature_releases`

| Column | Type | Description |
|---|---|---|
| `feature_id` | integer | Stable feature identifier |
| `feature_name` | string | Feature machine name |
| `version` | string | Version label in force during the interval |
| `is_enabled` | boolean | Whether the feature was enabled (always true in current data) |
| `effective_from` | date | Start of the validity interval (release date) |
| `effective_to` | date | End of the validity interval; 9999-12-31 for current records |
| `is_current` | boolean | True for the record currently in force |
| `record_hash` | string | md5(feature_name|version) used for change detection |

### `silver_feature_usage_facts`

Per-user, per-feature usage summary aggregated from raw telemetry. first_used_date is the key column for adoption-before-conversion analysis.

- **Grain**: One row per user per feature ever used
- **Path**: `data/silver/silver_feature_usage_facts`
- **Owner**: data-engineering
- **Upstreams**: `feature_usage_events`

| Column | Type | Description |
|---|---|---|
| `user_id` | integer | User |
| `feature_id` | integer | Feature |
| `first_used_date` | date | First interaction date (adoption moment) |
| `last_used_date` | date | Most recent interaction date |
| `total_usage_count` | long | Total interaction events |
| `avg_daily_usage` | double | total_usage_count / days between first and last use (inclusive) |
| `as_of_date` | date | Snapshot date the fact table was built |

### `silver_subscription_periods`

Periodized subscription lifecycle - each row is a (plan, mrr) state valid from period_start until the next event at period_end. Cancellations close the previous period without opening a new one, so churned customers have no active period. Point-in-time revenue questions use WHERE date >= period_start AND date < period_end.

- **Grain**: One row per subscription state validity interval
- **Path**: `data/silver/silver_subscription_periods`
- **Owner**: data-engineering
- **Upstreams**: `subscription_events`

| Column | Type | Description |
|---|---|---|
| `user_id` | integer | Customer |
| `plan` | string | Plan in force during the period (pro or enterprise) |
| `mrr` | integer | MRR (USD) in force during the period |
| `period_start` | date | Date the state took effect |
| `period_end` | date | Date the next event superseded it; 9999-12-31 if none |
| `is_active` | boolean | True for the customer's current, non-cancelled state |
| `change_type` | string | Subscription event type that opened the period |

### `silver_user_dim`

The user dimension. Combines signup firmographics, first-touch marketing attribution, and the current commercial state derived from the latest subscription lifecycle event. This is the main join target for user-level analysis.

- **Grain**: One row per user
- **Path**: `data/silver/silver_user_dim`
- **Owner**: data-engineering
- **Upstreams**: `user_signups`, `marketing_attribution`, `subscription_events`

| Column | Type | Description |
|---|---|---|
| `user_id` | integer | Unique user identifier |
| `signup_date` | date | Signup date |
| `company_size` | string | Company size bucket: 1-10, 11-50, 51-200, 201-1000, 1000+ |
| `industry` | string | Industry vertical |
| `acquisition_channel` | string | First-touch channel; 'unattributed' when no tracking record exists |
| `acquisition_campaign` | string | First-touch campaign; 'unattributed' when no tracking record exists |
| `current_plan` | string | free (never converted), pro, enterprise, or churned (subscription cancelled) |
| `current_mrr` | integer | MRR (USD) of the active subscription; 0 for free/churned users |

## Gold layer

Business-level marts consumed by analysts, dashboards, and the chatbot.

### `gold_channel_performance`

Acquisition funnel quality per channel per signup cohort - which channels bring users who actually convert, how fast, and at what revenue. Includes the 'unattributed' bucket so totals reconcile with overall signups.

- **Grain**: One row per signup month per acquisition channel
- **Path**: `data/gold/gold_channel_performance`
- **Owner**: analytics-engineering
- **Upstreams**: `silver_user_dim`, `conversions`

| Column | Type | Description |
|---|---|---|
| `signup_month` | date | First day of the signup month (cohort) |
| `acquisition_channel` | string | First-touch channel, or 'unattributed' |
| `signups` | long | Users who signed up in the cohort |
| `conversions` | long | Of those, users who later converted to paid |
| `conversion_rate` | double | conversions / signups |
| `avg_days_to_convert` | double | Average signup-to-conversion days (converted users only) |
| `total_new_mrr` | long | Total MRR (USD) acquired from this cohort at conversion |
| `avg_new_mrr` | double | Average MRR per conversion |

### `gold_feature_conversion_impact`

Cohort analysis answering "does feature adoption drive conversion?". For every feature, users are split into used_feature / available_not_used / not_available cohorts and conversion outcomes are compared across them. The ratio of conversion rates between the first two cohorts is the feature's conversion lift.

- **Grain**: One row per feature per cohort
- **Path**: `data/gold/gold_feature_conversion_impact`
- **Owner**: analytics-engineering
- **Upstreams**: `silver_user_dim`, `silver_feature_states`, `silver_feature_usage_facts`, `conversions`

| Column | Type | Description |
|---|---|---|
| `feature_name` | string | Feature machine name |
| `cohort` | string | used_feature, available_not_used, or not_available |
| `total_users` | long | Users in the cohort |
| `converted_users` | long | Users in the cohort who converted to paid |
| `conversion_rate` | double | converted_users / total_users |
| `avg_days_to_convert` | double | Average signup-to-conversion days (converted users only) |
| `avg_mrr` | double | Average MRR at conversion (converted users only) |

### `gold_mrr_waterfall`

Monthly MRR waterfall decomposing revenue growth into new business, expansion, contraction, and churn, with net revenue retention. Internally consistent by construction - ending_mrr = starting_mrr + net_new_mrr every month.

- **Grain**: One row per calendar month
- **Path**: `data/gold/gold_mrr_waterfall`
- **Owner**: analytics-engineering
- **Upstreams**: `subscription_events`

| Column | Type | Description |
|---|---|---|
| `month` | date | First day of the month |
| `starting_mrr` | long | MRR at the start of the month (previous month's ending) |
| `new_business_mrr` | long | MRR from subscriptions started this month |
| `expansion_mrr` | long | MRR gained from upgrades and seat expansion |
| `contraction_mrr` | long | MRR lost to downgrades and seat contraction |
| `churned_mrr` | long | MRR lost to cancellations |
| `net_new_mrr` | long | new_business + expansion - contraction - churned |
| `ending_mrr` | long | MRR at the end of the month |
| `new_customers` | long | Subscriptions started this month |
| `churned_customers` | long | Subscriptions cancelled this month |
| `net_revenue_retention` | double | (starting + expansion - contraction - churned) / starting. Excludes new business (standard SaaS NRR). NULL for the first month. |

### `gold_weekly_engagement`

Weekly engagement metrics per feature - weekly active users, event volume, intensity, and each feature's reach as a share of the overall weekly active base (pct_of_wau).

- **Grain**: One row per ISO week per feature
- **Path**: `data/gold/gold_weekly_engagement`
- **Owner**: analytics-engineering
- **Upstreams**: `feature_usage_events`

| Column | Type | Description |
|---|---|---|
| `week_start` | date | Monday of the ISO week |
| `feature_name` | string | Feature machine name |
| `active_users` | long | Distinct users of this feature during the week |
| `total_events` | long | Usage events for this feature during the week |
| `events_per_active_user` | double | total_events / active_users (engagement intensity) |
| `weekly_active_users` | long | Distinct users across ALL features that week (overall WAU) |
| `pct_of_wau` | double | active_users / weekly_active_users (feature reach) |
