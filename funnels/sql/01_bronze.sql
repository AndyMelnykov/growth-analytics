-- Bronze: typed views directly over the raw files. Nothing is copied.
-- {{RAW_DIR}} is replaced by funnels.warehouse.build().

create or replace view user_signups as
select user_id, email, signup_date, company_size, industry
from read_json(
    '{{RAW_DIR}}/user_signups.jsonl', format = 'newline_delimited',
    columns = {'user_id': 'INTEGER', 'email': 'VARCHAR', 'signup_date': 'DATE',
               'company_size': 'VARCHAR', 'industry': 'VARCHAR'});

create or replace view marketing_attribution as
select user_id, channel, campaign, first_touch_date
from read_json(
    '{{RAW_DIR}}/marketing_attribution.jsonl', format = 'newline_delimited',
    columns = {'user_id': 'INTEGER', 'channel': 'VARCHAR', 'campaign': 'VARCHAR',
               'first_touch_date': 'DATE'});

create or replace view conversions as
select user_id, conversion_date, plan, mrr, signup_date, days_to_convert,
       used_real_time_collab
from read_json(
    '{{RAW_DIR}}/conversions.jsonl', format = 'newline_delimited',
    columns = {'user_id': 'INTEGER', 'conversion_date': 'DATE', 'plan': 'VARCHAR',
               'mrr': 'INTEGER', 'signup_date': 'DATE', 'days_to_convert': 'INTEGER',
               'used_real_time_collab': 'BOOLEAN'});

create or replace view subscription_events as
select event_id, user_id, event_date, event_type, plan, mrr, previous_plan, previous_mrr
from read_json(
    '{{RAW_DIR}}/subscription_events.jsonl', format = 'newline_delimited',
    columns = {'event_id': 'INTEGER', 'user_id': 'INTEGER', 'event_date': 'DATE',
               'event_type': 'VARCHAR', 'plan': 'VARCHAR', 'mrr': 'INTEGER',
               'previous_plan': 'VARCHAR', 'previous_mrr': 'INTEGER'});

-- The raw column is called "timestamp"; the data dictionary calls it event_timestamp.
create or replace view feature_usage_events as
select user_id, feature_id, feature_name, event_type,
       "timestamp" as event_timestamp,
       cast("timestamp" as date) as event_date
from read_json(
    '{{RAW_DIR}}/feature_usage_events.jsonl', format = 'newline_delimited',
    columns = {'timestamp': 'TIMESTAMP', 'user_id': 'INTEGER', 'feature_id': 'INTEGER',
               'feature_name': 'VARCHAR', 'event_type': 'VARCHAR'});

-- The raw file is a JSON array with id / name.
create or replace view feature_releases as
select id as feature_id, name as feature_name, release_date, version
from read_json(
    '{{RAW_DIR}}/feature_releases.json', format = 'array',
    columns = {'id': 'INTEGER', 'name': 'VARCHAR', 'release_date': 'DATE',
               'version': 'VARCHAR'});
