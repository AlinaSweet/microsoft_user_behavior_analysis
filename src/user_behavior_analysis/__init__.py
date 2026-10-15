"""Initialize the project cache environment before importing native data engines."""

from user_behavior_analysis.common.sqlite_runtime import (
    configure_sqlite_temporary_storage as _configure_sqlite_temporary_storage,
)

_configure_sqlite_temporary_storage()
