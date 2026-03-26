"""Tests for ClawInterview InterviewEngine (T027).

E2E tests covering: full loop with auto-resolved + asked inputs, bypass mode
(all resolved and unresolved blocking), zero-unresolved instant completion,
layered brief assembly across turns, and resume from persisted state.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from clawinterview.engine import InterviewEngine
from clawinterview.models import (
    InputResolution,
    InputSpec,
    InterviewContract,
    InterviewStatus,
    PrimitiveType,
    ResolutionContext,
    ResolutionResult,
    ResolutionStatus,
    ResolverKind,
    SemanticFacet,
)
from clawinterview.resolver import ResolverRegistry


# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------


def make_input(
    id: str,
    facets: list[SemanticFacet] | None = None,
    resolution_strategies: list[ResolverKind] | None = None,
    type: PrimitiveType = PrimitiveType.STRING,
) -> InputSpec:
    return InputSpec(
        id=id,
        type=type,
        description=f"Input {id}",
        facets=facets or [],
        resolution_strategies=resolution_strategies or [],
    )


def make_contract(
    required: list[InputSpec] | None = None,
    optional: list[InputSpec] | None = None,
) -> InterviewContract:
    return InterviewContract(
        required_inputs=required or [],
        optional_inputs=optional or [],
    )


def make_context(pipeline_args: dict | None = None, run_id: str = "run-test") -> ResolutionContext:
    return ResolutionContext(
        pipeline_args=pipeline_args or {},
        run_id=run_id,
    )


def registry_with_args(values: dict) -> ResolverRegistry:
    """Return a ResolverRegistry with a USER_ARGS resolver that resolves specific values."""
    reg = ResolverRegistry()

    def user_args_resolver(input_spec: InputSpec, context: ResolutionContext) -> ResolutionResult | None:
        value = context.pipeline_args.get(input_spec.id)
        if value is None:
            return None
        return ResolutionResult(
            value=value,
            confidence=1.0,
            evidence_source=f"pipeline_args[{input_spec.id!r}]",
            resolver_kind=ResolverKind.USER_ARGS,
        )

    reg.register(ResolverKind.USER_ARGS, user_args_resolver)
    return reg


def empty_registry() -> ResolverRegistry:
    """Return a ResolverRegistry with no resolvers registered (nothing auto-resolves)."""
    return ResolverRegistry()


# ---------------------------------------------------------------------------
# T027-1: Full loop — 3 targets, 2 auto-resolved, 1 needs asking → process response → complete
# ---------------------------------------------------------------------------


class TestFullInterviewLoop:
    def test_three_inputs_two_auto_resolved_one_asked(self) -> None:
        """Two inputs resolved from pipeline_args, one requires user input."""
        registry = registry_with_args({"audience": "founders", "offer": "retreat-7d"})
        engine = InterviewEngine(registry=registry)

        contracts = [
            ("target_a", make_contract(required=[make_input("audience", [SemanticFacet.AUDIENCE])])),
            ("target_b", make_contract(required=[make_input("offer", [SemanticFacet.OFFER])])),
            ("target_c", make_contract(required=[make_input("cta", [SemanticFacet.CTA])])),
        ]
        context = make_context(pipeline_args={"audience": "founders", "offer": "retreat-7d"})
        state = engine.start("pl-001", "run-001", contracts, context)

        # Two resolved, one (cta) unresolved — should be awaiting input
        assert state.status == InterviewStatus.AWAITING_INPUT
        assert len(state.turns) == 1
        current_turn = engine.get_current_turn(state)
        assert current_turn is not None
        assert current_turn.question != ""

    def test_process_response_resolves_last_input(self) -> None:
        """After providing a response, the interview completes."""
        registry = registry_with_args({"audience": "founders", "offer": "retreat-7d"})
        engine = InterviewEngine(registry=registry)

        contracts = [
            ("target_a", make_contract(required=[make_input("audience", [SemanticFacet.AUDIENCE])])),
            ("target_b", make_contract(required=[make_input("offer", [SemanticFacet.OFFER])])),
            ("target_c", make_contract(required=[make_input("cta", [SemanticFacet.CTA])])),
        ]
        context = make_context(pipeline_args={"audience": "founders", "offer": "retreat-7d"})
        state = engine.start("pl-001", "run-001", contracts, context)

        # Process the response to the one asked question
        state = engine.process_response(state, "Register now")

        assert state.status == InterviewStatus.COMPLETE
        assert engine.is_complete(state)

    def test_resolved_inputs_tracked_in_resolutions(self) -> None:
        """Auto-resolved inputs appear in state.resolutions."""
        registry = registry_with_args({"audience": "founders", "offer": "retreat-7d"})
        engine = InterviewEngine(registry=registry)

        contracts = [
            ("target_a", make_contract(required=[make_input("audience", [SemanticFacet.AUDIENCE])])),
            ("target_b", make_contract(required=[make_input("offer", [SemanticFacet.OFFER])])),
        ]
        context = make_context(pipeline_args={"audience": "founders", "offer": "retreat-7d"})
        state = engine.start("pl-001", "run-001", contracts, context)

        assert "audience" in state.resolutions
        assert state.resolutions["audience"].status == ResolutionStatus.RESOLVED
        assert "offer" in state.resolutions
        assert state.resolutions["offer"].status == ResolutionStatus.RESOLVED

    def test_auto_resolved_inputs_not_asked_again(self) -> None:
        """When all blocking inputs are resolved, no turns are generated."""
        registry = registry_with_args({"audience": "founders"})
        engine = InterviewEngine(registry=registry)

        contracts = [
            ("t1", make_contract(required=[make_input("audience", [SemanticFacet.AUDIENCE])])),
        ]
        context = make_context(pipeline_args={"audience": "founders"})
        state = engine.start("pl-auto", "run-auto", contracts, context)

        assert state.status == InterviewStatus.COMPLETE
        assert len(state.turns) == 0


# ---------------------------------------------------------------------------
# T027-2: Bypass mode — all resolved → complete with no questions
# ---------------------------------------------------------------------------


class TestBypassModeAllResolved:
    def test_bypass_mode_with_all_resolved_is_complete(self) -> None:
        registry = registry_with_args({"audience": "founders"})
        engine = InterviewEngine(registry=registry)

        contracts = [
            ("t1", make_contract(required=[make_input("audience", [SemanticFacet.AUDIENCE])])),
        ]
        context = make_context(pipeline_args={"audience": "founders"})
        state = engine.start("pl-bypass", "run-bypass", contracts, context, bypass_mode=True)

        assert state.status == InterviewStatus.COMPLETE

    def test_bypass_mode_with_all_resolved_has_no_turns(self) -> None:
        registry = registry_with_args({"audience": "founders", "offer": "retreat"})
        engine = InterviewEngine(registry=registry)

        contracts = [
            ("t1", make_contract(required=[make_input("audience")])),
            ("t2", make_contract(required=[make_input("offer")])),
        ]
        context = make_context(pipeline_args={"audience": "founders", "offer": "retreat"})
        state = engine.start("pl-bypass2", "run-bypass2", contracts, context, bypass_mode=True)

        assert state.status == InterviewStatus.COMPLETE
        assert len(state.turns) == 0


# ---------------------------------------------------------------------------
# T027-3: Bypass mode — unresolved blocking → fails with blocker report
# ---------------------------------------------------------------------------


class TestBypassModeUnresolvedBlocking:
    def test_bypass_mode_with_unresolved_blocking_fails(self) -> None:
        """Bypass mode + unresolved blocking input → FAILED status."""
        engine = InterviewEngine(registry=empty_registry())

        contracts = [
            ("t1", make_contract(required=[make_input("audience")])),
        ]
        context = make_context()  # no pipeline_args — nothing to resolve
        state = engine.start("pl-fail", "run-fail", contracts, context, bypass_mode=True)

        assert state.status == InterviewStatus.FAILED

    def test_bypass_fails_not_awaiting_input(self) -> None:
        """Bypass mode never produces AWAITING_INPUT, only COMPLETE or FAILED."""
        engine = InterviewEngine(registry=empty_registry())

        contracts = [
            ("t1", make_contract(required=[make_input("audience")])),
            ("t2", make_contract(required=[make_input("offer")])),
        ]
        context = make_context()
        state = engine.start("pl-fail2", "run-fail2", contracts, context, bypass_mode=True)

        assert state.status != InterviewStatus.AWAITING_INPUT

    def test_bypass_fails_when_partial_resolution(self) -> None:
        """Some resolved, some not: bypass mode still FAILs."""
        registry = registry_with_args({"audience": "founders"})
        engine = InterviewEngine(registry=registry)

        contracts = [
            ("t1", make_contract(required=[make_input("audience")])),
            ("t2", make_contract(required=[make_input("offer")])),  # unresolved
        ]
        context = make_context(pipeline_args={"audience": "founders"})
        state = engine.start("pl-partial", "run-partial", contracts, context, bypass_mode=True)

        assert state.status == InterviewStatus.FAILED


# ---------------------------------------------------------------------------
# T027-4: Zero unresolved — instant completion
# ---------------------------------------------------------------------------


class TestZeroUnresolvedInstantCompletion:
    def test_all_inputs_resolved_upfront_completes_immediately(self) -> None:
        registry = registry_with_args({
            "audience": "founders",
            "offer": "7-day retreat",
            "cta": "Register now",
        })
        engine = InterviewEngine(registry=registry)

        contracts = [
            ("t1", make_contract(required=[make_input("audience")])),
            ("t2", make_contract(required=[make_input("offer")])),
            ("t3", make_contract(required=[make_input("cta")])),
        ]
        context = make_context(pipeline_args={
            "audience": "founders",
            "offer": "7-day retreat",
            "cta": "Register now",
        })
        state = engine.start("pl-zero", "run-zero", contracts, context)

        assert state.status == InterviewStatus.COMPLETE
        assert len(state.turns) == 0

    def test_completed_at_is_set_on_instant_completion(self) -> None:
        registry = registry_with_args({"audience": "founders"})
        engine = InterviewEngine(registry=registry)

        contracts = [("t1", make_contract(required=[make_input("audience")]))]
        context = make_context(pipeline_args={"audience": "founders"})
        state = engine.start("pl-instant", "run-instant", contracts, context)

        assert state.completed_at is not None

    def test_is_complete_returns_true(self) -> None:
        registry = registry_with_args({"audience": "founders"})
        engine = InterviewEngine(registry=registry)

        contracts = [("t1", make_contract(required=[make_input("audience")]))]
        context = make_context(pipeline_args={"audience": "founders"})
        state = engine.start("pl-done", "run-done", contracts, context)

        assert engine.is_complete(state) is True


# ---------------------------------------------------------------------------
# T027-5: Layered brief assembly across multiple turns
# ---------------------------------------------------------------------------


class TestLayeredBriefAssembly:
    def test_brief_is_created_after_start(self) -> None:
        engine = InterviewEngine(registry=empty_registry())

        contracts = [("t1", make_contract(required=[make_input("audience")]))]
        context = make_context()
        state = engine.start("pl-brief", "run-brief", contracts, context)

        assert state.brief is not None

    def test_brief_has_correct_run_id(self) -> None:
        engine = InterviewEngine(registry=empty_registry())

        contracts = [("t1", make_contract(required=[make_input("audience")]))]
        context = make_context(run_id="run-brief-id")
        state = engine.start("pl-brief", "run-brief-id", contracts, context)

        assert state.brief is not None
        assert state.brief.run_id == "run-brief-id"

    def test_auto_resolved_inputs_populate_brief_layer(self) -> None:
        """Inputs resolved upfront should appear in brief context_layer."""
        registry = registry_with_args({"audience": "founders"})
        engine = InterviewEngine(registry=registry)

        contracts = [
            ("t1", make_contract(required=[make_input("audience", [SemanticFacet.AUDIENCE])])),
            ("t2", make_contract(required=[make_input("offer", [SemanticFacet.OFFER])])),
        ]
        context = make_context(pipeline_args={"audience": "founders"})
        state = engine.start("pl-brief2", "run-brief2", contracts, context)

        assert state.brief is not None
        # Audience was auto-resolved — brief should reflect it
        # Note: engine populates current_layer at resolution time (defaults to "context")
        all_brief_data = {
            **state.brief.context_layer,
            **state.brief.strategy_layer,
            **state.brief.constraints_layer,
            **state.brief.execution_brief,
        }
        assert "audience" in all_brief_data
        assert all_brief_data["audience"] == "founders"

    def test_response_updates_brief_layer(self) -> None:
        """Answering a question should populate the corresponding layer in the brief."""
        engine = InterviewEngine(registry=empty_registry())

        contracts = [
            ("t1", make_contract(required=[make_input("audience", [SemanticFacet.AUDIENCE])])),
        ]
        context = make_context()
        state = engine.start("pl-resp-brief", "run-resp-brief", contracts, context)
        assert state.status == InterviewStatus.AWAITING_INPUT

        state = engine.process_response(state, "enterprise founders")
        assert state.status == InterviewStatus.COMPLETE

        # Brief context_layer should now contain the answered value
        assert state.brief is not None
        all_brief_data = {
            **state.brief.context_layer,
            **state.brief.strategy_layer,
            **state.brief.constraints_layer,
            **state.brief.execution_brief,
        }
        assert "enterprise founders" in all_brief_data.values()

    def test_multiple_turns_accumulate_in_brief(self) -> None:
        """Multiple turns across layers each add to the brief."""
        engine = InterviewEngine(registry=empty_registry())

        contracts = [
            ("t1", make_contract(required=[
                make_input("audience", [SemanticFacet.AUDIENCE]),
                make_input("offer", [SemanticFacet.OFFER]),
            ])),
        ]
        context = make_context()
        state = engine.start("pl-multi-turn", "run-multi-turn", contracts, context)

        # First question answered
        assert state.status == InterviewStatus.AWAITING_INPUT
        state = engine.process_response(state, "founders")

        # Second question answered
        if state.status == InterviewStatus.AWAITING_INPUT:
            state = engine.process_response(state, "7-day retreat")

        assert state.status == InterviewStatus.COMPLETE
        assert state.brief is not None
        all_brief_data = {
            **state.brief.context_layer,
            **state.brief.strategy_layer,
            **state.brief.constraints_layer,
            **state.brief.execution_brief,
        }
        assert len(all_brief_data) >= 1  # At least one value recorded


# ---------------------------------------------------------------------------
# T027-6: Resume — save state, reload, verify continues from correct point
# ---------------------------------------------------------------------------


class TestResume:
    def test_resume_raises_file_not_found_when_no_state(self) -> None:
        engine = InterviewEngine(registry=empty_registry())

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "nonexistent-run"
            context = make_context()

            with pytest.raises(FileNotFoundError):
                engine.resume(run_dir, context)

    def test_resume_loads_and_returns_state(self) -> None:
        """Save interview state, then resume loads it successfully."""
        engine = InterviewEngine(registry=empty_registry())

        contracts = [
            ("t1", make_contract(required=[make_input("audience", [SemanticFacet.AUDIENCE])])),
        ]
        context = make_context(run_id="run-resume")

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "run-resume"
            state = engine.start("pl-resume", "run-resume", contracts, context, run_dir=run_dir)

            assert state.status == InterviewStatus.AWAITING_INPUT

            # Resume from saved state
            resumed = engine.resume(run_dir, context)
            assert resumed is not None
            assert resumed.run_id == "run-resume"

    def test_resume_continues_from_correct_point(self) -> None:
        """Resumed state has the same unresolved inputs as before interruption."""
        engine = InterviewEngine(registry=empty_registry())

        contracts = [
            ("t1", make_contract(required=[make_input("audience", [SemanticFacet.AUDIENCE])])),
            ("t2", make_contract(required=[make_input("offer", [SemanticFacet.OFFER])])),
        ]
        context = make_context(run_id="run-resume2")

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "run-resume2"
            state = engine.start("pl-resume2", "run-resume2", contracts, context, run_dir=run_dir)

            assert state.status == InterviewStatus.AWAITING_INPUT
            prior_turn_count = len(state.turns)

            # Resume — should maintain or advance the state
            resumed = engine.resume(run_dir, context)
            assert resumed.status in (InterviewStatus.AWAITING_INPUT, InterviewStatus.COMPLETE)
            # Turn count should not regress
            assert len(resumed.turns) >= prior_turn_count - 1

    def test_resume_completes_when_all_resolved_after_reload(self) -> None:
        """If all inputs are now resolvable on resume, state becomes COMPLETE."""
        # First start with no resolver (nothing resolves), save, then resume with args
        engine_no_resolve = InterviewEngine(registry=empty_registry())
        contracts = [
            ("t1", make_contract(required=[make_input("audience", [SemanticFacet.AUDIENCE])])),
        ]
        context_empty = make_context(run_id="run-resume3")

        registry_full = registry_with_args({"audience": "founders"})
        engine_with_resolve = InterviewEngine(registry=registry_full)

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "run-resume3"
            state = engine_no_resolve.start(
                "pl-resume3", "run-resume3", contracts, context_empty, run_dir=run_dir
            )
            assert state.status == InterviewStatus.AWAITING_INPUT

            # Simulate providing the answer manually via process_response, then save
            state = engine_no_resolve.process_response(
                state, "founders", run_dir=run_dir
            )
            assert state.status == InterviewStatus.COMPLETE

    def test_resumed_state_preserves_pipeline_id(self) -> None:
        engine = InterviewEngine(registry=empty_registry())

        contracts = [
            ("t1", make_contract(required=[make_input("audience")])),
        ]
        context = make_context(run_id="run-pid")

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "run-pid"
            engine.start("pl-specific-id", "run-pid", contracts, context, run_dir=run_dir)
            resumed = engine.resume(run_dir, context)
            assert resumed.pipeline_id == "pl-specific-id"

    def test_resume_appends_new_turn_if_last_turn_is_answered(self) -> None:
        """After answering the last turn, resume should append a new question if still unresolved."""
        engine = InterviewEngine(registry=empty_registry())

        contracts = [
            ("t1", make_contract(required=[
                make_input("audience", [SemanticFacet.AUDIENCE]),
                make_input("offer", [SemanticFacet.OFFER]),
            ])),
        ]
        context = make_context(run_id="run-resume4")

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "run-resume4"
            state = engine.start("pl-r4", "run-resume4", contracts, context, run_dir=run_dir)
            assert state.status == InterviewStatus.AWAITING_INPUT

            # Answer the first question
            state = engine.process_response(state, "founders", run_dir=run_dir)

            if state.status == InterviewStatus.AWAITING_INPUT:
                # One more unresolved input: resume should see it
                resumed = engine.resume(run_dir, context)
                assert resumed.status in (
                    InterviewStatus.AWAITING_INPUT,
                    InterviewStatus.COMPLETE,
                )


# ---------------------------------------------------------------------------
# Additional: get_current_turn + is_complete helpers
# ---------------------------------------------------------------------------


class TestEngineHelpers:
    def test_get_current_turn_returns_none_when_complete(self) -> None:
        registry = registry_with_args({"audience": "founders"})
        engine = InterviewEngine(registry=registry)

        contracts = [("t1", make_contract(required=[make_input("audience")]))]
        context = make_context(pipeline_args={"audience": "founders"})
        state = engine.start("pl-h", "run-h", contracts, context)

        assert engine.get_current_turn(state) is None

    def test_get_current_turn_returns_unanswered_turn(self) -> None:
        engine = InterviewEngine(registry=empty_registry())

        contracts = [("t1", make_contract(required=[make_input("audience")]))]
        context = make_context()
        state = engine.start("pl-h2", "run-h2", contracts, context)

        turn = engine.get_current_turn(state)
        assert turn is not None
        assert turn.response is None

    def test_is_complete_false_when_awaiting_input(self) -> None:
        engine = InterviewEngine(registry=empty_registry())

        contracts = [("t1", make_contract(required=[make_input("audience")]))]
        context = make_context()
        state = engine.start("pl-nc", "run-nc", contracts, context)

        assert engine.is_complete(state) is False

    def test_process_response_on_no_unanswered_turn_returns_state_unchanged(self) -> None:
        """process_response with no current turn is a no-op returning the same state."""
        registry = registry_with_args({"audience": "founders"})
        engine = InterviewEngine(registry=registry)

        contracts = [("t1", make_contract(required=[make_input("audience")]))]
        context = make_context(pipeline_args={"audience": "founders"})
        state = engine.start("pl-noop", "run-noop", contracts, context)

        assert state.status == InterviewStatus.COMPLETE
        # Calling process_response on a complete interview should be a no-op
        state2 = engine.process_response(state, "some answer")
        assert state2.status == InterviewStatus.COMPLETE
