"""Compare exported event values with the canonical global relation."""

import hashlib
import sqlite3
from pathlib import Path

import pandas as pd

from user_behavior_analysis.common.event_values import canonical_event_bytes
from user_behavior_analysis.dao.cleaning_repository import CLEAN_EVENTS
from user_behavior_analysis.models.cleaning_models import ExportIntegrity


def verify_export(
    connection: sqlite3.Connection, paths: list[Path], batch_rows: int
) -> ExportIntegrity:
    """Read every exported value and compare with the canonical relation.

    Args:
        connection: Database that supplied the ordered export.
        paths: Exported files in the original deterministic part order.
        batch_rows: Maximum canonical database read batch.

    Returns:
        Full-scan row counts and fingerprints of canonical value hashes.

    Notes:
        The value fingerprint uses Pandas uint64 row hashes followed by SHA-256;
        it is an engineering equality check, not a collision-free mathematical
        proof. File SHA-256 values separately protect the actual artifacts.
    """
    expected = hashlib.sha256()
    exported = hashlib.sha256()
    expected_rows = 0
    exported_rows = 0
    cursor = connection.execute(CLEAN_EVENTS)
    columns = [entry[0] for entry in cursor.description]
    while rows := cursor.fetchmany(batch_rows):
        frame = pd.DataFrame.from_records(rows, columns=columns)
        expected.update(canonical_event_bytes(frame))
        expected_rows += len(frame)
    for path in paths:
        frame = pd.read_parquet(path)
        exported.update(canonical_event_bytes(frame))
        exported_rows += len(frame)
    expected_digest = expected.hexdigest()
    exported_digest = exported.hexdigest()
    return {
        "expected_rows": expected_rows,
        "exported_rows": exported_rows,
        "expected_value_sha256": expected_digest,
        "exported_value_sha256": exported_digest,
        "values_match": (
            expected_rows == exported_rows and expected_digest == exported_digest
        ),
        "algorithm": "Pandas 64-bit canonical row hashes then ordered SHA-256",
    }
