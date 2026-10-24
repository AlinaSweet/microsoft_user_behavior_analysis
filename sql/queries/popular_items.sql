SELECT b.item_id, i.category_id, COUNT(*) AS events,
       COUNT(DISTINCT b.user_id) AS users, SUM(b.behavior_type = 4) AS buy_records
FROM behaviors b JOIN items i USING (item_id)
WHERE b.event_time >= :start_time AND b.event_time < :end_time
GROUP BY b.item_id, i.category_id
ORDER BY buy_records DESC, events DESC, b.item_id LIMIT :limit;
