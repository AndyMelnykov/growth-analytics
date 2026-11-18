-- Acquisition: which channels / campaigns bring users who activate and convert.
-- Stage counts only include users whose early and conversion windows have elapsed.
create or replace view gold_acquisition_funnel as
with cohort as (
    select j.*, (j.early_window_observed and j.conversion_window_observed) as observed
    from silver_user_journey j
),
agg as (
    select
        acquisition_channel,
        acquisition_campaign,
        count(*) as signups,
        count(*) filter (where observed) as observed_signups,
        count(*) filter (where observed and first_use_day < p.early_window_days) as activated,
        count(*) filter (where observed and converted_in_window) as converted_in_window,
        avg(days_to_convert) filter (where observed and converted_in_window) as avg_days_to_convert,
        coalesce(sum(conversion_mrr) filter (where observed and converted_in_window), 0) as new_mrr,
        count(*) filter (
            where observed and converted_in_window and conversion_plan = 'enterprise'
        ) as enterprise_conversions
    from cohort
    cross join params p
    group by grouping sets ((acquisition_channel, acquisition_campaign), (acquisition_channel), ())
)
select
    case when acquisition_channel is null then 'total'
         when acquisition_campaign is null then 'channel'
         else 'campaign' end as level,
    coalesce(acquisition_channel, '(all)') as acquisition_channel,
    coalesce(acquisition_campaign, '(all)') as acquisition_campaign,
    signups,
    observed_signups,
    activated,
    safe_rate(activated, observed_signups) as activation_rate,
    converted_in_window,
    safe_rate(converted_in_window, observed_signups) as conversion_rate,
    wilson_low(converted_in_window, observed_signups) as conversion_ci_low,
    wilson_high(converted_in_window, observed_signups) as conversion_ci_high,
    avg_days_to_convert,
    new_mrr,
    safe_rate(new_mrr, converted_in_window) as avg_new_mrr,
    safe_rate(enterprise_conversions, converted_in_window) as enterprise_share,
    observed_signups < (select min_group_size from params) as low_n
from agg
order by
    case when acquisition_channel is null then 0 when acquisition_campaign is null then 1 else 2 end,
    acquisition_channel, acquisition_campaign;

-- Same conversion measure per signup month and channel, for trend lines.
create or replace view gold_acquisition_cohorts as
with cohort as (
    select j.*, (j.early_window_observed and j.conversion_window_observed) as observed
    from silver_user_journey j
),
agg as (
    select
        signup_month,
        acquisition_channel,
        count(*) as signups,
        count(*) filter (where observed) as observed_signups,
        count(*) filter (where observed and converted_in_window) as converted_in_window
    from cohort
    group by signup_month, acquisition_channel
)
select
    signup_month,
    acquisition_channel,
    signups,
    observed_signups,
    converted_in_window,
    safe_rate(converted_in_window, observed_signups) as conversion_rate,
    wilson_low(converted_in_window, observed_signups) as conversion_ci_low,
    wilson_high(converted_in_window, observed_signups) as conversion_ci_high,
    observed_signups < (select min_group_size from params) as low_n
from agg
order by signup_month, acquisition_channel;
