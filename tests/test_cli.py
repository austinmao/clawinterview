"""Tests for the ClawInterview CLI (T043).

Covers: cmd_validate, cmd_compile, cmd_run, and main() dispatch.
All tests use tmp_path and inline YAML fixtures — no network or gateway calls.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from clawinterview.cli import cmd_compile, cmd_validate, main


# ---------------------------------------------------------------------------
# Shared YAML fixtures
# ---------------------------------------------------------------------------

VALID_CONTRACT_YAML = {
    "version": "1.0",
    "required_inputs": [
        {
            "id": "campaign_topic",
            "type": "string",
            "description": "Working topic for the campaign",
            "facets": ["topic"],
            "resolution_strategies": ["user_args", "ask"],
            "confidence_threshold": 0.8,
        }
    ],
    "optional_inputs": [],
    "produces_outputs": [
        {
            "id": "brief_out",
            "type": "object",
            "facets": ["brief"],
        }
    ],
    "completion_rules": {"require": "campaign_topic"},
}

# A contract nested under contracts.interview (as produced by valid_contract.yaml)
VALID_NESTED_CONTRACT_YAML = {
    "contracts": {
        "interview": VALID_CONTRACT_YAML,
    }
}

# An invalid contract — missing required_inputs field entirely.
INVALID_CONTRACT_YAML = {
    "version": "1.0",
    # missing required_inputs
    "optional_inputs": [
        {
            "id": "bad-id",  # hyphen violates snake_case pattern
            "type": "not_a_type",  # invalid PrimitiveType
            "description": "broken",
        }
    ],
    "produces_outputs": [],
    "completion_rules": None,
}

INVALID_NESTED_CONTRACT_YAML = {
    "contracts": {
        "interview": INVALID_CONTRACT_YAML,
    }
}


def _write_yaml(path: Path, data: object) -> Path:
    """Serialize *data* to YAML at *path* and return the path."""
    path.write_text(yaml.dump(data))
    return path


def _make_pipeline_yaml(contract_path_str: str) -> dict:
    """Return a minimal pipeline YAML dict referencing *contract_path_str*."""
    return {
        "pipeline": {
            "name": "test-pipeline",
            "version": "1.0",
        },
        "participating_targets": [
            {
                "id": "webinar_target",
                "name": "Webinar Target",
                "contract_path": contract_path_str,
                "required": True,
            }
        ],
    }


# ---------------------------------------------------------------------------
# 1. cmd_validate — valid contract → returns 0
# ---------------------------------------------------------------------------


class TestCmdValidate:
    def test_valid_contract_returns_zero(self, tmp_path: Path) -> None:
        contract_file = _write_yaml(
            tmp_path / "valid.yaml", VALID_CONTRACT_YAML
        )
        result = cmd_validate(contract_file)
        assert result == 0

    def test_valid_nested_contract_returns_zero(self, tmp_path: Path) -> None:
        """contracts.interview nesting is transparently unwrapped."""
        contract_file = _write_yaml(
            tmp_path / "nested_valid.yaml", VALID_NESTED_CONTRACT_YAML
        )
        result = cmd_validate(contract_file)
        assert result == 0

    def test_invalid_contract_returns_one(self, tmp_path: Path) -> None:
        contract_file = _write_yaml(
            tmp_path / "invalid.yaml", INVALID_CONTRACT_YAML
        )
        result = cmd_validate(contract_file)
        assert result == 1

    def test_invalid_nested_contract_returns_one(self, tmp_path: Path) -> None:
        contract_file = _write_yaml(
            tmp_path / "nested_invalid.yaml", INVALID_NESTED_CONTRACT_YAML
        )
        result = cmd_validate(contract_file)
        assert result == 1

    def test_missing_file_returns_one(self, tmp_path: Path) -> None:
        missing = tmp_path / "does_not_exist.yaml"
        result = cmd_validate(missing)
        assert result == 1

    def test_invalid_yaml_syntax_returns_one(self, tmp_path: Path) -> None:
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("key: [unclosed bracket\nnested: {broken")
        result = cmd_validate(bad_yaml)
        assert result == 1


# ---------------------------------------------------------------------------
# 2. cmd_compile — pipeline with valid contract → returns 0
# ---------------------------------------------------------------------------


class TestCmdCompile:
    def test_compile_with_valid_pipeline_returns_zero(
        self, tmp_path: Path
    ) -> None:
        contract_file = _write_yaml(
            tmp_path / "contract.yaml", VALID_CONTRACT_YAML
        )
        pipeline_file = _write_yaml(
            tmp_path / "pipeline.yaml",
            _make_pipeline_yaml(contract_file.name),
        )
        result = cmd_compile(pipeline_file)
        assert result == 0

    def test_compile_missing_pipeline_file_returns_one(
        self, tmp_path: Path
    ) -> None:
        missing = tmp_path / "no_pipeline.yaml"
        result = cmd_compile(missing)
        assert result == 1

    def test_compile_pipeline_with_no_valid_targets_returns_one(
        self, tmp_path: Path
    ) -> None:
        # Pipeline references no contract_path entries.
        pipeline_data = {
            "pipeline": {"name": "empty-pipeline"},
            "participating_targets": [],
        }
        pipeline_file = _write_yaml(tmp_path / "empty_pipeline.yaml", pipeline_data)
        result = cmd_compile(pipeline_file)
        assert result == 1

    def test_compile_pipeline_with_nested_contract_returns_zero(
        self, tmp_path: Path
    ) -> None:
        contract_file = _write_yaml(
            tmp_path / "nested_contract.yaml", VALID_NESTED_CONTRACT_YAML
        )
        pipeline_file = _write_yaml(
            tmp_path / "pipeline.yaml",
            _make_pipeline_yaml(contract_file.name),
        )
        result = cmd_compile(pipeline_file)
        assert result == 0


# ---------------------------------------------------------------------------
# 3. main() dispatch — validate sub-command
# ---------------------------------------------------------------------------


class TestMainDispatch:
    def test_main_validate_valid_contract_returns_zero(
        self, tmp_path: Path
    ) -> None:
        contract_file = _write_yaml(
            tmp_path / "contract.yaml", VALID_CONTRACT_YAML
        )
        result = main(["validate", str(contract_file)])
        assert result == 0

    def test_main_validate_invalid_contract_returns_one(
        self, tmp_path: Path
    ) -> None:
        contract_file = _write_yaml(
            tmp_path / "invalid.yaml", INVALID_CONTRACT_YAML
        )
        result = main(["validate", str(contract_file)])
        assert result == 1

    def test_main_no_command_returns_one(self) -> None:
        result = main([])
        assert result == 1

    def test_main_compile_returns_zero(self, tmp_path: Path) -> None:
        contract_file = _write_yaml(
            tmp_path / "contract.yaml", VALID_CONTRACT_YAML
        )
        pipeline_file = _write_yaml(
            tmp_path / "pipeline.yaml",
            _make_pipeline_yaml(contract_file.name),
        )
        result = main(["compile", str(pipeline_file)])
        assert result == 0

    def test_main_compile_missing_file_returns_one(
        self, tmp_path: Path
    ) -> None:
        result = main(["compile", str(tmp_path / "no_such_file.yaml")])
        assert result == 1


# ---------------------------------------------------------------------------
# 4. cmd_run — basic smoke test (bypass mode, no human input required)
# ---------------------------------------------------------------------------


class TestCmdRun:
    """Smoke tests for cmd_run using bypass=True so no interactive input
    is needed.  These verify the engine starts without errors.
    """

    def test_run_bypass_with_valid_pipeline_returns_zero(
        self, tmp_path: Path
    ) -> None:
        from clawinterview.cli import cmd_run

        # Use a contract whose only required input can be resolved via
        # pipeline_state to allow bypass mode to succeed.  We supply an
        # optional-only contract so bypass doesn't fail on unresolved blocking.
        optional_only_contract = {
            "version": "1.0",
            "required_inputs": [],
            "optional_inputs": [
                {
                    "id": "extra_info",
                    "type": "string",
                    "description": "Extra optional info",
                }
            ],
            "produces_outputs": [],
            "completion_rules": None,
        }
        contract_file = _write_yaml(
            tmp_path / "optional_contract.yaml", optional_only_contract
        )
        pipeline_file = _write_yaml(
            tmp_path / "pipeline.yaml",
            _make_pipeline_yaml(contract_file.name),
        )
        result = cmd_run(pipeline_file, bypass=True)
        assert result == 0

    def test_run_bypass_missing_pipeline_returns_one(
        self, tmp_path: Path
    ) -> None:
        from clawinterview.cli import cmd_run

        result = cmd_run(tmp_path / "no_such.yaml", bypass=True)
        assert result == 1

    def test_main_run_bypass_returns_zero(self, tmp_path: Path) -> None:
        optional_only_contract = {
            "version": "1.0",
            "required_inputs": [],
            "optional_inputs": [
                {
                    "id": "hint",
                    "type": "string",
                    "description": "Optional hint",
                }
            ],
            "produces_outputs": [],
            "completion_rules": None,
        }
        contract_file = _write_yaml(
            tmp_path / "opt_contract.yaml", optional_only_contract
        )
        pipeline_file = _write_yaml(
            tmp_path / "pipeline.yaml",
            _make_pipeline_yaml(contract_file.name),
        )
        result = main(["run", str(pipeline_file), "--bypass"])
        assert result == 0
