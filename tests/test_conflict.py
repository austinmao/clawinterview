"""Tests for ClawInterview conflict detection module (T031).

Covers detect_conflicts and attempt_repair across EXACT_MATCH,
COMPATIBLE_REFINEMENT, and INCOMPATIBLE severities, plus integration
with the compiler for incompatible conflict raising.
"""

from __future__ import annotations

import pytest

from clawinterview.compiler import compile_run_contract
from clawinterview.conflict import attempt_repair, detect_conflicts
from clawinterview.models import (
    CompiledInput,
    ConflictSeverity,
    InputSpec,
    InterviewContract,
    PrimitiveType,
    ResolverKind,
    SemanticFacet,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_compiled_input(
    id: str,
    original_id: str,
    owner: str,
    type: PrimitiveType = PrimitiveType.STRING,
    facets: list[SemanticFacet] | None = None,
    strategies: list[ResolverKind] | None = None,
) -> CompiledInput:
    return CompiledInput(
        id=id,
        original_id=original_id,
        owner_target=owner,
        type=type,
        facets=facets or [],
        resolution_strategies=strategies or [],
        confidence_threshold=0.7,
        blocking=True,
    )


def _make_input_spec(
    id: str,
    type: PrimitiveType = PrimitiveType.STRING,
    facets: list[SemanticFacet] | None = None,
    strategies: list[ResolverKind] | None = None,
) -> InputSpec:
    return InputSpec(
        id=id,
        type=type,
        description=f"Input {id}",
        facets=facets or [],
        resolution_strategies=strategies or [],
        confidence_threshold=0.7,
    )


def _make_contract(
    required: list[InputSpec] | None = None,
    optional: list[InputSpec] | None = None,
) -> InterviewContract:
    return InterviewContract(
        required_inputs=required or [],
        optional_inputs=optional or [],
    )


# ---------------------------------------------------------------------------
# 1. Exact match (same type, same facets from 2 targets) — no conflict reported
# ---------------------------------------------------------------------------


class TestExactMatch:
    def test_no_conflict_when_type_and_facets_identical(self) -> None:
        inputs = [
            _make_compiled_input(
                "t1.audience",
                "audience",
                "t1",
                PrimitiveType.STRING,
                [SemanticFacet.AUDIENCE],
            ),
            _make_compiled_input(
                "t2.audience",
                "audience",
                "t2",
                PrimitiveType.STRING,
                [SemanticFacet.AUDIENCE],
            ),
        ]
        reports = detect_conflicts(inputs)
        assert reports == []

    def test_no_conflict_for_same_type_empty_facets_both(self) -> None:
        inputs = [
            _make_compiled_input("t1.name", "name", "t1", PrimitiveType.STRING),
            _make_compiled_input("t2.name", "name", "t2", PrimitiveType.STRING),
        ]
        reports = detect_conflicts(inputs)
        assert reports == []

    def test_no_conflict_for_single_owner_input(self) -> None:
        inputs = [
            _make_compiled_input("audience", "audience", "t1", PrimitiveType.STRING),
        ]
        reports = detect_conflicts(inputs)
        assert reports == []

    def test_no_conflict_for_different_original_ids(self) -> None:
        inputs = [
            _make_compiled_input("audience", "audience", "t1", PrimitiveType.STRING),
            _make_compiled_input("offer", "offer", "t2", PrimitiveType.NUMBER),
        ]
        reports = detect_conflicts(inputs)
        assert reports == []


# ---------------------------------------------------------------------------
# 2. Compatible refinement (same type, different facets)
# ---------------------------------------------------------------------------


class TestCompatibleRefinement:
    def test_compatible_refinement_reported_for_same_type_different_facets(self) -> None:
        inputs = [
            _make_compiled_input(
                "t1.brand",
                "brand",
                "t1",
                PrimitiveType.STRING,
                [SemanticFacet.BRAND],
            ),
            _make_compiled_input(
                "t2.brand",
                "brand",
                "t2",
                PrimitiveType.STRING,
                [SemanticFacet.BRAND, SemanticFacet.AUDIENCE],
            ),
        ]
        reports = detect_conflicts(inputs)
        assert len(reports) == 1
        assert reports[0].severity == ConflictSeverity.COMPATIBLE_REFINEMENT

    def test_report_contains_both_owner_targets(self) -> None:
        inputs = [
            _make_compiled_input(
                "t1.offer",
                "offer",
                "t1",
                PrimitiveType.STRING,
                [SemanticFacet.OFFER],
            ),
            _make_compiled_input(
                "t2.offer",
                "offer",
                "t2",
                PrimitiveType.STRING,
                [SemanticFacet.OFFER, SemanticFacet.CTA],
            ),
        ]
        reports = detect_conflicts(inputs)
        assert len(reports) == 1
        assert set(reports[0].owner_targets) == {"t1", "t2"}

    def test_report_contains_both_compiled_input_ids(self) -> None:
        inputs = [
            _make_compiled_input(
                "t1.schedule",
                "schedule",
                "t1",
                PrimitiveType.DATE,
                [SemanticFacet.SCHEDULE],
            ),
            _make_compiled_input(
                "t2.schedule",
                "schedule",
                "t2",
                PrimitiveType.DATE,
                [SemanticFacet.SCHEDULE, SemanticFacet.TIMELINE],
            ),
        ]
        reports = detect_conflicts(inputs)
        assert len(reports) == 1
        assert set(reports[0].input_ids) == {"t1.schedule", "t2.schedule"}

    def test_compatible_refinement_resolution_suggestion_present(self) -> None:
        inputs = [
            _make_compiled_input(
                "t1.brand",
                "brand",
                "t1",
                PrimitiveType.STRING,
                [SemanticFacet.BRAND],
            ),
            _make_compiled_input(
                "t2.brand",
                "brand",
                "t2",
                PrimitiveType.STRING,
                [SemanticFacet.AUDIENCE],
            ),
        ]
        reports = detect_conflicts(inputs)
        assert reports[0].resolution is not None
        assert len(reports[0].resolution) > 0


# ---------------------------------------------------------------------------
# 3. Incompatible (different types)
# ---------------------------------------------------------------------------


class TestIncompatibleConflict:
    def test_incompatible_reported_for_different_types(self) -> None:
        inputs = [
            _make_compiled_input(
                "t1.budget",
                "budget",
                "t1",
                PrimitiveType.NUMBER,
            ),
            _make_compiled_input(
                "t2.budget",
                "budget",
                "t2",
                PrimitiveType.STRING,
            ),
        ]
        reports = detect_conflicts(inputs)
        assert len(reports) == 1
        assert reports[0].severity == ConflictSeverity.INCOMPATIBLE

    def test_incompatible_report_has_no_resolution_suggestion(self) -> None:
        inputs = [
            _make_compiled_input("t1.date", "date", "t1", PrimitiveType.DATE),
            _make_compiled_input("t2.date", "date", "t2", PrimitiveType.BOOLEAN),
        ]
        reports = detect_conflicts(inputs)
        assert reports[0].resolution is None

    def test_incompatible_report_description_names_both_types(self) -> None:
        inputs = [
            _make_compiled_input("t1.count", "count", "t1", PrimitiveType.NUMBER),
            _make_compiled_input("t2.count", "count", "t2", PrimitiveType.STRING),
        ]
        reports = detect_conflicts(inputs)
        description = reports[0].description
        assert "number" in description.lower() or "string" in description.lower()

    def test_incompatible_report_names_both_owner_targets(self) -> None:
        inputs = [
            _make_compiled_input("alpha.item", "item", "alpha", PrimitiveType.NUMBER),
            _make_compiled_input("beta.item", "item", "beta", PrimitiveType.URL),
        ]
        reports = detect_conflicts(inputs)
        assert "alpha" in reports[0].description
        assert "beta" in reports[0].description


# ---------------------------------------------------------------------------
# 4. attempt_repair on compatible → returns merged CompiledInput
# ---------------------------------------------------------------------------


class TestAttemptRepairCompatible:
    def test_returns_compiled_input(self) -> None:
        inputs = [
            _make_compiled_input(
                "t1.brand",
                "brand",
                "t1",
                PrimitiveType.STRING,
                [SemanticFacet.BRAND],
            ),
            _make_compiled_input(
                "t2.brand",
                "brand",
                "t2",
                PrimitiveType.STRING,
                [SemanticFacet.AUDIENCE],
            ),
        ]
        reports = detect_conflicts(inputs)
        assert len(reports) == 1
        repaired = attempt_repair(reports[0], inputs)
        assert repaired is not None
        assert isinstance(repaired, CompiledInput)

    def test_merged_input_contains_all_facets(self) -> None:
        inputs = [
            _make_compiled_input(
                "t1.brand",
                "brand",
                "t1",
                PrimitiveType.STRING,
                [SemanticFacet.BRAND],
            ),
            _make_compiled_input(
                "t2.brand",
                "brand",
                "t2",
                PrimitiveType.STRING,
                [SemanticFacet.AUDIENCE],
            ),
        ]
        reports = detect_conflicts(inputs)
        repaired = attempt_repair(reports[0], inputs)
        assert repaired is not None
        assert SemanticFacet.BRAND in repaired.facets
        assert SemanticFacet.AUDIENCE in repaired.facets

    def test_merged_input_has_merged_owner_target(self) -> None:
        inputs = [
            _make_compiled_input(
                "t1.offer",
                "offer",
                "t1",
                PrimitiveType.STRING,
                [SemanticFacet.OFFER],
            ),
            _make_compiled_input(
                "t2.offer",
                "offer",
                "t2",
                PrimitiveType.STRING,
                [SemanticFacet.CTA],
            ),
        ]
        reports = detect_conflicts(inputs)
        repaired = attempt_repair(reports[0], inputs)
        assert repaired is not None
        assert repaired.owner_target == "merged"

    def test_merged_input_type_preserved(self) -> None:
        inputs = [
            _make_compiled_input(
                "t1.schedule",
                "schedule",
                "t1",
                PrimitiveType.DATE,
                [SemanticFacet.SCHEDULE],
            ),
            _make_compiled_input(
                "t2.schedule",
                "schedule",
                "t2",
                PrimitiveType.DATE,
                [SemanticFacet.TIMELINE],
            ),
        ]
        reports = detect_conflicts(inputs)
        repaired = attempt_repair(reports[0], inputs)
        assert repaired is not None
        assert repaired.type == PrimitiveType.DATE

    def test_merged_facets_are_deduplicated(self) -> None:
        """Same facet from both targets appears only once in merged output."""
        inputs = [
            _make_compiled_input(
                "t1.brand",
                "brand",
                "t1",
                PrimitiveType.STRING,
                [SemanticFacet.BRAND, SemanticFacet.OFFER],
            ),
            _make_compiled_input(
                "t2.brand",
                "brand",
                "t2",
                PrimitiveType.STRING,
                [SemanticFacet.BRAND, SemanticFacet.CTA],
            ),
        ]
        reports = detect_conflicts(inputs)
        repaired = attempt_repair(reports[0], inputs)
        assert repaired is not None
        brand_count = repaired.facets.count(SemanticFacet.BRAND)
        assert brand_count == 1

    def test_merged_strategies_combined(self) -> None:
        inputs = [
            _make_compiled_input(
                "t1.brand",
                "brand",
                "t1",
                PrimitiveType.STRING,
                [SemanticFacet.BRAND],
                [ResolverKind.USER_ARGS],
            ),
            _make_compiled_input(
                "t2.brand",
                "brand",
                "t2",
                PrimitiveType.STRING,
                [SemanticFacet.AUDIENCE],
                [ResolverKind.MEMORY],
            ),
        ]
        reports = detect_conflicts(inputs)
        repaired = attempt_repair(reports[0], inputs)
        assert repaired is not None
        assert ResolverKind.USER_ARGS in repaired.resolution_strategies
        assert ResolverKind.MEMORY in repaired.resolution_strategies


# ---------------------------------------------------------------------------
# 5. attempt_repair on incompatible → returns None
# ---------------------------------------------------------------------------


class TestAttemptRepairIncompatible:
    def test_returns_none_for_incompatible(self) -> None:
        inputs = [
            _make_compiled_input("t1.count", "count", "t1", PrimitiveType.NUMBER),
            _make_compiled_input("t2.count", "count", "t2", PrimitiveType.STRING),
        ]
        reports = detect_conflicts(inputs)
        assert len(reports) == 1
        assert reports[0].severity == ConflictSeverity.INCOMPATIBLE
        result = attempt_repair(reports[0], inputs)
        assert result is None

    def test_returns_none_for_different_type_with_facets(self) -> None:
        inputs = [
            _make_compiled_input(
                "t1.date",
                "date",
                "t1",
                PrimitiveType.DATE,
                [SemanticFacet.SCHEDULE],
            ),
            _make_compiled_input(
                "t2.date",
                "date",
                "t2",
                PrimitiveType.BOOLEAN,
                [SemanticFacet.COMPLIANCE],
            ),
        ]
        reports = detect_conflicts(inputs)
        result = attempt_repair(reports[0], inputs)
        assert result is None


# ---------------------------------------------------------------------------
# 6. Integration: compiler with conflicting inputs raises ValueError
# ---------------------------------------------------------------------------


class TestCompilerConflictIntegration:
    def test_incompatible_types_raise_value_error(self) -> None:
        c1 = _make_contract(
            required=[_make_input_spec("budget", PrimitiveType.NUMBER)]
        )
        c2 = _make_contract(
            required=[_make_input_spec("budget", PrimitiveType.STRING)]
        )
        with pytest.raises(ValueError, match="[Ii]ncompatible"):
            compile_run_contract(
                "pl-conflict",
                "run-conflict",
                [("finance_target", c1), ("copy_target", c2)],
            )

    def test_error_message_identifies_targets(self) -> None:
        c1 = _make_contract(
            required=[_make_input_spec("count", PrimitiveType.NUMBER)]
        )
        c2 = _make_contract(
            required=[_make_input_spec("count", PrimitiveType.STRING)]
        )
        with pytest.raises(ValueError) as exc_info:
            compile_run_contract(
                "pl-err-msg",
                "run-err-msg",
                [("target_alpha", c1), ("target_beta", c2)],
            )
        error_text = str(exc_info.value)
        assert "target_alpha" in error_text or "target_beta" in error_text

    def test_compatible_refinement_does_not_raise(self) -> None:
        """Same type + different facets should compile without raising."""
        c1 = _make_contract(
            required=[
                _make_input_spec("brand", PrimitiveType.STRING, [SemanticFacet.BRAND])
            ]
        )
        c2 = _make_contract(
            required=[
                _make_input_spec("brand", PrimitiveType.STRING, [SemanticFacet.AUDIENCE])
            ]
        )
        # Should not raise.
        result = compile_run_contract(
            "pl-compat",
            "run-compat",
            [("t1", c1), ("t2", c2)],
        )
        assert result is not None

    def test_compatible_refinement_produces_merged_input(self) -> None:
        """After repair the compiler should include a merged input."""
        c1 = _make_contract(
            required=[
                _make_input_spec("offer", PrimitiveType.STRING, [SemanticFacet.OFFER])
            ]
        )
        c2 = _make_contract(
            required=[
                _make_input_spec("offer", PrimitiveType.STRING, [SemanticFacet.CTA])
            ]
        )
        result = compile_run_contract(
            "pl-merged",
            "run-merged",
            [("t1", c1), ("t2", c2)],
        )
        # The two per-target qualified inputs are removed; merged input added.
        merged = [inp for inp in result.inputs if inp.owner_target == "merged"]
        assert len(merged) == 1
        assert SemanticFacet.OFFER in merged[0].facets
        assert SemanticFacet.CTA in merged[0].facets

    def test_conflicts_stored_in_contract(self) -> None:
        """ConflictReports should be serialized into compiled contract."""
        c1 = _make_contract(
            required=[
                _make_input_spec("brand", PrimitiveType.STRING, [SemanticFacet.BRAND])
            ]
        )
        c2 = _make_contract(
            required=[
                _make_input_spec("brand", PrimitiveType.STRING, [SemanticFacet.AUDIENCE])
            ]
        )
        result = compile_run_contract(
            "pl-stored",
            "run-stored",
            [("t1", c1), ("t2", c2)],
        )
        assert len(result.conflicts) == 1
        assert result.conflicts[0]["severity"] == ConflictSeverity.COMPATIBLE_REFINEMENT

    def test_exact_match_no_conflict_stored(self) -> None:
        """Exact matches produce no conflict reports in the contract."""
        c1 = _make_contract(
            required=[
                _make_input_spec("audience", PrimitiveType.STRING, [SemanticFacet.AUDIENCE])
            ]
        )
        c2 = _make_contract(
            required=[
                _make_input_spec("audience", PrimitiveType.STRING, [SemanticFacet.AUDIENCE])
            ]
        )
        result = compile_run_contract(
            "pl-exact",
            "run-exact",
            [("t1", c1), ("t2", c2)],
        )
        assert result.conflicts == []

    def test_unique_inputs_pass_through_without_conflicts(self) -> None:
        """Inputs with unique IDs across targets produce no conflicts."""
        c1 = _make_contract(required=[_make_input_spec("audience", PrimitiveType.STRING)])
        c2 = _make_contract(required=[_make_input_spec("offer", PrimitiveType.STRING)])
        result = compile_run_contract(
            "pl-unique",
            "run-unique",
            [("t1", c1), ("t2", c2)],
        )
        assert result.conflicts == []
        assert len(result.inputs) == 2
