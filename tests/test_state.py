"""Tests for ClawInterview YAML state persistence (T028).

Covers save/load round-trips for InterviewState, CompiledRunContract,
InputResolution, transcript, brief, and partial-resolution scenarios.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from clawinterview.models import (
    CompiledInput,
    CompiledRunContract,
    InputResolution,
    InterviewBrief,
    InterviewState,
    InterviewStatus,
    InterviewTurn,
    PrimitiveType,
    ResolutionStatus,
    ResolverKind,
    SemanticFacet,
)
from clawinterview.state import (
    load_compiled_contract,
    load_interview_state,
    save_brief,
    save_compiled_contract,
    save_interview_state,
    save_resolution_state,
    save_transcript,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_compiled_input(id: str, original_id: str, owner: str = "target_a") -> CompiledInput:
    return CompiledInput(
        id=id,
        original_id=original_id,
        owner_target=owner,
        type=PrimitiveType.STRING,
        facets=[SemanticFacet.AUDIENCE],
        resolution_strategies=[ResolverKind.USER_ARGS],
        confidence_threshold=0.7,
        blocking=True,
    )


def _make_contract(pipeline_id: str = "pl-001", run_id: str = "run-abc") -> CompiledRunContract:
    return CompiledRunContract(
        pipeline_id=pipeline_id,
        run_id=run_id,
        compiled_at="2026-03-25T10:00:00+00:00",
        participating_targets=["target_a", "target_b"],
        inputs=[
            _make_compiled_input("audience", "audience", "target_a"),
            _make_compiled_input("offer", "offer", "target_b"),
        ],
        outputs=[],
        completion_rules=None,
        conflicts=[],
    )


def _make_state(run_id: str = "run-abc") -> InterviewState:
    return InterviewState(
        run_id=run_id,
        pipeline_id="pl-001",
        status=InterviewStatus.AWAITING_INPUT,
        compiled_contract=_make_contract(run_id=run_id),
        resolutions={},
        turns=[],
        current_layer="context",
        bypass_mode=False,
        started_at="2026-03-25T10:00:00+00:00",
        updated_at="2026-03-25T10:05:00+00:00",
    )


# ---------------------------------------------------------------------------
# 1. save_interview_state + load_interview_state round-trip
# ---------------------------------------------------------------------------


class TestInterviewStateRoundTrip:
    def test_round_trip_preserves_run_id(self, tmp_path: Path) -> None:
        state = _make_state(run_id="run-xyz")
        save_interview_state(state, tmp_path)
        loaded = load_interview_state(tmp_path)
        assert loaded is not None
        assert loaded.run_id == "run-xyz"

    def test_round_trip_preserves_pipeline_id(self, tmp_path: Path) -> None:
        state = _make_state()
        state = state.model_copy(update={"pipeline_id": "pl-pipeline-999"})
        save_interview_state(state, tmp_path)
        loaded = load_interview_state(tmp_path)
        assert loaded is not None
        assert loaded.pipeline_id == "pl-pipeline-999"

    def test_round_trip_preserves_status(self, tmp_path: Path) -> None:
        state = _make_state()
        state = state.model_copy(update={"status": InterviewStatus.COMPLETE})
        save_interview_state(state, tmp_path)
        loaded = load_interview_state(tmp_path)
        assert loaded is not None
        assert loaded.status == InterviewStatus.COMPLETE

    def test_round_trip_preserves_bypass_mode(self, tmp_path: Path) -> None:
        state = _make_state()
        state = state.model_copy(update={"bypass_mode": True})
        save_interview_state(state, tmp_path)
        loaded = load_interview_state(tmp_path)
        assert loaded is not None
        assert loaded.bypass_mode is True

    def test_round_trip_preserves_compiled_contract(self, tmp_path: Path) -> None:
        state = _make_state()
        save_interview_state(state, tmp_path)
        loaded = load_interview_state(tmp_path)
        assert loaded is not None
        assert loaded.compiled_contract is not None
        assert loaded.compiled_contract.pipeline_id == "pl-001"
        assert len(loaded.compiled_contract.inputs) == 2

    def test_state_file_written_to_run_dir(self, tmp_path: Path) -> None:
        state = _make_state()
        save_interview_state(state, tmp_path)
        assert (tmp_path / "interview-state.yaml").exists()

    def test_run_dir_created_if_missing(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "nested" / "run"
        state = _make_state()
        save_interview_state(state, run_dir)
        assert (run_dir / "interview-state.yaml").exists()


# ---------------------------------------------------------------------------
# 2. load_interview_state returns None for missing file
# ---------------------------------------------------------------------------


class TestLoadInterviewStateMissing:
    def test_returns_none_when_file_missing(self, tmp_path: Path) -> None:
        result = load_interview_state(tmp_path)
        assert result is None

    def test_returns_none_for_nonexistent_dir(self, tmp_path: Path) -> None:
        result = load_interview_state(tmp_path / "does_not_exist")
        assert result is None


# ---------------------------------------------------------------------------
# 3. save_compiled_contract + load_compiled_contract round-trip
# ---------------------------------------------------------------------------


class TestCompiledContractRoundTrip:
    def test_round_trip_preserves_pipeline_id(self, tmp_path: Path) -> None:
        contract = _make_contract(pipeline_id="pl-cc-001")
        save_compiled_contract(contract, tmp_path)
        loaded = load_compiled_contract(tmp_path)
        assert loaded is not None
        assert loaded.pipeline_id == "pl-cc-001"

    def test_round_trip_preserves_run_id(self, tmp_path: Path) -> None:
        contract = _make_contract(run_id="run-cc-xyz")
        save_compiled_contract(contract, tmp_path)
        loaded = load_compiled_contract(tmp_path)
        assert loaded is not None
        assert loaded.run_id == "run-cc-xyz"

    def test_round_trip_preserves_inputs(self, tmp_path: Path) -> None:
        contract = _make_contract()
        save_compiled_contract(contract, tmp_path)
        loaded = load_compiled_contract(tmp_path)
        assert loaded is not None
        assert len(loaded.inputs) == 2
        ids = {ci.id for ci in loaded.inputs}
        assert ids == {"audience", "offer"}

    def test_round_trip_preserves_participating_targets(self, tmp_path: Path) -> None:
        contract = _make_contract()
        save_compiled_contract(contract, tmp_path)
        loaded = load_compiled_contract(tmp_path)
        assert loaded is not None
        assert loaded.participating_targets == ["target_a", "target_b"]

    def test_compiled_contract_file_exists(self, tmp_path: Path) -> None:
        contract = _make_contract()
        save_compiled_contract(contract, tmp_path)
        assert (tmp_path / "compiled-interview.yaml").exists()

    def test_returns_none_when_file_missing(self, tmp_path: Path) -> None:
        result = load_compiled_contract(tmp_path)
        assert result is None


# ---------------------------------------------------------------------------
# 4. save_resolution_state writes readable YAML
# ---------------------------------------------------------------------------


class TestSaveResolutionState:
    def test_writes_yaml_file(self, tmp_path: Path) -> None:
        resolutions: dict[str, InputResolution] = {
            "audience": InputResolution(
                input_id="audience",
                status=ResolutionStatus.RESOLVED,
                resolver_used=ResolverKind.USER_ARGS,
                confidence=0.9,
                evidence_source="pipeline_args",
                resolved_value="B2C marketers",
                resolved_at="2026-03-25T10:00:00+00:00",
            )
        }
        save_resolution_state(resolutions, tmp_path)
        path = tmp_path / "input-resolution-state.yaml"
        assert path.exists()

    def test_yaml_is_parseable(self, tmp_path: Path) -> None:
        resolutions: dict[str, InputResolution] = {
            "offer": InputResolution(
                input_id="offer",
                status=ResolutionStatus.UNRESOLVED,
            )
        }
        save_resolution_state(resolutions, tmp_path)
        path = tmp_path / "input-resolution-state.yaml"
        data = yaml.safe_load(path.read_text())
        assert isinstance(data, dict)

    def test_yaml_contains_input_id_key(self, tmp_path: Path) -> None:
        resolutions: dict[str, InputResolution] = {
            "schedule": InputResolution(
                input_id="schedule",
                status=ResolutionStatus.RESOLVED,
                confidence=1.0,
                evidence_source="operator_response",
                resolved_value="2026-04-01",
                resolved_at="2026-03-25T11:00:00+00:00",
            )
        }
        save_resolution_state(resolutions, tmp_path)
        path = tmp_path / "input-resolution-state.yaml"
        data = yaml.safe_load(path.read_text())
        assert "schedule" in data
        assert data["schedule"]["input_id"] == "schedule"

    def test_yaml_status_is_human_readable_string(self, tmp_path: Path) -> None:
        resolutions: dict[str, InputResolution] = {
            "brand": InputResolution(
                input_id="brand",
                status=ResolutionStatus.RESOLVED,
                confidence=0.85,
                evidence_source="tenant_file",
                resolved_value="Lumina",
                resolved_at="2026-03-25T09:00:00+00:00",
            )
        }
        save_resolution_state(resolutions, tmp_path)
        path = tmp_path / "input-resolution-state.yaml"
        text = path.read_text()
        # The status should appear as a readable string in the YAML
        assert "resolved" in text.lower()


# ---------------------------------------------------------------------------
# 5. save_transcript writes Markdown with turn format
# ---------------------------------------------------------------------------


class TestSaveTranscript:
    def _make_turn(self, number: int, layer: str = "context") -> InterviewTurn:
        return InterviewTurn(
            turn_number=number,
            layer=layer,
            summary="What is the primary audience?",
            recommendation="Choose the most specific segment",
            question="Who is the primary target audience?",
            response="B2C wellness professionals",
            resolved_inputs=["audience"],
            timestamp="2026-03-25T10:00:00+00:00",
        )

    def test_writes_markdown_file(self, tmp_path: Path) -> None:
        turns = [self._make_turn(1)]
        save_transcript(turns, tmp_path)
        path = tmp_path / "interview-transcript.md"
        assert path.exists()

    def test_markdown_contains_turn_heading(self, tmp_path: Path) -> None:
        turns = [self._make_turn(1, "context")]
        save_transcript(turns, tmp_path)
        content = (tmp_path / "interview-transcript.md").read_text()
        assert "## Turn 1" in content
        assert "context" in content

    def test_markdown_contains_question_and_response(self, tmp_path: Path) -> None:
        turns = [self._make_turn(1)]
        save_transcript(turns, tmp_path)
        content = (tmp_path / "interview-transcript.md").read_text()
        assert "Who is the primary target audience?" in content
        assert "B2C wellness professionals" in content

    def test_multiple_turns_all_present(self, tmp_path: Path) -> None:
        turns = [self._make_turn(i) for i in range(1, 4)]
        save_transcript(turns, tmp_path)
        content = (tmp_path / "interview-transcript.md").read_text()
        assert "## Turn 1" in content
        assert "## Turn 2" in content
        assert "## Turn 3" in content

    def test_turn_separator_present(self, tmp_path: Path) -> None:
        turns = [self._make_turn(1), self._make_turn(2)]
        save_transcript(turns, tmp_path)
        content = (tmp_path / "interview-transcript.md").read_text()
        assert "---" in content

    def test_empty_turns_writes_empty_file(self, tmp_path: Path) -> None:
        save_transcript([], tmp_path)
        path = tmp_path / "interview-transcript.md"
        assert path.exists()
        assert path.read_text() == ""


# ---------------------------------------------------------------------------
# 6. save_brief writes Markdown with layer sections
# ---------------------------------------------------------------------------


class TestSaveBrief:
    def _make_brief(self, run_id: str = "run-brief-001") -> InterviewBrief:
        return InterviewBrief(
            run_id=run_id,
            context_layer={"audience": "B2C wellness", "offer": "Spring retreat"},
            strategy_layer={"cta_approach": "urgency"},
            constraints_layer={"budget": "5000"},
            execution_brief={"channel": "email"},
            layer_status={"context": "complete", "strategy": "in_progress"},
        )

    def test_writes_markdown_file(self, tmp_path: Path) -> None:
        brief = self._make_brief()
        save_brief(brief, tmp_path)
        path = tmp_path / "interview-brief.md"
        assert path.exists()

    def test_contains_run_id_in_title(self, tmp_path: Path) -> None:
        brief = self._make_brief(run_id="run-brief-42")
        save_brief(brief, tmp_path)
        content = (tmp_path / "interview-brief.md").read_text()
        assert "run-brief-42" in content

    def test_contains_context_layer_section(self, tmp_path: Path) -> None:
        brief = self._make_brief()
        save_brief(brief, tmp_path)
        content = (tmp_path / "interview-brief.md").read_text()
        assert "Context Layer" in content
        assert "B2C wellness" in content

    def test_contains_strategy_layer_section(self, tmp_path: Path) -> None:
        brief = self._make_brief()
        save_brief(brief, tmp_path)
        content = (tmp_path / "interview-brief.md").read_text()
        assert "Strategy Layer" in content
        assert "urgency" in content

    def test_contains_constraints_layer_section(self, tmp_path: Path) -> None:
        brief = self._make_brief()
        save_brief(brief, tmp_path)
        content = (tmp_path / "interview-brief.md").read_text()
        assert "Constraints Layer" in content

    def test_contains_execution_brief_section(self, tmp_path: Path) -> None:
        brief = self._make_brief()
        save_brief(brief, tmp_path)
        content = (tmp_path / "interview-brief.md").read_text()
        assert "Execution Brief" in content

    def test_empty_layer_shows_empty_marker(self, tmp_path: Path) -> None:
        brief = InterviewBrief(run_id="run-empty-layer")
        save_brief(brief, tmp_path)
        content = (tmp_path / "interview-brief.md").read_text()
        assert "_(empty)_" in content

    def test_layer_status_section_present_when_non_empty(self, tmp_path: Path) -> None:
        brief = self._make_brief()
        save_brief(brief, tmp_path)
        content = (tmp_path / "interview-brief.md").read_text()
        assert "Layer Status" in content
        assert "complete" in content


# ---------------------------------------------------------------------------
# 7. State with 3 of 5 resolved: save, load, verify 3 marked resolved
# ---------------------------------------------------------------------------


class TestPartialResolutionRoundTrip:
    def _make_five_input_contract(self) -> CompiledRunContract:
        inputs = [
            _make_compiled_input(f"input_{i}", f"input_{i}", "target_a")
            for i in range(5)
        ]
        return CompiledRunContract(
            pipeline_id="pl-partial",
            run_id="run-partial",
            compiled_at="2026-03-25T10:00:00+00:00",
            participating_targets=["target_a"],
            inputs=inputs,
            outputs=[],
            completion_rules=None,
            conflicts=[],
        )

    def _make_state_with_3_resolved(self) -> InterviewState:
        contract = self._make_five_input_contract()
        resolutions: dict[str, InputResolution] = {}

        # Resolve inputs 0, 1, 2
        for i in range(3):
            resolutions[f"input_{i}"] = InputResolution(
                input_id=f"input_{i}",
                status=ResolutionStatus.RESOLVED,
                resolver_used=ResolverKind.USER_ARGS,
                confidence=0.9,
                evidence_source="pipeline_args",
                resolved_value=f"value_{i}",
                resolved_at="2026-03-25T10:00:00+00:00",
            )

        # Leave inputs 3, 4 unresolved
        for i in range(3, 5):
            resolutions[f"input_{i}"] = InputResolution(
                input_id=f"input_{i}",
                status=ResolutionStatus.UNRESOLVED,
            )

        return InterviewState(
            run_id="run-partial",
            pipeline_id="pl-partial",
            status=InterviewStatus.AWAITING_INPUT,
            compiled_contract=contract,
            resolutions=resolutions,
            turns=[],
            current_layer="context",
            bypass_mode=False,
            started_at="2026-03-25T10:00:00+00:00",
            updated_at="2026-03-25T10:05:00+00:00",
        )

    def test_three_of_five_resolved_after_round_trip(self, tmp_path: Path) -> None:
        state = self._make_state_with_3_resolved()
        save_interview_state(state, tmp_path)
        loaded = load_interview_state(tmp_path)
        assert loaded is not None

        resolved_count = sum(
            1
            for res in loaded.resolutions.values()
            if res.status == ResolutionStatus.RESOLVED
        )
        assert resolved_count == 3

    def test_correct_inputs_marked_resolved(self, tmp_path: Path) -> None:
        state = self._make_state_with_3_resolved()
        save_interview_state(state, tmp_path)
        loaded = load_interview_state(tmp_path)
        assert loaded is not None

        for i in range(3):
            assert loaded.resolutions[f"input_{i}"].status == ResolutionStatus.RESOLVED

    def test_remaining_inputs_marked_unresolved(self, tmp_path: Path) -> None:
        state = self._make_state_with_3_resolved()
        save_interview_state(state, tmp_path)
        loaded = load_interview_state(tmp_path)
        assert loaded is not None

        for i in range(3, 5):
            assert loaded.resolutions[f"input_{i}"].status == ResolutionStatus.UNRESOLVED

    def test_provenance_preserved_on_resolved_inputs(self, tmp_path: Path) -> None:
        state = self._make_state_with_3_resolved()
        save_interview_state(state, tmp_path)
        loaded = load_interview_state(tmp_path)
        assert loaded is not None

        for i in range(3):
            res = loaded.resolutions[f"input_{i}"]
            assert res.resolver_used == ResolverKind.USER_ARGS
            assert res.evidence_source == "pipeline_args"
            assert res.confidence == pytest.approx(0.9)
            assert res.resolved_value == f"value_{i}"
