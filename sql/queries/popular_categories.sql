SELECT i.category_id, COUNT(*) AS events,
       COUNT(DISTINCT b.user_id) AS users,
       COUNT(DISTINCT b.item_id) AS items, SUM(b.behavior_type = 4) AS buy_records
FROM behaviors b JOIN items i USING (item_id)
WHERE b.event_time >= :start_time AND b.event_time < :end_time
GROUP BY i.category_id
ORDER BY buy_records DESC, events DESC, i.category_id LIMIT :limit;
