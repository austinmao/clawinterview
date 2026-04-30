"""ClawInterview resolver registry and resolution pipeline.

Implements the multi-strategy input resolution system. Resolvers are
registered by kind and tried in MANDATORY_PRECEDENCE order. The first
result meeting the input's confidence_threshold wins; unresolved inputs
return an UNRESOLVED InputResolution.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from clawinterview.models import (
    InputResolution,
    InputSpec,
    ResolutionContext,
    ResolutionResult,
    ResolutionStatus,
    ResolverKind,
)

logger = logging.getLogger("clawinterview.resolver")

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

ResolverFn = Callable[[InputSpec, ResolutionContext], ResolutionResult | None]

# ---------------------------------------------------------------------------
# Mandatory precedence order
# ---------------------------------------------------------------------------

MANDATORY_PRECEDENCE: tuple[ResolverKind, ...] = (
    ResolverKind.USER_ARGS,
    ResolverKind.USER_MESSAGE,
    ResolverKind.HYPERSPELL_PROFILE,
    ResolverKind.PIPELINE_STATE,
    ResolverKind.MEMORY,
    ResolverKind.TENANT_FILE,
    ResolverKind.UPSTREAM_OUTPUT,
    ResolverKind.RAG,
    ResolverKind.WEB,
    ResolverKind.INFER,
    ResolverKind.ASK,
)

_PRECEDENCE_INDEX: dict[ResolverKind, int] = {
    kind: idx for idx, kind in enumerate(MANDATORY_PRECEDENCE)
}


# ---------------------------------------------------------------------------
# ResolverRegistry
# ---------------------------------------------------------------------------


class ResolverRegistry:
    def __init__(self) -> None:
        self._resolvers: dict[ResolverKind, ResolverFn] = {}

    def register(self, kind: ResolverKind, resolver_fn: ResolverFn) -> None:
        """Register a resolver function for a given kind."""
        self._resolvers[kind] = resolver_fn

    def get(self, kind: ResolverKind) -> ResolverFn | None:
        """Get resolver function by kind, or None if not registered."""
        return self._resolvers.get(kind)

    def available_kinds(self) -> list[ResolverKind]:
        """Return list of registered resolver kinds."""
        return list(self._resolvers.keys())


# ---------------------------------------------------------------------------
# Resolution pipeline
# ---------------------------------------------------------------------------


def resolve_input(
    registry: ResolverRegistry,
    input_spec: InputSpec,
    context: ResolutionContext,
    strategies: list[ResolverKind] | None = None,
) -> InputResolution:
    """Attempt to resolve a single input by trying each strategy in order.

    Strategy selection priority:
      1. ``strategies`` argument (if provided)
      2. ``input_spec.resolution_strategies`` (if non-empty)
      3. ``MANDATORY_PRECEDENCE`` (fallback)

    Selected strategies are reordered to match MANDATORY_PRECEDENCE. Any
    strategy not present in the precedence list is appended at the end in
    the order they appear.
    """
    input_id = input_spec.id
    threshold = input_spec.confidence_threshold

    # Determine candidate strategy list
    raw_strategies: list[ResolverKind]
    if strategies is not None:
        raw_strategies = list(strategies)
    elif input_spec.resolution_strategies:
        raw_strategies = list(input_spec.resolution_strategies)
    else:
        raw_strategies = list(MANDATORY_PRECEDENCE)

    # Reorder: known precedence first, unknowns appended in original order
    ordered_strategies = sorted(
        raw_strategies,
        key=lambda k: _PRECEDENCE_INDEX.get(k, len(MANDATORY_PRECEDENCE)),
    )

    for kind in ordered_strategies:
        resolver_fn = registry.get(kind)
        if resolver_fn is None:
            logger.debug(
                "resolver_skip resolver_not_registered input_id=%s resolver_kind=%s",
                input_id,
                kind.value,
            )
            continue

        try:
            result: ResolutionResult | None = resolver_fn(input_spec, context)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "resolver_error input_id=%s resolver_kind=%s error=%r",
                input_id,
                kind.value,
                exc,
            )
            continue

        if result is None:
            logger.debug(
                "resolver_skip resolver_returned_none input_id=%s resolver_kind=%s",
                input_id,
                kind.value,
            )
            continue

        if result.confidence >= threshold:
            logger.info(
                "resolver_resolved input_id=%s resolver_kind=%s confidence=%.3f",
                input_id,
                kind.value,
                result.confidence,
            )
            return InputResolution(
                input_id=input_id,
                status=ResolutionStatus.RESOLVED,
                resolver_used=kind,
                confidence=result.confidence,
                evidence_source=result.evidence_source,
                resolved_value=result.value,
                resolved_at=datetime.now(tz=timezone.utc).isoformat(),
            )

        logger.debug(
            "resolver_low_confidence input_id=%s resolver_kind=%s "
            "confidence=%.3f threshold=%.3f",
            input_id,
            kind.value,
            result.confidence,
            threshold,
        )

    logger.info(
        "resolver_unresolved input_id=%s strategies_tried=%d",
        input_id,
        len(ordered_strategies),
    )
    return InputResolution(
        input_id=input_id,
        status=ResolutionStatus.UNRESOLVED,
    )


# ---------------------------------------------------------------------------
# Freshness check (T030/US4)
# ---------------------------------------------------------------------------

_DURATION_PATTERN = re.compile(r"^(\d+)([hd])$")


def check_freshness(resolution: InputResolution, input_spec: InputSpec) -> bool:
    """Check if a resolution is still fresh per the input's freshness_policy.

    Supported policy strings: ``"any"``, ``"Nh"`` (hours), ``"Nd"`` (days).

    Returns True if fresh (or no freshness_policy / policy is "any").
    Returns False if the resolution is unresolved, has no resolved_at
    timestamp, or the timestamp is older than the policy window.
    """
    policy = input_spec.freshness_policy
    if not policy or policy == "any":
        return True

    if resolution.resolved_at is None:
        return False

    match = _DURATION_PATTERN.match(policy)
    if not match:
        logger.warning(
            "freshness_policy_unparseable input_id=%s policy=%r",
            resolution.input_id,
            policy,
        )
        return True  # unknown policy → treat as fresh to avoid false staleness

    amount = int(match.group(1))
    unit = match.group(2)
    delta = timedelta(hours=amount) if unit == "h" else timedelta(days=amount)

    try:
        resolved_at = datetime.fromisoformat(resolution.resolved_at)
    except ValueError:
        logger.warning(
            "freshness_resolved_at_unparseable input_id=%s resolved_at=%r",
            resolution.input_id,
            resolution.resolved_at,
        )
        return False

    # Ensure timezone-aware comparison
    if resolved_at.tzinfo is None:
        resolved_at = resolved_at.replace(tzinfo=timezone.utc)

    age = datetime.now(tz=timezone.utc) - resolved_at
    return age <= delta
