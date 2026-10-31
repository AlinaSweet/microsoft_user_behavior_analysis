"""Orchestrate complete-record features with resumable per-cutoff completion records."""

import json
import shutil
from datetime import datetime
from typing import Any

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.common.utils import sha256_file
from user_behavior_analysis.common.utils import write_json
from user_behavior_analysis.dao.feature_repository import export_relation
from user_behavior_analysis.dao.feature_repository import feature_connection
from user_behavior_analysis.models.feature_models import FeatureDefinition
from user_behavior_analysis.models.feature_models import FeatureSettings
from user_behavior_analysis.service.feature_assembly import assemble_entity_views
from user_behavior_analysis.service.feature_assembly import export_model_inputs
from user_behavior_analysis.service.feature_assembly import time_feature_table
from user_behavior_analysis.service.feature_business import create_history_hours
from user_behavior_analysis.service.feature_business import item_competition_features
from user_behavior_analysis.service.feature_business import lifecycle_features
from user_behavior_analysis.service.feature_business import preference_features
from user_behavior_analysis.service.feature_funnels import funnel_features
from user_behavior_analysis.service.feature_latent_transform import (
    cooccurrence_features,
)
from user_behavior_analysis.service.feature_latent_transform import (
    encode_sequence_tensors,
)
from user_behavior_analysis.service.feature_latent_transform import transform_latent
from user_behavior_analysis.service.feature_quality import export_user_targets
from user_behavior_analysis.service.feature_quality import profile_features
from user_behavior_analysis.service.feature_quality import temporal_count_controls
from user_behavior_analysis.service.feature_registry import ENTITY_KEYS
from user_behavior_analysis.service.feature_sequences import export_sequence_inputs
from user_behavior_analysis.service.feature_sequences import sequence_statistics
from user_behavior_analysis.service.feature_snapshots import create_history_view
from user_behavior_analysis.service.feature_snapshots import export_snapshot_entities

PROVISIONAL_RELATIONS = (
    "history_hours",
    "user_lifecycle_source",
    "user_lifecycle",
    "category_preferences",
    "user_preference",
    "user_category_preference",
    "pair_preference",
    "pair_coverages",
    "item_business",
    "category_business",
    "funnel_views",
    "funnel_cart",
    "funnel_fav",
    "funnel_buy",
    "funnel_pairs",
    "user_funnel",
    "item_funnel",
    "category_funnel",
    "user_category_funnel",
    "pair_funnel",
    "sequence_hours",
    "user_sequence",
    "sequence_runs",
    "user_sequence_runs",
    "sequence_units",
    "sequence_inputs",
    "user_svd",
    "item_svd",
    "pair_latent",
    "item_graph",
    "graph_items",
    "matched_neighbors",
    "pair_cooccurrence",
    "time_features",
    "user_targets",
)


def _reset_provisional(connection: Any, settings: FeatureSettings, anchor: str) -> None:
    """Reset only this run's unpublished derived relations and preserve prior exports.

    Args:
        connection: One feature snapshot cache.
        settings: Project output paths.
        anchor: Snapshot whose unfinished computation is being resumed.
    """
    for entity in ENTITY_KEYS:
        connection.execute(
            "CREATE OR REPLACE VIEW "
            + entity
            + "_features AS SELECT * FROM "
            + entity
            + "_stats"
        )
    for name in PROVISIONAL_RELATIONS:
        match = connection.execute(
            "SELECT table_type FROM information_schema.tables WHERE table_name=$name",
            {"name": name},
        ).fetchone()
        if match:
            connection.execute(
                ("DROP VIEW " if match[0] == "VIEW" else "DROP TABLE ") + name
            )
    directory = settings.output_dir / "snapshots" / anchor
    files = list(directory.rglob("*.parquet")) + list(directory.glob("*.npz"))
    if files:
        backup = (
            PROJECT_ROOT
            / ".cache/feature_system/provisional"
            / anchor
            / datetime.now().strftime("%Y%m%d_%H%M%S")
        )
        backup.mkdir(parents=True, exist_ok=True)
        for path in files:
            destination = backup / path.relative_to(directory)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(destination))


def _augment_features(
    connection: Any,
    settings: FeatureSettings,
    anchor: str,
    definitions: list[FeatureDefinition],
) -> dict[str, Any]:
    """Build reusable feature families before the output packing phase.

    Args:
        connection: Snapshot-local analytical cache.
        settings: Frozen feature parameters and artifact directories.
        anchor: Historical cutoff date.
        definitions: Already produced statistical field definitions.

    Returns:
        Complete definitions, sequence metadata and data quality controls.
    """
    _reset_provisional(connection, settings, anchor)
    history = create_history_view(connection, settings, anchor)
    parameters = history["parameters"]
    create_history_hours(connection)
    definitions += lifecycle_features(connection, parameters)
    definitions += preference_features(connection, parameters)
    definitions += item_competition_features(connection)
    definitions += funnel_features(connection, parameters)
    definitions += sequence_statistics(
        connection, parameters, settings.options["transition_max_gap_hours"]
    )
    sequence_evidence, sequence_defs = export_sequence_inputs(
        connection, settings, anchor, parameters
    )
    definitions += sequence_defs
    latent_defs, latent_coverage = transform_latent(connection, settings)
    definitions += latent_defs
    definitions += cooccurrence_features(connection, settings)
    definitions += time_feature_table(connection, parameters["anchor"])
    names = [row["name"] for row in definitions]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate feature definitions")
    assemble_entity_views(connection, definitions)
    return {
        "definitions": definitions,
        "sequences": sequence_evidence,
        "latent_coverage": latent_coverage,
        "controls": temporal_count_controls(connection, parameters),
        "quality": profile_features(connection, definitions, anchor),
    }


def _preserve_packing(settings: FeatureSettings, anchor: str) -> None:
    """Preserve unfinished output files before resuming their packing.

    Args:
        settings: Project-confined cache and output paths.
        anchor: Snapshot to resume without refitting feature families.
    """
    directory = settings.output_dir / "snapshots" / anchor
    backup = (
        PROJECT_ROOT
        / ".cache/feature_system/packing"
        / anchor
        / datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    for path in directory.rglob("*"):
        if not path.is_file() or path.name == "user_sequences.parquet":
            continue
        if path.suffix not in (".parquet", ".npz"):
            continue
        destination = backup / path.relative_to(directory)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(destination))


def _pack_snapshot(
    connection: Any,
    settings: FeatureSettings,
    anchor: str,
    augmented: dict[str, Any],
) -> dict[str, Any]:
    """Export completed feature relations and independent future user labels.

    Args:
        connection: Completed snapshot cache.
        settings: Project output directories and export bounds.
        anchor: Historical feature cutoff.
        augmented: Produced fields and quality evidence.

    Returns:
        Exported entities, tensors, candidate inputs and separate labels.
    """
    history = create_history_view(connection, settings, anchor)
    directory = settings.output_dir / "snapshots" / anchor
    connection.execute("SET threads = 1")
    entities = export_snapshot_entities(connection, settings, anchor)
    entities["time"] = export_relation(
        connection,
        "SELECT * FROM time_features",
        directory / "time_features.parquet",
    )
    user_ids = connection.execute(
        "SELECT user_id FROM user_stats ORDER BY user_id"
    ).df()["user_id"]
    tensors = encode_sequence_tensors(settings, anchor, user_ids)
    wide = export_model_inputs(connection, settings, anchor, augmented["definitions"])
    targets = export_user_targets(connection, settings, anchor, history["parameters"])
    return {
        "history": {
            key: value for key, value in history.items() if key != "parameters"
        },
        "entities": entities,
        "tensors": tensors,
        "model_inputs": wide,
        "user_targets": targets,
    }


def build_feature_snapshot(settings: FeatureSettings, anchor: str) -> dict[str, Any]:
    """Build all feature families and preserve completion evidence for one cutoff.

    Args:
        settings: Feature parameters and frozen model directories.
        anchor: ISO midnight snapshot date.

    Returns:
        Complete definitions, coverage, label maturity and file fingerprints.

    Raises:
        ValueError: A configuration, fingerprint or data control is inconsistent.
    """
    directory = settings.output_dir / "snapshots" / anchor
    complete = directory / "completion.json"
    if complete.exists():
        saved: dict[str, Any] = json.loads(complete.read_text(encoding="utf-8"))
        if saved["configuration"] != settings.options:
            raise ValueError("Completed parameters changed; use a new output version")
        for row in saved["files"]:
            if sha256_file(PROJECT_ROOT / row["path"]) != row["sha256"]:
                raise ValueError("Completed snapshot file changed")
        return saved
    state = json.loads(
        (directory / "statistics_state.json").read_text(encoding="utf-8")
    )
    with feature_connection(settings, directory / "features.duckdb") as connection:
        checkpoint = directory / "augmentation.json"
        if checkpoint.exists():
            augmented = json.loads(checkpoint.read_text(encoding="utf-8"))
            _preserve_packing(settings, anchor)
        else:
            augmented = _augment_features(
                connection, settings, anchor, state["definitions"]
            )
            write_json(checkpoint, augmented)
        packed = _pack_snapshot(connection, settings, anchor, augmented)
    for row in augmented["definitions"]:
        row["status"] = "produced"
        schema = (
            augmented["sequences"]["schema"]
            if row["table"] == "sequence"
            else packed["entities"][row["table"]]["schema"]
        )
        row["storage_dtype"] = schema[row["name"]]
    report = {
        "status": "completed",
        "anchor": anchor,
        "configuration": settings.options,
        **augmented,
        **packed,
        "files": [
            {
                "path": str(path.relative_to(PROJECT_ROOT)),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in sorted(directory.rglob("*"))
            if path.suffix in (".parquet", ".npz")
        ],
        "scalar_feature_count": len(augmented["quality"]),
        "sequence_logical_fields": sum(
            row["table"] == "sequence" for row in augmented["definitions"]
        ),
    }
    write_json(complete, report)
    write_json(settings.report_dir / ("snapshot_" + anchor + ".json"), report)
    return report
