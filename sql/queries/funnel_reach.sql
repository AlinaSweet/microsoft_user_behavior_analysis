-- Unordered observed reach. These counts need not be monotone.
WITH pairs AS (
    SELECT DISTINCT user_id, item_id, behavior_type FROM behaviors
    WHERE event_time >= :start_time AND event_time < :end_time
)
SELECT behavior_type, COUNT(*) AS observed_user_item_pairs,
       COUNT(DISTINCT user_id) AS observed_users
FROM pairs GROUP BY behavior_type ORDER BY behavior_type;
