"""Fit reproducible CPU models with train-only sampling and validation monitoring."""

from dataclasses import dataclass
from math import log
from time import perf_counter
from typing import Any

import numpy as np
import torch
from sklearn.metrics import roc_auc_score  # type: ignore[import-untyped]
from torch import Tensor
from torch import nn

from user_behavior_analysis.models.sequence_models import Budget
from user_behavior_analysis.models.sequence_models import SequenceSplit
from user_behavior_analysis.models.sequence_models import Variant
from user_behavior_analysis.models.sequence_models import Vocabulary
from user_behavior_analysis.service.sequence_networks import PurchaseNetwork
from user_behavior_analysis.service.wide_contracts import require_contract


@dataclass(frozen=True)
class Monitor:
    """Hold a fixed natural-label validation subset for epoch selection."""

    split: SequenceSplit
    rows: np.ndarray


@dataclass(frozen=True)
class FitResult:
    """Hold restorable weights and the observed training-only performance trace."""

    state: dict[str, Tensor]
    history: list[dict[str, Any]]
    selected_epoch: int
    offset: float
    seconds: float


def sampled_rows(target: np.ndarray, ratio: int, seed: int) -> np.ndarray:
    """Keep every positive and sample negatives without replacement.

    Args:
        target: Labels from the one permitted training or monitor split.
        ratio: Desired maximum negatives per positive.
        seed: Versioned random seed.

    Returns:
        Sorted row positions, stable regardless of execution batch sizes.
    """
    positives = np.flatnonzero(target == 1)
    negatives = np.flatnonzero(target == 0)
    require_contract(len(positives) > 0 and len(negatives) > 0, "Both labels required")
    chosen = np.random.default_rng(seed).choice(
        negatives, min(ratio * len(positives), len(negatives)), replace=False
    )
    return np.sort(np.concatenate((positives, chosen)))


def logits(
    model: PurchaseNetwork,
    split: SequenceSplit,
    batch_rows: int,
    positions: np.ndarray | None = None,
) -> np.ndarray:
    """Score requested rows in order without retaining autograd graphs.

    Args:
        model: Fitted network on CPU.
        split: Cutoff data with histories gathered per batch.
        batch_rows: Maximum inference rows in one batch.
        positions: Explicit selected row indices or all rows.

    Returns:
        A NumPy vector of finite raw model logits.
    """
    size = len(split.target) if positions is None else len(positions)
    values = np.empty(size, dtype=np.float64)
    model.eval()
    with torch.inference_mode():
        for start in range(0, size, batch_rows):
            span = slice(start, min(size, start + batch_rows))
            rows = span if positions is None else torch.from_numpy(positions[span])
            values[span] = model.forward(split.batch(rows)).numpy()
    require_contract(bool(np.isfinite(values).all()), "Nonfinite model predictions")
    return values


def probabilities(
    model: PurchaseNetwork, split: SequenceSplit, batch_rows: int, offset: float
) -> np.ndarray:
    """Score complete rows with the fixed sampling-odds adjustment.

    Args:
        model: Fitted network.
        split: Natural candidate evaluation rows.
        batch_rows: Maximum scored rows in one batch.
        offset: Log retention fraction of training negatives.

    Returns:
        Prior-adjusted scores in the original candidate row order.
    """
    scores = torch.from_numpy(logits(model, split, batch_rows) + offset)
    return torch.sigmoid(scores).numpy()


def _train_epoch(
    model: PurchaseNetwork,
    train: SequenceSplit,
    optimizer: torch.optim.Optimizer,
    rows: np.ndarray,
    batch_rows: int,
) -> float:
    """Update the model on one shuffled pass of the frozen training subset.

    Args:
        model: Model with trainable parameters.
        train: Chronological training split.
        optimizer: AdamW optimizer retaining accumulated state.
        rows: Shuffled selected training positions.
        batch_rows: Maximum training examples per step.

    Returns:
        Mean observed binary cross entropy for this epoch.
    """
    model.train()
    criterion = nn.BCEWithLogitsLoss()
    total = 0.0
    for start in range(0, len(rows), batch_rows):
        part = rows[start : start + batch_rows]
        optimizer.zero_grad(set_to_none=True)
        output = model.forward(train.batch(torch.from_numpy(part)))
        target = torch.from_numpy(train.target[part]).float()
        loss = criterion(output, target)
        loss.backward()
        nn.utils.clip_grad_norm_(
            model.parameters(), max_norm=2.0, error_if_nonfinite=True
        )
        optimizer.step()
        total += float(loss.detach()) * len(part)
    return total / len(rows)


def fit_network(
    variant: Variant,
    vocab: Vocabulary,
    train: SequenceSplit,
    budget: Budget,
    monitor: Monitor | None = None,
) -> FitResult:
    """Fit a validation-stopped variant or completely validation-blind stack member.

    Args:
        variant: Predeclared layer settings.
        vocab: Vocabulary fitted on the training cutoff.
        train: Verified natural training candidates.
        budget: Fixed seed, batch size and configured training exposure.
        monitor: Validation subset for ordinary variant tuning, optional for stacking.

    Returns:
        CPU model weights, selected epoch, training trace and sampling odds.
    """
    start = perf_counter()
    torch.manual_seed(budget["seed"])
    torch.set_num_threads(budget["threads"])
    torch.use_deterministic_algorithms(True)
    model = PurchaseNetwork(variant, vocab, train.dense.shape[1])
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.003, weight_decay=0.0001)
    scheduler = torch.optim.lr_scheduler.ExponentialLR(optimizer, gamma=0.8)
    rng = np.random.default_rng(budget["seed"])
    selected = sampled_rows(
        train.target, budget["training_negative_ratio"], budget["seed"]
    )
    positives = int(train.target.sum())
    offset = log((len(selected) - positives) / (len(train.target) - positives))
    trace: list[dict[str, Any]] = []
    best_state: dict[str, Tensor] = {}
    best_auc, best_epoch, stale = -1.0, 0, 0
    total_epochs = budget["stack_epochs"] if monitor is None else budget["max_epochs"]
    for epoch in range(1, total_epochs + 1):
        loss = _train_epoch(
            model, train, optimizer, rng.permutation(selected), budget["batch_rows"]
        )
        current = None
        if monitor is not None:
            scores = logits(model, monitor.split, budget["batch_rows"], monitor.rows)
            current = float(roc_auc_score(monitor.split.target[monitor.rows], scores))
        trace.append(
            {
                "epoch": epoch,
                "train_rows": len(selected),
                "loss": loss,
                "learning_rate": scheduler.get_last_lr()[0],
                "monitor_auc": current,
            }
        )
        if current is None or current > best_auc + 0.0002:
            best_auc = -1.0 if current is None else current
            best_epoch, stale = epoch, 0
            best_state = {
                name: value.detach().clone()
                for name, value in model.state_dict().items()
            }
        else:
            stale += 1
        print(
            f"{variant['name']} epoch {epoch}: loss={loss:.6f}, monitor_auc={current}",
            flush=True,
        )
        if stale >= budget["patience"]:
            break
        scheduler.step()
    return FitResult(best_state, trace, best_epoch, offset, perf_counter() - start)
