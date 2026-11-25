"""Build recurrent sequence baselines and a candidate-aware DIN purchase model."""

from typing import cast

import torch
from torch import Tensor
from torch import nn

from user_behavior_analysis.models.sequence_models import ModelBatch
from user_behavior_analysis.models.sequence_models import Variant
from user_behavior_analysis.models.sequence_models import Vocabulary


class PurchaseNetwork(nn.Module):
    """Encode history tokens using hour pooling or candidate-conditioned attention."""

    def __init__(self, options: Variant, vocab: Vocabulary, dense_width: int) -> None:
        """Initialize independent model weights for one declared experiment.

        Args:
            options: Recurrent or DIN variant and layer widths.
            vocab: Frozen item and category token lists.
            dense_width: Count of historical scalar features.
        """
        super().__init__()
        size, hidden = options["embedding"], options["hidden"]
        self.items = nn.Embedding(len(vocab["items"]) + 2, size, padding_idx=0)
        self.categories = nn.Embedding(
            len(vocab["categories"]) + 2, size, padding_idx=0
        )
        self.behaviors = nn.Embedding(16, 4, padding_idx=0)
        self.token = nn.Sequential(nn.Linear(2 * size + 9, hidden), nn.ReLU())
        self.query = nn.Sequential(nn.Linear(2 * size, hidden), nn.ReLU())
        self.recurrent: nn.GRU | nn.LSTM | None = None
        self.activation: nn.Sequential | None = None
        self.attention: nn.MultiheadAttention | None = None
        if options["family"] == "din":
            self.activation = nn.Sequential(
                nn.Linear(4 * hidden, hidden), nn.ReLU(), nn.Linear(hidden, 1)
            )
        else:
            constructor = nn.GRU if options["family"] == "gru" else nn.LSTM
            self.recurrent = constructor(hidden, hidden, batch_first=True)
        if options["heads"]:
            self.attention = nn.MultiheadAttention(
                hidden, options["heads"], batch_first=True
            )
        width = dense_width + hidden * (3 if self.attention is not None else 2)
        self.head = nn.Sequential(
            nn.Linear(width, hidden),
            nn.ReLU(),
            nn.Dropout(options["dropout"]),
            nn.Linear(hidden, 1),
        )

    def _hour_pool(self, tokens: Tensor, hour: Tensor) -> Tensor:
        """Mean-pool simultaneous item tokens before applying a recurrent layer.

        Args:
            tokens: Embedded history units, with arbitrary order within an hour.
            hour: One-based observed hours, reserving zero for padding.

        Returns:
            The last valid GRU or LSTM state for each user.
        """
        assert self.recurrent is not None
        axes = (hour - 1).clamp_min(0).unsqueeze(-1)
        valid = hour.gt(0).unsqueeze(-1)
        totals = torch.zeros_like(tokens).scatter_add(
            1, axes.expand_as(tokens), tokens.masked_fill(~valid, 0.0)
        )
        count = torch.zeros_like(tokens[:, :, :1]).scatter_add(
            1, axes, valid.to(tokens.dtype)
        )
        states, _ = self.recurrent(totals / count.clamp_min(1.0))
        rows = torch.arange(hour.size(0), device=hour.device)
        return cast(Tensor, states)[rows, axes.amax(dim=1).squeeze(-1)]

    def _interest(self, tokens: Tensor, candidate: Tensor, valid: Tensor) -> Tensor:
        """Pool user interests conditioned on the specific candidate item.

        Args:
            tokens: Projected history keys and values.
            candidate: Query from the candidate item and category.
            valid: Mask distinguishing observed units from padding.

        Returns:
            DIN activation pooling, optionally joined with multihead context.
        """
        assert self.activation is not None
        query = candidate.unsqueeze(1).expand_as(tokens)
        weights = torch.sigmoid(
            self.activation(
                torch.cat((query, tokens, query - tokens, query * tokens), dim=-1)
            )
        ).masked_fill(~valid.unsqueeze(-1), 0)
        interest = (weights * tokens).sum(dim=1)
        interest = interest / valid.sum(dim=1, keepdim=True).clamp_min(1).sqrt()
        if self.attention is None:
            return interest
        context, _ = self.attention(
            candidate.unsqueeze(1),
            tokens,
            tokens,
            key_padding_mask=~valid,
            need_weights=False,
        )
        return torch.cat((interest, context[:, 0]), dim=1)

    def forward(self, batch: ModelBatch) -> Tensor:
        """Predict uncalibrated purchase log odds from past information.

        Args:
            batch: Aligned historical numeric, candidate and sequence inputs.

        Returns:
            One logit per candidate.
        """
        history = batch.history
        tokens = self.token(
            torch.cat(
                (
                    self.items(history.item),
                    self.categories(history.category),
                    self.behaviors(history.behavior),
                    history.continuous,
                ),
                dim=-1,
            )
        )
        candidate = self.query(
            torch.cat(
                (
                    self.items(batch.candidate[:, 0]),
                    self.categories(batch.candidate[:, 1]),
                ),
                dim=1,
            )
        )
        context = (
            self._hour_pool(tokens, history.hour)
            if self.recurrent is not None
            else self._interest(tokens, candidate, history.hour.gt(0))
        )
        return cast(
            Tensor, self.head(torch.cat((batch.dense, candidate, context), dim=1))
        ).squeeze(-1)
