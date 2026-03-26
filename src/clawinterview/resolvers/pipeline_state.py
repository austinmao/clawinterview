"""Resolver: pipeline_state — look up input ID in prior_state from a previous run."""

from __future__ import annotations

from clawinterview.models import (
    InputSpec,
    ResolutionContext,
    ResolutionResult,
    ResolverKind,
)

# Prior state carries high confidence; it was resolved in a previous run.
_CONFIDENCE = 0.9


def resolve(input_spec: InputSpec, context: ResolutionContext) -> ResolutionResult | None:
    """Return value from context.prior_state if the input ID is present."""
    value = context.prior_state.get(input_spec.id)
    if value is None:
        return None
    return ResolutionResult(
        value=value,
        confidence=_CONFIDENCE,
        evidence_source=f"prior_state[{input_spec.id!r}] run_id={context.run_id!r}",
        resolver_kind=ResolverKind.PIPELINE_STATE,
    )
