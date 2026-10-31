-- Read-only source attachment is named raw. These are EDA summaries, not model inputs.
CREATE TABLE pair_metrics AS
SELECT user_id, item_id, COUNT(*) AS events,
       SUM(behavior_type = 1) AS pv,
       SUM(behavior_type = 2) AS fav,
       SUM(behavior_type = 3) AS cart,
       SUM(behavior_type = 4) AS buy,
       COUNT(DISTINCT CASE WHEN behavior_type = 1 THEN event_time END) AS pv_keys,
       COUNT(DISTINCT CASE WHEN behavior_type = 2 THEN event_time END) AS fav_keys,
       COUNT(DISTINCT CASE WHEN behavior_type = 3 THEN event_time END) AS cart_keys,
       COUNT(DISTINCT CASE WHEN behavior_type = 4 THEN event_time END) AS buy_keys
FROM raw.behaviors INDEXED BY idx_pair_behavior_time
GROUP BY user_id, item_id;

CREATE INDEX idx_eda_pair_user ON pair_metrics(user_id);
CREATE INDEX idx_eda_pair_item ON pair_metrics(item_id);

CREATE TABLE user_days AS
SELECT user_id, substr(event_time, 1, 10) AS event_date,
       COUNT(*) AS active_hour_buckets,
       SUM(raw_record_count) AS events,
       SUM(distinct_item_behavior_count) AS event_keys,
       SUM(pv_count) AS pv, SUM(fav_count) AS fav,
       SUM(cart_count) AS cart, SUM(buy_count) AS buy,
       SUM(raw_record_count > 90) AS flagged_hours
FROM raw.user_hour_stats
GROUP BY user_id, substr(event_time, 1, 10);
CREATE INDEX idx_eda_day_user ON user_days(user_id);

CREATE TABLE hourly AS
SELECT event_time, COUNT(*) AS active_users,
       SUM(raw_record_count) AS events,
       SUM(distinct_item_behavior_count) AS event_keys,
       SUM(pv_count) AS pv, SUM(fav_count) AS fav,
       SUM(cart_count) AS cart, SUM(buy_count) AS buy,
       SUM(pv_count > 0) AS pv_users, SUM(buy_count > 0) AS buy_users,
       SUM(raw_record_count > 90) AS flagged_hours,
       SUM(CASE WHEN raw_record_count > 90 THEN raw_record_count ELSE 0 END)
           AS flagged_records
FROM raw.user_hour_stats GROUP BY event_time;

CREATE TABLE user_profiles AS
WITH p AS (
    SELECT p.user_id, SUM(events) AS events,
           SUM(pv) AS pv, SUM(fav) AS fav, SUM(cart) AS cart, SUM(buy) AS buy,
           SUM(pv_keys) AS pv_keys, SUM(fav_keys) AS fav_keys,
           SUM(cart_keys) AS cart_keys, SUM(buy_keys) AS buy_keys,
           COUNT(*) AS interacted_items,
           COUNT(DISTINCT i.category_id) AS interacted_categories,
           SUM(buy > 0) AS purchased_items
    FROM pair_metrics p JOIN raw.items i USING (item_id) GROUP BY p.user_id
), d AS (
    SELECT user_id, COUNT(*) AS active_days,
           SUM(active_hour_buckets) AS active_hour_buckets,
           SUM(buy > 0) AS purchase_days,
           SUM(flagged_hours) AS flagged_hours
    FROM user_days GROUP BY user_id
)
SELECT p.*, d.active_days, d.active_hour_buckets, d.purchase_days, d.flagged_hours
FROM p JOIN d USING (user_id);

CREATE TABLE item_profiles AS
SELECT item_id, COUNT(*) AS users,
       SUM(events) AS events, SUM(pv) AS pv, SUM(buy) AS buy,
       SUM(pv > 0) AS view_pairs, SUM(buy > 0) AS purchase_pairs,
       SUM(pv > 0 AND buy > 0) AS converted_pairs
FROM pair_metrics GROUP BY item_id;
CREATE INDEX idx_eda_item_id ON item_profiles(item_id);

CREATE TABLE category_profiles AS
SELECT i.category_id, COUNT(DISTINCT p.user_id) AS users,
       COUNT(DISTINCT p.item_id) AS items,
       SUM(p.events) AS events, SUM(p.pv) AS pv, SUM(p.buy) AS buy,
       SUM(p.pv > 0) AS view_pairs, SUM(p.buy > 0) AS purchase_pairs,
       SUM(p.pv > 0 AND p.buy > 0) AS converted_pairs
FROM pair_metrics p JOIN raw.items i USING (item_id) GROUP BY i.category_id;

CREATE TABLE user_categories AS
SELECT p.user_id, i.category_id, SUM(p.events) AS events,
       SUM(p.pv_keys + p.fav_keys + p.cart_keys + p.buy_keys) AS event_keys
FROM pair_metrics p JOIN raw.items i USING (item_id)
GROUP BY p.user_id, i.category_id;
