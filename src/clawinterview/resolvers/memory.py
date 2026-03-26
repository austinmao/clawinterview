"""Resolver: memory — gateway memory.search integration hook.

Integration pattern (when wired):
  POST http://localhost:18789/tools/invoke
  Body: {"tool": "memory.search", "args": {"query": input_spec.id,
                                            "namespace": context.tenant_id}}
  Returns: list of memory hits with score and value fields.

Until the gateway integration is active this resolver is a stub that
returns None so the pipeline falls through to the next strategy.
"""

from __future__ import annotations

from clawinterview.models import (
    InputSpec,
    ResolutionContext,
    ResolutionResult,
)


def resolve(input_spec: InputSpec, context: ResolutionContext) -> ResolutionResult | None:  # noqa: ARG001
    """Stub: gateway memory.search integration hook — returns None until wired."""
    # TODO: wire httpx call to gateway memory.search endpoint
    # Example:
    #   import httpx
    #   response = httpx.post(
    #       "http://localhost:18789/tools/invoke",
    #       json={"tool": "memory.search",
    #             "args": {"query": input_spec.id, "namespace": context.tenant_id}},
    #       timeout=5.0,
    #   )
    #   hits = response.json().get("results", [])
    #   if hits:
    #       best = hits[0]
    #       return ResolutionResult(value=best["value"], confidence=best["score"],
    #                               evidence_source="memory.search",
    #                               resolver_kind=ResolverKind.MEMORY)
    return None
