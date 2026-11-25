"""Describe temporal sequence tensors, model variants and versioned destinations."""

from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple
from typing import TypedDict

import numpy as np
import pandas as pd
from torch import Tensor


class Variant(TypedDict):
    """One predeclared recurrent or candidate-attention architecture."""

    name: str
    family: str
    embedding: int
    hidden: int
    dropout: float
    heads: int


class Budget(TypedDict):
    """Training sizes and seeds, selected before seeing held-out outcomes."""

    seed: int
    threads: int
    sequence_length: int
    vocabulary_limit: int
    batch_rows: int
    training_negative_ratio: int
    monitor_negative_ratio: int
    max_epochs: int
    patience: int
    stack_epochs: int
    shap_cases: int
    shap_background: int
    bootstrap_repeats: int


@dataclass(frozen=True)
class StagePaths:
    """New local binary directory, small-report directory and artifact catalog."""

    data_root: Path
    report_dir: Path
    catalog: Path


@dataclass(frozen=True)
class AdvancedSettings:
    """Hold the approved upstream inputs and both experiments' configuration."""

    sampling_catalog: Path
    feature_catalog: Path
    traditional_catalog: Path
    deep: StagePaths
    ensemble: StagePaths
    budget: Budget
    variants: tuple[Variant, ...]
    stack_architecture: str


class Vocabulary(TypedDict):
    """Training-only item and category lists, with codes starting at two."""

    items: list[str]
    categories: list[str]


class History(NamedTuple):
    """User history token channels and right-padded, one-based hour segments."""

    item: Tensor
    category: Tensor
    behavior: Tensor
    continuous: Tensor
    hour: Tensor

    def take(self, rows: Tensor) -> "History":
        """Gather history on demand for a batch of candidate rows.

        Args:
            rows: Integer positions in the history bank.

        Returns:
            Aligned tensors for the requested users, including repeats.
        """
        return History(
            self.item[rows],
            self.category[rows],
            self.behavior[rows],
            self.continuous[rows],
            self.hour[rows],
        )


class ModelBatch(NamedTuple):
    """One detached or trainable batch of dense, candidate and sequence inputs."""

    dense: Tensor
    candidate: Tensor
    history: History


@dataclass
class SequenceSplit:
    """One time split with one history per user and a stable candidate row order."""

    dense: Tensor
    candidate: Tensor
    history: History
    history_rows: Tensor
    keys: pd.DataFrame
    target: np.ndarray

    def batch(self, rows: slice | Tensor) -> ModelBatch:
        """Select features, gathering histories only for current candidate rows.

        Args:
            rows: Contiguous slice or integer tensor of candidate positions.

        Returns:
            Candidate-aligned tensors, excluding the actual outcomes.
        """
        return ModelBatch(
            self.dense[rows],
            self.candidate[rows],
            self.history.take(self.history_rows[rows]),
        )
