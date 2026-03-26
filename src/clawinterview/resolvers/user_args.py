"""Resolver: user_args — extract value from pipeline_args by input ID."""

from __future__ import annotations

from clawinterview.models import (
    InputSpec,
    ResolutionContext,
    ResolutionResult,
    ResolverKind,
)


def resolve(input_spec: InputSpec, context: ResolutionContext) -> ResolutionResult | None:
    """Return the pipeline_args value matching input_spec.id, confidence=1.0."""
    value = context.pipeline_args.get(input_spec.id)
    if value is None:
        return None
    return ResolutionResult(
        value=value,
        confidence=1.0,
        evidence_source=f"pipeline_args[{input_spec.id!r}]",
        resolver_kind=ResolverKind.USER_ARGS,
    )
