-- Normalized persisted relations. Calendar attributes are derived in views.
PRAGMA foreign_keys = ON;

CREATE TABLE users (
    user_id TEXT PRIMARY KEY CHECK (length(user_id) > 0)
) STRICT, WITHOUT ROWID;

CREATE TABLE categories (
    category_id TEXT PRIMARY KEY CHECK (length(category_id) > 0)
) STRICT, WITHOUT ROWID;

CREATE TABLE items (
    item_id TEXT PRIMARY KEY CHECK (length(item_id) > 0),
    category_id TEXT NOT NULL REFERENCES categories(category_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE calendar_dates (
    event_date TEXT PRIMARY KEY
        CHECK (date(event_date) IS NOT NULL AND date(event_date) = event_date)
) STRICT, WITHOUT ROWID;

CREATE TABLE event_times (
    event_time TEXT PRIMARY KEY,
    event_date TEXT NOT NULL REFERENCES calendar_dates(event_date),
    CHECK (substr(event_time, 1, 10) = event_date),
    CHECK (strftime('%Y-%m-%d %H:%M:%S', event_time) IS NOT NULL),
    CHECK (strftime('%Y-%m-%d %H:%M:%S', event_time) = event_time),
    CHECK (substr(event_time, 15) = '00:00')
) STRICT, WITHOUT ROWID;

CREATE TABLE behavior_types (
    behavior_type INTEGER PRIMARY KEY CHECK (behavior_type BETWEEN 1 AND 4),
    behavior_name TEXT NOT NULL UNIQUE
) STRICT;

INSERT INTO behavior_types VALUES (1, 'pv'), (2, 'fav'), (3, 'cart'), (4, 'buy');

CREATE TABLE behaviors (
    event_id INTEGER PRIMARY KEY CHECK (event_id > 0),
    user_id TEXT NOT NULL REFERENCES users(user_id),
    item_id TEXT NOT NULL REFERENCES items(item_id),
    behavior_type INTEGER NOT NULL REFERENCES behavior_types(behavior_type),
    event_time TEXT NOT NULL REFERENCES event_times(event_time)
) STRICT;

CREATE TABLE dataset_metadata (
    metadata_key TEXT PRIMARY KEY,
    metadata_value TEXT NOT NULL
) STRICT, WITHOUT ROWID;

CREATE VIEW canonical_events AS
SELECT b.event_id, b.user_id, b.item_id, i.category_id,
       b.behavior_type, b.event_time
FROM behaviors AS b JOIN items AS i USING (item_id);

CREATE VIEW calendar_features AS
SELECT event_date,
       CAST(strftime('%w', event_date) AS INTEGER) AS weekday_sunday_zero,
       CASE WHEN strftime('%w', event_date) IN ('0', '6') THEN 1 ELSE 0 END
           AS is_weekend,
       date(event_date, 'weekday 0', '-6 days') AS week_start_monday
FROM calendar_dates;


-- Comparison only: every source row stays in behaviors.
CREATE VIEW key_occurrences AS
SELECT user_id, event_time, item_id, behavior_type,
       MIN(event_id) AS first_source_record, COUNT(*) AS occurrences
FROM behaviors GROUP BY user_id, event_time, item_id, behavior_type;
