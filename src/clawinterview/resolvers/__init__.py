"""ClawInterview built-in resolver implementations.

Call ``register_all_resolvers(registry)`` to populate a ResolverRegistry
with all 11 built-in resolvers in one step.
"""

from __future__ import annotations

from clawinterview.models import ResolverKind
from clawinterview.resolver import ResolverRegistry

from clawinterview.resolvers import (
    ask,
    hyperspell_profile,
    infer,
    memory,
    pipeline_state,
    rag,
    tenant_file,
    upstream_output,
    user_args,
    user_message,
    web,
)

__all__ = ["register_all_resolvers"]


def register_all_resolvers(registry: ResolverRegistry) -> None:
    """Register all 11 built-in resolvers into the given registry."""
    registry.register(ResolverKind.USER_ARGS, user_args.resolve)
    registry.register(ResolverKind.USER_MESSAGE, user_message.resolve)
    registry.register(ResolverKind.HYPERSPELL_PROFILE, hyperspell_profile.resolve)
    registry.register(ResolverKind.PIPELINE_STATE, pipeline_state.resolve)
    registry.register(ResolverKind.MEMORY, memory.resolve)
    registry.register(ResolverKind.TENANT_FILE, tenant_file.resolve)
    registry.register(ResolverKind.UPSTREAM_OUTPUT, upstream_output.resolve)
    registry.register(ResolverKind.RAG, rag.resolve)
    registry.register(ResolverKind.WEB, web.resolve)
    registry.register(ResolverKind.INFER, infer.resolve)
    registry.register(ResolverKind.ASK, ask.resolve)
