"""Resolver: web — web search integration hook.

# Integration hook: connect to web search when available.
# Expected pattern:
#   Issue a search query derived from input_spec.description via the
#   brave-search skill or any configured search API. Extract a typed
#   value from the top result and assign a moderate confidence score
#   (suggested: 0.5–0.7) reflecting the uncertainty of web extraction.
"""

from __future__ import annotations

from clawinterview.models import (
    InputSpec,
    ResolutionContext,
    ResolutionResult,
)


def resolve(input_spec: InputSpec, context: ResolutionContext) -> ResolutionResult | None:  # noqa: ARG001
    """Stub: web search integration hook — returns None until wired."""
    return None
