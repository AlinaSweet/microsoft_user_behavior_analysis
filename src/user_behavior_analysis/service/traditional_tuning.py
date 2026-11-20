"""Tune complete training rows with a fixed, validation-only ROC-AUC objective."""

from dataclasses import dataclass
from time import perf_counter
from typing import Any

import numpy as np
import optuna
import psutil
from lightgbm import LGBMClassifier  # type: ignore[import-untyped]
from sklearn.linear_model import LogisticRegression  # type: ignore[import-untyped]
from sklearn.metrics import roc_auc_score  # type: ignore[import-untyped]
from xgboost import XGBClassifier

from user_behavior_analysis.models.traditional_models import LabeledMatrix
from user_behavior_analysis.models.traditional_models import TraditionalSettings
from user_behavior_analysis.service.wide_contracts import require_contract

_MAX_LOGISTIC_ITER = 400
_TREE_DEFAULT = {
    "n_estimators": 96,
    "learning_rate": 0.08,
    "subsample": 0.85,
    "colsample_bytree": 0.85,
    "reg_lambda": 1.0,
    "positive_weight": 1.0,
}
BASELINE = {
    "logistic_regression": {"C": 1.0, "positive_weight": 1.0},
    "xgboost": {**_TREE_DEFAULT, "max_depth": 4, "min_child_weight": 5.0},
    "lightgbm": {**_TREE_DEFAULT, "num_leaves": 31, "min_child_samples": 64},
}


@dataclass(frozen=True)
class FittedVariant:
    """A fitted candidate summarized before test access.

    Attributes:
        estimator: Trained binary classifier supporting probability prediction.
        parameters: Predeclared or sampled parameters.
        trial: Optuna trial number, where zero is the baseline.
        validation_auc: Full chronological validation ROC-AUC.
        fit_seconds: Elapsed model fit time.
        rss_after_fit_bytes: Process RSS sampled after the model fit.
    """

    estimator: Any
    parameters: dict[str, Any]
    trial: int
    validation_auc: float
    fit_seconds: float
    rss_after_fit_bytes: int


@dataclass(frozen=True)
class FamilyFit:
    """Keep only the baseline and best validation model with the complete trace.

    Attributes:
        baseline: Initial predeclared model.
        tuned: Model selected by maximum validation ROC-AUC.
        trials: Evidence of all completed trials.
    """

    baseline: FittedVariant
    tuned: FittedVariant
    trials: list[dict[str, Any]]


def _sample(trial: optuna.Trial, family: str) -> dict[str, Any]:
    """Suggest bounded parameters for the requested model family.

    Args:
        trial: Current Optuna candidate.
        family: One of the three registered classifier families.

    Returns:
        All varying parameters, including the training positive weight.
    """
    weight = trial.suggest_float("positive_weight", 1.0, 24.0, log=True)
    if family == "logistic_regression":
        return {
            "positive_weight": weight,
            "C": trial.suggest_float("C", 0.001, 20.0, log=True),
        }
    common = {
        "positive_weight": weight,
        "n_estimators": trial.suggest_int("n_estimators", 64, 160, step=16),
        "learning_rate": trial.suggest_float("learning_rate", 0.025, 0.16, log=True),
        "subsample": trial.suggest_float("subsample", 0.65, 1.0),
        "colsample_bytree": trial.suggest_float("colsample_bytree", 0.65, 1.0),
        "reg_lambda": trial.suggest_float("reg_lambda", 0.001, 30.0, log=True),
    }
    if family == "xgboost":
        return {
            **common,
            "max_depth": trial.suggest_int("max_depth", 3, 7),
            "min_child_weight": trial.suggest_float(
                "min_child_weight", 1.0, 30.0, log=True
            ),
        }
    return {
        **common,
        "num_leaves": trial.suggest_int("num_leaves", 15, 63),
        "min_child_samples": trial.suggest_int("min_child_samples", 32, 512, log=True),
    }


def _build(
    family: str, parameters: dict[str, Any], settings: TraditionalSettings
) -> Any:
    """Initialize one CPU-based model with the shared resource and seed settings.

    Args:
        family: Registered binary model family.
        parameters: Predeclared or Optuna-selected parameters.
        settings: Native thread count and fixed training seed.

    Returns:
        Unfit classifier.
    """
    options = {
        name: value for name, value in parameters.items() if name != "positive_weight"
    }
    if family == "logistic_regression":
        return LogisticRegression(
            solver="lbfgs", max_iter=_MAX_LOGISTIC_ITER, **options
        )
    options.update(n_jobs=settings.threads, random_state=settings.seed)
    if family == "xgboost":
        return XGBClassifier(
            objective="binary:logistic",
            eval_metric="auc",
            tree_method="hist",
            device="cpu",
            max_bin=128,
            **options,
        )
    return LGBMClassifier(
        objective="binary",
        max_bin=127,
        subsample_freq=1,
        deterministic=True,
        force_col_wise=True,
        verbosity=-1,
        **options,
    )


def predict_probability(estimator: Any, values: np.ndarray) -> np.ndarray:
    """Predict the positive-class probability for the unchanged input order.

    Args:
        estimator: Train-fitted classifier from a supported family.
        values: Already transformed validation or test rows.

    Returns:
        Finite positive probabilities, one per input row.
    """
    if isinstance(estimator, LGBMClassifier):
        scores = estimator.booster_.predict(values, num_threads=estimator.n_jobs)
    else:
        scores = estimator.predict_proba(values)[:, 1]
    probabilities = np.asarray(scores, dtype=np.float64)
    finite_unit_interval = (
        np.isfinite(probabilities) & (0 <= probabilities) & (probabilities <= 1)
    )
    require_contract(
        probabilities.shape == (len(values),) and bool(finite_unit_interval.all()),
        "Invalid positive-class probabilities",
    )
    return probabilities


def _fit(
    family: str,
    trial: optuna.Trial,
    train: LabeledMatrix,
    validation: LabeledMatrix,
    settings: TraditionalSettings,
) -> FittedVariant:
    """Fit one candidate on training rows and score every validation row.

    Args:
        family: Registered binary classifier family.
        trial: Current Optuna candidate.
        train: Features and labels from the time-ordered training set.
        validation: Frozen chronological validation features and labels.
        settings: Declared computation and seed settings.

    Returns:
        The fitted candidate and exact validation objective.
    """
    parameters = _sample(trial, family)
    estimator = _build(family, parameters, settings)
    weights = np.where(train.target == 1, parameters["positive_weight"], 1.0)
    weights /= weights.mean()
    start = perf_counter()
    estimator.fit(train.values, train.target, sample_weight=weights)
    fit_seconds = perf_counter() - start
    rss = psutil.Process().memory_info().rss
    if family == "logistic_regression":
        require_contract(
            int(estimator.n_iter_.max()) < _MAX_LOGISTIC_ITER,
            "Logistic regression did not converge in the predeclared budget",
        )
    scores = predict_probability(estimator, validation.values)
    return FittedVariant(
        estimator,
        parameters,
        trial.number,
        float(roc_auc_score(validation.target, scores)),
        fit_seconds,
        rss,
    )


def tune_family(
    family: str,
    train: LabeledMatrix,
    validation: LabeledMatrix,
    settings: TraditionalSettings,
) -> FamilyFit:
    """Fit the baseline and run seeded TPE on the same natural validation set.

    Args:
        family: Registered model family.
        train: Complete transformed chronological training rows.
        validation: Complete transformed chronological validation rows.
        settings: Predeclared full-row per-model trial budget.

    Returns:
        Baseline, best candidate and all trial records, without test access.
    """
    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(
            seed=settings.seed, n_startup_trials=min(4, settings.trials_per_model - 1)
        ),
    )
    study.enqueue_trial(BASELINE[family])
    kept: dict[str, FittedVariant] = {}
    traces = []

    def objective(trial: optuna.Trial) -> float:
        """Evaluate a candidate and retain the earliest best fit.

        Args:
            trial: Current candidate supplied by the seeded sampler.

        Returns:
            ROC-AUC on the complete validation split.
        """
        result = _fit(family, trial, train, validation, settings)
        if trial.number == 0:
            kept.update(baseline=result, tuned=result)
        if result.validation_auc > kept["tuned"].validation_auc:
            kept["tuned"] = result
        traces.append(
            {
                "family": family,
                "trial": result.trial,
                "validation_roc_auc": result.validation_auc,
                "fit_seconds": result.fit_seconds,
                "rss_after_fit_bytes": result.rss_after_fit_bytes,
                "parameters": result.parameters,
            }
        )
        print(
            f"{family} trial {trial.number + 1}: AUC {result.validation_auc:.6f}",
            flush=True,
        )
        return result.validation_auc

    study.optimize(objective, n_trials=settings.trials_per_model, n_jobs=1)
    require_contract(
        len(traces) == settings.trials_per_model
        and kept["tuned"].validation_auc == study.best_value,
        "Incomplete tuning trace or inconsistent Optuna winner",
    )
    return FamilyFit(kept["baseline"], kept["tuned"], traces)
