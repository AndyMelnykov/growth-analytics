-- Aha moment, landmark design. Cohort = users still free at the end of the early window
-- whose outcome window has fully elapsed. Predictor = behavior inside the early window.
-- Outcome = converted in the following outcome_window_days. Users who converted before
-- the landmark are excluded, so post-conversion usage can never explain conversion.

create or replace view gold_aha_features as
with members as (
    select user_id, signup_date, converted_after_landmark
    from silver_user_journey
    where landmark_member
),
features as (
    select feature_id, feature_name, min(effective_from) as released_on
    from silver_feature_states
    group by feature_id, feature_name
),
early_use as (
    select e.user_id, e.feature_id
    from silver_usage_events e, params p
    where e.event_type = 'use' and e.day_index < p.early_window_days
    group by e.user_id, e.feature_id
),
cohorted as (
    select f.feature_name,
           m.converted_after_landmark,
           case when eu.user_id is not null then 'used_feature'
                when f.released_on <= m.signup_date then 'available_not_used'
                else 'not_available' end as cohort
    from members m
    cross join features f
    left join early_use eu on eu.user_id = m.user_id and eu.feature_id = f.feature_id
),
agg as (
    select feature_name, cohort,
           count(*) as users,
           count(*) filter (where converted_after_landmark) as converted
    from cohorted
    group by feature_name, cohort
)
select feature_name, cohort, users, converted,
       safe_rate(converted, users) as conversion_rate,
       wilson_low(converted, users) as conversion_ci_low,
       wilson_high(converted, users) as conversion_ci_high,
       users < (select min_group_size from params) as low_n
from agg
order by feature_name, cohort;

-- used_feature vs available_not_used: difference in conversion rate with a 95% interval.
-- Six features are compared, so treat an interval that excludes zero as a lead, not proof.
create or replace view gold_aha_feature_lift as
select
    u.feature_name,
    u.users as used_users,
    u.converted as used_converted,
    u.conversion_rate as used_rate,
    b.users as baseline_users,
    b.converted as baseline_converted,
    b.conversion_rate as baseline_rate,
    u.conversion_rate - b.conversion_rate as rate_diff,
    diff_low(u.converted, u.users, b.converted, b.users) as rate_diff_ci_low,
    diff_high(u.converted, u.users, b.converted, b.users) as rate_diff_ci_high,
    case when b.conversion_rate > 0 then u.conversion_rate / b.conversion_rate end as lift_ratio,
    coalesce(
        diff_low(u.converted, u.users, b.converted, b.users) > 0
        or diff_high(u.converted, u.users, b.converted, b.users) < 0,
        false) as ci_excludes_zero,
    least(u.users, b.users) < (select min_group_size from params) as low_n
from gold_aha_features u
join gold_aha_features b
  on b.feature_name = u.feature_name and b.cohort = 'available_not_used'
where u.cohort = 'used_feature'
order by u.feature_name;

-- Behavior thresholds: how conversion changes with the amount of early activity.
create or replace view gold_aha_behaviors as
with members as (
    select * from silver_user_journey where landmark_member
),
leveled as (
    select 'early_features_used' as behavior,
           case when early_features_used >= 3 then '3+'
                else cast(early_features_used as varchar) end as level,
           least(early_features_used, 3) as level_order,
           converted_after_landmark
    from members
    union all
    select 'early_active_days',
           activity_bucket(early_active_days),
           activity_bucket_order(early_active_days),
           converted_after_landmark
    from members
    union all
    select 'early_shared',
           case when early_shares > 0 then 'yes' else 'no' end,
           case when early_shares > 0 then 1 else 0 end,
           converted_after_landmark
    from members
),
agg as (
    select behavior, level, level_order,
           count(*) as users,
           count(*) filter (where converted_after_landmark) as converted
    from leveled
    group by behavior, level, level_order
)
select behavior, level, level_order, users, converted,
       safe_rate(converted, users) as conversion_rate,
       wilson_low(converted, users) as conversion_ci_low,
       wilson_high(converted, users) as conversion_ci_high,
       users < (select min_group_size from params) as low_n
from agg
order by behavior, level_order;
