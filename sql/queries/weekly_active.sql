-- Rolling seven natural days, not the sum of daily active users.
SELECT d.event_date,
       d.event_date >= date(:start_time,'+6 days') AS full_window,
       (SELECT COUNT(DISTINCT s.user_id) FROM user_hour_stats s
        WHERE s.event_time>=MAX(:start_time,datetime(d.event_date,'-6 days'))
          AND s.event_time<datetime(d.event_date,'+1 day')) AS active_users_7d
FROM calendar_dates d ORDER BY d.event_date;
