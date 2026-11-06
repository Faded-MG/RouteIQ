"""Verify constants match docs/ALGORITHM.md §2."""

import json
from pathlib import Path

from apps.common import constants


def test_constants_match_algorithm_doc():
    tests_root = Path(__file__).resolve().parent.parent.parent
    fixture_path = tests_root / "fixtures" / "algorithm_constants.json"
    with open(fixture_path, encoding="utf-8") as f:
        expected = json.load(f)

    for key, expected_val in expected.items():
        assert hasattr(constants, key), f"Constant {key} missing from apps.common.constants"
        actual_val = getattr(constants, key)
        assert actual_val == expected_val, (
            f"Constant {key} mismatch: expected {expected_val!r}, got {actual_val!r}"
        )
