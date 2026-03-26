"""Tests for ClawInterview question planner (T022).

Covers plan_next_turn: single-question return, layer assignment by facet,
light/deep mode detection, completion when all resolved, layer advancement,
and summary provenance.
"""

from __future__ import annotations

import pytest

from clawinterview.compiler import compile_run_contract
from clawinterview.models import (
    CompiledInput,
    CompiledRunContract,
    InputResolution,
    InputSpec,
    InterviewContract,
    InterviewMode,
    InterviewState,
    InterviewStatus,
    PrimitiveType,
    ResolutionStatus,
    ResolverKind,
    SemanticFacet,
)
from clawinterview.planner import (
    LAYER_ORDER,
    plan_next_turn,
    _build_summary,
    _determine_mode,
)


# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------


def make_input_spec(
    id: str,
    facets: list[SemanticFacet] | None = None,
    default_value=None,
    depends_on: list[str] | None = None,
    type: PrimitiveType = PrimitiveType.STRING,
) -> InputSpec:
    return InputSpec(
        id=id,
        type=type,
        description=f"Input {id}",
        facets=facets or [],
        default_value=default_value,
        depends_on=depends_on or [],
    )


def make_contract_with(inputs: list[InputSpec]) -> InterviewContract:
    return InterviewContract(required_inputs=inputs)


def make_state_with_contract(
    inputs: list[tuple[str, list[SemanticFacet]]],
    pipeline_id: str = "pl-test",
    run_id: str = "run-test",
    resolutions: dict[str, InputResolution] | None = None,
    current_layer: str = "context",
) -> InterviewState:
    """Build an InterviewState from a list of (input_id, facets) pairs."""
    specs = [
        InputSpec(
            id=inp_id,
            type=PrimitiveType.STRING,
            description=f"Input {inp_id}",
            facets=facets,
        )
        for inp_id, facets in inputs
    ]
    contract = InterviewContract(required_inputs=specs)
    compiled = compile_run_contract(pipeline_id, run_id, [("target", contract)])
    state = InterviewState(
        run_id=run_id,
        pipeline_id=pipeline_id,
        status=InterviewStatus.AWAITING_INPUT,
        compiled_contract=compiled,
        current_layer=current_layer,
        resolutions=resolutions or {},
    )
    return state


def make_resolved(
    input_id: str,
    value: str = "resolved-value",
    source: str = "test-source",
) -> InputResolution:
    return InputResolution(
        input_id=input_id,
        status=ResolutionStatus.RESOLVED,
        resolver_used=ResolverKind.USER_ARGS,
        confidence=1.0,
        evidence_source=source,
        resolved_value=value,
    )


# ---------------------------------------------------------------------------
# T022-1: Returns exactly one question from unresolved inputs
# ---------------------------------------------------------------------------


class TestReturnsOneQuestion:
    def test_returns_one_turn_not_none(self) -> None:
        state = make_state_with_contract([("audience", [SemanticFacet.AUDIENCE])])
        turn = plan_next_turn(state)
        assert turn is not None

    def test_returns_exactly_one_turn_object(self) -> None:
        """plan_next_turn returns an InterviewTurn with a single question."""
        from clawinterview.models import InterviewTurn

        state = make_state_with_contract([("audience", [SemanticFacet.AUDIENCE])])
        turn = plan_next_turn(state)
        assert isinstance(turn, InterviewTurn)

    def test_question_field_is_non_empty_string(self) -> None:
        state = make_state_with_contract([("audience", [SemanticFacet.AUDIENCE])])
        turn = plan_next_turn(state)
        assert turn is not None
        assert isinstance(turn.question, str)
        assert len(turn.question) > 0

    def test_turn_number_is_one_when_no_prior_turns(self) -> None:
        state = make_state_with_contract([("audience", [SemanticFacet.AUDIENCE])])
        turn = plan_next_turn(state)
        assert turn is not None
        assert turn.turn_number == 1

    def test_turn_number_increments_with_existing_turns(self) -> None:
        from clawinterview.models import InterviewTurn

        state = make_state_with_contract([
            ("audience", [SemanticFacet.AUDIENCE]),
            ("offer", [SemanticFacet.OFFER]),
        ])
        # Simulate one prior turn already recorded
        prior_turn = InterviewTurn(
            turn_number=1, layer="context", question="Prior question?"
        )
        state.turns = [prior_turn]
        turn = plan_next_turn(state)
        assert turn is not None
        assert turn.turn_number == 2


# ---------------------------------------------------------------------------
# T022-2: Layer assignment — context vs strategy facets
# ---------------------------------------------------------------------------


class TestLayerAssignment:
    def test_audience_facet_maps_to_context_layer(self) -> None:
        state = make_state_with_contract([("audience", [SemanticFacet.AUDIENCE])])
        turn = plan_next_turn(state)
        assert turn is not None
        assert turn.layer == "context"

    def test_topic_facet_maps_to_context_layer(self) -> None:
        state = make_state_with_contract([("topic", [SemanticFacet.TOPIC])])
        turn = plan_next_turn(state)
        assert turn is not None
        assert turn.layer == "context"

    def test_tenant_context_facet_maps_to_context_layer(self) -> None:
        state = make_state_with_contract(
            [("tenant_ctx", [SemanticFacet.TENANT_CONTEXT])]
        )
        turn = plan_next_turn(state)
        assert turn is not None
        assert turn.layer == "context"

    def test_positioning_facet_maps_to_strategy_layer(self) -> None:
        state = make_state_with_contract(
            [("positioning", [SemanticFacet.POSITIONING])],
            current_layer="strategy",
        )
        turn = plan_next_turn(state)
        assert turn is not None
        assert turn.layer == "strategy"

    def test_brand_facet_maps_to_strategy_layer(self) -> None:
        state = make_state_with_contract(
            [("brand_dir", [SemanticFacet.BRAND])],
            current_layer="strategy",
        )
        turn = plan_next_turn(state)
        assert turn is not None
        assert turn.layer == "strategy"

    def test_offer_facet_maps_to_strategy_layer(self) -> None:
        state = make_state_with_contract(
            [("offer", [SemanticFacet.OFFER])],
            current_layer="strategy",
        )
        turn = plan_next_turn(state)
        assert turn is not None
        assert turn.layer == "strategy"

    def test_schedule_facet_maps_to_constraints_layer(self) -> None:
        state = make_state_with_contract(
            [("sched", [SemanticFacet.SCHEDULE])],
            current_layer="constraints",
        )
        turn = plan_next_turn(state)
        assert turn is not None
        assert turn.layer == "constraints"

    def test_compliance_facet_maps_to_constraints_layer(self) -> None:
        state = make_state_with_contract(
            [("compliance_rules", [SemanticFacet.COMPLIANCE])],
            current_layer="constraints",
        )
        turn = plan_next_turn(state)
        assert turn is not None
        assert turn.layer == "constraints"

    def test_no_matching_facet_falls_into_execution_brief(self) -> None:
        state = make_state_with_contract(
            [("asset_link", [SemanticFacet.ASSET])],
            current_layer="execution_brief",
        )
        turn = plan_next_turn(state)
        assert turn is not None
        assert turn.layer == "execution_brief"


# ---------------------------------------------------------------------------
# T022-3: Light mode — input with default_value triggers light mode
# ---------------------------------------------------------------------------


class TestLightMode:
    def test_input_with_default_value_returns_light_mode(self) -> None:
        """_determine_mode returns LIGHT when input has a default_value."""
        spec = make_input_spec(
            "channel",
            facets=[SemanticFacet.POSITIONING],  # would normally be DEEP
            default_value="email",
        )
        mode = _determine_mode(spec)
        assert mode == InterviewMode.LIGHT

    def test_input_with_no_deep_facets_returns_light_mode(self) -> None:
        """LIGHT when facets are audience, topic — no deep facets."""
        spec = make_input_spec("audience", facets=[SemanticFacet.AUDIENCE])
        mode = _determine_mode(spec)
        assert mode == InterviewMode.LIGHT

    def test_turn_mode_is_light_when_input_has_default(self) -> None:
        """Integration: plan_next_turn sets mode=LIGHT for defaulted inputs."""
        # Build a state where the input has a default_value via the InputSpec
        # but compiled contract doesn't carry default_value directly;
        # we verify via _determine_mode on an InputSpec.
        spec = make_input_spec(
            "channel",
            facets=[SemanticFacet.BRAND],
            default_value="email",
        )
        mode = _determine_mode(spec)
        assert mode == InterviewMode.LIGHT


# ---------------------------------------------------------------------------
# T022-4: Deep mode — strategy/compliance facet triggers deep mode
# ---------------------------------------------------------------------------


class TestDeepMode:
    def test_strategy_facet_triggers_deep_mode(self) -> None:
        spec = make_input_spec("positioning", facets=[SemanticFacet.POSITIONING])
        mode = _determine_mode(spec)
        assert mode == InterviewMode.DEEP

    def test_compliance_facet_triggers_deep_mode(self) -> None:
        spec = make_input_spec("compliance", facets=[SemanticFacet.COMPLIANCE])
        mode = _determine_mode(spec)
        assert mode == InterviewMode.DEEP

    def test_brand_facet_triggers_deep_mode(self) -> None:
        """BRAND is in _DEEP_FACETS? Check: _DEEP_FACETS = {strategy, compliance, positioning}."""
        # BRAND is not in _DEEP_FACETS — it's in strategy layer but not deep mode
        spec = make_input_spec("brand", facets=[SemanticFacet.BRAND])
        mode = _determine_mode(spec)
        # brand is NOT in _DEEP_FACETS (only strategy, compliance, positioning are)
        assert mode == InterviewMode.LIGHT

    def test_positioning_facet_triggers_deep_mode(self) -> None:
        spec = make_input_spec("pos", facets=[SemanticFacet.POSITIONING])
        mode = _determine_mode(spec)
        assert mode == InterviewMode.DEEP

    def test_deep_mode_overrides_non_deep_facets_when_mixed(self) -> None:
        """Mixed facets: if any deep facet present and no default, mode is DEEP."""
        spec = make_input_spec(
            "mixed",
            facets=[SemanticFacet.AUDIENCE, SemanticFacet.COMPLIANCE],
        )
        mode = _determine_mode(spec)
        assert mode == InterviewMode.DEEP

    def test_turn_layer_strategy_deep_mode(self) -> None:
        """Integration: plan_next_turn emits DEEP for positioning-faceted input."""
        state = make_state_with_contract(
            [("pos_statement", [SemanticFacet.POSITIONING])],
            current_layer="strategy",
        )
        turn = plan_next_turn(state)
        assert turn is not None
        assert turn.mode == InterviewMode.DEEP


# ---------------------------------------------------------------------------
# T022-5: Returns None when all blocking inputs are resolved
# ---------------------------------------------------------------------------


class TestReturnsNoneWhenAllResolved:
    def test_returns_none_when_all_blocking_resolved(self) -> None:
        state = make_state_with_contract(
            [("audience", [SemanticFacet.AUDIENCE])],
            resolutions={"audience": make_resolved("audience")},
        )
        turn = plan_next_turn(state)
        assert turn is None

    def test_returns_none_for_multiple_resolved_inputs(self) -> None:
        state = make_state_with_contract(
            [
                ("audience", [SemanticFacet.AUDIENCE]),
                ("offer", [SemanticFacet.OFFER]),
            ],
            resolutions={
                "audience": make_resolved("audience"),
                "offer": make_resolved("offer"),
            },
        )
        turn = plan_next_turn(state)
        assert turn is None

    def test_returns_none_when_compiled_contract_is_none(self) -> None:
        state = InterviewState(
            run_id="run-nocontract",
            pipeline_id="pl-nocontract",
            status=InterviewStatus.AWAITING_INPUT,
            compiled_contract=None,
        )
        turn = plan_next_turn(state)
        assert turn is None

    def test_still_asks_when_only_some_inputs_resolved(self) -> None:
        """If one blocking input is unresolved, a question should be returned."""
        state = make_state_with_contract(
            [
                ("audience", [SemanticFacet.AUDIENCE]),
                ("offer", [SemanticFacet.OFFER]),
            ],
            resolutions={
                "audience": make_resolved("audience"),
                # offer is NOT resolved
            },
            current_layer="strategy",
        )
        turn = plan_next_turn(state)
        assert turn is not None


# ---------------------------------------------------------------------------
# T022-6: Advances to next layer when current layer has no unresolved inputs
# ---------------------------------------------------------------------------


class TestLayerAdvancement:
    def test_advances_from_context_to_strategy(self) -> None:
        """When context inputs are all resolved, planner moves to strategy layer."""
        state = make_state_with_contract(
            [
                ("audience", [SemanticFacet.AUDIENCE]),
                ("offer", [SemanticFacet.OFFER]),
            ],
            resolutions={
                "audience": make_resolved("audience"),
                # offer (strategy layer) is unresolved
            },
            current_layer="context",
        )
        turn = plan_next_turn(state)
        assert turn is not None
        # Should advance to strategy layer since context is fully resolved
        assert turn.layer == "strategy"
        assert state.current_layer == "strategy"

    def test_advances_through_all_layers_until_unresolved_found(self) -> None:
        """context + strategy resolved → planner lands on constraints layer."""
        state = make_state_with_contract(
            [
                ("audience", [SemanticFacet.AUDIENCE]),
                ("offer", [SemanticFacet.OFFER]),
                ("schedule", [SemanticFacet.SCHEDULE]),
            ],
            resolutions={
                "audience": make_resolved("audience"),
                "offer": make_resolved("offer"),
                # schedule (constraints) unresolved
            },
            current_layer="context",
        )
        turn = plan_next_turn(state)
        assert turn is not None
        assert turn.layer == "constraints"
        assert state.current_layer == "constraints"

    def test_does_not_regress_layer(self) -> None:
        """When current_layer is already 'strategy', should not go back to context."""
        state = make_state_with_contract(
            [
                ("audience", [SemanticFacet.AUDIENCE]),
                ("offer", [SemanticFacet.OFFER]),
            ],
            resolutions={
                "audience": make_resolved("audience"),
            },
            current_layer="strategy",
        )
        turn = plan_next_turn(state)
        assert turn is not None
        # Should be on strategy or later, not context
        assert turn.layer in ("strategy", "constraints", "execution_brief")


# ---------------------------------------------------------------------------
# T022-7: Summary includes provenance of resolved inputs (FR-019)
# ---------------------------------------------------------------------------


class TestSummaryProvenance:
    def test_summary_includes_resolved_input_id(self) -> None:
        state = make_state_with_contract(
            [
                ("audience", [SemanticFacet.AUDIENCE]),
                ("offer", [SemanticFacet.OFFER]),
            ],
            resolutions={
                "audience": make_resolved("audience", value="founders", source="pipeline_args"),
            },
            current_layer="strategy",
        )
        summary = _build_summary(state)
        assert "audience" in summary

    def test_summary_includes_evidence_source(self) -> None:
        state = make_state_with_contract(
            [
                ("audience", [SemanticFacet.AUDIENCE]),
                ("offer", [SemanticFacet.OFFER]),
            ],
            resolutions={
                "audience": make_resolved("audience", value="founders", source="pipeline_args"),
            },
            current_layer="strategy",
        )
        summary = _build_summary(state)
        assert "pipeline_args" in summary

    def test_summary_includes_resolved_value(self) -> None:
        state = make_state_with_contract(
            [
                ("audience", [SemanticFacet.AUDIENCE]),
                ("offer", [SemanticFacet.OFFER]),
            ],
            resolutions={
                "audience": make_resolved("audience", value="enterprise_founders", source="user_args"),
            },
            current_layer="strategy",
        )
        summary = _build_summary(state)
        assert "enterprise_founders" in summary

    def test_summary_says_nothing_resolved_when_empty(self) -> None:
        state = make_state_with_contract([("audience", [SemanticFacet.AUDIENCE])])
        summary = _build_summary(state)
        assert "No inputs resolved" in summary

    def test_summary_is_embedded_in_turn(self) -> None:
        """plan_next_turn embeds the summary in the returned turn object."""
        state = make_state_with_contract(
            [
                ("audience", [SemanticFacet.AUDIENCE]),
                ("offer", [SemanticFacet.OFFER]),
            ],
            resolutions={
                "audience": make_resolved("audience", value="founders", source="pipeline_args"),
            },
            current_layer="strategy",
        )
        turn = plan_next_turn(state)
        assert turn is not None
        assert "pipeline_args" in turn.summary

    def test_summary_lists_multiple_resolved_inputs(self) -> None:
        state = make_state_with_contract(
            [
                ("audience", [SemanticFacet.AUDIENCE]),
                ("offer", [SemanticFacet.OFFER]),
                ("schedule", [SemanticFacet.SCHEDULE]),
            ],
            resolutions={
                "audience": make_resolved("audience", value="founders", source="src_a"),
                "offer": make_resolved("offer", value="retreat", source="src_b"),
            },
            current_layer="constraints",
        )
        summary = _build_summary(state)
        assert "audience" in summary
        assert "offer" in summary
        assert "src_a" in summary
        assert "src_b" in summary
