"""Resolver: infer — LLM inference integration hook.

# Integration hook: LLM inference from available context.
# Expected pattern:
#   Assemble a prompt from available context (user_message, prior_state,
#   upstream_outputs, description) and ask the LLM to infer a typed
#   value for input_spec.id. Parse the structured response and assign
#   confidence based on the model's expressed certainty (e.g. 0.6–0.8).
#   Use this as a last-resort before falling through to ASK.
"""

from __future__ import annotations

from clawinterview.models import (
    InputSpec,
    ResolutionContext,
    ResolutionResult,
)


def resolve(input_spec: InputSpec, context: ResolutionContext) -> ResolutionResult | None:  # noqa: ARG001
    """Stub: LLM inference integration hook — returns None until wired."""
    return None
