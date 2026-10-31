-- Alternative paths overlap; they share a complete first-view seven-day cohort.
WITH views AS MATERIALIZED (
 SELECT user_id, item_id, MIN(event_time) AS first_view
 FROM behaviors WHERE behavior_type = 1
  AND event_time >= :start_time AND event_time < :end_time GROUP BY user_id,item_id
), eligible AS MATERIALIZED (
 SELECT * FROM views
 WHERE first_view <= datetime(:end_time, printf('-%d days', :window_days))
), steps AS MATERIALIZED (
 SELECT v.*,
 (SELECT MIN(b.event_time) FROM behaviors b
  WHERE b.user_id=v.user_id AND b.item_id=v.item_id AND b.behavior_type=3
  AND b.event_time>v.first_view
  AND b.event_time<datetime(v.first_view,printf('+%d days',:window_days))) AS cart,
 (SELECT MIN(b.event_time) FROM behaviors b
  WHERE b.user_id=v.user_id AND b.item_id=v.item_id AND b.behavior_type=2
  AND b.event_time>v.first_view
  AND b.event_time<datetime(v.first_view,printf('+%d days',:window_days))) AS fav
 FROM eligible v
)
SELECT COUNT(*) AS eligible_view_pairs,
 SUM(EXISTS(SELECT 1 FROM behaviors b
  WHERE b.user_id=v.user_id AND b.item_id=v.item_id AND b.behavior_type=4
  AND b.event_time>v.first_view
  AND b.event_time<datetime(v.first_view,printf('+%d days',:window_days))
 )) AS pv_buy_cross_hour,
 SUM(EXISTS(SELECT 1 FROM behaviors b
  WHERE b.user_id=v.user_id AND b.item_id=v.item_id AND b.behavior_type=4
  AND b.event_time>=v.first_view
  AND b.event_time<datetime(v.first_view,printf('+%d days',:window_days))
 )) AS pv_buy_same_hour_compatible,
 SUM(EXISTS(SELECT 1 FROM behaviors b
  WHERE b.user_id=v.user_id AND b.item_id=v.item_id AND b.behavior_type=4
  AND b.event_time>v.cart
  AND b.event_time<datetime(v.first_view,printf('+%d days',:window_days))
 )) AS pv_cart_buy_cross_hour,
 SUM(EXISTS(SELECT 1 FROM behaviors b
  WHERE b.user_id=v.user_id AND b.item_id=v.item_id AND b.behavior_type=4
  AND b.event_time>v.fav
  AND b.event_time<datetime(v.first_view,printf('+%d days',:window_days))
 )) AS pv_fav_buy_cross_hour FROM steps v;
