-- Repeat purchase means another observed purchase DATE within seven days.
-- It does not identify orders, quantities, actual repurchase, or monetary revenue.
WITH firsts AS (
    SELECT user_id, item_id, MIN(event_time) AS first_buy
    FROM behaviors
    WHERE behavior_type = 4 AND event_time >= :start_time AND event_time < :end_time
    GROUP BY user_id, item_id
), pairs AS (
    SELECT f.*,
        first_buy <= datetime(:end_time, printf('-%d days', :window_days)) AS eligible,
        EXISTS (
            SELECT 1 FROM behaviors b
            WHERE b.user_id = f.user_id AND b.item_id = f.item_id
              AND b.behavior_type = 4 AND date(b.event_time) > date(f.first_buy)
              AND b.event_time < datetime(f.first_buy, printf('+%d days', :window_days))
        ) AS repeated_within_window
    FROM firsts f
)
SELECT item_id, COUNT(*) AS observed_buyers, SUM(eligible) AS eligible_buyers,
       SUM(eligible AND repeated_within_window) AS repeat_buyers,
       1.0 * SUM(eligible AND repeated_within_window) / NULLIF(SUM(eligible), 0)
           AS repeat_user_rate_7d
FROM pairs GROUP BY item_id ORDER BY item_id;
