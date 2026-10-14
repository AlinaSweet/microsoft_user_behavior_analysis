"""Provide project paths and bounded resource constants."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SMALL_FILE_LIMIT_BYTES = 10 * 1024 * 1024
HASH_CHUNK_BYTES = 1024 * 1024
SAMPLE_TIMEOUT_SECONDS = 120
MEMORY_SAMPLE_INTERVAL_SECONDS = 0.1
MEMORY_THRESHOLD_KEYS = ("target", "spill", "pause", "terminate")
