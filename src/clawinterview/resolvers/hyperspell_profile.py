"""Resolver: hyperspell_profile — extract values from a HyperSpell extracted profile.

Reads a JSON profile file (path passed via ``pipeline_args["hyperspell_profile_path"]``)
and maps profile fields to interview input IDs.  Each profile field carries an
overall confidence score; if the field value exists and the profile confidence
meets or exceeds the input's ``confidence_threshold``, the input is resolved
automatically.

Field mapping is declared per-input via the ``resolution_strategies`` list in the
interview contract.  The contract author adds a strategy entry like::

    resolution_strategies:
      - kind: hyperspell_profile
        field: business_type      # profile key to read
        threshold: 0.8            # minimum profile confidence

The ``field`` and ``threshold`` values are passed through the InputSpec's
``resolution_strategies`` metadata.  Because the current InputSpec model stores
strategies as a flat ``list[ResolverKind]`` without per-strategy options, this
resolver falls back to matching ``input_spec.id`` directly against profile keys
when no explicit field mapping is available.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from clawinterview.models import (
    InputSpec,
    ResolutionContext,
    ResolutionResult,
    ResolverKind,
)

logger = logging.getLogger("clawinterview.resolver.hyperspell_profile")

# Default confidence assigned when the profile has a value but no per-field
# confidence.  The overall ``confidence`` key on the profile is used instead.
_DEFAULT_CONFIDENCE = 0.75

# Cache to avoid re-reading the same profile file within a single resolution pass.
_profile_cache: dict[str, dict[str, Any]] = {}


def _load_profile(path: str) -> dict[str, Any]:
    """Load a HyperSpell profile JSON file, returning an empty dict on failure."""
    if path in _profile_cache:
        return _profile_cache[path]

    try:
        raw = Path(path).read_text()
        data = json.loads(raw)
        if not isinstance(data, dict):
            logger.debug("hyperspell_profile invalid_format path=%s", path)
            data = {}
    except Exception as exc:  # noqa: BLE001
        logger.debug("hyperspell_profile load_failed path=%s error=%r", path, exc)
        data = {}

    _profile_cache[path] = data
    return data


def clear_cache() -> None:
    """Clear the in-memory profile cache (useful between test runs)."""
    _profile_cache.clear()


def resolve(input_spec: InputSpec, context: ResolutionContext) -> ResolutionResult | None:
    """Resolve an input from a HyperSpell extracted profile.

    The profile file path is expected in ``context.pipeline_args["hyperspell_profile_path"]``
    or, alternatively, the profile dict itself in ``context.pipeline_args["hyperspell_profile"]``.

    Field lookup order:
      1. Exact match on ``input_spec.id`` as a profile key.
      2. Common alias mappings (e.g. ``team_involvement`` -> ``team_size``).

    Returns ``None`` if the profile does not contain the requested field or if
    the profile's overall confidence is below the input's threshold.
    """
    # Load profile from file path or inline dict
    profile: dict[str, Any] = {}
    inline_profile = context.pipeline_args.get("hyperspell_profile")
    if isinstance(inline_profile, dict):
        profile = inline_profile
    elif isinstance(inline_profile, str) and inline_profile.strip():
        try:
            parsed = json.loads(inline_profile)
        except json.JSONDecodeError:
            parsed = None

        if isinstance(parsed, dict):
            profile = parsed
    if not profile:
        profile_path = context.pipeline_args.get("hyperspell_profile_path")
        if not profile_path or not isinstance(profile_path, str):
            return None
        profile = _load_profile(profile_path)

    if not profile:
        return None

    # Overall profile confidence
    profile_confidence: float = float(profile.get("confidence", _DEFAULT_CONFIDENCE))

    # Check confidence threshold
    if profile_confidence < input_spec.confidence_threshold:
        logger.debug(
            "hyperspell_profile confidence_below_threshold input=%s "
            "profile_confidence=%.2f threshold=%.2f",
            input_spec.id,
            profile_confidence,
            input_spec.confidence_threshold,
        )
        return None

    # Alias mappings for common interview inputs that don't match profile keys 1:1
    _ALIASES: dict[str, list[str]] = {
        "team_involvement": ["team_size", "key_roles"],
        "brand_description": ["industry", "products"],
        "channel_preferences": ["channels_connected"],
    }

    # Try direct field match first
    value = profile.get(input_spec.id)
    source_field = input_spec.id

    # Fall back to aliases
    if value is None and input_spec.id in _ALIASES:
        for alias in _ALIASES[input_spec.id]:
            candidate = profile.get(alias)
            if candidate is not None:
                value = candidate
                source_field = alias
                break

    if value is None:
        return None

    # Skip empty values
    if isinstance(value, str) and not value.strip():
        return None
    if isinstance(value, list) and len(value) == 0:
        return None

    return ResolutionResult(
        value=value,
        confidence=profile_confidence,
        evidence_source=f"hyperspell_profile[{source_field!r}]",
        resolver_kind=ResolverKind.HYPERSPELL_PROFILE,
    )
