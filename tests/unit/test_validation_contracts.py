"""Check temporal boundaries, exhaustive grouping and protected feature decisions."""

import copy
import json
import unittest
from unittest.mock import patch

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.dao.validation_repository import load_validation_settings
from user_behavior_analysis.service.validation_groups import business_protected
from user_behavior_analysis.service.validation_groups import feature_group


class ValidationContractTests(unittest.TestCase):
    """Reject leakage-prone configurations before reading model data."""

    def setUp(self) -> None:
        """Read the small, versioned experiment configuration."""
        self.configuration = json.loads(
            (PROJECT_ROOT / "configs/feature_validation.json").read_text()
        )

    def test_overlapping_label_windows_are_rejected(self) -> None:
        """A training label must mature before validation prediction time."""
        # Arrange
        configuration = copy.deepcopy(self.configuration)
        configuration["splits"]["validation"] = "2025-12-01"
        # Act / Assert
        with patch(
            ("user_behavior_analysis.dao.validation_reposit" + "ory.read_json_object"),
            return_value=configuration,
        ):
            with self.assertRaisesRegex(ValueError, "overlap"):
                load_validation_settings(PROJECT_ROOT / "unused.json")

    def test_output_escape_is_rejected(self) -> None:
        """Model samples must remain within the project root."""
        # Arrange
        configuration = copy.deepcopy(self.configuration)
        configuration["sample_root"] = "../outside"
        # Act / Assert
        with patch(
            ("user_behavior_analysis.dao.validation_reposit" + "ory.read_json_object"),
            return_value=configuration,
        ):
            with self.assertRaisesRegex(ValueError, "remain under"):
                load_validation_settings(PROJECT_ROOT / "unused.json")

    def test_original_scalars_are_assigned_once(self) -> None:
        """Cover the real dictionary without including six raw arrays or IDs."""
        # Arrange
        dictionary = json.loads(
            (
                PROJECT_ROOT
                / (
                    "outputs/reports/feature_system_20261029/featu"
                    + "re_dictionary.json"
                )
            ).read_text()
        )
        definitions = [d for d in dictionary["features"] if d["table"] != "sequence"]
        # Act
        groups = {d["name"]: feature_group(d) for d in definitions}
        # Assert
        self.assertEqual(len(groups), 439)

    def test_business_funnel_has_explicit_protection(self) -> None:
        """Retain historical funnel meaning despite a weak univariate score."""
        # Arrange / Act
        protected = business_protected(
            {"name": "pair_funnel_has_buy_7d", "family": "严格小时漏斗"}
        )
        # Assert
        self.assertTrue(protected)


if __name__ == "__main__":
    unittest.main()
