"""Resolver: tenant_file — read config values from workspace YAML files."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from clawinterview.models import (
    InputSpec,
    ResolutionContext,
    ResolutionResult,
    ResolverKind,
)

logger = logging.getLogger("clawinterview.resolver.tenant_file")

_CONFIDENCE = 0.85


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file, returning an empty dict on failure."""
    try:
        import yaml  # type: ignore[import-untyped]

        return yaml.safe_load(path.read_text()) or {}
    except Exception as exc:  # noqa: BLE001
        logger.debug("tenant_file yaml_load_failed path=%s error=%r", path, exc)
        return {}


def resolve(input_spec: InputSpec, context: ResolutionContext) -> ResolutionResult | None:
    """Look for input_spec.id in the workspace config directory.

    Search order:
      1. ``{workspace_path}/config/{input_id}.yaml`` — dedicated file
      2. Any YAML file in ``{workspace_path}/config/`` with a top-level
         key matching ``input_spec.id`` or a nested ``context`` dict.
    """
    if not context.workspace_path:
        return None

    workspace = Path(context.workspace_path)
    config_dir = workspace / "config"

    # 1. Dedicated file: config/<input_id>.yaml
    dedicated = config_dir / f"{input_spec.id}.yaml"
    if dedicated.is_file():
        data = _load_yaml(dedicated)
        value = data.get("value", data) if data else None
        if value is not None:
            return ResolutionResult(
                value=value,
                confidence=_CONFIDENCE,
                evidence_source=str(dedicated),
                resolver_kind=ResolverKind.TENANT_FILE,
            )

    # 2. Scan all YAML files for a matching top-level key or context sub-key
    if config_dir.is_dir():
        for yaml_file in sorted(config_dir.glob("*.yaml")):
            data = _load_yaml(yaml_file)
            # Direct key match
            if input_spec.id in data:
                return ResolutionResult(
                    value=data[input_spec.id],
                    confidence=_CONFIDENCE,
                    evidence_source=f"{yaml_file}[{input_spec.id!r}]",
                    resolver_kind=ResolverKind.TENANT_FILE,
                )
            # Nested under a 'context' key
            context_block = data.get("context", {})
            if isinstance(context_block, dict) and input_spec.id in context_block:
                return ResolutionResult(
                    value=context_block[input_spec.id],
                    confidence=_CONFIDENCE,
                    evidence_source=f"{yaml_file}[context][{input_spec.id!r}]",
                    resolver_kind=ResolverKind.TENANT_FILE,
                )

    return None
