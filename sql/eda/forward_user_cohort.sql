-- Historical activity and future observed purchase are strictly separated.
-- Historical active users only; zero means no purchase observed in the next window.
WITH h AS (
    SELECT user_id,
           SUM(pv_count) AS pv, SUM(fav_count) AS fav,
           SUM(cart_count) AS cart, SUM(buy_count) AS buy,
           SUM(raw_record_count) AS events,
           SUM(distinct_item_behavior_count) AS event_keys,
           COUNT(*) AS active_hours,
           COUNT(DISTINCT substr(event_time, 1, 10)) AS active_days,
           SUM(raw_record_count > 90) AS flagged_hours
    FROM user_hour_stats
    WHERE event_time >= :history_start AND event_time < :anchor
    GROUP BY user_id
), f AS (
    SELECT user_id, SUM(buy_count) AS future_buy_records
    FROM user_hour_stats WHERE event_time >= :anchor AND event_time < :label_end
    GROUP BY user_id
)
SELECT h.*, COALESCE(f.future_buy_records, 0) AS future_buy_records,
       CASE WHEN COALESCE(f.future_buy_records, 0) > 0 THEN 1 ELSE 0 END AS target
FROM h LEFT JOIN f USING (user_id);
