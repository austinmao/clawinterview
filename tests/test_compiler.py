"""Tests for ClawInterview contract compiler.

Covers compile_run_contract: single target, multi-target union, producer-consumer
mapping, blocking classification, error cases, ambiguous ID qualification, completion
rule merging, and empty contract rejection.
"""

from __future__ import annotations

import pytest

from clawinterview.compiler import compile_run_contract
from clawinterview.models import (
    CompletionRule,
    InputSpec,
    InterviewContract,
    OutputSpec,
    PrimitiveType,
    ResolverKind,
    SemanticFacet,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_input(
    id: str,
    type: PrimitiveType = PrimitiveType.STRING,
    facets: list[SemanticFacet] | None = None,
    resolution_strategies: list[ResolverKind] | None = None,
    confidence_threshold: float = 0.7,
) -> InputSpec:
    return InputSpec(
        id=id,
        type=type,
        description=f"Input {id}",
        facets=facets or [],
        resolution_strategies=resolution_strategies or [],
        confidence_threshold=confidence_threshold,
    )


def make_output(
    id: str,
    type: PrimitiveType = PrimitiveType.STRING,
    facets: list[SemanticFacet] | None = None,
) -> OutputSpec:
    return OutputSpec(id=id, type=type, facets=facets or [])


def make_contract(
    required: list[InputSpec] | None = None,
    optional: list[InputSpec] | None = None,
    outputs: list[OutputSpec] | None = None,
    completion_rules: CompletionRule | None = None,
    resolution_strategies: list[ResolverKind] | None = None,
) -> InterviewContract:
    return InterviewContract(
        required_inputs=required or [],
        optional_inputs=optional or [],
        produces_outputs=outputs or [],
        completion_rules=completion_rules,
        resolution_strategies=resolution_strategies or [],
    )


# ---------------------------------------------------------------------------
# 1. Compile 1 target — verify run_id, pipeline_id, inputs list, outputs list
# ---------------------------------------------------------------------------


class TestCompileSingleTarget:
    def test_run_id_and_pipeline_id_preserved(self) -> None:
        contract = make_contract(required=[make_input("name")])
        result = compile_run_contract(
            pipeline_id="pl-001",
            run_id="run-abc",
            target_contracts=[("email", contract)],
        )
        assert result.pipeline_id == "pl-001"
        assert result.run_id == "run-abc"

    def test_inputs_list_populated(self) -> None:
        contract = make_contract(required=[make_input("subject"), make_input("body")])
        result = compile_run_contract("pl-x", "run-x", [("target_a", contract)])
        assert len(result.inputs) == 2
        input_ids = {ci.id for ci in result.inputs}
        assert input_ids == {"subject", "body"}

    def test_outputs_list_populated(self) -> None:
        contract = make_contract(
            required=[make_input("title")],
            outputs=[make_output("draft_html"), make_output("draft_text")],
        )
        result = compile_run_contract("pl-y", "run-y", [("target_b", contract)])
        assert len(result.outputs) == 2
        output_ids = {o.id for o in result.outputs}
        assert output_ids == {"draft_html", "draft_text"}

    def test_participating_targets_contains_target(self) -> None:
        contract = make_contract(required=[make_input("foo")])
        result = compile_run_contract("pl-z", "run-z", [("my_target", contract)])
        assert result.participating_targets == ["my_target"]


# ---------------------------------------------------------------------------
# 2. Compile 3 targets — union of all inputs with ownership preserved
# ---------------------------------------------------------------------------


class TestCompileMultipleTargets:
    def test_union_of_inputs(self) -> None:
        c1 = make_contract(required=[make_input("audience")])
        c2 = make_contract(required=[make_input("offer")])
        c3 = make_contract(required=[make_input("schedule")])
        result = compile_run_contract(
            "pl-multi",
            "run-multi",
            [("t1", c1), ("t2", c2), ("t3", c3)],
        )
        assert len(result.inputs) == 3
        ids = {ci.id for ci in result.inputs}
        assert ids == {"audience", "offer", "schedule"}

    def test_ownership_preserved(self) -> None:
        c1 = make_contract(required=[make_input("audience")])
        c2 = make_contract(required=[make_input("offer")])
        c3 = make_contract(required=[make_input("schedule")])
        result = compile_run_contract(
            "pl-multi",
            "run-multi",
            [("t1", c1), ("t2", c2), ("t3", c3)],
        )
        owner_map = {ci.id: ci.owner_target for ci in result.inputs}
        assert owner_map["audience"] == "t1"
        assert owner_map["offer"] == "t2"
        assert owner_map["schedule"] == "t3"

    def test_all_targets_in_participating(self) -> None:
        c1 = make_contract(required=[make_input("x")])
        c2 = make_contract(required=[make_input("y")])
        c3 = make_contract(required=[make_input("z")])
        result = compile_run_contract(
            "pl-multi2",
            "run-m2",
            [("alpha", c1), ("beta", c2), ("gamma", c3)],
        )
        assert result.participating_targets == ["alpha", "beta", "gamma"]


# ---------------------------------------------------------------------------
# 3. Producer-consumer mapping via semantic-facet overlap
# ---------------------------------------------------------------------------


class TestProducerConsumerMapping:
    def test_producer_mapping_set_on_facet_match(self) -> None:
        # Target A produces an output with facet BRIEF
        producer_contract = make_contract(
            required=[make_input("brief_source")],
            outputs=[make_output("campaign_brief", facets=[SemanticFacet.BRIEF])],
        )
        # Target B requires an input with facet BRIEF — should map to campaign_brief
        consumer_input = make_input(
            "brief_content",
            facets=[SemanticFacet.BRIEF],
        )
        consumer_contract = make_contract(required=[consumer_input])

        result = compile_run_contract(
            "pl-pc",
            "run-pc",
            [("producer", producer_contract), ("consumer", consumer_contract)],
        )

        consumer_compiled = next(
            ci for ci in result.inputs if ci.original_id == "brief_content"
        )
        assert consumer_compiled.producer_mapping == "campaign_brief"

    def test_no_producer_mapping_without_facets(self) -> None:
        producer_contract = make_contract(
            required=[make_input("source")],
            outputs=[make_output("out_a", facets=[SemanticFacet.BRAND])],
        )
        # Input has NO facets — cannot match any producer
        consumer_input = make_input("no_facet_input")
        consumer_contract = make_contract(required=[consumer_input])

        result = compile_run_contract(
            "pl-nf",
            "run-nf",
            [("prod", producer_contract), ("cons", consumer_contract)],
        )

        consumer_compiled = next(
            ci for ci in result.inputs if ci.original_id == "no_facet_input"
        )
        assert consumer_compiled.producer_mapping is None

    def test_no_producer_mapping_when_facets_dont_overlap(self) -> None:
        producer_contract = make_contract(
            required=[make_input("src")],
            outputs=[make_output("out_b", facets=[SemanticFacet.AUDIENCE])],
        )
        consumer_input = make_input("unrelated", facets=[SemanticFacet.BUDGET])
        consumer_contract = make_contract(required=[consumer_input])

        result = compile_run_contract(
            "pl-no-overlap",
            "run-no-overlap",
            [("prod", producer_contract), ("cons", consumer_contract)],
        )

        consumer_compiled = next(
            ci for ci in result.inputs if ci.original_id == "unrelated"
        )
        assert consumer_compiled.producer_mapping is None


# ---------------------------------------------------------------------------
# 4. Classify blocking vs non-blocking
# ---------------------------------------------------------------------------


class TestBlockingClassification:
    def test_required_inputs_are_blocking(self) -> None:
        contract = make_contract(required=[make_input("required_field")])
        result = compile_run_contract("pl-b", "run-b", [("t", contract)])
        compiled = result.inputs[0]
        assert compiled.blocking is True

    def test_optional_inputs_are_non_blocking(self) -> None:
        contract = make_contract(
            required=[make_input("required_field")],
            optional=[make_input("optional_field")],
        )
        result = compile_run_contract("pl-ob", "run-ob", [("t", contract)])
        optional_compiled = next(
            ci for ci in result.inputs if ci.original_id == "optional_field"
        )
        assert optional_compiled.blocking is False

    def test_both_required_and_optional_in_same_contract(self) -> None:
        contract = make_contract(
            required=[make_input("r1"), make_input("r2")],
            optional=[make_input("o1")],
        )
        result = compile_run_contract("pl-mixed", "run-mixed", [("t", contract)])
        blocking_map = {ci.original_id: ci.blocking for ci in result.inputs}
        assert blocking_map["r1"] is True
        assert blocking_map["r2"] is True
        assert blocking_map["o1"] is False


# ---------------------------------------------------------------------------
# 5. Handle missing contract — empty list raises ValueError
# ---------------------------------------------------------------------------


class TestMissingContract:
    def test_empty_target_contracts_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="No target contracts to compile"):
            compile_run_contract("pl-empty", "run-empty", [])


# ---------------------------------------------------------------------------
# 6. Ambiguous input IDs — same id across targets gets qualified
# ---------------------------------------------------------------------------


class TestAmbiguousInputIds:
    def test_shared_id_gets_qualified_with_target_prefix(self) -> None:
        c1 = make_contract(required=[make_input("title")])
        c2 = make_contract(required=[make_input("title")])
        result = compile_run_contract(
            "pl-amb", "run-amb", [("email_target", c1), ("sms_target", c2)]
        )
        compiled_ids = {ci.id for ci in result.inputs}
        assert "email_target.title" in compiled_ids
        assert "sms_target.title" in compiled_ids

    def test_original_id_preserved_on_ambiguous_input(self) -> None:
        c1 = make_contract(required=[make_input("subject")])
        c2 = make_contract(required=[make_input("subject")])
        result = compile_run_contract(
            "pl-orig", "run-orig", [("t1", c1), ("t2", c2)]
        )
        for ci in result.inputs:
            assert ci.original_id == "subject"

    def test_unique_id_not_qualified(self) -> None:
        c1 = make_contract(required=[make_input("unique_field")])
        c2 = make_contract(required=[make_input("other_field")])
        result = compile_run_contract(
            "pl-uniq", "run-uniq", [("t1", c1), ("t2", c2)]
        )
        ids = {ci.id for ci in result.inputs}
        assert "unique_field" in ids
        assert "other_field" in ids
        # Neither should be qualified since there's no ambiguity
        assert "t1.unique_field" not in ids
        assert "t2.other_field" not in ids


# ---------------------------------------------------------------------------
# 7. Merge completion rules — all target rules wrapped in all_of
# ---------------------------------------------------------------------------


class TestMergeCompletionRules:
    def test_multiple_rules_wrapped_in_all_of(self) -> None:
        rule_a = CompletionRule(require="field_a")
        rule_b = CompletionRule(require="field_b")
        c1 = make_contract(required=[make_input("a")], completion_rules=rule_a)
        c2 = make_contract(required=[make_input("b")], completion_rules=rule_b)
        result = compile_run_contract(
            "pl-rules", "run-rules", [("t1", c1), ("t2", c2)]
        )
        assert result.completion_rules is not None
        assert result.completion_rules.all_of is not None
        assert len(result.completion_rules.all_of) == 2

    def test_single_rule_not_wrapped(self) -> None:
        rule = CompletionRule(require="field_x")
        c1 = make_contract(required=[make_input("x")], completion_rules=rule)
        c2 = make_contract(required=[make_input("y")])  # no rule
        result = compile_run_contract(
            "pl-single-rule", "run-sr", [("t1", c1), ("t2", c2)]
        )
        # Single non-None rule is returned directly without all_of wrapper
        assert result.completion_rules is not None
        assert result.completion_rules.all_of is None
        assert result.completion_rules.require == "field_x"

    def test_no_rules_returns_none(self) -> None:
        c1 = make_contract(required=[make_input("p")])
        c2 = make_contract(required=[make_input("q")])
        result = compile_run_contract(
            "pl-no-rules", "run-nr", [("t1", c1), ("t2", c2)]
        )
        assert result.completion_rules is None


# ---------------------------------------------------------------------------
# 8. Empty contract raises ValueError
# ---------------------------------------------------------------------------


class TestEmptyContractRejected:
    def test_contract_with_no_inputs_raises_value_error(self) -> None:
        empty_contract = make_contract()  # no required, no optional
        with pytest.raises(ValueError, match="zero required_inputs and zero optional_inputs"):
            compile_run_contract(
                "pl-badcontract",
                "run-bad",
                [("broken_target", empty_contract)],
            )

    def test_error_message_includes_target_id(self) -> None:
        empty_contract = make_contract()
        with pytest.raises(ValueError, match="broken_target"):
            compile_run_contract(
                "pl-bc2",
                "run-bc2",
                [("broken_target", empty_contract)],
            )

    def test_valid_contract_with_only_optional_inputs_is_accepted(self) -> None:
        # optional-only is non-empty and should NOT raise
        contract = make_contract(optional=[make_input("opt_field")])
        result = compile_run_contract("pl-opt", "run-opt", [("t", contract)])
        assert len(result.inputs) == 1
        assert result.inputs[0].blocking is False


# ---------------------------------------------------------------------------
# 9. Pipeline-scoped compilation
# ---------------------------------------------------------------------------


class TestPipelineScopedCompilation:
    """Tests that verify pipeline-scoped isolation when the same target
    contracts are compiled under different pipeline / run identifiers.
    """

    def _make_shared_target_contracts(
        self,
    ) -> list[tuple[str, "InterviewContract"]]:
        """Return two target contracts sharing 2 input IDs (audience, offer)."""
        c1 = make_contract(
            required=[
                make_input("audience", facets=[SemanticFacet.AUDIENCE]),
                make_input("offer", facets=[SemanticFacet.OFFER]),
            ],
            outputs=[make_output("brief_out", facets=[SemanticFacet.BRIEF])],
        )
        c2 = make_contract(
            required=[
                make_input("audience", facets=[SemanticFacet.AUDIENCE]),
                make_input("offer", facets=[SemanticFacet.OFFER]),
            ],
        )
        return [("target_a", c1), ("target_b", c2)]

    def test_two_pipelines_produce_independent_run_ids(self) -> None:
        """Compiling the same targets under two pipelines yields distinct run_ids."""
        shared = self._make_shared_target_contracts()

        result_one = compile_run_contract("pl-scope-1", "run-001", shared)
        result_two = compile_run_contract("pl-scope-2", "run-002", shared)

        assert result_one.run_id == "run-001"
        assert result_two.run_id == "run-002"
        assert result_one.run_id != result_two.run_id

    def test_two_pipelines_produce_separate_objects(self) -> None:
        """Each compile call returns a distinct CompiledRunContract object."""
        shared = self._make_shared_target_contracts()

        result_one = compile_run_contract("pl-scope-1", "run-001", shared)
        result_two = compile_run_contract("pl-scope-2", "run-002", shared)

        assert result_one is not result_two
        assert result_one.inputs is not result_two.inputs

    def test_no_shared_mutable_state_between_runs(self) -> None:
        """Mutating one compiled contract's inputs list does not affect the other."""
        shared = self._make_shared_target_contracts()

        result_one = compile_run_contract("pl-scope-mut", "run-m1", shared)
        result_two = compile_run_contract("pl-scope-mut", "run-m2", shared)

        # Record original input IDs from result_two before any mutation.
        original_two_ids = [ci.id for ci in result_two.inputs]

        # Mutate result_one's inputs list in place.
        result_one.inputs.clear()

        # result_two must be completely unaffected.
        assert [ci.id for ci in result_two.inputs] == original_two_ids
        assert len(result_one.inputs) == 0

    def test_producer_consumer_mapping_is_run_scoped(self) -> None:
        """Each pipeline's producer-consumer mapping is independent even when
        the same target contracts are compiled in different pipeline contexts.
        """
        shared = self._make_shared_target_contracts()

        result_one = compile_run_contract("pl-pc-scope-1", "run-pc-1", shared)
        result_two = compile_run_contract("pl-pc-scope-2", "run-pc-2", shared)

        # Both contracts compile the same targets — producer mappings should
        # be functionally equivalent but housed in separate objects.
        producer_map_one = {
            ci.id: ci.producer_mapping for ci in result_one.inputs
        }
        producer_map_two = {
            ci.id: ci.producer_mapping for ci in result_two.inputs
        }

        # Same logical content (same inputs/outputs compiled from same sources)…
        assert producer_map_one == producer_map_two

        # …but the dicts are separate objects, not the same reference.
        assert producer_map_one is not producer_map_two
