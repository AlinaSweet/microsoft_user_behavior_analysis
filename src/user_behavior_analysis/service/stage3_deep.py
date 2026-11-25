"""Train and compare sequence models on frozen chronological data."""

from dataclasses import asdict
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from platform import machine
from platform import system
from time import perf_counter
from typing import Any

import joblib  # type: ignore[import-untyped]
import numpy as np
import pandas as pd
import torch
from sklearn.pipeline import Pipeline  # type: ignore[import-untyped]

from user_behavior_analysis.common.utils import utc_timestamp
from user_behavior_analysis.common.utils import write_json
from user_behavior_analysis.dao.sequence_repository import encode_split
from user_behavior_analysis.dao.sequence_repository import fit_vocabulary
from user_behavior_analysis.dao.sequence_repository import read_sequence_source
from user_behavior_analysis.dao.traditional_repository import check_traditional_catalog
from user_behavior_analysis.dao.traditional_repository import historical_transform
from user_behavior_analysis.dao.traditional_repository import load_temporal_plan
from user_behavior_analysis.dao.traditional_repository import write_test_predictions
from user_behavior_analysis.dao.wide_repository import verify_registered_file
from user_behavior_analysis.models.sequence_models import AdvancedSettings
from user_behavior_analysis.models.sequence_models import SequenceSplit
from user_behavior_analysis.models.sequence_models import StagePaths
from user_behavior_analysis.models.sequence_models import Variant
from user_behavior_analysis.models.sequence_models import Vocabulary
from user_behavior_analysis.models.traditional_models import TemporalPlan
from user_behavior_analysis.service.sequence_networks import PurchaseNetwork
from user_behavior_analysis.service.sequence_training import FitResult
from user_behavior_analysis.service.sequence_training import Monitor
from user_behavior_analysis.service.sequence_training import fit_network
from user_behavior_analysis.service.sequence_training import probabilities
from user_behavior_analysis.service.sequence_training import sampled_rows
from user_behavior_analysis.service.validation_metrics import probability_metrics
from user_behavior_analysis.service.validation_metrics import validation_f1_threshold
from user_behavior_analysis.service.wide_audit import file_record


@dataclass(frozen=True)
class _FrozenFit:
    """Artifacts, training evidence and preprocessing frozen before test."""

    preprocess: Pipeline
    preprocess_file: dict[str, Any]
    model_file: dict[str, Any]
    stack_file: dict[str, Any]
    decision: dict[str, Any]
    epochs: list[dict[str, Any]]
    audit: dict[str, Any]


def prepare_outputs(paths: StagePaths) -> None:
    """Reserve unused version locations without replacing historical outputs.

    Args:
        paths: Model, report and catalog destinations for a new run.

    Raises:
        FileExistsError: A destination for this version already exists.
    """
    for path in asdict(paths).values():
        if path.exists():
            raise FileExistsError(f"Choose an unused stage output: {path}")
    paths.data_root.mkdir(parents=True)
    paths.report_dir.mkdir(parents=True)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write a new aggregate CSV with stable output line endings.

    Args:
        path: Versioned report destination.
        rows: Public aggregate rows in report order.
    """
    with path.open("x", encoding="utf-8", newline="") as stream:
        pd.DataFrame(rows).to_csv(stream, index=False, lineterminator="\n")


def restore_network(
    checkpoint: dict[str, Any], vocab: Vocabulary, width: int
) -> PurchaseNetwork:
    """Restore only the tensors of a fingerprinted sequence network.

    Args:
        checkpoint: Architecture and verified weight tensors.
        vocab: Stored training-only vocabulary.
        width: Expected ordered dense feature count.

    Returns:
        Reconstructed CPU network in inference mode.
    """
    model = PurchaseNetwork(checkpoint["variant"], vocab, width)
    model.load_state_dict(checkpoint["state"])
    model.eval()
    return model


def _checkpoint(variant: Variant, fit: FitResult) -> dict[str, Any]:
    """Collect the model state and probability correction for persistence.

    Args:
        variant: Declared network structure.
        fit: Output of the training loop.

    Returns:
        Tensor-only checkpoint with primitive metadata.
    """
    return {
        "variant": dict(variant),
        "state": fit.state,
        "offset": fit.offset,
        "selected_epoch": fit.selected_epoch,
        "fit_seconds": fit.seconds,
    }


def _observe(
    checkpoint: dict[str, Any],
    split: SequenceSplit,
    vocab: Vocabulary,
    batch_rows: int,
    threshold: float | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Measure one variant on a full natural split and optionally select a threshold.

    Args:
        checkpoint: Frozen weights and metadata.
        split: Complete validation or test candidates, in source order.
        vocab: Training-only token map.
        batch_rows: Scoring resource limit.
        threshold: Fixed validation threshold for test, otherwise fit on validation.

    Returns:
        Aligned probabilities and aggregate metrics.
    """
    model = restore_network(checkpoint, vocab, split.dense.shape[1])
    start = perf_counter()
    result = probabilities(model, split, batch_rows, checkpoint["offset"])
    seconds = perf_counter() - start
    if threshold is None:
        threshold = validation_f1_threshold(split.target, result)
    return result, dict(
        checkpoint["variant"],
        selected_epoch=checkpoint["selected_epoch"],
        fit_seconds=checkpoint["fit_seconds"],
        score_seconds=seconds,
        **probability_metrics(split.target, result, threshold),
    )


def _save_stack_base(
    settings: AdvancedSettings, train: SequenceSplit, vocab: Vocabulary
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Freeze one DIN using only training labels, before opening validation.

    Args:
        settings: Fixed architecture and number of epochs.
        train: Natural training rows.
        vocab: Train-fitted token lists.

    Returns:
        Fingerprint of the frozen DIN bundle and its training-only trace.
    """
    architecture = next(
        v for v in settings.variants if v["name"] == settings.stack_architecture
    )
    learned = fit_network(architecture, vocab, train, settings.budget)
    path = settings.deep.data_root / "stack_din.pt"
    with path.open("xb") as stream:
        torch.save(
            {"vocabulary": vocab, "model": _checkpoint(architecture, learned)}, stream
        )
    return file_record(path), [
        dict(row, variant="din_stack_train_only") for row in learned.history
    ]


def _compare_traditional(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    """Read the already frozen aggregate scores for the same temporal test rows.

    Args:
        catalog: Approved traditional model catalog.

    Returns:
        Three tuned traditional test summary records for comparison only.
    """
    item = next(
        row
        for row in catalog["reports"]
        if row["path"].endswith("/model_comparison.csv")
    )
    return [
        {
            **{str(k): v for k, v in row.items()},
            "name": str(row["family"]) + "_tuned",
            "model_type": "traditional",
        }
        for row in pd.read_csv(verify_registered_file(item)).to_dict("records")
        if row["split"] == "test" and row["variant"] == "tuned"
    ]


def _tune(
    settings: AdvancedSettings,
    train: SequenceSplit,
    vocab: Vocabulary,
    monitor: Monitor,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Choose checkpoints with early stopping, then compare full validation AUC.

    Args:
        settings: Predeclared variants and training budget.
        train: Audited training rows.
        vocab: Embedding vocabularies fitted on training only.
        monitor: Fixed validation monitor subset and full validation data.

    Returns:
        Frozen candidate weights, validation decisions and per-epoch summaries.
    """
    checkpoints, selection = {}, {}
    epochs: list[dict[str, Any]] = []
    for variant in settings.variants:
        trained = fit_network(variant, vocab, train, settings.budget, monitor)
        checkpoint = _checkpoint(variant, trained)
        name = variant["name"]
        checkpoints[name] = checkpoint
        epochs.extend(dict(row, variant=name) for row in trained.history)
        _, selection[name] = _observe(
            checkpoint, monitor.split, vocab, settings.budget["batch_rows"]
        )
        print(
            f"{name}: full validation AUC={selection[name]['roc_auc']:.6f}", flush=True
        )
    return checkpoints, selection, epochs


def _fit_and_freeze(settings: AdvancedSettings, plan: TemporalPlan) -> _FrozenFit:
    """Read training and validation only and persist all test-time decisions.

    Args:
        settings: Versioned inputs and destinations.
        plan: Audited chronological split metadata.

    Returns:
        Persisted artifacts and temporal controls for held-out scoring.
    """
    paths, budget = settings.deep, settings.budget
    original = read_sequence_source(plan, settings.feature_catalog, "train")
    vocab = fit_vocabulary(original, budget["vocabulary_limit"])
    train_audit = original.audit
    preprocess = historical_transform().fit(original.matrix.values)
    prep_path = paths.data_root / "preprocess.joblib"
    with prep_path.open("xb") as stream:
        joblib.dump(preprocess, stream)
    train = encode_split(original, vocab, preprocess, budget["sequence_length"])
    del original
    stack_file, epochs = _save_stack_base(settings, train, vocab)

    original = read_sequence_source(plan, settings.feature_catalog, "validation")
    validation_audit = original.audit
    validation = encode_split(original, vocab, preprocess, budget["sequence_length"])
    del original
    monitor = Monitor(
        validation,
        sampled_rows(
            validation.target, budget["monitor_negative_ratio"], budget["seed"] + 1
        ),
    )
    monitor_counts = {
        "rows": len(monitor.rows),
        "positives": int(validation.target[monitor.rows].sum()),
    }
    checkpoints, selection, tuned_epochs = _tune(settings, train, vocab, monitor)
    epochs.extend(tuned_epochs)
    path = paths.data_root / "sequence_models.pt"
    with path.open("xb") as stream:
        torch.save({"vocabulary": vocab, "models": checkpoints}, stream)
    chosen = max(selection, key=lambda variant: selection[variant]["roc_auc"])
    frozen = {
        "frozen_at_utc": utc_timestamp(),
        "chosen": chosen,
        "criterion": "Highest full validation ROC-AUC in declared order",
        "threshold": "Validation F1 maximum, tie selects higher threshold",
        "models": selection,
    }
    write_json(paths.report_dir / "validation_selection.json", frozen)
    return _FrozenFit(
        preprocess,
        file_record(prep_path),
        file_record(path),
        stack_file,
        frozen,
        epochs,
        {
            "splits": {"train": train_audit, "validation": validation_audit},
            "training_rows": epochs[0]["train_rows"],
            "validation_monitor": monitor_counts,
            "embedding_vocabulary": {
                "items": len(vocab["items"]),
                "categories": len(vocab["categories"]),
            },
        },
    )


def _score_deep_test(
    settings: AdvancedSettings,
    plan: TemporalPlan,
    fit: _FrozenFit,
    prior: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    """Load the held-out data only after the chosen checkpoints and thresholds exist.

    Args:
        settings: Test feature location and CPU scoring budget.
        plan: Approved natural test partition.
        fit: Previously stored preprocessing and freeze record.
        prior: Approved traditional scores for same-row comparison.

    Returns:
        Verified prediction file, aggregate comparisons and held-out data audit.
    """
    print("Deep selection frozen. Reading test rows.", flush=True)
    reloaded = torch.load(
        verify_registered_file(fit.model_file), map_location="cpu", weights_only=True
    )
    original = read_sequence_source(plan, settings.feature_catalog, "test")
    test = encode_split(
        original,
        reloaded["vocabulary"],
        fit.preprocess,
        settings.budget["sequence_length"],
    )
    predictions, scores = {}, _compare_traditional(prior)
    selection = fit.decision["models"]
    for name, checkpoint in reloaded["models"].items():
        threshold = selection[name]["threshold"]
        predictions[name], observed = _observe(
            checkpoint,
            test,
            reloaded["vocabulary"],
            settings.budget["batch_rows"],
            threshold,
        )
        scores.extend(
            (
                dict(selection[name], split="validation", model_type="deep"),
                dict(observed, split="test", model_type="deep"),
            )
        )
    saved = write_test_predictions(
        plan.partitions["test"],
        predictions,
        settings.deep.data_root / "test_predictions.parquet",
    )
    return saved, scores, original.audit


def run_deep_models(settings: AdvancedSettings) -> dict[str, Any]:
    """Complete stage 3.3, freezing all decisions before reading test data.

    Args:
        settings: Source manifests, declared architectures and new output version.

    Returns:
        Catalog of audited sequence models, prediction rows and published summaries.
    """
    started = perf_counter()
    paths, budget = settings.deep, settings.budget
    torch.set_num_threads(budget["threads"])
    plan = load_temporal_plan(settings.sampling_catalog)
    prior = check_traditional_catalog(settings.traditional_catalog, plan)
    prepare_outputs(paths)
    fit = _fit_and_freeze(settings, plan)
    saved, scores, test_audit = _score_deep_test(settings, plan, fit, prior)
    audit = {
        **fit.audit,
        "status": "passed",
        "protocol": "time_backtest",
        "splits": {**fit.audit["splits"], "test": test_audit},
        "budget": dict(budget),
        "torch_version": version("torch"),
        "platform": system() + " " + machine(),
        "elapsed_seconds": perf_counter() - started,
    }
    write_csv(paths.report_dir / "model_comparison.csv", scores)
    write_csv(paths.report_dir / "epochs.csv", fit.epochs)
    write_json(paths.report_dir / "audit.json", audit)
    catalog = {
        "kind": "stage3_deep_models",
        "status": "passed",
        "source_sampling_catalog": plan.source,
        "feature_catalog": file_record(settings.feature_catalog),
        "models": fit.model_file,
        "preprocess": fit.preprocess_file,
        "traditional_catalog": file_record(settings.traditional_catalog),
        "test_predictions": saved,
        "chosen": fit.decision["chosen"],
        "stack_member": fit.stack_file,
        "stack_plan": {
            "training_anchor": plan.anchors["train"],
            "epochs": budget["stack_epochs"],
            "validation_used": False,
            "architecture": settings.stack_architecture,
        },
        "reports": [file_record(p) for p in sorted(paths.report_dir.iterdir())],
    }
    write_json(paths.catalog, catalog)
    return catalog
