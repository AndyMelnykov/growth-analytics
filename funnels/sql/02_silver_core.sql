-- Silver core: conformed entities. Names and columns follow docs/data_dictionary.md.

-- SCD Type 2 feature version history: a new release closes the previous version.
create or replace table silver_feature_states as
with ordered as (
    select feature_id, feature_name, version, release_date as effective_from,
           lead(release_date) over (partition by feature_id order by release_date) as next_release
    from feature_releases
)
select feature_id, feature_name, version,
       true as is_enabled,
       effective_from,
       coalesce(next_release, date '9999-12-31') as effective_to,
       next_release is null as is_current,
       md5(feature_name || '|' || version) as record_hash
from ordered;

-- One row per user: firmographics + first-touch attribution + current commercial state.
-- Same-day events are ordered by event_id so the latest state is deterministic.
create or replace table silver_user_dim as
with ranked as (
    select *,
           row_number() over (partition by user_id order by event_date desc, event_id desc) as rn
    from subscription_events
),
latest as (
    select user_id, event_type, plan, mrr from ranked where rn = 1
)
select s.user_id,
       s.signup_date,
       s.company_size,
       s.industry,
       coalesce(a.channel, 'unattributed') as acquisition_channel,
       coalesce(a.campaign, 'unattributed') as acquisition_campaign,
       case when l.user_id is null then 'free'
            when l.event_type = 'subscription_cancelled' then 'churned'
            else l.plan end as current_plan,
       case when l.user_id is null or l.event_type = 'subscription_cancelled' then 0
            else l.mrr end as current_mrr
from user_signups s
left join marketing_attribution a using (user_id)
left join latest l using (user_id);

-- Usage events with their position on the user's own timeline (day 0 = signup date).
-- The inner join drops orphan events whose user never signed up.
create or replace table silver_usage_events as
select e.user_id, e.feature_id, e.feature_name, e.event_type,
       e.event_timestamp, e.event_date,
       date_diff('day', u.signup_date, e.event_date) as day_index
from feature_usage_events e
join user_signups u using (user_id);

-- Observation ends: the parameter wins, otherwise the latest date seen in the data.
create or replace table silver_extent as
select coalesce(p.usage_end, (select max(event_date) from feature_usage_events)) as usage_end,
       coalesce(p.conversion_end, (select max(conversion_date) from conversions)) as conversion_end
from params p;
