"""Compress storage types while preserving canonical event values."""

import pandas as pd
import pyarrow as pa  # type: ignore[import-untyped]  # No Arrow stubs.

from user_behavior_analysis.dao.dataset_repository import EVENT_COLUMNS
from user_behavior_analysis.dao.dataset_repository import read_event_batches
from user_behavior_analysis.models.preprocessing_models import EncodingPlan
from user_behavior_analysis.models.preprocessing_models import PreprocessingPolicy
from user_behavior_analysis.models.preprocessing_models import SourceDataset


def choose_encoding_plan(
    source: SourceDataset, policy: PreprocessingPolicy
) -> EncodingPlan:
    """Inspect ranges before choosing compact types or category dictionaries.

    Args:
        source: Content-verified event source.
        policy: Bounded category collection and input batch settings.

    Returns:
        Safe unsigned lineage width and an optional complete category dictionary.
    """
    categories: set[str] | None = set()
    maximum = 0
    for frame in read_event_batches(
        source.parts, policy.batch_rows, ["event_id", "category_id"]
    ):
        minimum = int(frame["event_id"].min())
        if minimum < 1:
            raise ValueError("Source event ordinals must be positive")
        maximum = max(maximum, int(frame["event_id"].max()))
        if categories is not None:
            categories.update(str(value) for value in frame["category_id"].unique())
            if len(categories) > policy.dictionary_category_limit:
                categories = None
    if maximum > 2**64 - 1:
        raise ValueError("Event ordinals exceed uint64 capacity")
    return EncodingPlan(
        32 if maximum <= 2**32 - 1 else 64,
        tuple(sorted(categories)) if categories is not None else None,
        maximum,
    )


def encode_events(frame: pd.DataFrame, plan: EncodingPlan) -> pa.Table:
    """Build compact Arrow arrays with explicit lossless casts.

    Args:
        frame: Canonical event values; the frame is not modified.
        plan: Validated lineage width and optional source category dictionary.

    Returns:
        An Arrow table with stable identifier strings and source-time semantics.

    Raises:
        ValueError: Behavior values, category membership, or lineage range differ.
    """
    if plan.event_id_bits not in (32, 64):
        raise ValueError("Lineage width must be uint32 or uint64")
    if list(frame.columns) != EVENT_COLUMNS:
        raise ValueError("Encoding requires canonical event column order")
    if pd.to_datetime(frame["event_time"]).dt.tz is not None:
        raise ValueError("Encoding cannot drop a source timezone")
    behaviors = pd.to_numeric(frame["behavior_type"], errors="raise")
    if not behaviors.isin([1, 2, 3, 4]).all():
        raise ValueError("Encoding cannot change invalid behavior values")
    category = pa.array(frame["category_id"], type=pa.string())
    if plan.categories is not None:
        if not frame["category_id"].isin(plan.categories).all():
            raise ValueError("A category is absent from the verified encoding plan")
        categorical = pd.Categorical(frame["category_id"], categories=plan.categories)
        if (categorical.codes < 0).any():
            raise ValueError("A category is absent from the verified encoding plan")
        category = pa.DictionaryArray.from_arrays(
            pa.array(
                categorical.codes,
                type=pa.int16() if len(plan.categories) < 32768 else pa.int32(),
            ),
            pa.array(plan.categories, type=pa.string()),
        )
    lineage_type = pa.uint32() if plan.event_id_bits == 32 else pa.uint64()
    table = pa.Table.from_arrays(
        [
            pa.array(frame["event_id"], type=lineage_type, safe=True),
            pa.array(frame["user_id"], type=pa.string()),
            pa.array(frame["item_id"], type=pa.string()),
            category,
            pa.array(behaviors, type=pa.uint8(), safe=True),
            pa.array(frame["event_time"]).cast(pa.timestamp("ms"), safe=True),
        ],
        names=EVENT_COLUMNS,
    )
    if any(column.null_count for column in table.columns):
        raise ValueError("Encoding cannot introduce missing canonical values")
    return table
