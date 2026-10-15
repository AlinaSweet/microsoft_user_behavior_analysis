-- Behavior proxies: F = distinct purchase dates, M_count = purchase log records.
WITH stats AS (
    SELECT user_id, COUNT(*) AS events, MAX(event_time) AS last_active,
           MAX(CASE WHEN behavior_type = 4 THEN event_time END) AS last_buy,
           COUNT(DISTINCT CASE WHEN behavior_type = 4
                 THEN substr(event_time, 1, 10) END) AS purchase_days,
           SUM(behavior_type = 4) AS purchase_records
    FROM behaviors
    WHERE event_time >= :start_time AND event_time < :end_time
    GROUP BY user_id
), recency AS (
    SELECT *,
        CAST(julianday(date(:end_time, '-1 second')) - julianday(date(last_buy))
             AS INTEGER) AS purchase_recency_days,
        CAST(julianday(date(:end_time, '-1 second')) - julianday(date(last_active))
             AS INTEGER) AS inactive_days
    FROM stats
)
SELECT *, CASE
    WHEN purchase_recency_days < 7 AND purchase_days >= 3 AND purchase_records >= 5
        THEN 'high_value_proxy'
    WHEN inactive_days < 7 THEN 'potential_proxy'
    WHEN inactive_days < 14 THEN 'churn_risk_proxy'
    ELSE 'dormant_proxy' END AS segment
FROM recency ORDER BY user_id;
