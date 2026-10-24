"""Measure exact global integrity and activity-count anomaly evidence."""

import math
import sqlite3
from pathlib import Path

from user_behavior_analysis.common.utils import project_output_path
from user_behavior_analysis.dao.cleaning_repository import export_query
from user_behavior_analysis.models.cleaning_models import AnomalyMetric
from user_behavior_analysis.models.cleaning_models import DataProfile

CREATE_ACTIVITY_COUNTS = """
CREATE TABLE activity_counts (
    entity_kind TEXT NOT NULL, entity_id TEXT NOT NULL, event_count INTEGER NOT NULL
);
INSERT INTO activity_counts
SELECT 'user', user_id, COUNT(*) FROM events
WHERE category_conflict = 0 GROUP BY user_id;
INSERT INTO activity_counts
SELECT 'item', item_id, COUNT(*) FROM events
WHERE category_conflict = 0 GROUP BY item_id;
CREATE INDEX activity_distribution
ON activity_counts(entity_kind, event_count);
"""
OUTLIER_ROWS = """
SELECT entity_id, event_count,
       (event_count < ? OR event_count > ?) AS is_iqr_outlier,
       (event_count < ? OR event_count > ?) AS is_sigma_outlier,
       MIN(MAX(event_count, ?), ?) AS iqr_capped_count
FROM activity_counts
WHERE entity_kind = ? AND (
    event_count < ? OR event_count > ? OR event_count < ? OR event_count > ?
)
"""


def profile_events(connection: sqlite3.Connection) -> DataProfile:
    """Compute exact global integrity and coverage counts.

    Args:
        connection: Completely ingested cleaning database.

    Returns:
        Exact retained-entity counts, distributions, and consistency findings.
    """
    row = connection.execute("""
        SELECT COUNT(*), COUNT(DISTINCT user_id), COUNT(DISTINCT item_id),
               COUNT(DISTINCT category_id), MIN(event_time), MAX(event_time)
        FROM events WHERE category_conflict = 0
        """).fetchone()
    behavior_counts = dict(connection.execute("""
        SELECT behavior_type, COUNT(*) FROM events
        WHERE category_conflict = 0 GROUP BY behavior_type
        """))
    daily_counts = dict(connection.execute("""
        SELECT SUBSTR(event_time, 1, 10), COUNT(*) FROM events
        WHERE category_conflict = 0 GROUP BY SUBSTR(event_time, 1, 10)
        """))
    multiple_categories = connection.execute("""
        SELECT COUNT(*) FROM (
          SELECT item_id FROM events WHERE category_conflict = 0
          GROUP BY item_id HAVING COUNT(DISTINCT category_id) > 1
        )
        """).fetchone()[0]
    duplicates = connection.execute("""
        SELECT COUNT(*) FROM (
          SELECT user_id, item_id, behavior_type, event_time
          FROM events WHERE category_conflict = 0
          GROUP BY user_id, item_id, behavior_type, event_time HAVING COUNT(*) > 1
        )
        """).fetchone()[0]
    missing = connection.execute("""
        SELECT COUNT(*) FROM events WHERE category_conflict = 0 AND (
          user_id IS NULL OR user_id = '' OR item_id IS NULL OR item_id = ''
          OR category_id IS NULL OR category_id = '' OR behavior_type IS NULL
          OR event_time IS NULL
        )
        """).fetchone()[0]
    return {
        "rows": int(row[0]),
        "users": int(row[1]),
        "items": int(row[2]),
        "categories": int(row[3]),
        "minimum_event_time": row[4],
        "maximum_event_time": row[5],
        "behavior_counts": behavior_counts,
        "daily_counts": daily_counts,
        "items_with_multiple_categories": int(multiple_categories),
        "duplicate_keys_remaining": int(duplicates),
        "null_required_values": int(missing),
    }


def _quantile(
    connection: sqlite3.Connection, entity: str, count: int, probability: float
) -> float:
    """Read an exact activity-count quantile from the SQLite relation.

    Args:
        connection: Cleaning database containing the activity_counts table.
        entity: Entity kind whose counts are selected, normally user or item.
        count: Number of activity rows for that entity kind.
        probability: Quantile in [0, 1], supplied by the calling metric routine.

    Returns:
        The linearly interpolated quantile, or 0.0 when count is zero.

    Raises:
        sqlite3.DatabaseError: The activity-count query cannot be executed.

    Notes:
        Count must match the selected population. Reads only the ordered values
        needed for interpolation rather than loading every entity count.
    """
    if not count:
        return 0.0
    position = (count - 1) * probability
    lower = math.floor(position)
    values = connection.execute(
        """
        SELECT event_count FROM activity_counts WHERE entity_kind = ?
        ORDER BY event_count LIMIT 2 OFFSET ?
        """,
        (entity, lower),
    ).fetchall()
    fraction = position - lower
    return float(values[0][0] * (1 - fraction) + values[-1][0] * fraction)


def _metric(
    connection: sqlite3.Connection, entity: str, directory: Path, batch_rows: int
) -> AnomalyMetric:
    """Compute activity thresholds and export flagged entities for one kind.

    Args:
        connection: Database containing complete per-entity activity counts.
        entity: User or item entity kind to summarize.
        directory: Project-local root for per-kind diagnostic output.
        batch_rows: Positive maximum number of diagnostic rows per export batch.

    Returns:
        Quartiles, IQR and population-three-sigma thresholds, flagged counts,
        and the diagnostic output directory.

    Raises:
        ValueError: The export path escapes the project or batch size is invalid.
        sqlite3.DatabaseError: The summary or flagged-row query fails.
        OSError: Diagnostic files cannot be written.

    Notes:
        Exports an IQR-capped diagnostic count while retaining original event
        counts; an activity flag does not establish that an entity is a bot.
    """
    count, mean, mean_square = connection.execute(
        """
        SELECT COUNT(*), COALESCE(AVG(event_count), 0),
               COALESCE(AVG(1.0 * event_count * event_count), 0)
        FROM activity_counts WHERE entity_kind = ?
        """,
        (entity,),
    ).fetchone()
    q1 = _quantile(connection, entity, count, 0.25)
    q3 = _quantile(connection, entity, count, 0.75)
    iqr_lower, iqr_upper = q1 - 1.5 * (q3 - q1), q3 + 1.5 * (q3 - q1)
    deviation = math.sqrt(max(0.0, mean_square - mean**2))
    sigma_lower, sigma_upper = mean - 3 * deviation, mean + 3 * deviation
    parameters = (iqr_lower, iqr_upper, sigma_lower, sigma_upper)
    flagged = connection.execute(
        """
        SELECT COALESCE(SUM(event_count < ? OR event_count > ?), 0),
               COALESCE(SUM(event_count < ? OR event_count > ?), 0)
        FROM activity_counts WHERE entity_kind = ?
        """,
        (*parameters, entity),
    ).fetchone()
    output = project_output_path(directory / entity)
    export_query(
        connection,
        OUTLIER_ROWS,
        output,
        batch_rows,
        (*parameters, iqr_lower, iqr_upper, entity, *parameters),
    )
    return {
        "entity": entity,
        "entities": int(count),
        "q1": q1,
        "q3": q3,
        "iqr_lower": iqr_lower,
        "iqr_upper": iqr_upper,
        "mean": float(mean),
        "population_std": deviation,
        "sigma_lower": sigma_lower,
        "sigma_upper": sigma_upper,
        "iqr_flagged_entities": int(flagged[0]),
        "sigma_flagged_entities": int(flagged[1]),
        "action": (
            "Retain raw event counts; flag for review and provide a separate "
            + "IQR-capped diagnostic value. No automatic bot label or deletion."
        ),
        "output_path": str(output),
    }


def detect_activity_anomalies(
    connection: sqlite3.Connection, directory: Path, batch_rows: int
) -> list[AnomalyMetric]:
    """Flag IQR and population-three-sigma outliers in entity activity counts.

    Args:
        connection: Fully ingested cleaning relation.
        directory: Destination for flagged entity records.
        batch_rows: Maximum export batch size.

    Returns:
        Exact linearly interpolated quartiles, thresholds, and flagged counts.

    Notes:
        Materializes disk-backed user/item count tables. Valid high-activity
        events remain in the clean relation; IDs are never treated as measures.
    """
    connection.executescript(CREATE_ACTIVITY_COUNTS)
    return [
        _metric(connection, entity, directory, batch_rows)
        for entity in ("user", "item")
    ]
