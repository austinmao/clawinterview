"""Tests for ClawInterview InterviewBriefAssembler (T023).

Covers: empty brief creation, layer update/transition, mark_layer_complete,
is_layer_complete, render_layer_summary, render_execution_brief,
render_markdown, and render_transcript (FR-012).
"""

from __future__ import annotations

import pytest

from clawinterview.brief import InterviewBriefAssembler
from clawinterview.models import (
    BoundedOption,
    InterviewMode,
    InterviewTurn,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def assembler() -> InterviewBriefAssembler:
    return InterviewBriefAssembler(run_id="run-001")


def make_turn(
    turn_number: int = 1,
    layer: str = "context",
    mode: InterviewMode = InterviewMode.LIGHT,
    summary: str = "No inputs resolved yet.",
    question: str = "What is the audience?",
    response: str | None = None,
    recommendation: str | None = None,
    resolved_inputs: list[str] | None = None,
) -> InterviewTurn:
    return InterviewTurn(
        turn_number=turn_number,
        layer=layer,
        mode=mode,
        summary=summary,
        question=question,
        response=response,
        recommendation=recommendation,
        resolved_inputs=resolved_inputs or [],
    )


# ---------------------------------------------------------------------------
# T023-1: Create empty brief — all layers pending
# ---------------------------------------------------------------------------


class TestCreateEmptyBrief:
    def test_brief_has_correct_run_id(self, assembler: InterviewBriefAssembler) -> None:
        assert assembler.brief.run_id == "run-001"

    def test_all_layers_are_pending_on_init(self, assembler: InterviewBriefAssembler) -> None:
        for layer in InterviewBriefAssembler.LAYERS:
            assert assembler.brief.layer_status[layer] == "pending"

    def test_all_layer_data_is_empty_on_init(self, assembler: InterviewBriefAssembler) -> None:
        assert assembler.brief.context_layer == {}
        assert assembler.brief.strategy_layer == {}
        assert assembler.brief.constraints_layer == {}
        assert assembler.brief.execution_brief == {}

    def test_four_layers_exist(self, assembler: InterviewBriefAssembler) -> None:
        assert len(assembler.brief.layer_status) == 4

    def test_layer_names_are_canonical(self, assembler: InterviewBriefAssembler) -> None:
        expected = {"context", "strategy", "constraints", "execution_brief"}
        assert set(assembler.brief.layer_status.keys()) == expected


# ---------------------------------------------------------------------------
# T023-2: Update context layer — status transitions to in_progress
# ---------------------------------------------------------------------------


class TestUpdateLayerTransition:
    def test_pending_transitions_to_in_progress_on_first_update(
        self, assembler: InterviewBriefAssembler
    ) -> None:
        assembler.update_layer("context", {"audience": "founders"})
        assert assembler.brief.layer_status["context"] == "in_progress"

    def test_other_layers_remain_pending_after_single_update(
        self, assembler: InterviewBriefAssembler
    ) -> None:
        assembler.update_layer("context", {"audience": "founders"})
        for layer in ("strategy", "constraints", "execution_brief"):
            assert assembler.brief.layer_status[layer] == "pending"

    def test_update_merges_values_into_context_layer(
        self, assembler: InterviewBriefAssembler
    ) -> None:
        assembler.update_layer("context", {"audience": "founders"})
        assembler.update_layer("context", {"topic": "psilocybin therapy"})
        assert assembler.brief.context_layer["audience"] == "founders"
        assert assembler.brief.context_layer["topic"] == "psilocybin therapy"

    def test_update_in_progress_layer_stays_in_progress(
        self, assembler: InterviewBriefAssembler
    ) -> None:
        assembler.update_layer("context", {"audience": "founders"})
        assembler.update_layer("context", {"topic": "wellness"})
        assert assembler.brief.layer_status["context"] == "in_progress"

    def test_update_strategy_layer(self, assembler: InterviewBriefAssembler) -> None:
        assembler.update_layer("strategy", {"positioning": "premium retreat"})
        assert assembler.brief.strategy_layer["positioning"] == "premium retreat"
        assert assembler.brief.layer_status["strategy"] == "in_progress"

    def test_update_constraints_layer(self, assembler: InterviewBriefAssembler) -> None:
        assembler.update_layer("constraints", {"deadline": "2026-04-01"})
        assert assembler.brief.constraints_layer["deadline"] == "2026-04-01"

    def test_update_execution_brief_layer(self, assembler: InterviewBriefAssembler) -> None:
        assembler.update_layer("execution_brief", {"asset_url": "https://example.com"})
        assert assembler.brief.execution_brief["asset_url"] == "https://example.com"

    def test_update_unknown_layer_raises_value_error(
        self, assembler: InterviewBriefAssembler
    ) -> None:
        with pytest.raises(ValueError, match="Unknown layer"):
            assembler.update_layer("nonexistent_layer", {"key": "val"})


# ---------------------------------------------------------------------------
# T023-3: Mark layer complete — status is "complete"
# ---------------------------------------------------------------------------


class TestMarkLayerComplete:
    def test_mark_pending_layer_complete(self, assembler: InterviewBriefAssembler) -> None:
        assembler.mark_layer_complete("context")
        assert assembler.brief.layer_status["context"] == "complete"

    def test_mark_in_progress_layer_complete(
        self, assembler: InterviewBriefAssembler
    ) -> None:
        assembler.update_layer("context", {"audience": "founders"})
        assembler.mark_layer_complete("context")
        assert assembler.brief.layer_status["context"] == "complete"

    def test_other_layers_unaffected_after_mark(
        self, assembler: InterviewBriefAssembler
    ) -> None:
        assembler.mark_layer_complete("context")
        for layer in ("strategy", "constraints", "execution_brief"):
            assert assembler.brief.layer_status[layer] == "pending"

    def test_mark_all_layers_complete(self, assembler: InterviewBriefAssembler) -> None:
        for layer in InterviewBriefAssembler.LAYERS:
            assembler.mark_layer_complete(layer)
        for layer in InterviewBriefAssembler.LAYERS:
            assert assembler.brief.layer_status[layer] == "complete"


# ---------------------------------------------------------------------------
# T023-4: is_layer_complete returns True/False correctly
# ---------------------------------------------------------------------------


class TestIsLayerComplete:
    def test_returns_false_for_pending_layer(self, assembler: InterviewBriefAssembler) -> None:
        assert assembler.is_layer_complete("context") is False

    def test_returns_false_for_in_progress_layer(
        self, assembler: InterviewBriefAssembler
    ) -> None:
        assembler.update_layer("context", {"audience": "founders"})
        assert assembler.is_layer_complete("context") is False

    def test_returns_true_after_mark_complete(
        self, assembler: InterviewBriefAssembler
    ) -> None:
        assembler.mark_layer_complete("context")
        assert assembler.is_layer_complete("context") is True

    def test_returns_false_for_unknown_layer(
        self, assembler: InterviewBriefAssembler
    ) -> None:
        assert assembler.is_layer_complete("bogus_layer") is False

    def test_independent_per_layer(self, assembler: InterviewBriefAssembler) -> None:
        assembler.mark_layer_complete("strategy")
        assert assembler.is_layer_complete("strategy") is True
        assert assembler.is_layer_complete("context") is False


# ---------------------------------------------------------------------------
# T023-5: render_layer_summary — produces readable Markdown
# ---------------------------------------------------------------------------


class TestRenderLayerSummary:
    def test_empty_layer_produces_placeholder(
        self, assembler: InterviewBriefAssembler
    ) -> None:
        summary = assembler.render_layer_summary("context")
        assert "## Context" in summary
        assert "_No inputs resolved yet._" in summary

    def test_layer_heading_uses_title_case(
        self, assembler: InterviewBriefAssembler
    ) -> None:
        summary = assembler.render_layer_summary("execution_brief")
        assert "## Execution Brief" in summary

    def test_populated_layer_renders_key_value_bullets(
        self, assembler: InterviewBriefAssembler
    ) -> None:
        assembler.update_layer("context", {"audience": "founders", "topic": "wellness"})
        summary = assembler.render_layer_summary("context")
        assert "**audience**" in summary
        assert "founders" in summary
        assert "**topic**" in summary
        assert "wellness" in summary

    def test_populated_layer_does_not_contain_placeholder(
        self, assembler: InterviewBriefAssembler
    ) -> None:
        assembler.update_layer("context", {"audience": "founders"})
        summary = assembler.render_layer_summary("context")
        assert "_No inputs resolved yet._" not in summary

    def test_strategy_layer_renders_correctly(
        self, assembler: InterviewBriefAssembler
    ) -> None:
        assembler.update_layer("strategy", {"positioning": "premium"})
        summary = assembler.render_layer_summary("strategy")
        assert "## Strategy" in summary
        assert "positioning" in summary
        assert "premium" in summary


# ---------------------------------------------------------------------------
# T023-6: render_execution_brief — returns dict with all 4 layers
# ---------------------------------------------------------------------------


class TestRenderExecutionBrief:
    def test_returns_dict(self, assembler: InterviewBriefAssembler) -> None:
        result = assembler.render_execution_brief()
        assert isinstance(result, dict)

    def test_has_all_four_keys(self, assembler: InterviewBriefAssembler) -> None:
        result = assembler.render_execution_brief()
        assert set(result.keys()) == {"context", "strategy", "constraints", "execution"}

    def test_empty_layers_return_empty_dicts(
        self, assembler: InterviewBriefAssembler
    ) -> None:
        result = assembler.render_execution_brief()
        for key in ("context", "strategy", "constraints", "execution"):
            assert result[key] == {}

    def test_context_data_populates_context_key(
        self, assembler: InterviewBriefAssembler
    ) -> None:
        assembler.update_layer("context", {"audience": "founders"})
        result = assembler.render_execution_brief()
        assert result["context"]["audience"] == "founders"

    def test_execution_brief_data_populates_execution_key(
        self, assembler: InterviewBriefAssembler
    ) -> None:
        assembler.update_layer("execution_brief", {"asset_url": "https://example.com"})
        result = assembler.render_execution_brief()
        assert result["execution"]["asset_url"] == "https://example.com"

    def test_all_layers_populated(self, assembler: InterviewBriefAssembler) -> None:
        assembler.update_layer("context", {"audience": "founders"})
        assembler.update_layer("strategy", {"positioning": "premium"})
        assembler.update_layer("constraints", {"deadline": "2026-04-01"})
        assembler.update_layer("execution_brief", {"asset": "banner.png"})
        result = assembler.render_execution_brief()
        assert result["context"]["audience"] == "founders"
        assert result["strategy"]["positioning"] == "premium"
        assert result["constraints"]["deadline"] == "2026-04-01"
        assert result["execution"]["asset"] == "banner.png"


# ---------------------------------------------------------------------------
# T023-7: render_markdown — produces full Markdown document
# ---------------------------------------------------------------------------


class TestRenderMarkdown:
    def test_starts_with_h1_heading(self, assembler: InterviewBriefAssembler) -> None:
        md = assembler.render_markdown()
        assert md.startswith("# Interview Brief")

    def test_heading_includes_run_id(self, assembler: InterviewBriefAssembler) -> None:
        md = assembler.render_markdown()
        assert "run-001" in md

    def test_contains_all_layer_headings(self, assembler: InterviewBriefAssembler) -> None:
        md = assembler.render_markdown()
        assert "## Context" in md
        assert "## Strategy" in md
        assert "## Constraints" in md
        assert "## Execution Brief" in md

    def test_populated_layers_appear_in_output(
        self, assembler: InterviewBriefAssembler
    ) -> None:
        assembler.update_layer("context", {"audience": "founders"})
        assembler.update_layer("strategy", {"positioning": "premium"})
        md = assembler.render_markdown()
        assert "founders" in md
        assert "premium" in md

    def test_is_string_output(self, assembler: InterviewBriefAssembler) -> None:
        md = assembler.render_markdown()
        assert isinstance(md, str)

    def test_layer_order_preserved(self, assembler: InterviewBriefAssembler) -> None:
        md = assembler.render_markdown()
        context_pos = md.index("## Context")
        strategy_pos = md.index("## Strategy")
        constraints_pos = md.index("## Constraints")
        execution_pos = md.index("## Execution Brief")
        assert context_pos < strategy_pos < constraints_pos < execution_pos


# ---------------------------------------------------------------------------
# T023-8: render_transcript — formats turns per FR-012
# ---------------------------------------------------------------------------


class TestRenderTranscript:
    def test_no_turns_returns_placeholder(
        self, assembler: InterviewBriefAssembler
    ) -> None:
        result = assembler.render_transcript([])
        assert "_No turns recorded._" in result

    def test_single_turn_contains_turn_number(
        self, assembler: InterviewBriefAssembler
    ) -> None:
        turn = make_turn(turn_number=1, question="Who is the audience?")
        result = assembler.render_transcript([turn])
        assert "## Turn 1" in result

    def test_single_turn_contains_layer(
        self, assembler: InterviewBriefAssembler
    ) -> None:
        turn = make_turn(layer="context")
        result = assembler.render_transcript([turn])
        assert "context" in result

    def test_single_turn_contains_mode(
        self, assembler: InterviewBriefAssembler
    ) -> None:
        turn = make_turn(mode=InterviewMode.DEEP)
        result = assembler.render_transcript([turn])
        assert "deep" in result

    def test_single_turn_contains_question(
        self, assembler: InterviewBriefAssembler
    ) -> None:
        turn = make_turn(question="What is the core offer?")
        result = assembler.render_transcript([turn])
        assert "What is the core offer?" in result

    def test_turn_with_response_shows_response(
        self, assembler: InterviewBriefAssembler
    ) -> None:
        turn = make_turn(response="A 7-day retreat")
        result = assembler.render_transcript([turn])
        assert "A 7-day retreat" in result

    def test_turn_without_response_shows_awaiting(
        self, assembler: InterviewBriefAssembler
    ) -> None:
        turn = make_turn(response=None)
        result = assembler.render_transcript([turn])
        assert "(awaiting)" in result

    def test_turn_without_recommendation_shows_none(
        self, assembler: InterviewBriefAssembler
    ) -> None:
        turn = make_turn(recommendation=None)
        result = assembler.render_transcript([turn])
        assert "**Recommendation**: None" in result

    def test_turn_with_recommendation_shows_text(
        self, assembler: InterviewBriefAssembler
    ) -> None:
        turn = make_turn(recommendation="Try email campaign")
        result = assembler.render_transcript([turn])
        assert "Try email campaign" in result

    def test_multiple_turns_all_present(
        self, assembler: InterviewBriefAssembler
    ) -> None:
        turns = [
            make_turn(turn_number=1, question="Question 1?"),
            make_turn(turn_number=2, question="Question 2?"),
            make_turn(turn_number=3, question="Question 3?"),
        ]
        result = assembler.render_transcript(turns)
        assert "## Turn 1" in result
        assert "## Turn 2" in result
        assert "## Turn 3" in result

    def test_turns_separated_by_horizontal_rule(
        self, assembler: InterviewBriefAssembler
    ) -> None:
        turns = [make_turn(turn_number=1), make_turn(turn_number=2)]
        result = assembler.render_transcript(turns)
        assert "---" in result

    def test_transcript_contains_summary_field(
        self, assembler: InterviewBriefAssembler
    ) -> None:
        turn = make_turn(summary="Resolved so far: audience=founders")
        result = assembler.render_transcript([turn])
        assert "**Summary**" in result
        assert "audience=founders" in result
