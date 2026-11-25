"""Validate and align cutoff-specific Parquet sequence inputs with audited samples."""

import re
from collections import Counter
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any
from typing import TypedDict
from typing import cast

import numpy as np
import pandas as pd
import pyarrow.parquet as pq  # type: ignore[import-untyped]
import torch

from user_behavior_analysis.common.utils import project_output_path
from user_behavior_analysis.dao.traditional_repository import read_temporal_split
from user_behavior_analysis.dao.wide_repository import read_json_object
from user_behavior_analysis.dao.wide_repository import verify_registered_file
from user_behavior_analysis.models.sequence_models import AdvancedSettings
from user_behavior_analysis.models.sequence_models import Budget
from user_behavior_analysis.models.sequence_models import History
from user_behavior_analysis.models.sequence_models import SequenceSplit
from user_behavior_analysis.models.sequence_models import StagePaths
from user_behavior_analysis.models.sequence_models import Variant
from user_behavior_analysis.models.sequence_models import Vocabulary
from user_behavior_analysis.models.traditional_models import LabeledMatrix
from user_behavior_analysis.models.traditional_models import TemporalPlan
from user_behavior_analysis.service.wide_contracts import require_contract

_BOUNDS = {
    "seed": (0, 2**32 - 6),
    "threads": (1, 16),
    "sequence_length": (1, 50),
    "vocabulary_limit": (2, 50000),
    "batch_rows": (8, 4096),
    "training_negative_ratio": (1, 1000),
    "monitor_negative_ratio": (1, 1000),
    "max_epochs": (2, 50),
    "patience": (1, 10),
    "stack_epochs": (1, 30),
    "shap_cases": (8, 512),
    "shap_background": (2, 24),
    "bootstrap_repeats": (10, 1000),
}


@dataclass(frozen=True)
class SequenceSource:
    """Represent source arrays joined to the candidate order of one cutoff."""

    matrix: LabeledMatrix
    keys: pd.DataFrame
    categories: pd.Series
    histories: pd.DataFrame
    audit: dict[str, Any]


class _HistoryRow(TypedDict):
    """Typed Arrow list columns materialized at a checked Parquet boundary."""

    sequence_length: int
    seq_item_ids: np.ndarray
    seq_category_ids: np.ndarray
    seq_gap_hours: np.ndarray
    seq_behavior_masks: np.ndarray
    seq_raw_behavior_counts: np.ndarray
    source_max_event_time: pd.Timestamp


def _bounded_int(value: object, lower: int, upper: int) -> bool:
    """Check a configuration integer without accepting a JSON boolean.

    Args:
        value: Value from the configuration document.
        lower: Inclusive minimum.
        upper: Inclusive maximum.

    Returns:
        Whether the value is a permitted integer.
    """
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and lower <= value <= upper
    )


def _variant(raw: dict[str, Any]) -> Variant:
    """Check model dimensions and attention compatibility.

    Args:
        raw: One JSON architecture entry.

    Returns:
        Validated architecture arguments.
    """
    require_contract(
        len(raw) == 6
        and re.fullmatch("[a-z][a-z0-9_]*", raw["name"]) is not None
        and raw["family"] in {"gru", "lstm", "din"}
        and _bounded_int(raw["embedding"], 2, 32)
        and _bounded_int(raw["hidden"], 4, 64)
        and 0 <= raw["dropout"] < 1
        and _bounded_int(raw["heads"], 0, 8)
        and (
            raw["heads"] == 0
            or (
                raw["family"] == "din"
                and 1 < raw["heads"] <= 8
                and raw["hidden"] % raw["heads"] == 0
            )
        ),
        "Invalid sequence architecture",
    )
    return cast(Variant, raw)


def load_advanced_settings(path: Path) -> AdvancedSettings:
    """Validate the two stages' source and versioned destinations.

    Args:
        path: Project-contained experiment configuration.

    Returns:
        Checked settings and predeclared experiment variants.
    """
    raw = read_json_object(path)
    source = {
        k: project_output_path(raw[k])
        for k in ("sampling_catalog", "feature_catalog", "traditional_catalog")
    }
    outputs = {
        stage: StagePaths(
            **{
                key: project_output_path(raw[stage][key])
                for key in ("data_root", "report_dir", "catalog")
            }
        )
        for stage in ("deep", "ensemble")
    }
    paths = list(source.values())
    for dest in outputs.values():
        paths.extend((dest.data_root, dest.report_dir, dest.catalog))
    require_contract(
        all(
            not left.is_relative_to(right) and not right.is_relative_to(left)
            for left, right in combinations(paths, 2)
        ),
        "Stage input and output locations must be separate",
    )
    budget = {}
    for key, (minimum, maximum) in _BOUNDS.items():
        value = raw[key]
        require_contract(
            _bounded_int(value, minimum, maximum),
            "Invalid model budget: " + key,
        )
        budget[key] = value
    variants = tuple(_variant(row) for row in raw["variants"])
    names = {row["name"] for row in variants}
    stack_architecture = raw["stack_architecture"]
    require_contract(
        len(names) == len(variants)
        and {v["family"] for v in variants} == {"gru", "lstm", "din"}
        and any(v["heads"] > 1 for v in variants)
        and any(
            v["name"] == stack_architecture and v["family"] == "din" for v in variants
        ),
        "Expected distinct recurrent, DIN and multihead trials and a fixed DIN recipe",
    )
    return AdvancedSettings(
        sampling_catalog=source["sampling_catalog"],
        feature_catalog=source["feature_catalog"],
        traditional_catalog=source["traditional_catalog"],
        deep=outputs["deep"],
        ensemble=outputs["ensemble"],
        budget=cast(Budget, budget),
        variants=variants,
        stack_architecture=stack_architecture,
    )


def read_sequence_source(
    plan: TemporalPlan, feature_catalog: Path, split: str
) -> SequenceSource:
    """Validate and load the candidate rows and strictly historical sequences.

    Args:
        plan: Audited temporal partitions and dense feature whitelist.
        feature_catalog: Feature delivery catalog with immutable cutoff files.
        split: Split to load at the permitted stage of the experiment.

    Returns:
        Aligned dense data, raw identifiers and one sequence per user.
    """
    matrix, audit = read_temporal_split(plan, split)
    anchor = plan.anchors[split]
    cutoff = pd.Timestamp(anchor)
    catalog = read_json_object(feature_catalog)
    require_contract(
        catalog.get("status") == "completed", "Feature catalog was not completed"
    )
    snapshot = next(row for row in catalog["snapshots"] if row["anchor"] == anchor)
    records = {Path(row["path"]).name: row for row in snapshot["files"]}
    sequences = records["user_sequences.parquet"]
    items = records["item_features.parquet"]
    history = pq.read_table(verify_registered_file(sequences)).to_pandas()
    item = pq.read_table(
        verify_registered_file(items),
        columns=["item_id", "category_id", "as_of_time", "source_max_event_time"],
    ).to_pandas()
    keys = pq.read_table(
        verify_registered_file(plan.partitions[split]["file"]),
        columns=["as_of_time", "user_id", "item_id"],
    ).to_pandas()
    require_contract(
        not history["user_id"].duplicated().any()
        and history["source_max_event_time"].lt(cutoff).all()
        and item["as_of_time"].eq(cutoff).all()
        and item["source_max_event_time"].lt(cutoff).all()
        and not item["item_id"].duplicated().any(),
        f"Future or ambiguous sequence or item metadata in {split}",
    )
    categories = keys["item_id"].map(item.set_index("item_id")["category_id"])
    require_contract(
        categories.notna().all() and keys["user_id"].isin(history["user_id"]).all(),
        f"Missing cutoff category or user history in {split}",
    )
    return SequenceSource(
        matrix,
        keys,
        categories,
        history,
        dict(
            audit,
            sequence_file=sequences,
            item_file=items,
            history_users=len(history),
            latest_sequence_event=history["source_max_event_time"].max().isoformat(),
        ),
    )


def fit_vocabulary(source: SequenceSource, limit: int) -> Vocabulary:
    """Fit deterministic item and category vocabularies on training history only.

    Args:
        source: Chronological training candidates and historical sequences.
        limit: Maximum number of candidate item embeddings.

    Returns:
        Items ordered by training support and sorted category tokens.
    """
    frequencies = Counter(source.keys["item_id"])
    category = set(source.categories)
    frequencies.update(
        item for row in source.histories["seq_item_ids"].tolist() for item in row
    )
    category.update(
        token for row in source.histories["seq_category_ids"].tolist() for token in row
    )
    items = sorted(frequencies, key=lambda token: (-frequencies[token], token))
    return {"items": items[:limit], "categories": sorted(category)}


def _codes(values: np.ndarray | pd.Series, vocabulary: pd.Index) -> np.ndarray:
    """Map exact category or item identifiers, reserving 0 for pad and 1 for OOV.

    Args:
        values: Source identifiers in their original order.
        vocabulary: Fitted unique identifiers.

    Returns:
        One code per requested token.
    """
    return vocabulary.get_indexer(pd.Index(values)) + 2


def _history_bank(
    frame: pd.DataFrame, vocab: Vocabulary, anchor: str, length: int
) -> History:
    """Keep recent item-hours and encode true hour boundaries and recency.

    Args:
        frame: Verified per-user histories in the input file order.
        vocab: Training-only item and category vocabularies.
        anchor: Prediction time, exclusive in the history.
        length: Maximum number of stored tokens retained per user.

    Returns:
        Right-padded tensors and one-based indexes grouping same-hour tokens.
    """
    items, categories = pd.Index(vocab["items"]), pd.Index(vocab["categories"])
    shape = (len(frame), length)
    ids = np.zeros(shape, dtype=np.int64)
    cats, masks, hours = (np.zeros_like(ids) for _ in range(3))
    continuous = np.zeros((*shape, 5), dtype=np.float32)
    cutoff = pd.Timestamp(anchor)
    for index, row in enumerate(cast(list[_HistoryRow], frame.to_dict("records"))):
        size = min(row["sequence_length"], length)
        gaps = row["seq_gap_hours"][-size:].astype(np.int64, copy=True)
        mask = row["seq_behavior_masks"][-size:]
        counts = np.stack(list(row["seq_raw_behavior_counts"][-size:]))
        require_contract(
            0 < size == len(gaps) == len(mask) == len(counts)
            and bool((gaps >= 0).all() and (mask > 0).all() and (mask <= 15).all())
            and counts.shape == (size, 4)
            and bool((counts >= 0).all()),
            "Invalid sequence component or sequence length",
        )
        gaps[0] = 0
        delay = (cutoff - row["source_max_event_time"]).total_seconds() / 3600
        age = delay + np.cumsum(gaps[::-1])[::-1] - gaps
        require_contract(
            bool((age > 0).all() and (age <= 720).all()),
            "Sequence token is outside the historical lookback",
        )
        window = (index, slice(size))
        ids[window] = _codes(row["seq_item_ids"][-size:], items)
        cats[window] = _codes(row["seq_category_ids"][-size:], categories)
        masks[window] = mask
        hours[window] = np.cumsum(gaps > 0) + 1
        continuous[window] = np.column_stack((np.log1p(counts), np.log1p(age) / 6.6))
    return History(
        *(torch.from_numpy(a) for a in (ids, cats, masks, continuous, hours))
    )


def encode_split(
    source: SequenceSource, vocab: Vocabulary, preprocess: Any, length: int
) -> SequenceSplit:
    """Apply frozen encoders while keeping shared histories compact.

    Args:
        source: Verified raw split data in the same order as its sample partition.
        vocab: Training-only embedding codes.
        preprocess: Numeric imputer/scaler fitted by the approved 3.2 training.
        length: Maximum history tokens for the sequence models.

    Returns:
        Encoded candidate tensors with per-user history indices and original keys.
    """
    history_rows = pd.Index(source.histories["user_id"]).get_indexer(
        source.keys["user_id"]
    )
    dense = np.asarray(preprocess.transform(source.matrix.values), dtype=np.float32)
    require_contract(
        bool((history_rows >= 0).all() and np.isfinite(dense).all()),
        "Unavailable histories or nonfinite standardized feature values",
    )
    candidate = np.column_stack(
        (
            _codes(source.keys["item_id"], pd.Index(vocab["items"])),
            _codes(source.categories, pd.Index(vocab["categories"])),
        )
    )
    return SequenceSplit(
        torch.from_numpy(dense),
        torch.from_numpy(candidate),
        _history_bank(source.histories, vocab, source.audit["cutoff"], length),
        torch.from_numpy(history_rows),
        source.keys,
        source.matrix.target,
    )
