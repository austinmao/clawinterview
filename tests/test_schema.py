"""Tests for ClawInterview schema validation.

Covers validate_contract_schema() and validate_interview_contract() against
the inline JSON Schema defined in clawinterview.schema.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from clawinterview.schema import validate_contract_schema, validate_interview_contract


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_interview_block(fixtures_dir: Path, filename: str) -> dict:
    """Load ``contracts.interview`` block from a fixture YAML file."""
    path = fixtures_dir / filename
    with path.open() as fh:
        data = yaml.safe_load(fh)
    return data["contracts"]["interview"]


# ---------------------------------------------------------------------------
# Test 1: Valid contract passes
# ---------------------------------------------------------------------------


def test_valid_contract_passes(fixtures_dir: Path) -> None:
    """A well-formed contract loaded from valid_contract.yaml must pass validation."""
    contract = _load_interview_block(fixtures_dir, "valid_contract.yaml")

    result = validate_contract_schema(contract)

    assert result.is_valid is True
    assert result.errors == []


# ---------------------------------------------------------------------------
# Test 2: Invalid contract fails
# ---------------------------------------------------------------------------


def test_invalid_contract_fails(fixtures_dir: Path) -> None:
    """A contract with known errors loaded from invalid_contract.yaml must fail."""
    contract = _load_interview_block(fixtures_dir, "invalid_contract.yaml")

    result = validate_contract_schema(contract)

    assert result.is_valid is False
    assert len(result.errors) > 0


# ---------------------------------------------------------------------------
# Test 3: Missing required fields
# ---------------------------------------------------------------------------


def test_missing_required_inputs_reported(fixtures_dir: Path) -> None:
    """A contract dict without required_inputs must produce an error mentioning it."""
    # Build a minimally valid contract then strip the required field.
    contract = _load_interview_block(fixtures_dir, "valid_contract.yaml")
    del contract["required_inputs"]

    result = validate_contract_schema(contract)

    assert result.is_valid is False
    all_messages = " ".join(e["message"] for e in result.errors)
    assert "required_inputs" in all_messages


# ---------------------------------------------------------------------------
# Test 4: Invalid primitive type on an input
# ---------------------------------------------------------------------------


def test_invalid_primitive_type_reported(fixtures_dir: Path) -> None:
    """An input with type 'not_a_type' must produce a schema error."""
    contract = _load_interview_block(fixtures_dir, "valid_contract.yaml")
    # Inject a bad type into the first required input.
    contract["required_inputs"][0]["type"] = "not_a_type"

    result = validate_contract_schema(contract)

    assert result.is_valid is False
    all_messages = " ".join(e["message"] for e in result.errors)
    # jsonschema reports the invalid value in the error message.
    assert "not_a_type" in all_messages


# ---------------------------------------------------------------------------
# Test 5: Invalid resolver kind
# ---------------------------------------------------------------------------


def test_invalid_resolver_kind_reported(fixtures_dir: Path) -> None:
    """A resolution_strategies list containing an unknown resolver must fail."""
    contract = _load_interview_block(fixtures_dir, "valid_contract.yaml")
    contract["resolution_strategies"] = ["invalid_resolver"]

    result = validate_contract_schema(contract)

    assert result.is_valid is False
    all_messages = " ".join(e["message"] for e in result.errors)
    assert "invalid_resolver" in all_messages


# ---------------------------------------------------------------------------
# Test 6: Nested completion rules validate
# ---------------------------------------------------------------------------


def test_nested_completion_rules_valid(fixtures_dir: Path) -> None:
    """A contract with nested all_of → any_of → require structure must pass."""
    contract = _load_interview_block(fixtures_dir, "valid_contract.yaml")
    # Replace completion_rules with a deeply nested valid structure.
    contract["completion_rules"] = {
        "all_of": [
            {"require": "webinar_topic"},
            {
                "any_of": [
                    {"require": "target_audience"},
                    {"require": "webinar_topic"},
                ]
            },
        ]
    }

    result = validate_contract_schema(contract)

    assert result.is_valid is True
    assert result.errors == []


# ---------------------------------------------------------------------------
# Test 7: Empty contract fails with multiple errors
# ---------------------------------------------------------------------------


def test_empty_contract_fails_with_multiple_errors() -> None:
    """An empty dict must fail with errors for every missing required field."""
    required_fields = {
        "version",
        "required_inputs",
        "optional_inputs",
        "produces_outputs",
        "completion_rules",
    }

    result = validate_contract_schema({})

    assert result.is_valid is False
    # Each missing required field should surface at least one error.
    all_messages = " ".join(e["message"] for e in result.errors)
    for field in required_fields:
        assert field in all_messages, (
            f"Expected error mentioning '{field}' but got: {all_messages}"
        )


# ---------------------------------------------------------------------------
# Test 8: validate_interview_contract wrapper
# ---------------------------------------------------------------------------


def test_validate_interview_contract_delegates_on_valid(fixtures_dir: Path) -> None:
    """validate_interview_contract returns is_valid=True for a valid contract."""
    contract = _load_interview_block(fixtures_dir, "valid_contract.yaml")

    result = validate_interview_contract(contract)

    assert result.is_valid is True
    assert result.errors == []


def test_validate_interview_contract_delegates_on_invalid(fixtures_dir: Path) -> None:
    """validate_interview_contract returns is_valid=False for an invalid contract."""
    contract = _load_interview_block(fixtures_dir, "invalid_contract.yaml")

    result = validate_interview_contract(contract)

    assert result.is_valid is False
    assert len(result.errors) > 0


def test_validate_interview_contract_matches_schema_validation(
    fixtures_dir: Path,
) -> None:
    """validate_interview_contract and validate_contract_schema agree on validity."""
    for filename in ("valid_contract.yaml", "invalid_contract.yaml"):
        contract = _load_interview_block(fixtures_dir, filename)
        schema_result = validate_contract_schema(contract)
        wrapper_result = validate_interview_contract(contract)

        assert schema_result.is_valid == wrapper_result.is_valid, (
            f"Mismatch for {filename}: schema={schema_result.is_valid}, "
            f"wrapper={wrapper_result.is_valid}"
        )
