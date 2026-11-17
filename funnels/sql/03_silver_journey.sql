-- One row per user: attribution, outcome, first-milestone days, early/late behavior,
-- and which measurement windows have fully elapsed by the observation end.
create or replace table silver_user_journey as
with
p as (select * from params),
x as (select * from silver_extent),
milestones as (
    select user_id,
           min(day_index) filter (where event_type = 'view')  as first_view_day,
           min(day_index) filter (where event_type = 'use')   as first_use_day,
           min(day_index) filter (where event_type = 'share') as first_share_day
    from silver_usage_events
    group by user_id
),
first_use_by_feature as (
    select user_id, feature_id, min(day_index) as day_index
    from silver_usage_events
    where event_type = 'use'
    group by user_id, feature_id
),
second_feature as (
    select user_id, day_index as second_feature_day
    from (
        select *, row_number() over (partition by user_id order by day_index, feature_id) as rn
        from first_use_by_feature
    )
    where rn = 2
),
early as (
    select e.user_id,
           count(*) as early_events,
           count(distinct e.day_index) as early_active_days,
           count(distinct e.feature_id) filter (where e.event_type = 'use') as early_features_used,
           count(*) filter (where e.event_type = 'share') as early_shares
    from silver_usage_events e, p
    where e.day_index < p.early_window_days
    group by e.user_id
),
late as (
    select e.user_id, count(distinct e.day_index) as late_active_days
    from silver_usage_events e, p
    where e.day_index >= p.retained_from_day and e.day_index < p.retained_to_day
    group by e.user_id
),
base as (
    select d.user_id, d.signup_date,
           date_trunc('month', d.signup_date)::date as signup_month,
           d.company_size, d.industry, d.acquisition_channel, d.acquisition_campaign,
           c.user_id is not null as converted,
           date_diff('day', d.signup_date, c.conversion_date) as days_to_convert,
           c.plan as conversion_plan,
           c.mrr as conversion_mrr,
           m.first_view_day, m.first_use_day, m.first_share_day,
           sf.second_feature_day,
           coalesce(e.early_events, 0) as early_events,
           coalesce(e.early_active_days, 0) as early_active_days,
           coalesce(e.early_features_used, 0) as early_features_used,
           coalesce(e.early_shares, 0) as early_shares,
           coalesce(l.late_active_days, 0) as late_active_days
    from silver_user_dim d
    left join conversions c on c.user_id = d.user_id
    left join milestones m on m.user_id = d.user_id
    left join second_feature sf on sf.user_id = d.user_id
    left join early e on e.user_id = d.user_id
    left join late l on l.user_id = d.user_id
)
select b.*,
       b.signup_date + p.early_window_days <= x.usage_end as early_window_observed,
       b.signup_date + p.outcome_window_days <= x.conversion_end as conversion_window_observed,
       b.signup_date + p.retained_to_day <= x.usage_end as retention_window_observed,
       coalesce(b.days_to_convert < p.outcome_window_days, false) as converted_in_window,
       (not b.converted or b.days_to_convert >= p.early_window_days) as free_at_landmark,
       ((not b.converted or b.days_to_convert >= p.early_window_days)
           and b.signup_date + p.early_window_days + p.outcome_window_days <= x.conversion_end
       ) as landmark_member,
       coalesce(b.days_to_convert >= p.early_window_days
                and b.days_to_convert < p.early_window_days + p.outcome_window_days,
                false) as converted_after_landmark
from base b
cross join p
cross join x;
