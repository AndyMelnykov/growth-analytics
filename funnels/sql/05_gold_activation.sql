-- Activation: what share of new signups reach each product milestone in their first
-- early_window_days, overall and per segment. Milestones are reach counts, not a
-- strictly nested funnel.
create or replace view gold_activation_funnel as
with cohort as (
    select * from silver_user_journey
    where early_window_observed and conversion_window_observed
),
segmented as (
    select 'all' as dimension, 'all' as segment, * from cohort
    union all select 'acquisition_channel', acquisition_channel, * from cohort
    union all select 'company_size', company_size, * from cohort
    union all select 'industry', industry, * from cohort
),
agg as (
    select
        dimension,
        segment,
        count(*) as signups,
        count(*) filter (where first_view_day < p.early_window_days) as viewed,
        count(*) filter (where first_use_day < p.early_window_days) as activated,
        count(*) filter (where first_share_day < p.early_window_days) as shared,
        count(*) filter (where second_feature_day < p.early_window_days) as multi_feature,
        count(*) filter (where converted_in_window) as converted_in_window,
        median(first_use_day) filter (where first_use_day < p.early_window_days)
            as median_days_to_first_use
    from segmented
    cross join params p
    group by dimension, segment
)
select
    dimension,
    segment,
    signups,
    viewed,
    activated,
    shared,
    multi_feature,
    converted_in_window,
    safe_rate(activated, signups) as activation_rate,
    wilson_low(activated, signups) as activation_ci_low,
    wilson_high(activated, signups) as activation_ci_high,
    safe_rate(multi_feature, activated) as multi_feature_rate_of_activated,
    safe_rate(converted_in_window, signups) as conversion_rate,
    median_days_to_first_use,
    signups < (select min_group_size from params) as low_n
from agg
order by case dimension when 'all' then 0 else 1 end, dimension, segment;
