-- Earliest observed view anchors a user-item cohort. Complete seven-day follow-up.
-- Strict hours: pv -> cart -> fav -> buy, all before first_view + window_days.
WITH views AS MATERIALIZED (
    SELECT user_id, item_id, MIN(event_time) AS first_view FROM behaviors
    WHERE behavior_type = 1 AND event_time >= :start_time AND event_time < :end_time
    GROUP BY user_id, item_id
), carts AS MATERIALIZED (
    SELECT v.*, (
        SELECT MIN(b.event_time) FROM behaviors b
        WHERE b.user_id = v.user_id AND b.item_id = v.item_id AND b.behavior_type = 3
          AND b.event_time > v.first_view
          AND b.event_time < datetime(v.first_view, printf('+%d days', :window_days))
    ) AS first_cart FROM views v
), favorites AS MATERIALIZED (
    SELECT c.*, (
        SELECT MIN(b.event_time) FROM behaviors b
        WHERE b.user_id = c.user_id AND b.item_id = c.item_id AND b.behavior_type = 2
          AND b.event_time > c.first_cart
          AND b.event_time < datetime(c.first_view, printf('+%d days', :window_days))
    ) AS first_fav FROM carts c
), purchases AS MATERIALIZED (
    SELECT f.*, (
        SELECT MIN(b.event_time) FROM behaviors b
        WHERE b.user_id = f.user_id AND b.item_id = f.item_id AND b.behavior_type = 4
          AND b.event_time > f.first_fav
          AND b.event_time < datetime(f.first_view, printf('+%d days', :window_days))
    ) AS first_buy FROM favorites f
), cohort AS (
    SELECT *, first_view <= datetime(:end_time, printf('-%d days', :window_days))
        AS eligible FROM purchases
)
SELECT COUNT(*) AS observed_view_pairs,
       COALESCE(SUM(eligible), 0) AS eligible_view_pairs,
       COALESCE(SUM(NOT eligible), 0) AS right_censored_pairs,
       COALESCE(SUM(eligible AND first_cart IS NOT NULL), 0) AS cart_pairs,
       COALESCE(SUM(eligible AND first_fav IS NOT NULL), 0) AS favorite_pairs,
       COALESCE(SUM(eligible AND first_buy IS NOT NULL), 0) AS purchase_pairs
FROM cohort;
