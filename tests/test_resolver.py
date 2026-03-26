"""Tests for ClawInterview resolver registry and resolution pipeline.

Covers: ResolverRegistry registration/lookup, MANDATORY_PRECEDENCE ordering,
user_args extraction, graceful skip of unregistered resolvers, UNRESOLVED
fallback, confidence threshold gating, exception handling, and check_freshness.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pytest

from clawinterview.models import (
    InputResolution,
    InputSpec,
    PrimitiveType,
    ResolutionContext,
    ResolutionResult,
    ResolutionStatus,
    ResolverKind,
    SemanticFacet,
)
from clawinterview.resolver import (
    MANDATORY_PRECEDENCE,
    ResolverRegistry,
    check_freshness,
    resolve_input,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_input(
    id: str = "test_field",
    type: PrimitiveType = PrimitiveType.STRING,
    confidence_threshold: float = 0.7,
    resolution_strategies: list[ResolverKind] | None = None,
    freshness_policy: str | None = None,
) -> InputSpec:
    return InputSpec(
        id=id,
        type=type,
        description=f"Test input {id}",
        confidence_threshold=confidence_threshold,
        resolution_strategies=resolution_strategies or [],
        freshness_policy=freshness_policy,
    )


def make_context(pipeline_args: dict | None = None) -> ResolutionContext:
    return ResolutionContext(pipeline_args=pipeline_args or {})


def make_result(
    value: object,
    confidence: float = 0.9,
    evidence_source: str = "test",
    kind: ResolverKind = ResolverKind.USER_ARGS,
) -> ResolutionResult:
    return ResolutionResult(
        value=value,
        confidence=confidence,
        evidence_source=evidence_source,
        resolver_kind=kind,
    )


def make_resolution(
    input_id: str = "test_field",
    status: ResolutionStatus = ResolutionStatus.RESOLVED,
    resolved_at: str | None = None,
) -> InputResolution:
    return InputResolution(
        input_id=input_id,
        status=status,
        resolved_at=resolved_at,
    )


# ---------------------------------------------------------------------------
# 1. Registry registration — register a resolver, get it back
# ---------------------------------------------------------------------------


class TestRegistryRegistration:
    def test_register_and_get_resolver(self) -> None:
        registry = ResolverRegistry()
        fn = lambda spec, ctx: None
        registry.register(ResolverKind.USER_ARGS, fn)
        assert registry.get(ResolverKind.USER_ARGS) is fn

    def test_registered_kind_appears_in_available(self) -> None:
        registry = ResolverRegistry()
        registry.register(ResolverKind.MEMORY, lambda s, c: None)
        assert ResolverKind.MEMORY in registry.available_kinds()

    def test_overwrite_existing_resolver(self) -> None:
        registry = ResolverRegistry()
        fn_a = lambda spec, ctx: None
        fn_b = lambda spec, ctx: None
        registry.register(ResolverKind.INFER, fn_a)
        registry.register(ResolverKind.INFER, fn_b)
        assert registry.get(ResolverKind.INFER) is fn_b


# ---------------------------------------------------------------------------
# 2. Registry get unknown — returns None
# ---------------------------------------------------------------------------


class TestRegistryGetUnknown:
    def test_get_unregistered_kind_returns_none(self) -> None:
        registry = ResolverRegistry()
        assert registry.get(ResolverKind.WEB) is None

    def test_empty_registry_available_kinds_is_empty(self) -> None:
        registry = ResolverRegistry()
        assert registry.available_kinds() == []


# ---------------------------------------------------------------------------
# 3. Precedence order enforcement — user_args tried before memory
# ---------------------------------------------------------------------------


class TestPrecedenceOrderEnforcement:
    def test_user_args_precedes_memory_in_mandatory_order(self) -> None:
        user_args_idx = list(MANDATORY_PRECEDENCE).index(ResolverKind.USER_ARGS)
        memory_idx = list(MANDATORY_PRECEDENCE).index(ResolverKind.MEMORY)
        assert user_args_idx < memory_idx

    def test_user_args_resolver_wins_over_memory(self) -> None:
        """When both user_args and memory resolvers are registered and the
        input spec specifies both strategies, user_args should win."""
        registry = ResolverRegistry()
        call_order: list[str] = []

        def user_args_fn(spec: InputSpec, ctx: ResolutionContext) -> ResolutionResult:
            call_order.append("user_args")
            return make_result("from_user_args", confidence=0.95, kind=ResolverKind.USER_ARGS)

        def memory_fn(spec: InputSpec, ctx: ResolutionContext) -> ResolutionResult:
            call_order.append("memory")
            return make_result("from_memory", confidence=0.95, kind=ResolverKind.MEMORY)

        registry.register(ResolverKind.USER_ARGS, user_args_fn)
        registry.register(ResolverKind.MEMORY, memory_fn)

        spec = make_input(
            resolution_strategies=[ResolverKind.MEMORY, ResolverKind.USER_ARGS]
        )
        result = resolve_input(registry, spec, make_context())

        assert result.status == ResolutionStatus.RESOLVED
        assert result.resolved_value == "from_user_args"
        # memory should never have been called once user_args resolved
        assert call_order == ["user_args"]


# ---------------------------------------------------------------------------
# 4. user_args resolver — extracts from pipeline_args dict
# ---------------------------------------------------------------------------


class TestUserArgsResolver:
    def test_extracts_value_from_pipeline_args(self) -> None:
        registry = ResolverRegistry()

        def user_args_fn(spec: InputSpec, ctx: ResolutionContext) -> ResolutionResult | None:
            value = ctx.pipeline_args.get(spec.id)
            if value is None:
                return None
            return make_result(value, confidence=1.0, kind=ResolverKind.USER_ARGS)

        registry.register(ResolverKind.USER_ARGS, user_args_fn)

        spec = make_input(id="campaign_name", resolution_strategies=[ResolverKind.USER_ARGS])
        ctx = make_context(pipeline_args={"campaign_name": "Spring Launch"})
        resolution = resolve_input(registry, spec, ctx)

        assert resolution.status == ResolutionStatus.RESOLVED
        assert resolution.resolved_value == "Spring Launch"
        assert resolution.resolver_used == ResolverKind.USER_ARGS

    def test_returns_unresolved_when_key_absent(self) -> None:
        registry = ResolverRegistry()

        def user_args_fn(spec: InputSpec, ctx: ResolutionContext) -> ResolutionResult | None:
            value = ctx.pipeline_args.get(spec.id)
            if value is None:
                return None
            return make_result(value, confidence=1.0, kind=ResolverKind.USER_ARGS)

        registry.register(ResolverKind.USER_ARGS, user_args_fn)

        spec = make_input(id="missing_key", resolution_strategies=[ResolverKind.USER_ARGS])
        resolution = resolve_input(registry, spec, make_context())

        assert resolution.status == ResolutionStatus.UNRESOLVED


# ---------------------------------------------------------------------------
# 5. Graceful skip on unavailable resolver — doesn't crash
# ---------------------------------------------------------------------------


class TestGracefulSkipOnUnavailableResolver:
    def test_unregistered_resolver_in_strategy_is_skipped(self) -> None:
        registry = ResolverRegistry()
        # Strategy lists RAG and WEB but neither is registered
        spec = make_input(
            resolution_strategies=[ResolverKind.RAG, ResolverKind.WEB]
        )
        # Should not raise; should return UNRESOLVED
        resolution = resolve_input(registry, spec, make_context())
        assert resolution.status == ResolutionStatus.UNRESOLVED

    def test_skipped_resolver_does_not_prevent_later_resolver(self) -> None:
        registry = ResolverRegistry()

        def infer_fn(spec: InputSpec, ctx: ResolutionContext) -> ResolutionResult:
            return make_result("inferred", confidence=0.85, kind=ResolverKind.INFER)

        registry.register(ResolverKind.INFER, infer_fn)
        # RAG not registered; INFER is — INFER should still resolve
        spec = make_input(
            resolution_strategies=[ResolverKind.RAG, ResolverKind.INFER]
        )
        resolution = resolve_input(registry, spec, make_context())
        assert resolution.status == ResolutionStatus.RESOLVED
        assert resolution.resolver_used == ResolverKind.INFER


# ---------------------------------------------------------------------------
# 6. Never fabricate value on failure — all resolvers return None → UNRESOLVED
# ---------------------------------------------------------------------------


class TestNeverFabricateOnFailure:
    def test_all_none_resolvers_produce_unresolved(self) -> None:
        registry = ResolverRegistry()
        # Register resolvers that all return None
        for kind in (ResolverKind.USER_ARGS, ResolverKind.MEMORY, ResolverKind.INFER):
            registry.register(kind, lambda spec, ctx: None)

        spec = make_input(
            resolution_strategies=[
                ResolverKind.USER_ARGS,
                ResolverKind.MEMORY,
                ResolverKind.INFER,
            ]
        )
        resolution = resolve_input(registry, spec, make_context())
        assert resolution.status == ResolutionStatus.UNRESOLVED
        assert resolution.resolved_value is None
        assert resolution.resolver_used is None

    def test_unresolved_has_zero_confidence(self) -> None:
        registry = ResolverRegistry()
        spec = make_input(resolution_strategies=[ResolverKind.ASK])
        resolution = resolve_input(registry, spec, make_context())
        assert resolution.confidence == 0.0


# ---------------------------------------------------------------------------
# 7. Confidence threshold — low confidence result falls through to UNRESOLVED
# ---------------------------------------------------------------------------


class TestConfidenceThreshold:
    def test_below_threshold_result_is_not_used(self) -> None:
        registry = ResolverRegistry()

        # Returns confidence 0.3, but threshold is 0.7 — should be rejected
        def low_conf_fn(spec: InputSpec, ctx: ResolutionContext) -> ResolutionResult:
            return make_result("low_quality_value", confidence=0.3, kind=ResolverKind.INFER)

        registry.register(ResolverKind.INFER, low_conf_fn)
        spec = make_input(confidence_threshold=0.7, resolution_strategies=[ResolverKind.INFER])
        resolution = resolve_input(registry, spec, make_context())

        assert resolution.status == ResolutionStatus.UNRESOLVED

    def test_exactly_at_threshold_is_accepted(self) -> None:
        registry = ResolverRegistry()

        def exact_threshold_fn(spec: InputSpec, ctx: ResolutionContext) -> ResolutionResult:
            return make_result("exact", confidence=0.7, kind=ResolverKind.INFER)

        registry.register(ResolverKind.INFER, exact_threshold_fn)
        spec = make_input(confidence_threshold=0.7, resolution_strategies=[ResolverKind.INFER])
        resolution = resolve_input(registry, spec, make_context())

        assert resolution.status == ResolutionStatus.RESOLVED
        assert resolution.resolved_value == "exact"

    def test_above_threshold_is_accepted(self) -> None:
        registry = ResolverRegistry()

        def high_conf_fn(spec: InputSpec, ctx: ResolutionContext) -> ResolutionResult:
            return make_result("good_value", confidence=0.95, kind=ResolverKind.USER_ARGS)

        registry.register(ResolverKind.USER_ARGS, high_conf_fn)
        spec = make_input(confidence_threshold=0.7, resolution_strategies=[ResolverKind.USER_ARGS])
        resolution = resolve_input(registry, spec, make_context())

        assert resolution.status == ResolutionStatus.RESOLVED

    def test_low_conf_first_resolver_falls_through_to_high_conf_second(self) -> None:
        registry = ResolverRegistry()

        def rag_fn(spec: InputSpec, ctx: ResolutionContext) -> ResolutionResult:
            return make_result("rag_value", confidence=0.3, kind=ResolverKind.RAG)

        def infer_fn(spec: InputSpec, ctx: ResolutionContext) -> ResolutionResult:
            return make_result("infer_value", confidence=0.95, kind=ResolverKind.INFER)

        registry.register(ResolverKind.RAG, rag_fn)
        registry.register(ResolverKind.INFER, infer_fn)
        spec = make_input(
            confidence_threshold=0.7,
            resolution_strategies=[ResolverKind.RAG, ResolverKind.INFER],
        )
        resolution = resolve_input(registry, spec, make_context())

        assert resolution.status == ResolutionStatus.RESOLVED
        assert resolution.resolver_used == ResolverKind.INFER
        assert resolution.resolved_value == "infer_value"


# ---------------------------------------------------------------------------
# 8. Resolver exception handling — exception caught and logged, not propagated
# ---------------------------------------------------------------------------


class TestResolverExceptionHandling:
    def test_raising_resolver_does_not_propagate(self) -> None:
        registry = ResolverRegistry()

        def broken_fn(spec: InputSpec, ctx: ResolutionContext) -> ResolutionResult:
            raise RuntimeError("resolver exploded")

        registry.register(ResolverKind.WEB, broken_fn)
        spec = make_input(resolution_strategies=[ResolverKind.WEB])

        # Should not raise; exception is caught internally
        resolution = resolve_input(registry, spec, make_context())
        assert resolution.status == ResolutionStatus.UNRESOLVED

    def test_exception_in_first_resolver_allows_second_to_run(self) -> None:
        registry = ResolverRegistry()

        def broken_fn(spec: InputSpec, ctx: ResolutionContext) -> ResolutionResult:
            raise ValueError("boom")

        def good_fn(spec: InputSpec, ctx: ResolutionContext) -> ResolutionResult:
            return make_result("fallback_value", confidence=0.9, kind=ResolverKind.INFER)

        registry.register(ResolverKind.RAG, broken_fn)
        registry.register(ResolverKind.INFER, good_fn)

        spec = make_input(
            resolution_strategies=[ResolverKind.RAG, ResolverKind.INFER]
        )
        resolution = resolve_input(registry, spec, make_context())

        assert resolution.status == ResolutionStatus.RESOLVED
        assert resolution.resolved_value == "fallback_value"
        assert resolution.resolver_used == ResolverKind.INFER

    def test_exception_is_logged_at_error_level(self, caplog: pytest.LogCaptureFixture) -> None:
        registry = ResolverRegistry()
        err = RuntimeError("log_this_error")

        def raising_fn(spec: InputSpec, ctx: ResolutionContext) -> ResolutionResult:
            raise err

        registry.register(ResolverKind.WEB, raising_fn)
        spec = make_input(id="logged_input", resolution_strategies=[ResolverKind.WEB])

        with caplog.at_level(logging.ERROR, logger="clawinterview.resolver"):
            resolve_input(registry, spec, make_context())

        assert any("resolver_error" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# 9. check_freshness — 24h policy, recent (True), old (False), any (True)
# ---------------------------------------------------------------------------


class TestCheckFreshness:
    def test_recent_resolution_within_24h_is_fresh(self) -> None:
        # Resolved 1 hour ago — well within 24h window
        resolved_at = (datetime.now(tz=timezone.utc) - timedelta(hours=1)).isoformat()
        resolution = make_resolution(resolved_at=resolved_at)
        spec = make_input(freshness_policy="24h")
        assert check_freshness(resolution, spec) is True

    def test_old_resolution_beyond_24h_is_stale(self) -> None:
        # Resolved 25 hours ago — outside 24h window
        resolved_at = (datetime.now(tz=timezone.utc) - timedelta(hours=25)).isoformat()
        resolution = make_resolution(resolved_at=resolved_at)
        spec = make_input(freshness_policy="24h")
        assert check_freshness(resolution, spec) is False

    def test_any_policy_is_always_fresh(self) -> None:
        # Resolved very long ago — but "any" policy means always fresh
        resolved_at = (datetime.now(tz=timezone.utc) - timedelta(days=365)).isoformat()
        resolution = make_resolution(resolved_at=resolved_at)
        spec = make_input(freshness_policy="any")
        assert check_freshness(resolution, spec) is True

    def test_no_policy_is_always_fresh(self) -> None:
        resolution = make_resolution(resolved_at=None)
        spec = make_input(freshness_policy=None)
        assert check_freshness(resolution, spec) is True

    def test_days_policy_recent_is_fresh(self) -> None:
        resolved_at = (datetime.now(tz=timezone.utc) - timedelta(hours=1)).isoformat()
        resolution = make_resolution(resolved_at=resolved_at)
        spec = make_input(freshness_policy="7d")
        assert check_freshness(resolution, spec) is True

    def test_days_policy_old_is_stale(self) -> None:
        resolved_at = (datetime.now(tz=timezone.utc) - timedelta(days=8)).isoformat()
        resolution = make_resolution(resolved_at=resolved_at)
        spec = make_input(freshness_policy="7d")
        assert check_freshness(resolution, spec) is False

    def test_no_resolved_at_timestamp_with_24h_policy_returns_false(self) -> None:
        resolution = make_resolution(resolved_at=None)
        spec = make_input(freshness_policy="24h")
        assert check_freshness(resolution, spec) is False

    def test_exactly_at_boundary_is_fresh(self) -> None:
        # 1 second before the 24h boundary — should still be fresh (age <= delta)
        resolved_at = (
            datetime.now(tz=timezone.utc) - timedelta(hours=24) + timedelta(seconds=1)
        ).isoformat()
        resolution = make_resolution(resolved_at=resolved_at)
        spec = make_input(freshness_policy="24h")
        assert check_freshness(resolution, spec) is True
