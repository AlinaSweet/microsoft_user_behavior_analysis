SELECT c.week_start_monday, COUNT(DISTINCT b.user_id) AS active_users,
       COUNT(*) AS events, COUNT(DISTINCT c.event_date) AS observed_days
FROM behaviors b JOIN event_times t USING (event_time)
JOIN calendar_features c USING (event_date)
WHERE b.event_time >= :start_time AND b.event_time < :end_time
GROUP BY c.week_start_monday ORDER BY c.week_start_monday;
