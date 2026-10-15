SELECT COUNT(*) AS events, COUNT(DISTINCT b.user_id) AS users,
       COUNT(DISTINCT b.item_id) AS items,
       COUNT(DISTINCT i.category_id) AS categories,
       MIN(b.event_time) AS first_event_time, MAX(b.event_time) AS last_event_time
FROM behaviors b JOIN items i USING (item_id)
WHERE b.event_time >= :start_time AND b.event_time < :end_time;
