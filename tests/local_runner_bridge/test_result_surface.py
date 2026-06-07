import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from local_runner_bridge.result_surface import (
    REQUIRED_SAFETY_FLAGS,
    build_result_surface,
)


MINIMUM_FIELDS = {
    "result_surface_version",
    "result_id",
    "source_task_reference",
    "source_task_validation_result",
    "operation_mode",
    "status",
    "summary",
    "files_changed",
    "tests_run",
    "safety_flags",
    "blocked_reasons",
    "requires_user_approval",
    "next_recommended_step",
    "created_at",
}


def test_builder_returns_all_minimum_fields():
    surface = build_result_surface(
        result_id="result-test",
        created_at="2026-06-05T00:00:00Z",
    )

    assert set(surface) == MINIMUM_FIELDS


def test_required_safety_flags_default_to_false():
    surface = build_result_surface()

    assert set(surface["safety_flags"]) == set(REQUIRED_SAFETY_FLAGS)
    assert all(value is False for value in surface["safety_flags"].values())


def test_requires_user_approval_defaults_to_true():
    surface = build_result_surface()

    assert surface["requires_user_approval"] is True


def test_deterministic_result_id_and_created_at_can_be_injected():
    surface = build_result_surface(
        result_id="result-deterministic",
        created_at="2026-06-05T00:00:00Z",
    )

    assert surface["result_id"] == "result-deterministic"
    assert surface["created_at"] == "2026-06-05T00:00:00Z"


def test_default_created_at_is_python310_compatible_utc_timestamp():
    surface = build_result_surface()

    assert surface["created_at"].endswith("Z")
    assert "+00:00" not in surface["created_at"]

