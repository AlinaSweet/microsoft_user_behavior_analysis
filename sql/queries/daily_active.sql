SELECT t.event_date, COUNT(DISTINCT b.user_id) AS active_users,
       COUNT(*) AS events, SUM(b.behavior_type = 4) AS buy_records
FROM behaviors b JOIN event_times t USING (event_time)
WHERE b.event_time >= :start_time AND b.event_time < :end_time
GROUP BY t.event_date ORDER BY t.event_date;
