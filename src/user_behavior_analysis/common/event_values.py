"""Provide canonical, dtype-independent value hashes for event round trips."""

import pandas as pd


def canonical_event_bytes(frame: pd.DataFrame) -> bytes:
    """Hash event-row values consistently across storage dtype changes.

    Args:
        frame: Canonical event fields in their declared column order.

    Returns:
        Consecutive uint64 row hashes for an outer ordered SHA-256 digest.

    Notes:
        Times are rendered to seconds without assigning a timezone. This is an
        engineering comparison; file fingerprints are recorded separately.
    """
    canonical = frame.copy()
    canonical["event_time"] = pd.to_datetime(canonical["event_time"]).dt.strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    values = pd.util.hash_pandas_object(
        canonical.astype("string[pyarrow]"), index=False, categorize=False
    ).to_numpy(dtype="uint64")
    return values.tobytes()
