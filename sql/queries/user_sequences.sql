-- event_id is only a deterministic tie-breaker, never verified within-hour order.
SELECT event_id, user_id, item_id, behavior_type, event_time,
       ROW_NUMBER() OVER w AS technical_sequence_position,
       COUNT(*) OVER (PARTITION BY user_id, event_time) AS same_hour_events,
       LEAD(behavior_type) OVER w AS next_behavior_type,
       LEAD(event_time) OVER w AS next_event_time,
       CAST(ROUND((julianday(LEAD(event_time) OVER w) - julianday(event_time))
            * 86400) AS INTEGER) AS next_gap_seconds
FROM behaviors
WHERE event_time >= :start_time AND event_time < :end_time
WINDOW w AS (PARTITION BY user_id ORDER BY event_time, event_id)
ORDER BY user_id, event_time, event_id;
