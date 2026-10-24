-- Descriptive purchase/high-frequency cohorts; not monetary RFM segments.
WITH users_by_flags AS (
    SELECT user_id, SUM(raw_record_count) AS records,
           SUM(buy_count)>0 AS observed_purchase,
           MAX(raw_record_count > CAST((
              SELECT metadata_value FROM dataset_metadata
              WHERE metadata_key='high_frequency_threshold'
           ) AS INTEGER)) AS has_high_frequency_hour
    FROM user_hour_stats
    WHERE event_time>=:start_time AND event_time<:end_time
    GROUP BY user_id
)
SELECT observed_purchase,has_high_frequency_hour,COUNT(*) AS users,
       SUM(records) AS raw_records
FROM users_by_flags GROUP BY observed_purchase,has_high_frequency_hour;
