SELECT behavior_type, COUNT(*) AS events,
       1.0 * COUNT(*) / SUM(COUNT(*)) OVER () AS event_share,
       COUNT(DISTINCT user_id) AS users
FROM behaviors
WHERE event_time >= :start_time AND event_time < :end_time
GROUP BY behavior_type ORDER BY behavior_type;
