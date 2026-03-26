"""Resolver: rag — RAG infrastructure integration hook.

# Integration hook: connect to RAG infrastructure when available.
# Expected pattern:
#   Query the vector store (ChromaDB / Qdrant) with input_spec.id or
#   input_spec.description as the search query. Map the top-ranked
#   document chunk back to a typed value. Assign confidence proportional
#   to the retrieval similarity score.
"""

from __future__ import annotations

from clawinterview.models import (
    InputSpec,
    ResolutionContext,
    ResolutionResult,
)


def resolve(input_spec: InputSpec, context: ResolutionContext) -> ResolutionResult | None:  # noqa: ARG001
    """Stub: RAG integration hook — returns None until wired."""
    return None
