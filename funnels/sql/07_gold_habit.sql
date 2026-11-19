-- Habit moment: how much early activity predicts still using the product weeks later.
-- Caveat (documented in docs/funnel_metrics.md): activity persists, so a strong curve
-- shows where retention jumps, not that the early usage caused it.
create or replace view gold_habit_curve as
with base as (
    select j.*, (j.late_active_days >= p.retained_min_active_days) as retained
    from silver_user_journey j
    cross join params p
    where j.early_window_observed and j.retention_window_observed
),
cohorts as (
    select 'all_users' as cohort, * from base
    union all
    select 'free_at_landmark', * from base where free_at_landmark
),
agg as (
    select cohort,
           activity_bucket(early_active_days) as early_active_days_bucket,
           activity_bucket_order(early_active_days) as bucket_order,
           count(*) as users,
           count(*) filter (where retained) as retained_users
    from cohorts
    group by cohort, early_active_days_bucket, bucket_order
)
select cohort, early_active_days_bucket, bucket_order, users, retained_users,
       safe_rate(retained_users, users) as retained_rate,
       wilson_low(retained_users, users) as retained_ci_low,
       wilson_high(retained_users, users) as retained_ci_high,
       users < (select min_group_size from params) as low_n
from agg
order by cohort, bucket_order;

-- The habit moment candidate: the smallest early-activity bucket whose retention interval
-- lower bound reaches habit_target_retention. Using the lower bound keeps tiny buckets
-- from qualifying by luck.
create or replace view gold_habit_threshold as
select c.cohort,
       p.habit_target_retention as target_retention,
       arg_min(c.early_active_days_bucket, c.bucket_order)
           filter (where c.retained_ci_low >= p.habit_target_retention) as threshold_bucket
from gold_habit_curve c
cross join params p
group by c.cohort, p.habit_target_retention
order by c.cohort;

-- Weekly usage retention by signup month. A cell only exists once week n has fully
-- elapsed for that user, so recent cohorts end earlier instead of showing a false drop.
create or replace view gold_usage_retention as
with weeks as (
    select cast(unnest(range(0, 13)) as integer) as week_n  -- weeks 0..12; INTEGER so date + 7n works
),
active as (
    select distinct user_id, day_index // 7 as week_n
    from silver_usage_events
    where day_index >= 0
),
grid as (
    select j.signup_month, j.user_id, w.week_n
    from silver_user_journey j
    cross join weeks w
    cross join silver_extent x
    where j.signup_date + 7 * (w.week_n + 1) <= x.usage_end
),
agg as (
    select g.signup_month, g.week_n,
           count(*) as cohort_users,
           count(a.user_id) as active_users
    from grid g
    left join active a on a.user_id = g.user_id and a.week_n = g.week_n
    group by g.signup_month, g.week_n
)
select signup_month, week_n, cohort_users, active_users,
       safe_rate(active_users, cohort_users) as retention_rate,
       wilson_low(active_users, cohort_users) as retention_ci_low,
       wilson_high(active_users, cohort_users) as retention_ci_high
from agg
order by signup_month, week_n;
