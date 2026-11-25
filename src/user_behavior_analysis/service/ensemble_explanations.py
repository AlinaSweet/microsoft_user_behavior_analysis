"""Explain frozen model margins and publish aggregate SHAP visualizations."""

from io import StringIO
from math import comb
from pathlib import Path
from typing import Any

import numpy as np
import torch
from matplotlib.figure import Figure
from torch import Tensor

from user_behavior_analysis.models.sequence_models import History
from user_behavior_analysis.models.sequence_models import ModelBatch
from user_behavior_analysis.service.sequence_networks import PurchaseNetwork
from user_behavior_analysis.service.stage3_deep import write_csv
from user_behavior_analysis.service.wide_contracts import require_contract


def _dense_groups(features: tuple[str, ...]) -> list[list[int]]:
    """Partition historical scalar features into three documented entity groups.

    Args:
        features: Exact ordered input features from stage 3.1.

    Returns:
        Column indexes for user, candidate pair, and item/category groups.
    """
    groups: list[list[int]] = [[], [], []]
    for index, name in enumerate(features):
        group = 1 if name.startswith("pair_") else 0 if name.startswith("user_") else 2
        groups[group].append(index)
    return groups


def shapley_values(coalitions: np.ndarray) -> np.ndarray:
    """Compute exact Shapley values from every coalition of an empirical game.

    Args:
        coalitions: Rows of predictions for ascending binary coalition masks.

    Returns:
        Additive attribution for each row and input group.
    """
    count = coalitions.shape[1]
    groups = count.bit_length() - 1
    require_contract(groups > 0 and count == 1 << groups, "Incomplete SHAP game")
    out = np.zeros((coalitions.shape[0], groups), dtype=np.float64)
    for member in range(groups):
        bit = 1 << member
        for subset in range(count):
            if not subset & bit:
                weight = 1 / (groups * comb(groups - 1, subset.bit_count()))
                out[:, member] += weight * (
                    coalitions[:, subset | bit] - coalitions[:, subset]
                )
    return out


def _repeat_tensor(value: Tensor, repeats: int, case: bool) -> Tensor:
    """Expand empirical reference pairs in case-major order.

    Args:
        value: Tensor with one row per case or background record.
        repeats: Number of records on the other side of the product.
        case: Whether rows are test cases or background values.

    Returns:
        Repeated rows in a consistent cross-product order.
    """
    if case:
        return value.repeat_interleave(repeats, dim=0)
    return value.repeat(repeats, *([1] * (value.ndim - 1)))


def _expand(batch: ModelBatch, repeats: int, case: bool) -> ModelBatch:
    """Broadcast complete and physically valid sequence blocks together.

    Args:
        batch: Real rows from one of the two populations.
        repeats: Other population's row count.
        case: Whether to repeat each case or repeat the whole background.

    Returns:
        Case-major model inputs retaining all history masks and lengths.
    """
    return ModelBatch(
        _repeat_tensor(batch.dense, repeats, case),
        _repeat_tensor(batch.candidate, repeats, case),
        History(*(_repeat_tensor(t, repeats, case) for t in batch.history)),
    )


def din_shap(
    model: PurchaseNetwork,
    cases: ModelBatch,
    background: ModelBatch,
    features: tuple[str, ...],
) -> tuple[list[str], np.ndarray, float]:
    """Explain DIN using exact grouped interventional SHAP in its logit space.

    Args:
        model: The frozen DIN used by the stacking experiment.
        cases: Deterministic, stratified test examples, used only for interpretation.
        background: Fixed natural rows sampled from training only.
        features: Approved dense feature names.

    Returns:
        Group labels, additive values and largest residual versus the model margin.
    """
    dense_groups = _dense_groups(features)
    names = [
        "User ratios",
        "Pair ratios",
        "Item and category ratios",
        "Candidate item and category",
        "Historical sequence",
    ]
    case_count, background_count = len(cases.dense), len(background.dense)
    left = _expand(cases, background_count, True)
    right = _expand(background, case_count, False)
    scores = []
    model.eval()
    with torch.inference_mode():
        for subset in range(1 << len(names)):
            dense = right.dense.clone()
            for group, columns in enumerate(dense_groups):
                if subset & (1 << group):
                    dense[:, columns] = left.dense[:, columns]
            hybrid = ModelBatch(
                dense,
                left.candidate if subset & 8 else right.candidate,
                left.history if subset & 16 else right.history,
            )
            out = model.forward(hybrid).numpy().reshape(case_count, background_count)
            scores.append(np.asarray(out, dtype=np.float64).mean(axis=1))
        actual = model.forward(cases).numpy()
    coalitions = np.column_stack(scores)
    values = shapley_values(coalitions)
    error = float(np.max(np.abs(coalitions[:, 0] + values.sum(axis=1) - actual)))
    require_contract(error <= 3e-5, "DIN SHAP values did not recover the model logit")
    return names, values, error


def publish_attributions(
    output: Path, stem: str, title: str, names: list[str], values: np.ndarray
) -> list[dict[str, Any]]:
    """Publish only aggregate statistics and their mean absolute SHAP chart.

    Args:
        output: Small, versioned report directory.
        stem: New CSV and SVG stem.
        title: Model and numerical attribution method.
        names: Model feature or feature group labels.
        values: Local rowwise attributions in model-margin units.

    Returns:
        Sorted rows with magnitude and signed distribution quantiles.
    """
    rows: list[dict[str, Any]] = [
        {
            "feature": name,
            "cases": len(values),
            "mean_abs_shap": float(np.mean(np.abs(values[:, i]))),
            "mean_shap": float(np.mean(values[:, i])),
            "p05_shap": float(np.quantile(values[:, i], 0.05)),
            "p95_shap": float(np.quantile(values[:, i], 0.95)),
        }
        for i, name in enumerate(names)
    ]
    rows.sort(key=lambda row: row["mean_abs_shap"], reverse=True)
    write_csv(output / (stem + ".csv"), rows)
    plotted = list(reversed(rows[:10]))
    figure = Figure(figsize=(10.6, max(3.4, len(plotted) * 0.46 + 1.25)))
    axis = figure.add_subplot()
    axis.barh(
        [row["feature"].replace("_", " ") for row in plotted],
        [row["mean_abs_shap"] for row in plotted],
        color="#24577b",
    )
    axis.set_title(title, loc="left", pad=13)
    axis.set_xlabel("Mean absolute attribution (log odds)")
    axis.grid(axis="x", alpha=0.25)
    axis.set_axisbelow(True)
    with StringIO() as svg:
        figure.savefig(svg, format="svg", bbox_inches="tight")
        content = "\n".join(line.rstrip() for line in svg.getvalue().splitlines())
    with (output / (stem + ".svg")).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(content + "\n")
    return rows
