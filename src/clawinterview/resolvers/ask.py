"""Resolver: ask — human input sentinel.

Returns a ResolutionResult with confidence=0.0 and a structured question
marker as the value. The engine interprets confidence=0.0 from the ASK
resolver as a signal that human input is required before proceeding.
"""

from __future__ import annotations

from clawinterview.models import (
    InputSpec,
    ResolutionContext,
    ResolutionResult,
    ResolverKind,
)


def resolve(input_spec: InputSpec, context: ResolutionContext) -> ResolutionResult | None:  # noqa: ARG001
    """Return a human_question sentinel; confidence=0.0 triggers ASK flow."""
    question_marker = {
        "type": "human_question",
        "input_id": input_spec.id,
        "description": input_spec.description,
    }
    return ResolutionResult(
        value=question_marker,
        confidence=0.0,
        evidence_source="ask",
        resolver_kind=ResolverKind.ASK,
    )
