-- Created after raw bulk import. Business keys deliberately allow repeated records.
CREATE INDEX idx_items_category ON items(category_id, item_id);
CREATE INDEX idx_user_time ON behaviors(user_id, event_time, event_id);
CREATE INDEX idx_item_behavior_user
    ON behaviors(item_id, behavior_type, user_id, event_time);
CREATE INDEX idx_behavior_time ON behaviors(behavior_type, event_time, user_id);
CREATE INDEX idx_time_user ON behaviors(event_time, user_id);
CREATE INDEX idx_event_date ON event_times(event_date, event_time);
ANALYZE;

CREATE INDEX idx_raw_comparison ON behaviors(user_id,event_time,item_id,behavior_type);

CREATE INDEX idx_pair_behavior_time ON behaviors(user_id,item_id,behavior_type,event_time);
