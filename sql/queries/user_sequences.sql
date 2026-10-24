-- One state per observed hour; same-hour order is unknown.
SELECT user_id,event_time,raw_record_count,pv_count,fav_count,cart_count,buy_count,
       LAG(event_time) OVER w AS previous_observed_hour,
       ROUND((julianday(event_time)-julianday(LAG(event_time) OVER w))*24)
           AS gap_hours
FROM user_hour_stats
WHERE event_time>=:start_time AND event_time<:end_time
WINDOW w AS (PARTITION BY user_id ORDER BY event_time)
ORDER BY user_id,event_time;
