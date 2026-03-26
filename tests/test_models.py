"""Comprehensive tests for ClawInterview Pydantic v2 models.

Covers enum membership, serialization round-trips, validation errors,
CompletionRule recursion, optional field defaults, and deep nested state.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from clawinterview.models import (
    BoundedOption,
    CompiledInput,
    CompiledRunContract,
    CompletionRule,
    ConflictReport,
    ConflictSeverity,
    InputResolution,
    InputSpec,
    InterviewBrief,
    InterviewContract,
    InterviewMode,
    InterviewState,
    InterviewStatus,
    InterviewTurn,
    OutputSpec,
    PrimitiveType,
    ResolutionContext,
    ResolutionResult,
    ResolutionStatus,
    ResolverKind,
    SemanticFacet,
    TenantOverlay,
)


# ---------------------------------------------------------------------------
# 1. Enum membership
# ---------------------------------------------------------------------------


class TestPrimitiveType:
    def test_all_expected_values(self) -> None:
        expected = {
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
        }
        actual = {member.value for member in PrimitiveType}
        assert actual == expected

    def test_member_count(self) -> None:
        assert len(PrimitiveType) == 11

    def test_string_enum_inherits_str(self) -> None:
        assert isinstance(PrimitiveType.STRING, str)
        assert PrimitiveType.STRING == "string"


class TestResolverKind:
    def test_all_expected_values(self) -> None:
        expected = {
            "user_args",
            "user_message",
            "pipeline_state",
            "memory",
            "tenant_file",
            "upstream_output",
            "rag",
            "web",
            "infer",
            "ask",
        }
        actual = {member.value for member in ResolverKind}
        assert actual == expected

    def test_member_count(self) -> None:
        assert len(ResolverKind) == 10

    def test_string_enum_inherits_str(self) -> None:
        assert isinstance(ResolverKind.ASK, str)
        assert ResolverKind.ASK == "ask"


class TestSemanticFacet:
    def test_all_expected_values(self) -> None:
        expected = {
            "audience",
            "offer",
            "schedule",
            "brand",
            "proof",
            "cta",
            "asset",
            "tenant_context",
            "brief",
            "approval",
            "compliance",
            "topic",
            "positioning",
            "partner",
            "budget",
            "timeline",
        }
        actual = {member.value for member in SemanticFacet}
        assert actual == expected

    def test_member_count(self) -> None:
        assert len(SemanticFacet) == 16

    def test_string_enum_inherits_str(self) -> None:
        assert isinstance(SemanticFacet.AUDIENCE, str)
        assert SemanticFacet.AUDIENCE == "audience"


class TestInterviewStatus:
    def test_all_expected_values(self) -> None:
        expected = {
            "pending",
            "compiling",
            "resolving",
            "in_progress",
            "awaiting_input",
            "complete",
            "failed",
        }
        actual = {member.value for member in InterviewStatus}
        assert actual == expected

    def test_member_count(self) -> None:
        assert len(InterviewStatus) == 7

    def test_string_enum_inherits_str(self) -> None:
        assert isinstance(InterviewStatus.PENDING, str)
        assert InterviewStatus.PENDING == "pending"


class TestResolutionStatus:
    def test_all_expected_values(self) -> None:
        expected = {"unresolved", "resolved", "stale", "conflict"}
        actual = {member.value for member in ResolutionStatus}
        assert actual == expected

    def test_member_count(self) -> None:
        assert len(ResolutionStatus) == 4

    def test_string_enum_inherits_str(self) -> None:
        assert isinstance(ResolutionStatus.RESOLVED, str)
        assert ResolutionStatus.RESOLVED == "resolved"


class TestInterviewMode:
    def test_all_expected_values(self) -> None:
        expected = {"light", "deep"}
        actual = {member.value for member in InterviewMode}
        assert actual == expected

    def test_member_count(self) -> None:
        assert len(InterviewMode) == 2

    def test_string_enum_inherits_str(self) -> None:
        assert isinstance(InterviewMode.LIGHT, str)
        assert InterviewMode.LIGHT == "light"


class TestConflictSeverity:
    def test_all_expected_values(self) -> None:
        expected = {"exact_match", "compatible_refinement", "incompatible"}
        actual = {member.value for member in ConflictSeverity}
        assert actual == expected

    def test_member_count(self) -> None:
        assert len(ConflictSeverity) == 3

    def test_string_enum_inherits_str(self) -> None:
        assert isinstance(ConflictSeverity.INCOMPATIBLE, str)
        assert ConflictSeverity.INCOMPATIBLE == "incompatible"


# ---------------------------------------------------------------------------
# 2. Model serialization round-trips
# ---------------------------------------------------------------------------


class TestInputSpecRoundTrip:
    def test_minimal_round_trip(self) -> None:
        original = InputSpec(
            id="campaign_name",
            type=PrimitiveType.STRING,
            description="The name of the campaign.",
        )
        dumped = original.model_dump()
        reconstructed = InputSpec.model_validate(dumped)
        assert reconstructed == original

    def test_full_round_trip(self) -> None:
        original = InputSpec(
            id="budget",
            type=PrimitiveType.MONEY,
            description="Total campaign budget.",
            facets=[SemanticFacet.BUDGET],
            resolution_strategies=[ResolverKind.USER_ARGS, ResolverKind.ASK],
            confidence_threshold=0.9,
            freshness_policy="1d",
            ask_policy="always",
            depends_on=["campaign_name"],
            default_value=5000,
        )
        dumped = original.model_dump()
        reconstructed = InputSpec.model_validate(dumped)
        assert reconstructed == original

    def test_enum_values_serialized_as_strings(self) -> None:
        spec = InputSpec(
            id="x",
            type=PrimitiveType.BOOLEAN,
            description="A boolean flag.",
            facets=[SemanticFacet.COMPLIANCE],
        )
        dumped = spec.model_dump()
        assert dumped["type"] == "boolean"
        assert dumped["facets"] == ["compliance"]


class TestInterviewContractRoundTrip:
    def test_empty_contract_round_trip(self) -> None:
        original = InterviewContract()
        dumped = original.model_dump()
        reconstructed = InterviewContract.model_validate(dumped)
        assert reconstructed == original

    def test_full_contract_round_trip(self) -> None:
        input_spec = InputSpec(
            id="audience_segment",
            type=PrimitiveType.ENUM,
            description="Target audience segment.",
            facets=[SemanticFacet.AUDIENCE],
            resolution_strategies=[ResolverKind.MEMORY, ResolverKind.ASK],
        )
        output_spec = OutputSpec(
            id="email_subject",
            type=PrimitiveType.STRING,
            facets=[SemanticFacet.BRIEF],
        )
        rule = CompletionRule(require="audience_segment")
        original = InterviewContract(
            version="2.0",
            required_inputs=[input_spec],
            optional_inputs=[],
            produces_outputs=[output_spec],
            resolution_strategies=[ResolverKind.USER_ARGS],
            completion_rules=rule,
            semantic_facets=[SemanticFacet.AUDIENCE, SemanticFacet.BRIEF],
            evidence_policy={"min_sources": 1},
        )
        dumped = original.model_dump()
        reconstructed = InterviewContract.model_validate(dumped)
        assert reconstructed == original


class TestCompiledRunContractRoundTrip:
    def _make_compiled_run_contract(self) -> CompiledRunContract:
        compiled_input = CompiledInput(
            id="global_audience_segment",
            original_id="audience_segment",
            owner_target="email_campaign",
            type=PrimitiveType.ENUM,
            facets=[SemanticFacet.AUDIENCE],
            resolution_strategies=[ResolverKind.MEMORY],
            confidence_threshold=0.8,
            blocking=True,
            stage_needed_by="stage_1",
            producer_mapping=None,
        )
        output_spec = OutputSpec(
            id="final_subject",
            type=PrimitiveType.STRING,
        )
        rule = CompletionRule(require="global_audience_segment")
        return CompiledRunContract(
            pipeline_id="pipeline-abc",
            run_id="run-001",
            compiled_at="2026-03-25T10:00:00Z",
            participating_targets=["email_campaign", "sms_campaign"],
            inputs=[compiled_input],
            outputs=[output_spec],
            completion_rules=rule,
            conflicts=[{"input_id": "x", "severity": "incompatible"}],
        )

    def test_round_trip(self) -> None:
        original = self._make_compiled_run_contract()
        dumped = original.model_dump()
        reconstructed = CompiledRunContract.model_validate(dumped)
        assert reconstructed == original

    def test_pipeline_id_preserved(self) -> None:
        contract = self._make_compiled_run_contract()
        dumped = contract.model_dump()
        assert dumped["pipeline_id"] == "pipeline-abc"
        assert dumped["run_id"] == "run-001"


class TestInterviewStateRoundTrip:
    def _make_interview_state(self) -> InterviewState:
        compiled_input = CompiledInput(
            id="topic",
            original_id="topic",
            owner_target="newsletter",
            type=PrimitiveType.STRING,
        )
        compiled_contract = CompiledRunContract(
            pipeline_id="pipeline-newsletter",
            run_id="run-42",
            compiled_at="2026-03-25T09:00:00Z",
            participating_targets=["newsletter"],
            inputs=[compiled_input],
        )
        resolution = InputResolution(
            input_id="topic",
            status=ResolutionStatus.RESOLVED,
            resolver_used=ResolverKind.USER_ARGS,
            confidence=0.95,
            evidence_source="args",
            resolved_value="Q1 Growth Campaign",
            resolved_at="2026-03-25T09:01:00Z",
        )
        option = BoundedOption(
            value="q1_growth",
            label="Q1 Growth",
            description="Focus on growth metrics.",
            is_recommended=True,
        )
        turn = InterviewTurn(
            turn_number=1,
            layer="context",
            mode=InterviewMode.LIGHT,
            summary="Gathered topic.",
            recommendation="Use Q1 Growth Campaign.",
            options=[option],
            question="What is the campaign topic?",
            response="Q1 Growth Campaign",
            resolved_inputs=["topic"],
            timestamp="2026-03-25T09:01:00Z",
        )
        brief = InterviewBrief(
            run_id="run-42",
            context_layer={"topic": "Q1 Growth Campaign"},
            strategy_layer={"channel": "email"},
            constraints_layer={"max_words": 500},
            execution_brief={"template": "newsletter-v2"},
            layer_status={"context": "complete"},
        )
        return InterviewState(
            run_id="run-42",
            pipeline_id="pipeline-newsletter",
            status=InterviewStatus.COMPLETE,
            compiled_contract=compiled_contract,
            resolutions={"topic": resolution},
            turns=[turn],
            brief=brief,
            current_layer="execution",
            bypass_mode=False,
            started_at="2026-03-25T09:00:00Z",
            updated_at="2026-03-25T09:05:00Z",
            completed_at="2026-03-25T09:05:00Z",
        )

    def test_round_trip(self) -> None:
        original = self._make_interview_state()
        dumped = original.model_dump()
        reconstructed = InterviewState.model_validate(dumped)
        assert reconstructed == original

    def test_status_preserved(self) -> None:
        state = self._make_interview_state()
        dumped = state.model_dump()
        assert dumped["status"] == "complete"

    def test_nested_resolution_preserved(self) -> None:
        state = self._make_interview_state()
        dumped = state.model_dump()
        assert dumped["resolutions"]["topic"]["status"] == "resolved"
        assert dumped["resolutions"]["topic"]["confidence"] == 0.95

    def test_nested_turn_options_preserved(self) -> None:
        state = self._make_interview_state()
        dumped = state.model_dump()
        assert len(dumped["turns"]) == 1
        assert dumped["turns"][0]["options"][0]["is_recommended"] is True

    def test_brief_layers_preserved(self) -> None:
        state = self._make_interview_state()
        dumped = state.model_dump()
        assert dumped["brief"]["context_layer"]["topic"] == "Q1 Growth Campaign"
        assert dumped["brief"]["layer_status"]["context"] == "complete"


# ---------------------------------------------------------------------------
# 3. Validation errors on invalid data
# ---------------------------------------------------------------------------


class TestInputSpecValidation:
    def test_invalid_primitive_type_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            InputSpec(
                id="field1",
                type="not_a_valid_type",  # type: ignore[arg-type]
                description="A field.",
            )
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("type",) for e in errors)

    def test_missing_required_id_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            InputSpec(  # type: ignore[call-arg]
                type=PrimitiveType.STRING,
                description="Missing id.",
            )
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("id",) for e in errors)

    def test_missing_required_description_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            InputSpec(  # type: ignore[call-arg]
                id="x",
                type=PrimitiveType.STRING,
            )
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("description",) for e in errors)

    def test_extra_field_forbidden(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            InputSpec(  # type: ignore[call-arg]
                id="x",
                type=PrimitiveType.STRING,
                description="Valid.",
                unknown_field="should_fail",
            )
        errors = exc_info.value.errors()
        assert any("extra" in e["type"] for e in errors)


class TestCompletionRuleValidation:
    def test_empty_rule_is_valid(self) -> None:
        """CompletionRule with no fields set should be valid — all are optional."""
        rule = CompletionRule()
        assert rule.all_of is None
        assert rule.any_of is None
        assert rule.require is None
        assert rule.min_items is None
        assert rule.freshness_required is None
        assert rule.confidence_threshold is None
        assert rule.must_produce is None

    def test_extra_field_forbidden(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            CompletionRule(nonexistent_field="bad")  # type: ignore[call-arg]
        errors = exc_info.value.errors()
        assert any("extra" in e["type"] for e in errors)


class TestInterviewContractValidation:
    def test_extra_field_forbidden(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            InterviewContract(injected_key="injection_attempt")  # type: ignore[call-arg]
        errors = exc_info.value.errors()
        assert any("extra" in e["type"] for e in errors)

    def test_invalid_resolver_kind_in_list_raises(self) -> None:
        with pytest.raises(ValidationError):
            InterviewContract(
                resolution_strategies=["not_a_resolver"],  # type: ignore[list-item]
            )

    def test_invalid_semantic_facet_in_list_raises(self) -> None:
        with pytest.raises(ValidationError):
            InterviewContract(
                semantic_facets=["not_a_facet"],  # type: ignore[list-item]
            )


class TestCompiledRunContractValidation:
    def test_missing_required_fields_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            CompiledRunContract()  # type: ignore[call-arg]
        errors = exc_info.value.errors()
        missing_fields = {e["loc"][0] for e in errors if e["type"] == "missing"}
        assert "pipeline_id" in missing_fields
        assert "run_id" in missing_fields
        assert "compiled_at" in missing_fields

    def test_extra_field_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            CompiledRunContract(  # type: ignore[call-arg]
                pipeline_id="p",
                run_id="r",
                compiled_at="2026-01-01T00:00:00Z",
                surprise_field="nope",
            )


class TestInterviewStateValidation:
    def test_missing_required_fields_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            InterviewState()  # type: ignore[call-arg]
        errors = exc_info.value.errors()
        missing_fields = {e["loc"][0] for e in errors if e["type"] == "missing"}
        assert "run_id" in missing_fields
        assert "pipeline_id" in missing_fields

    def test_invalid_status_raises(self) -> None:
        with pytest.raises(ValidationError):
            InterviewState(
                run_id="r",
                pipeline_id="p",
                status="unknown_status",  # type: ignore[arg-type]
            )

    def test_extra_field_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            InterviewState(  # type: ignore[call-arg]
                run_id="r",
                pipeline_id="p",
                unknown_field="bad",
            )


# ---------------------------------------------------------------------------
# 4. CompletionRule recursion
# ---------------------------------------------------------------------------


class TestCompletionRuleRecursion:
    def test_deeply_nested_round_trip(self) -> None:
        """Nested all_of containing any_of containing require."""
        inner_require = CompletionRule(require="audience_segment")
        inner_confidence = CompletionRule(confidence_threshold=0.8)
        any_of_rule = CompletionRule(any_of=[inner_require, inner_confidence])
        outer = CompletionRule(all_of=[any_of_rule])

        dumped = outer.model_dump()
        reconstructed = CompletionRule.model_validate(dumped)
        assert reconstructed == outer

    def test_nested_structure_integrity(self) -> None:
        inner = CompletionRule(require="topic")
        mid = CompletionRule(any_of=[inner])
        outer = CompletionRule(all_of=[mid])

        dumped = outer.model_dump()
        # Verify nested dict structure
        assert dumped["all_of"] is not None
        assert len(dumped["all_of"]) == 1
        assert dumped["all_of"][0]["any_of"] is not None
        assert len(dumped["all_of"][0]["any_of"]) == 1
        assert dumped["all_of"][0]["any_of"][0]["require"] == "topic"

    def test_three_levels_deep(self) -> None:
        leaf = CompletionRule(require="final_input")
        level_2 = CompletionRule(all_of=[leaf], min_items=1)
        level_3 = CompletionRule(any_of=[level_2], must_produce="email_subject")
        level_4 = CompletionRule(
            all_of=[level_3], freshness_required="1h", confidence_threshold=0.75
        )

        dumped = level_4.model_dump()
        reconstructed = CompletionRule.model_validate(dumped)
        assert reconstructed == level_4

    def test_mixed_siblings_in_all_of(self) -> None:
        rule1 = CompletionRule(require="input_a")
        rule2 = CompletionRule(min_items=2)
        rule3 = CompletionRule(must_produce="output_x")
        compound = CompletionRule(all_of=[rule1, rule2, rule3])

        dumped = compound.model_dump()
        reconstructed = CompletionRule.model_validate(dumped)
        assert reconstructed == compound
        assert len(reconstructed.all_of) == 3  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 5. Optional field defaults
# ---------------------------------------------------------------------------


class TestInputSpecDefaults:
    def test_minimal_construction_applies_defaults(self) -> None:
        spec = InputSpec(
            id="event_date",
            type=PrimitiveType.DATE,
            description="The date of the event.",
        )
        assert spec.confidence_threshold == 0.7
        assert spec.ask_policy == "only_if_unresolved"
        assert spec.facets == []
        assert spec.resolution_strategies == []
        assert spec.depends_on == []
        assert spec.freshness_policy is None
        assert spec.default_value is None

    def test_id_type_description_set_correctly(self) -> None:
        spec = InputSpec(
            id="my_id",
            type=PrimitiveType.NUMBER,
            description="A number field.",
        )
        assert spec.id == "my_id"
        assert spec.type == PrimitiveType.NUMBER
        assert spec.description == "A number field."

    def test_defaults_serialized_in_model_dump(self) -> None:
        spec = InputSpec(
            id="x",
            type=PrimitiveType.URL,
            description="A URL.",
        )
        dumped = spec.model_dump()
        assert dumped["confidence_threshold"] == 0.7
        assert dumped["ask_policy"] == "only_if_unresolved"
        assert dumped["facets"] == []
        assert dumped["resolution_strategies"] == []
        assert dumped["depends_on"] == []
        assert dumped["freshness_policy"] is None
        assert dumped["default_value"] is None


class TestInterviewContractDefaults:
    def test_empty_contract_defaults(self) -> None:
        contract = InterviewContract()
        assert contract.version == "1.0"
        assert contract.required_inputs == []
        assert contract.optional_inputs == []
        assert contract.produces_outputs == []
        assert contract.resolution_strategies == []
        assert contract.completion_rules is None
        assert contract.semantic_facets == []
        assert contract.evidence_policy == {}


class TestCompiledInputDefaults:
    def test_minimal_compiled_input_defaults(self) -> None:
        ci = CompiledInput(
            id="ci_topic",
            original_id="topic",
            owner_target="newsletter",
            type=PrimitiveType.STRING,
        )
        assert ci.facets == []
        assert ci.resolution_strategies == []
        assert ci.confidence_threshold == 0.7
        assert ci.blocking is True
        assert ci.stage_needed_by == ""
        assert ci.producer_mapping is None


class TestInterviewStateDefaults:
    def test_minimal_state_defaults(self) -> None:
        state = InterviewState(run_id="r-001", pipeline_id="p-001")
        assert state.status == InterviewStatus.PENDING
        assert state.compiled_contract is None
        assert state.resolutions == {}
        assert state.turns == []
        assert state.brief is None
        assert state.current_layer == "context"
        assert state.bypass_mode is False
        assert state.started_at == ""
        assert state.updated_at == ""
        assert state.completed_at is None


class TestInputResolutionDefaults:
    def test_minimal_resolution_defaults(self) -> None:
        resolution = InputResolution(input_id="topic")
        assert resolution.status == ResolutionStatus.UNRESOLVED
        assert resolution.resolver_used is None
        assert resolution.confidence == 0.0
        assert resolution.evidence_source == ""
        assert resolution.resolved_value is None
        assert resolution.resolved_at is None
        assert resolution.stale_since is None


class TestInterviewTurnDefaults:
    def test_minimal_turn_defaults(self) -> None:
        turn = InterviewTurn(turn_number=1, layer="context")
        assert turn.mode == InterviewMode.LIGHT
        assert turn.summary == ""
        assert turn.recommendation is None
        assert turn.options == []
        assert turn.question == ""
        assert turn.response is None
        assert turn.resolved_inputs == []
        assert turn.timestamp == ""


class TestBoundedOptionDefaults:
    def test_minimal_option_defaults(self) -> None:
        opt = BoundedOption(value="opt1", label="Option 1")
        assert opt.description == ""
        assert opt.is_recommended is False


# ---------------------------------------------------------------------------
# 6. InterviewState with nested data — deep serialization
# ---------------------------------------------------------------------------


class TestInterviewStateDeepSerialization:
    def _build_state(self) -> InterviewState:
        """Build a maximally populated InterviewState for deep tests."""
        compiled_input_a = CompiledInput(
            id="g_audience",
            original_id="audience",
            owner_target="email_stage",
            type=PrimitiveType.ENUM,
            facets=[SemanticFacet.AUDIENCE],
            resolution_strategies=[ResolverKind.MEMORY, ResolverKind.ASK],
            confidence_threshold=0.85,
            blocking=True,
            stage_needed_by="stage_email",
        )
        compiled_input_b = CompiledInput(
            id="g_budget",
            original_id="budget",
            owner_target="ads_stage",
            type=PrimitiveType.MONEY,
            facets=[SemanticFacet.BUDGET],
            resolution_strategies=[ResolverKind.USER_ARGS],
            confidence_threshold=0.9,
            blocking=False,
            stage_needed_by="stage_ads",
            producer_mapping="finance_output.budget",
        )
        output = OutputSpec(
            id="campaign_brief",
            type=PrimitiveType.OBJECT,
            facets=[SemanticFacet.BRIEF],
        )
        rule = CompletionRule(
            all_of=[
                CompletionRule(require="g_audience"),
                CompletionRule(
                    any_of=[
                        CompletionRule(require="g_budget"),
                        CompletionRule(confidence_threshold=0.8),
                    ]
                ),
            ]
        )
        contract = CompiledRunContract(
            pipeline_id="pipeline-full",
            run_id="run-99",
            compiled_at="2026-03-25T08:00:00Z",
            participating_targets=["email_stage", "ads_stage"],
            inputs=[compiled_input_a, compiled_input_b],
            outputs=[output],
            completion_rules=rule,
            conflicts=[
                {
                    "input_ids": ["g_audience"],
                    "severity": "compatible_refinement",
                    "description": "Minor overlap",
                }
            ],
        )
        resolution_a = InputResolution(
            input_id="g_audience",
            status=ResolutionStatus.RESOLVED,
            resolver_used=ResolverKind.MEMORY,
            confidence=0.92,
            evidence_source="mem0:global/audience",
            resolved_value="young_professionals",
            resolved_at="2026-03-25T08:01:00Z",
        )
        resolution_b = InputResolution(
            input_id="g_budget",
            status=ResolutionStatus.UNRESOLVED,
            confidence=0.0,
        )
        option_a = BoundedOption(
            value="young_professionals",
            label="Young Professionals",
            description="25-35 urban professionals.",
            is_recommended=True,
        )
        option_b = BoundedOption(
            value="wellness_seekers",
            label="Wellness Seekers",
            description="Health-focused audience.",
            is_recommended=False,
        )
        turn_1 = InterviewTurn(
            turn_number=1,
            layer="context",
            mode=InterviewMode.DEEP,
            summary="Confirmed audience segment.",
            recommendation="young_professionals based on recent campaign data.",
            options=[option_a, option_b],
            question="Which audience segment should we target?",
            response="young_professionals",
            resolved_inputs=["g_audience"],
            timestamp="2026-03-25T08:01:00Z",
        )
        brief = InterviewBrief(
            run_id="run-99",
            context_layer={"audience": "young_professionals", "pipeline": "full"},
            strategy_layer={"channel_mix": ["email", "ads"], "priority": "email"},
            constraints_layer={"budget_cap": 10000, "max_touches_per_week": 3},
            execution_brief={"template_set": "q1-growth", "personalization": True},
            layer_status={"context": "complete", "strategy": "in_progress"},
        )
        return InterviewState(
            run_id="run-99",
            pipeline_id="pipeline-full",
            status=InterviewStatus.IN_PROGRESS,
            compiled_contract=contract,
            resolutions={"g_audience": resolution_a, "g_budget": resolution_b},
            turns=[turn_1],
            brief=brief,
            current_layer="strategy",
            bypass_mode=False,
            started_at="2026-03-25T08:00:00Z",
            updated_at="2026-03-25T08:05:00Z",
            completed_at=None,
        )

    def test_deep_round_trip(self) -> None:
        original = self._build_state()
        dumped = original.model_dump()
        reconstructed = InterviewState.model_validate(dumped)
        assert reconstructed == original

    def test_compiled_contract_inputs_preserved(self) -> None:
        state = self._build_state()
        dumped = state.model_dump()
        inputs = dumped["compiled_contract"]["inputs"]
        assert len(inputs) == 2
        assert inputs[0]["id"] == "g_audience"
        assert inputs[0]["type"] == "enum"
        assert inputs[1]["id"] == "g_budget"
        assert inputs[1]["type"] == "money"

    def test_nested_completion_rule_preserved(self) -> None:
        state = self._build_state()
        dumped = state.model_dump()
        rules = dumped["compiled_contract"]["completion_rules"]
        assert rules["all_of"] is not None
        assert len(rules["all_of"]) == 2
        assert rules["all_of"][0]["require"] == "g_audience"
        assert rules["all_of"][1]["any_of"] is not None

    def test_resolutions_dict_preserved(self) -> None:
        state = self._build_state()
        dumped = state.model_dump()
        assert dumped["resolutions"]["g_audience"]["status"] == "resolved"
        assert dumped["resolutions"]["g_audience"]["resolver_used"] == "memory"
        assert dumped["resolutions"]["g_audience"]["resolved_value"] == "young_professionals"
        assert dumped["resolutions"]["g_budget"]["status"] == "unresolved"

    def test_turns_with_options_preserved(self) -> None:
        state = self._build_state()
        dumped = state.model_dump()
        turn = dumped["turns"][0]
        assert turn["turn_number"] == 1
        assert turn["mode"] == "deep"
        assert len(turn["options"]) == 2
        assert turn["options"][0]["value"] == "young_professionals"
        assert turn["options"][0]["is_recommended"] is True
        assert turn["options"][1]["is_recommended"] is False

    def test_brief_all_layers_preserved(self) -> None:
        state = self._build_state()
        dumped = state.model_dump()
        brief = dumped["brief"]
        assert brief["run_id"] == "run-99"
        assert brief["context_layer"]["audience"] == "young_professionals"
        assert brief["strategy_layer"]["priority"] == "email"
        assert brief["constraints_layer"]["max_touches_per_week"] == 3
        assert brief["execution_brief"]["personalization"] is True
        assert brief["layer_status"]["context"] == "complete"

    def test_status_and_layer_preserved(self) -> None:
        state = self._build_state()
        dumped = state.model_dump()
        assert dumped["status"] == "in_progress"
        assert dumped["current_layer"] == "strategy"
        assert dumped["completed_at"] is None


# ---------------------------------------------------------------------------
# 7. Additional model coverage
# ---------------------------------------------------------------------------


class TestOutputSpec:
    def test_minimal_round_trip(self) -> None:
        original = OutputSpec(id="result", type=PrimitiveType.STRING)
        dumped = original.model_dump()
        reconstructed = OutputSpec.model_validate(dumped)
        assert reconstructed == original

    def test_defaults(self) -> None:
        spec = OutputSpec(id="x", type=PrimitiveType.OBJECT)
        assert spec.facets == []

    def test_extra_field_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            OutputSpec(id="x", type=PrimitiveType.STRING, extra="bad")  # type: ignore[call-arg]


class TestResolutionResult:
    def test_round_trip(self) -> None:
        original = ResolutionResult(
            value={"key": "val"},
            confidence=0.95,
            evidence_source="pipeline_state:audience",
            resolver_kind=ResolverKind.PIPELINE_STATE,
        )
        dumped = original.model_dump()
        reconstructed = ResolutionResult.model_validate(dumped)
        assert reconstructed == original

    def test_invalid_resolver_kind_raises(self) -> None:
        with pytest.raises(ValidationError):
            ResolutionResult(
                value="x",
                confidence=0.5,
                evidence_source="src",
                resolver_kind="not_valid",  # type: ignore[arg-type]
            )


class TestResolutionContext:
    def test_defaults(self) -> None:
        ctx = ResolutionContext()
        assert ctx.pipeline_args == {}
        assert ctx.user_message == ""
        assert ctx.prior_state == {}
        assert ctx.tenant_id == ""
        assert ctx.workspace_path == ""
        assert ctx.run_id == ""
        assert ctx.upstream_outputs == {}

    def test_round_trip(self) -> None:
        original = ResolutionContext(
            pipeline_args={"mode": "deep"},
            user_message="Use young professionals.",
            prior_state={"stage": "context"},
            tenant_id="ceremonia",
            workspace_path="/agents/ceremonia",
            run_id="run-42",
            upstream_outputs={"research_output": {"summary": "..."}},
        )
        dumped = original.model_dump()
        reconstructed = ResolutionContext.model_validate(dumped)
        assert reconstructed == original


class TestTenantOverlay:
    def test_defaults(self) -> None:
        overlay = TenantOverlay(tenant_id="ceremonia")
        assert overlay.additional_facets == []
        assert overlay.resolver_overrides == {}
        assert overlay.evidence_policy == {}
        assert overlay.custom_completion_rules is None

    def test_with_custom_completion_rules_round_trip(self) -> None:
        rule = CompletionRule(all_of=[CompletionRule(require="brand_guide")])
        original = TenantOverlay(
            tenant_id="ceremonia",
            additional_facets=["retreat_style"],
            resolver_overrides={"memory": {"namespace": "ceremonia"}},
            evidence_policy={"min_confidence": 0.9},
            custom_completion_rules=rule,
        )
        dumped = original.model_dump()
        reconstructed = TenantOverlay.model_validate(dumped)
        assert reconstructed == original

    def test_extra_field_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            TenantOverlay(tenant_id="t", surprise="bad")  # type: ignore[call-arg]


class TestConflictReport:
    def test_round_trip(self) -> None:
        original = ConflictReport(
            input_ids=["g_audience", "g_audience_v2"],
            owner_targets=["email_stage", "sms_stage"],
            severity=ConflictSeverity.INCOMPATIBLE,
            description="Both stages define audience with incompatible constraints.",
            resolution=None,
        )
        dumped = original.model_dump()
        reconstructed = ConflictReport.model_validate(dumped)
        assert reconstructed == original

    def test_severity_serialized_as_string(self) -> None:
        report = ConflictReport(
            input_ids=["x"],
            owner_targets=["a"],
            severity=ConflictSeverity.EXACT_MATCH,
            description="Exact match.",
        )
        dumped = report.model_dump()
        assert dumped["severity"] == "exact_match"

    def test_resolution_defaults_to_none(self) -> None:
        report = ConflictReport(
            input_ids=["x"],
            owner_targets=["a"],
            severity=ConflictSeverity.COMPATIBLE_REFINEMENT,
            description="Minor.",
        )
        assert report.resolution is None

    def test_extra_field_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            ConflictReport(  # type: ignore[call-arg]
                input_ids=["x"],
                owner_targets=["a"],
                severity=ConflictSeverity.INCOMPATIBLE,
                description="Bad.",
                injected="evil",
            )


class TestInterviewBrief:
    def test_defaults(self) -> None:
        brief = InterviewBrief(run_id="run-001")
        assert brief.context_layer == {}
        assert brief.strategy_layer == {}
        assert brief.constraints_layer == {}
        assert brief.execution_brief == {}
        assert brief.layer_status == {}

    def test_round_trip(self) -> None:
        original = InterviewBrief(
            run_id="run-001",
            context_layer={"audience": "all"},
            strategy_layer={"channel": "email"},
            constraints_layer={"word_limit": 300},
            execution_brief={"template": "v2"},
            layer_status={"context": "complete"},
        )
        dumped = original.model_dump()
        reconstructed = InterviewBrief.model_validate(dumped)
        assert reconstructed == original

    def test_extra_field_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            InterviewBrief(run_id="r", extra_layer="nope")  # type: ignore[call-arg]
