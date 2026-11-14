"""Apply train-fitted imputation, sparse categories and scaled numeric inputs."""

from dataclasses import asdict
from typing import Any

import duckdb
import numpy as np
import pandas as pd
from scipy import sparse  # type: ignore[import-untyped]

from user_behavior_analysis.models.validation_models import FeatureTransform
from user_behavior_analysis.service.wide_contracts import identifier
from user_behavior_analysis.service.wide_contracts import require_contract


def training_profiles(
    connection: duckdb.DuckDBPyConnection, definitions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Calculate exact full-training moments and training-only approximate medians.

    Args:
        connection: View train containing only the declared training cutoff.
        definitions: All registered scalar definitions.

    Returns:
        Per-field missingness, finite counts, variance and imputation statistics.
    """
    output = []
    for start in range(0, len(definitions), 32):
        group = definitions[start : start + 32]
        clauses = ["COUNT(*) AS rows"]
        for index, definition in enumerate(group):
            field = identifier(definition["name"])
            prefix = "f" + str(index)
            clauses += [
                f"COUNT({field}) AS {prefix}_nonnull",
                (
                    f"COUNT(DISTINCT {field}) AS {prefix}_distinct"
                    if definition["dtype"] == "category"
                    else f"approx_count_distinct({field}) AS {prefix}_distinct"
                ),
            ]
            if definition["dtype"] != "category":
                clauses += [
                    f"AVG({field}) AS {prefix}_mean",
                    f"VAR_POP({field}) AS {prefix}_variance",
                    f"approx_quantile({field},0.5) AS {prefix}_median",
                    f"COUNT(*) FILTER(WHERE {field}=0) AS {prefix}_zeros",
                    (
                        f"COUNT(*) FILTER(WHERE {field} IS NOT NULL "
                        + f"AND NOT isfinite({field})) AS {prefix}_invalid"
                    ),
                ]
        row = (
            connection.execute("SELECT " + ",".join(clauses) + " FROM train")
            .df()
            .iloc[0]
        )
        for index, definition in enumerate(group):
            prefix = "f" + str(index)
            total, nonnull = int(row["rows"]), int(row[prefix + "_nonnull"])
            record = dict(
                definition,
                rows=total,
                missing_rate=1 - nonnull / total,
                distinct=int(row[prefix + "_distinct"]),
                nonnull=nonnull,
            )
            if definition["dtype"] != "category":
                record.update(
                    {
                        name: (
                            None
                            if pd.isna(row[prefix + "_" + name])
                            else float(row[prefix + "_" + name])
                        )
                        for name in ("mean", "variance", "median")
                    }
                )
                record["zero_rate"] = int(row[prefix + "_zeros"]) / total
                require_contract(
                    row[prefix + "_invalid"] == 0, "Nonfinite training feature"
                )
            output.append(record)
    return output


def fit_transform_contract(
    connection: duckdb.DuckDBPyConnection,
    profiles: list[dict[str, Any]],
    columns: list[str],
) -> FeatureTransform:
    """Freeze full-training numeric moments and categorical vocabularies.

    Args:
        connection: Training-only analytical view.
        profiles: Full training column statistics.
        columns: Selected names without keys, source times or labels.

    Returns:
        Reusable preprocessing state without any validation or test observations.
    """
    by_name = {row["name"]: row for row in profiles}
    result = FeatureTransform(columns, {}, {}, {}, {}, [])
    for name in columns:
        row = by_name[name]
        if row["dtype"] == "category":
            values = connection.execute(
                "SELECT DISTINCT "
                + identifier(name)
                + " FROM train WHERE "
                + name
                + " IS NOT NULL ORDER BY 1"
            ).fetchall()
            result.categories[name] = [str(value[0]) for value in values]
            continue
        median = float(row["median"] or 0)
        fraction = 1 - row["missing_rate"]
        mean = fraction * float(row["mean"] or 0) + (1 - fraction) * median
        variance = fraction * (
            float(row["variance"] or 0) + (float(row["mean"] or 0) - mean) ** 2
        )
        variance += (1 - fraction) * (median - mean) ** 2
        result.medians[name], result.means[name] = median, mean
        result.scales[name] = max(float(np.sqrt(variance)), 1e-8)
        if row["missing_rate"] > 0:
            result.missing_indicators.append(name)
    return result


def transform_frame(frame: pd.DataFrame, state: FeatureTransform) -> Any:
    """Transform a bounded frame without updating any fitted state.

    Args:
        frame: Training, validation or test feature rows.
        state: Immutable training-fitted parameters.

    Returns:
        Float32 CSR matrix with unknown-category buckets and missing indicators.

    Raises:
        ValueError: An infinite numeric value is encountered.
    """
    numeric = [name for name in state.columns if name not in state.categories]
    blocks = []
    if numeric:
        values = frame[numeric].to_numpy(dtype=np.float32, copy=True)
        require_contract(not np.isinf(values).any(), "Infinite input")
        missing = np.isnan(values)
        values = np.where(
            missing, np.array([state.medians[n] for n in numeric]), values
        )
        values = (values - np.array([state.means[n] for n in numeric])) / np.array(
            [state.scales[n] for n in numeric]
        )
        blocks.append(sparse.csr_matrix(values.astype(np.float32)))
        indices = [numeric.index(name) for name in state.missing_indicators]
        if indices:
            blocks.append(sparse.csr_matrix(missing[:, indices].astype(np.float32)))
    for name, vocabulary in state.categories.items():
        mapping = {value: index + 1 for index, value in enumerate(vocabulary)}
        tokens = frame[name].map(mapping).fillna(0).to_numpy(dtype=np.int32)
        blocks.append(
            sparse.csr_matrix(
                (
                    np.ones(len(frame), dtype=np.float32),
                    (np.arange(len(frame)), tokens),
                ),
                shape=(len(frame), len(vocabulary) + 1),
            )
        )
    return sparse.hstack(blocks, format="csr", dtype=np.float32)


def transform_record(state: FeatureTransform) -> dict[str, Any]:
    """Describe preprocessing and its exact matrix-column order.

    Args:
        state: Training-fitted preprocessing parameters.

    Returns:
        JSON-compatible state and encoded matrix column names.
    """
    numeric = [n for n in state.columns if n not in state.categories]
    names = numeric + [name + "__missing" for name in state.missing_indicators]
    for name, vocabulary in state.categories.items():
        names += [name + "__unknown"] + [name + "__" + value for value in vocabulary]
    return dict(asdict(state), encoded_columns=names, fit_split="train")
