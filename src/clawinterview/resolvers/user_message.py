"""Resolver: user_message — heuristic keyword extraction from user message."""

from __future__ import annotations

import re

from clawinterview.models import (
    InputSpec,
    ResolutionContext,
    ResolutionResult,
    ResolverKind,
)

# Confidence is intentionally low; this is heuristic extraction.
_CONFIDENCE = 0.6


def _build_keywords(input_spec: InputSpec) -> list[str]:
    """Return candidate keywords derived from the input ID and description."""
    id_words = re.split(r"[_\-\s]+", input_spec.id.lower())
    desc_words = re.split(r"\W+", input_spec.description.lower())
    # Keep meaningful words (len > 2)
    return [w for w in id_words + desc_words if len(w) > 2]


def resolve(input_spec: InputSpec, context: ResolutionContext) -> ResolutionResult | None:
    """Return a substring match from user_message if any keyword is found."""
    if not context.user_message:
        return None

    message_lower = context.user_message.lower()
    keywords = _build_keywords(input_spec)

    for keyword in keywords:
        if keyword in message_lower:
            # Return the full user message as the raw extracted value.
            return ResolutionResult(
                value=context.user_message,
                confidence=_CONFIDENCE,
                evidence_source=f"user_message keyword={keyword!r}",
                resolver_kind=ResolverKind.USER_MESSAGE,
            )
    return None
