# Overview of `data/raw`

## Product type
The product is a freemium B2B SaaS analytics and collaboration platform, with a product-led growth (PLG) model. The data dictionary doesn't name the product, so this is inferred from the features and the funnel.
- **Funnel:** users sign up free, then convert to a paid plan, **Pro** or **Enterprise**.
- **Revenue:** revenue is tracked as MRR (USD) through the subscription lifecycle: start, upgrade or downgrade, seat expansion or contraction, cancellation.
- **Customers:** 5,000 users, in 6 industries (technology 29%, retail, finance, healthcare, education, manufacturing) and 5 company-size buckets (1-10 up to 1000+).
- **Scale:** 1,526 users (~31%) converted to paid.

## Time period

| Data | Range |
|---|---|
| Signups | 2024-01-01 to 2024-09-15 |
| First marketing touch | 2023-12-18 to 2024-09-14 (touches can precede signup) |
| Conversions | 2024-01-04 to 2024-11-02 |
| Subscription events | 2024-01-04 to 2024-12-31 |
| Feature usage events | 2024-01-15 to 2024-12-30 |
| Feature releases | 2024-01-15 to 2024-11-01 |

Overall, it covers calendar year 2024.

## Products (features)
Six features were released over 2024, and two of them got a v2.0 upgrade:

| ID | Feature | Released | v2.0 |
|---|---|---|---|
| 1 | real_time_collab | 2024-01-15 | 2024-07-01 |
| 2 | ai_insights | 2024-03-01 | 2024-10-01 |
| 3 | advanced_export | 2024-05-01 | – |
| 4 | api_access | 2024-07-01 | – |
| 5 | team_analytics | 2024-09-01 | – |
| 6 | custom_workflows | 2024-11-01 | – |

- **Usage:** there are 48,666 usage events from 4,104 users, split into view (19.6k), use (22.0k) and share (7.1k).
- **Most used:** real_time_collab accounts for 21.7k events (45%), followed by ai_insights (9.9k) and team_analytics (9.1k).
- **Least used:** custom_workflows (1.2k) and api_access (1.9k), which are also the newest.
- **Plans:**

| Plan | Conversions | MRR at conversion |
|---|---|---|
| Pro | 989 | avg ~$322 (range $29–$1,986) |
| Enterprise | 537 | avg ~$3,519 (range $199–$9,957) |

## Marketing channels
There are 7 first-touch channels and 18 campaigns in 4,774 attribution records. That is 95.5% of signups, and the other ~4.5% (226 users) have no record and are treated as `unattributed`.

| Channel | Users | Campaigns |
|---|---|---|
| organic_search | 1,192 | seo_docs, seo_blog, seo_landing |
| paid_search | 971 | google_generic, google_competitor, google_brand |
| paid_social | 708 | linkedin_retargeting, linkedin_cold, meta_lookalike |
| content_marketing | 565 | ebook_plg, webinar_series, newsletter |
| referral | 509 | user_invite, affiliate |
| outbound | 436 | sdr_sequence_q1, sdr_sequence_q2 |
| partner | 393 | integration_slack, marketplace_aws |

## Files

| File | Rows | Contents |
|---|---|---|
| `user_signups.jsonl` | 5,000 | Signup date, company size, industry (email is synthetic) |
| `marketing_attribution.jsonl` | 4,774 | First-touch channel and campaign |
| `conversions.jsonl` | 1,526 | Free-to-paid conversion with plan, MRR and days to convert (1–95 days, avg ~17) |
| `subscription_events.jsonl` | 2,651 | Billing lifecycle: 1,526 started, 596 seats expanded, 253 cancelled, 169 seats contracted, 80 upgraded, 27 downgraded |
| `feature_usage_events.jsonl` | 48,666 | Product telemetry |
| `feature_releases.json` | 8 | Release and version log |
| `_feature_users_metadata.json` | – | List of 2,416 users (48%) who used real_time_collab, plus per-feature adoption. It looks like a leftover generator artifact, and the data dictionary doesn't cover it. |

## Differences from the dictionary
- Raw `feature_usage_events` uses `timestamp`, where the dictionary says `event_timestamp`.
- Raw `feature_releases` uses `id` and `name`, where the dictionary says `feature_id` and `feature_name`.
- `event_id` is absent from the raw usage file, so it is generated at ingestion.
