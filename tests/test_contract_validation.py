"""Contract validation tests for ClawInterview (T008).

Covers both structural (schema) validation via validate_contract_schema() and
semantic validation via validate_interview_contract().

All tests follow the TDD naming convention: test_<scenario>_<expected_outcome>.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from clawinterview.schema import validate_contract_schema, validate_interview_contract


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_valid_contract() -> dict:
    """Return the canonical valid contract dict (contracts.interview block)."""
    with (FIXTURES_DIR / "valid_contract.yaml").open() as fh:
        data = yaml.safe_load(fh)
    return data["contracts"]["interview"]


def _minimal_valid_contract() -> dict:
    """Return the smallest contract that passes both schema and semantic checks."""
    return {
        "version": "1.0",
        "required_inputs": [
            {
                "id": "topic",
                "type": "string",
                "description": "The topic",
            }
        ],
        "optional_inputs": [],
        "produces_outputs": [
            {
                "id": "brief",
                "type": "object",
            }
        ],
        "completion_rules": {
            "require": "topic",
        },
    }


# ---------------------------------------------------------------------------
# Test 1: Complete valid contract passes
# ---------------------------------------------------------------------------


def test_complete_valid_contract_passes() -> None:
    """The canonical valid_contract.yaml must pass both schema and semantic checks."""
    contract = _load_valid_contract()

    result = validate_interview_contract(contract)

    assert result.is_valid is True
    assert result.errors == []


# ---------------------------------------------------------------------------
# Test 2: Missing required_inputs key fails
# ---------------------------------------------------------------------------


def test_missing_required_inputs_fails() -> None:
    """A contract without 'required_inputs' must fail schema validation."""
    contract = _load_valid_contract()
    del contract["required_inputs"]

    result = validate_interview_contract(contract)

    assert result.is_valid is False
    all_messages = " ".join(e["message"] for e in result.errors)
    assert "required_inputs" in all_messages


# ---------------------------------------------------------------------------
# Test 3: Invalid input type fails
# ---------------------------------------------------------------------------


def test_invalid_input_type_fails() -> None:
    """An input with an unknown type value must fail schema validation."""
    contract = _load_valid_contract()
    contract["required_inputs"][0]["type"] = "not_a_valid_type"

    result = validate_interview_contract(contract)

    assert result.is_valid is False
    all_messages = " ".join(e["message"] for e in result.errors)
    assert "not_a_valid_type" in all_messages


# ---------------------------------------------------------------------------
# Test 4: Empty completion_rules validates OK at schema level; Pydantic allows None
# ---------------------------------------------------------------------------


def test_no_completion_rules_passes_schema_validation() -> None:
    """A contract with completion_rules omitted entirely must pass schema validation.

    The JSON Schema marks completion_rules as required, but the Pydantic model
    sets completion_rules: CompletionRule | None = None.  This test exercises
    the schema path: since the schema requires completion_rules, omitting it
    must produce a validation error.
    """
    contract = _load_valid_contract()
    del contract["completion_rules"]

    schema_result = validate_contract_schema(contract)

    # Schema requires completion_rules so this must fail at the schema level.
    assert schema_result.is_valid is False
    all_messages = " ".join(e["message"] for e in schema_result.errors)
    assert "completion_rules" in all_messages


def test_empty_completion_rules_dict_passes_schema() -> None:
    """An empty completion_rules dict {} must pass schema validation (all fields optional)."""
    contract = _load_valid_contract()
    contract["completion_rules"] = {}

    schema_result = validate_contract_schema(contract)

    assert schema_result.is_valid is True
    assert schema_result.errors == []


# ---------------------------------------------------------------------------
# Test 5: Valid nested completion rule with all_of / any_of passes
# ---------------------------------------------------------------------------


def test_nested_all_of_any_of_completion_rule_passes() -> None:
    """A deeply nested all_of → any_of → require structure must pass validation."""
    contract = _load_valid_contract()
    contract["completion_rules"] = {
        "all_of": [
            {"require": "webinar_topic"},
            {
                "any_of": [
                    {"require": "target_audience"},
                    {"require": "cohost"},
                ]
            },
        ]
    }

    result = validate_interview_contract(contract)

    assert result.is_valid is True
    assert result.errors == []


# ---------------------------------------------------------------------------
# Test 6: depends_on referencing non-existent input ID fails semantic check
# ---------------------------------------------------------------------------


def test_depends_on_unknown_input_id_fails_semantic() -> None:
    """An input whose depends_on references a non-existent ID must fail semantics."""
    contract = _minimal_valid_contract()
    # Add a depends_on that points to an ID not declared anywhere.
    contract["required_inputs"][0]["depends_on"] = ["nonexistent_input"]

    result = validate_interview_contract(contract)

    assert result.is_valid is False
    all_messages = " ".join(e["message"] for e in result.errors)
    assert "nonexistent_input" in all_messages
    # Error must appear on the depends_on path.
    all_paths = " ".join(e["path"] for e in result.errors)
    assert "depends_on" in all_paths


# ---------------------------------------------------------------------------
# Test 7: Completion rule require referencing non-existent input fails semantic
# ---------------------------------------------------------------------------


def test_completion_rule_require_unknown_input_fails_semantic() -> None:
    """completion_rules.require referencing an undeclared input ID must fail."""
    contract = _minimal_valid_contract()
    contract["completion_rules"] = {"require": "no_such_input"}

    result = validate_interview_contract(contract)

    assert result.is_valid is False
    all_messages = " ".join(e["message"] for e in result.errors)
    assert "no_such_input" in all_messages


def test_completion_rule_require_in_nested_all_of_unknown_fails() -> None:
    """A require nested inside all_of that references an unknown ID must fail."""
    contract = _minimal_valid_contract()
    contract["completion_rules"] = {
        "all_of": [
            {"require": "topic"},          # valid
            {"require": "ghost_input"},    # invalid
        ]
    }

    result = validate_interview_contract(contract)

    assert result.is_valid is False
    all_messages = " ".join(e["message"] for e in result.errors)
    assert "ghost_input" in all_messages


# ---------------------------------------------------------------------------
# Test 8: Duplicate input IDs across required/optional fails semantic check
# ---------------------------------------------------------------------------


def test_duplicate_input_ids_across_required_and_optional_fails() -> None:
    """The same input ID in both required_inputs and optional_inputs must fail."""
    contract = _minimal_valid_contract()
    contract["optional_inputs"] = [
        {
            "id": "topic",   # duplicate of required_inputs[0].id
            "type": "string",
            "description": "Duplicate topic input",
        }
    ]

    result = validate_interview_contract(contract)

    assert result.is_valid is False
    all_messages = " ".join(e["message"] for e in result.errors)
    assert "topic" in all_messages
    # Must explicitly mention duplicate / duplication.
    assert "uplicate" in all_messages or "Duplicate" in all_messages


def test_duplicate_input_ids_within_same_list_fails() -> None:
    """Two inputs with the same ID inside required_inputs must fail."""
    contract = _minimal_valid_contract()
    contract["required_inputs"].append(
        {
            "id": "topic",   # same as existing required input
            "type": "number",
            "description": "A second topic — duplicate",
        }
    )

    result = validate_interview_contract(contract)

    assert result.is_valid is False
    all_messages = " ".join(e["message"] for e in result.errors)
    assert "topic" in all_messages


# ---------------------------------------------------------------------------
# Test 9: must_produce referencing non-existent output fails semantic check
# ---------------------------------------------------------------------------


def test_completion_rule_must_produce_unknown_output_fails_semantic() -> None:
    """completion_rules.must_produce referencing an undeclared output ID must fail."""
    contract = _minimal_valid_contract()
    contract["completion_rules"] = {"must_produce": "nonexistent_output"}

    result = validate_interview_contract(contract)

    assert result.is_valid is False
    all_messages = " ".join(e["message"] for e in result.errors)
    assert "nonexistent_output" in all_messages


def test_completion_rule_must_produce_valid_output_passes() -> None:
    """completion_rules.must_produce referencing a declared output ID must pass."""
    contract = _minimal_valid_contract()
    contract["completion_rules"] = {"must_produce": "brief"}

    result = validate_interview_contract(contract)

    assert result.is_valid is True
    assert result.errors == []


def test_completion_rule_must_produce_nested_in_any_of_unknown_fails() -> None:
    """A must_produce nested inside any_of referencing an unknown output must fail."""
    contract = _minimal_valid_contract()
    contract["completion_rules"] = {
        "any_of": [
            {"must_produce": "brief"},           # valid
            {"must_produce": "missing_output"},  # invalid
        ]
    }

    result = validate_interview_contract(contract)

    assert result.is_valid is False
    all_messages = " ".join(e["message"] for e in result.errors)
    assert "missing_output" in all_messages
