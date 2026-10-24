-- Reproducible aggregates; metadata supplies the confirmed flag threshold.
CREATE TABLE user_hour_stats AS
SELECT user_id,event_time,SUM(occurrences) AS raw_record_count,
       COUNT(*) AS distinct_item_behavior_count,
       SUM(occurrences)-COUNT(*) AS extra_same_key_records,
       MAX(occurrences) AS max_key_occurrences,
       COUNT(DISTINCT item_id) AS distinct_items,
       COUNT(DISTINCT behavior_type) AS behavior_type_count,
       SUM(CASE WHEN behavior_type=1 THEN occurrences ELSE 0 END) AS pv_count,
       SUM(CASE WHEN behavior_type=2 THEN occurrences ELSE 0 END) AS fav_count,
       SUM(CASE WHEN behavior_type=3 THEN occurrences ELSE 0 END) AS cart_count,
       SUM(CASE WHEN behavior_type=4 THEN occurrences ELSE 0 END) AS buy_count
FROM key_occurrences GROUP BY user_id,event_time;
CREATE UNIQUE INDEX idx_user_hour ON user_hour_stats(user_id,event_time);
CREATE INDEX idx_user_hour_time ON user_hour_stats(event_time,user_id);
CREATE VIEW high_frequency_user_hours AS
SELECT *, 'pending_review' AS review_status FROM user_hour_stats
WHERE raw_record_count > CAST(
    (SELECT metadata_value FROM dataset_metadata
     WHERE metadata_key='high_frequency_threshold') AS INTEGER
);
