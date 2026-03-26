"""Resolver: upstream_output — look up input ID in upstream stage outputs."""

from __future__ import annotations

from clawinterview.models import (
    InputSpec,
    ResolutionContext,
    ResolutionResult,
    ResolverKind,
)

# Upstream outputs are pipeline-produced — very high confidence.
_CONFIDENCE = 0.95


def resolve(input_spec: InputSpec, context: ResolutionContext) -> ResolutionResult | None:
    """Return value from context.upstream_outputs if the input ID is present."""
    value = context.upstream_outputs.get(input_spec.id)
    if value is None:
        return None
    return ResolutionResult(
        value=value,
        confidence=_CONFIDENCE,
        evidence_source=f"upstream_outputs[{input_spec.id!r}]",
        resolver_kind=ResolverKind.UPSTREAM_OUTPUT,
    )
