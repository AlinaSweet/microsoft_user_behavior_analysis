"""Resolve new stage-two versions while reusing checked historical samples."""

from pathlib import Path
from typing import Any

from user_behavior_analysis.common.utils import project_output_path
from user_behavior_analysis.dao.validation_repository import load_validation_settings
from user_behavior_analysis.dao.wide_repository import read_json_object
from user_behavior_analysis.models.encoding_models import CompletionSettings
from user_behavior_analysis.service.wide_contracts import require_contract


def load_completion_settings(path: Path) -> CompletionSettings:
    """Validate new output paths and encoding choices before any artifact creation.

    Args:
        path: Versioned JSON completion configuration.

    Returns:
        Confined paths, existing sample configuration and fixed new options.
    """
    raw = read_json_object(path)
    validation = load_validation_settings(Path(raw.pop("validation_config")))
    locations = {
        name: project_output_path(raw.pop(name))
        for name in ("data_root", "report_dir", "catalog")
    }
    require_contract(2 <= raw["target_folds"] <= 10, "Target fold bounds")
    require_contract(raw["target_smoothing"] > 0, "Positive smoothing")
    require_contract(1 <= raw["embedding_dimensions"] <= 32, "Embedding bounds")
    require_contract(raw["epochs"] == 5, "Predeclared five epochs required")
    return CompletionSettings(validation, **locations, options=raw)


def completion_inputs(settings: CompletionSettings) -> dict[str, Any]:
    """Read the accepted source sample and selection records without rewriting them.

    Args:
        settings: New completion paths and prior validation configuration.

    Returns:
        Existing source manifest and training-only selected preprocessing.
    """
    directory = settings.validation.report_dir
    return {
        "samples": read_json_object(directory / "samples.json"),
        "selection": read_json_object(directory / "selection.json"),
    }
