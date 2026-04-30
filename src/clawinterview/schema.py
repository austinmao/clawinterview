"""ClawInterview JSON Schema loading and validation.

Provides schema-based validation for interview contracts using jsonschema.
The contract schema is embedded inline to guarantee availability regardless
of how the package is installed (wheel, editable, etc.).

Schema version: 1.0
Source of truth: specs/069-clawinterview/contracts/interview-contract-schema.yaml
"""

from __future__ import annotations

from dataclasses import dataclass, field

from jsonschema import ValidationError as JsonSchemaValidationError
from jsonschema import validate
from jsonschema.exceptions import best_match

# ---------------------------------------------------------------------------
# Inline schema — mirrors interview-contract-schema.yaml exactly.
# Kept as a Python dict so no file I/O is required at runtime.
# ---------------------------------------------------------------------------

_INTERVIEW_CONTRACT_SCHEMA: dict = {
    "type": "object",
    "required": [
        "version",
        "required_inputs",
        "optional_inputs",
        "produces_outputs",
        "completion_rules",
    ],
    "properties": {
        "version": {
            "type": "string",
            "pattern": r"^\d+\.\d+$",
            "description": "Schema version (e.g., '1.0')",
        },
        "required_inputs": {
            "type": "array",
            "items": {"$ref": "#/$defs/InputSpec"},
            "description": "Inputs that must be resolved before pipeline can proceed",
        },
        "optional_inputs": {
            "type": "array",
            "items": {"$ref": "#/$defs/InputSpec"},
            "description": "Inputs that enhance but do not block execution",
        },
        "produces_outputs": {
            "type": "array",
            "items": {"$ref": "#/$defs/OutputSpec"},
            "description": "What this target produces for downstream consumption",
        },
        "resolution_strategies": {
            "type": "array",
            "items": {"$ref": "#/$defs/ResolverKind"},
            "description": "Default resolver precedence for all inputs (overridable per input)",
        },
        "completion_rules": {
            "$ref": "#/$defs/CompletionRule",
            "description": "Declarative rules for when interview is complete for this target",
        },
        "semantic_facets": {
            "type": "array",
            "items": {"$ref": "#/$defs/SemanticFacet"},
            "description": "Controlled vocabulary tags for cross-target reasoning",
        },
        "evidence_policy": {
            "type": "object",
            "description": "Requirements for evidence quality (freshness, source trust)",
            "additionalProperties": True,
        },
    },
    "$defs": {
        "InputSpec": {
            "type": "object",
            "required": ["id", "type", "description"],
            "properties": {
                "id": {
                    "type": "string",
                    "pattern": r"^[a-z][a-z0-9_]*$",
                    "description": "Target-local identifier (snake_case)",
                },
                "type": {"$ref": "#/$defs/PrimitiveType"},
                "description": {"type": "string"},
                "facets": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/SemanticFacet"},
                },
                "resolution_strategies": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/ResolverKind"},
                },
                "confidence_threshold": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "default": 0.7,
                },
                "freshness_policy": {
                    "type": "string",
                    "description": "Duration string: 24h, 7d, 30d, any",
                },
                "ask_policy": {
                    "type": "string",
                    "enum": ["always", "only_if_unresolved", "never"],
                    "default": "only_if_unresolved",
                },
                "depends_on": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "default_value": {},
            },
        },
        "OutputSpec": {
            "type": "object",
            "required": ["id", "type"],
            "properties": {
                "id": {
                    "type": "string",
                    "pattern": r"^[a-z][a-z0-9_]*$",
                },
                "type": {"$ref": "#/$defs/PrimitiveType"},
                "facets": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/SemanticFacet"},
                },
            },
        },
        "CompletionRule": {
            "type": "object",
            "description": "Recursive completion rule. Exactly one key should be present.",
            "properties": {
                "all_of": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/CompletionRule"},
                },
                "any_of": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/CompletionRule"},
                },
                "require": {
                    "type": "string",
                    "description": "Named input that must be resolved",
                },
                "min_items": {
                    "type": "integer",
                    "minimum": 1,
                },
                "freshness_required": {"type": "string"},
                "confidence_threshold": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                },
                "must_produce": {
                    "type": "string",
                    "description": "Named output that must be producible",
                },
            },
            "additionalProperties": False,
        },
        "PrimitiveType": {
            "type": "string",
            "enum": [
                "string",
                "number",
                "boolean",
                "date",
                "datetime",
                "money",
                "url",
                "enum",
                "entity_ref",
                "list",
                "object",
            ],
        },
        "ResolverKind": {
            "type": "string",
            "enum": [
                "user_args",
                "user_message",
                "hyperspell_profile",
                "pipeline_state",
                "memory",
                "tenant_file",
                "upstream_output",
                "rag",
                "web",
                "infer",
                "ask",
            ],
        },
        "SemanticFacet": {
            "type": "string",
            "description": (
                "Controlled vocabulary tag. Core set is fixed; "
                "tenant/department extensions allowed."
            ),
        },
    },
}


# ---------------------------------------------------------------------------
# ValidationResult
# ---------------------------------------------------------------------------


@dataclass
class ValidationResult:
    """Result of a contract validation pass.

    Attributes:
        is_valid: True when the contract passed all checks.
        errors:   Ordered list of structured error dicts, each containing
                  ``"path"`` (dot-separated JSON path) and ``"message"``
                  (human-readable description).  Empty when ``is_valid`` is
                  True.
    """

    is_valid: bool
    errors: list[dict[str, str]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_schema() -> dict:
    """Return the interview contract JSON Schema as a plain dict.

    The schema is embedded inline in this module so that it is always
    available regardless of the package installation method (wheel, editable,
    sdist).  No file I/O is performed.
    """
    return _INTERVIEW_CONTRACT_SCHEMA


def _error_path(error: JsonSchemaValidationError) -> str:
    """Convert a jsonschema error's absolute_path deque to a dot-separated string."""
    parts = list(error.absolute_path)
    if not parts:
        return "$"
    return "$.{}".format(".".join(str(p) for p in parts))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_contract_schema(contract_dict: dict) -> ValidationResult:
    """Validate *contract_dict* against the interview contract JSON Schema.

    Runs structural validation only — field types, required keys, enum
    membership, pattern constraints, and numeric bounds.  Semantic checks
    (e.g. referential integrity between ``depends_on`` IDs and declared input
    IDs) are handled by :func:`validate_interview_contract`.

    Args:
        contract_dict: Raw mapping deserialized from a YAML/JSON contract
                       file, or built programmatically.

    Returns:
        A :class:`ValidationResult` whose ``is_valid`` field is ``True`` iff
        no schema violations were found.  On failure, ``errors`` contains one
        entry per violation with ``"path"`` and ``"message"`` keys.
    """
    schema = _load_schema()
    errors: list[dict[str, str]] = []

    try:
        validate(instance=contract_dict, schema=schema)
    except JsonSchemaValidationError:
        # jsonschema raises only on the *first* error when using validate().
        # Re-collect all violations via the validator iterator for richer output.
        from jsonschema import Draft202012Validator

        validator = Draft202012Validator(schema)
        raw_errors = list(validator.iter_errors(contract_dict))

        # Prefer the most-specific sub-error for composite schemas (anyOf/oneOf).
        for raw_error in raw_errors:
            condensed = best_match([raw_error]) or raw_error
            errors.append(
                {
                    "path": _error_path(condensed),
                    "message": condensed.message,
                }
            )

    return ValidationResult(is_valid=len(errors) == 0, errors=errors)


def _collect_completion_rule_refs(
    rule: dict,
    require_refs: list[str],
    must_produce_refs: list[str],
) -> None:
    """Recursively collect all ``require`` and ``must_produce`` values from a rule tree."""
    if not isinstance(rule, dict):
        return
    if "require" in rule and rule["require"] is not None:
        require_refs.append(rule["require"])
    if "must_produce" in rule and rule["must_produce"] is not None:
        must_produce_refs.append(rule["must_produce"])
    for nested in rule.get("all_of") or []:
        _collect_completion_rule_refs(nested, require_refs, must_produce_refs)
    for nested in rule.get("any_of") or []:
        _collect_completion_rule_refs(nested, require_refs, must_produce_refs)


def validate_interview_contract(contract_dict: dict) -> ValidationResult:
    """Validate *contract_dict* with schema checks and semantic checks.

    Runs structural schema validation first, then — if the contract is
    structurally valid — applies semantic checks for referential integrity:

    1. ``depends_on`` IDs on each input must reference a declared input ID
       (from ``required_inputs`` or ``optional_inputs``).
    2. ``completion_rules.require`` fields must reference a declared input ID.
    3. ``completion_rules.must_produce`` fields must reference a declared
       output ID (from ``produces_outputs``).
    4. No duplicate input IDs across ``required_inputs`` and
       ``optional_inputs``.

    Args:
        contract_dict: Raw mapping representing an interview contract.

    Returns:
        A :class:`ValidationResult` combining all schema and semantic errors.
        Semantic errors are only generated when the contract is structurally
        valid (schema errors are returned early without running semantics).
    """
    # --- Phase 1: structural schema validation ---
    result = validate_contract_schema(contract_dict)
    if not result.is_valid:
        # Return early: semantic checks are meaningless on a malformed contract.
        return result

    # --- Phase 2: semantic validation ---
    semantic_errors: list[dict[str, str]] = []

    # Build declared ID sets.
    required_inputs: list[dict] = contract_dict.get("required_inputs") or []
    optional_inputs: list[dict] = contract_dict.get("optional_inputs") or []
    produces_outputs: list[dict] = contract_dict.get("produces_outputs") or []

    required_ids = [inp["id"] for inp in required_inputs if "id" in inp]
    optional_ids = [inp["id"] for inp in optional_inputs if "id" in inp]
    all_input_ids: set[str] = set(required_ids) | set(optional_ids)
    all_output_ids: set[str] = {
        out["id"] for out in produces_outputs if "id" in out
    }

    # Check 1: No duplicate input IDs across required_inputs + optional_inputs.
    combined_ids = required_ids + optional_ids
    seen: set[str] = set()
    for inp_id in combined_ids:
        if inp_id in seen:
            semantic_errors.append(
                {
                    "path": "$",
                    "message": (
                        f"Duplicate input ID '{inp_id}' found across "
                        "required_inputs and optional_inputs."
                    ),
                }
            )
        seen.add(inp_id)

    # Check 2: depends_on references must point to valid input IDs.
    for section_name, inputs in (
        ("required_inputs", required_inputs),
        ("optional_inputs", optional_inputs),
    ):
        for i, inp in enumerate(inputs):
            for dep_id in inp.get("depends_on") or []:
                if dep_id not in all_input_ids:
                    semantic_errors.append(
                        {
                            "path": f"$.{section_name}.{i}.depends_on",
                            "message": (
                                f"depends_on references unknown input ID '{dep_id}'. "
                                "Must be declared in required_inputs or optional_inputs."
                            ),
                        }
                    )

    # Check 3 & 4: completion_rules require/must_produce must reference valid IDs.
    completion_rules = contract_dict.get("completion_rules")
    if completion_rules and isinstance(completion_rules, dict):
        require_refs: list[str] = []
        must_produce_refs: list[str] = []
        _collect_completion_rule_refs(completion_rules, require_refs, must_produce_refs)

        for ref in require_refs:
            if ref not in all_input_ids:
                semantic_errors.append(
                    {
                        "path": "$.completion_rules",
                        "message": (
                            f"completion_rules 'require' references unknown input ID "
                            f"'{ref}'. Must be declared in required_inputs or "
                            "optional_inputs."
                        ),
                    }
                )

        for ref in must_produce_refs:
            if ref not in all_output_ids:
                semantic_errors.append(
                    {
                        "path": "$.completion_rules",
                        "message": (
                            f"completion_rules 'must_produce' references unknown output "
                            f"ID '{ref}'. Must be declared in produces_outputs."
                        ),
                    }
                )

    if semantic_errors:
        return ValidationResult(is_valid=False, errors=semantic_errors)

    return ValidationResult(is_valid=True)
