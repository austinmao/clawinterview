"""ClawInterview overlay module.

Provides three composable functions for loading and merging interview
contracts from department packs and tenant overlays:

- ``load_department_pack`` — load bundled packs/<department>.yaml
- ``load_tenant_overlay``  — load per-tenant interview-overlays.yaml
- ``merge_contract``       — layered merge: base ← pack defaults ← overlay

The merge follows an immutable pattern: input objects are never mutated.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from clawinterview.models import (
    CompletionRule,
    InputSpec,
    InterviewContract,
    PrimitiveType,
    ResolverKind,
    SemanticFacet,
    TenantOverlay,
)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_PACKS_DIR = Path(__file__).parent / "packs"


def _parse_facets(raw: list[str]) -> list[SemanticFacet]:
    """Convert a list of string facet names into SemanticFacet enums.

    Unknown facet names are silently dropped so that tenant-specific
    facets (e.g. ``retreat_context``) do not break parsing.
    """
    result: list[SemanticFacet] = []
    for item in raw:
        try:
            result.append(SemanticFacet(item))
        except ValueError:
            pass
    return result


def _parse_strategies(raw: list[str]) -> list[ResolverKind]:
    """Convert a list of resolver kind strings into ResolverKind enums."""
    return [ResolverKind(s) for s in raw]


def _pack_input_to_spec(entry: dict[str, Any]) -> InputSpec:
    """Convert a department pack input dict into an InputSpec."""
    return InputSpec(
        id=entry["name"],
        type=PrimitiveType(entry["type"]),
        description=entry.get("help", entry.get("description", "")),
        facets=_parse_facets(entry.get("facets", [])),
        resolution_strategies=_parse_strategies(
            entry.get("resolution_strategies", [])
        ),
        confidence_threshold=float(entry.get("confidence_threshold", 0.7)),
        freshness_policy=entry.get("freshness_policy"),
        ask_policy=entry.get("ask_policy", "only_if_unresolved"),
        depends_on=entry.get("depends_on", []),
        default_value=entry.get("default_value"),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_department_pack(department: str) -> InterviewContract | None:
    """Load a bundled department pack and return an InterviewContract.

    Reads ``packs/<department>.yaml`` from the package directory.
    Returns ``None`` if the file does not exist.

    Args:
        department: Department name, e.g. ``"marketing"`` or ``"engineering"``.

    Returns:
        An :class:`~clawinterview.models.InterviewContract` populated with
        the pack's ``default_inputs``, ``default_facets``, and
        ``default_resolution_strategies``, or ``None`` if the file is absent.
    """
    pack_path = _PACKS_DIR / f"{department}.yaml"
    if not pack_path.exists():
        return None

    with pack_path.open() as fh:
        data: dict[str, Any] = yaml.safe_load(fh)

    default_inputs: dict[str, Any] = data.get("default_inputs", {})
    required_raw: list[dict[str, Any]] = default_inputs.get("required", [])
    optional_raw: list[dict[str, Any]] = default_inputs.get("optional", [])

    required_inputs = [_pack_input_to_spec(e) for e in required_raw]
    optional_inputs = [_pack_input_to_spec(e) for e in optional_raw]

    raw_facets: list[str] = data.get("default_facets", [])
    semantic_facets = _parse_facets(raw_facets)

    raw_strategies: list[str] = data.get("default_resolution_strategies", [])
    resolution_strategies = _parse_strategies(raw_strategies)

    return InterviewContract(
        required_inputs=required_inputs,
        optional_inputs=optional_inputs,
        resolution_strategies=resolution_strategies,
        semantic_facets=semantic_facets,
    )


def load_tenant_overlay(
    tenant_id: str,
    workspace_path: str,
) -> TenantOverlay | None:
    """Load a per-tenant interview overlay from disk.

    Looks for the YAML file in the following order:
    1. ``<workspace_path>/tenants/<tenant_id>/config/interview-overlays.yaml``
    2. ``<workspace_path>/config/interview-overlays.yaml`` (fallback)

    Args:
        tenant_id: Tenant identifier, e.g. ``"ceremonia"``.
        workspace_path: Absolute or relative path to the workspace root.

    Returns:
        A :class:`~clawinterview.models.TenantOverlay` if a file is found,
        or ``None`` otherwise.
    """
    workspace = Path(workspace_path)

    candidate_paths = [
        workspace / "tenants" / tenant_id / "config" / "interview-overlays.yaml",
        workspace / "config" / "interview-overlays.yaml",
    ]

    chosen: Path | None = None
    for candidate in candidate_paths:
        if candidate.exists():
            chosen = candidate
            break

    if chosen is None:
        return None

    with chosen.open() as fh:
        data: dict[str, Any] = yaml.safe_load(fh)

    # Extract only the fields that TenantOverlay accepts.
    additional_facets: list[str] = data.get("additional_facets", [])
    resolver_overrides: dict[str, Any] = data.get("resolver_overrides", {})
    evidence_policy: dict[str, Any] = data.get("evidence_policy", {})

    # Parse optional custom_completion_rules
    custom_rules: CompletionRule | None = None
    raw_rules = data.get("custom_completion_rules")
    if raw_rules:
        custom_rules = CompletionRule.model_validate(raw_rules)

    return TenantOverlay(
        tenant_id=tenant_id,
        additional_facets=additional_facets,
        resolver_overrides=resolver_overrides,
        evidence_policy=evidence_policy,
        custom_completion_rules=custom_rules,
    )


def merge_contract(
    base: InterviewContract,
    pack: InterviewContract | None = None,
    overlay: TenantOverlay | None = None,
) -> InterviewContract:
    """Produce a merged InterviewContract from layered sources.

    Merge precedence (highest → lowest):
    - ``overlay`` — tenant-specific refinements
    - ``base``    — contract declared by the spec
    - ``pack``    — department-wide defaults

    Detailed rules per field:

    ``required_inputs`` / ``optional_inputs``
        Base inputs take precedence.  Pack inputs whose ``id`` is **not**
        already present in base are appended.

    ``resolution_strategies``
        Base value is used when non-empty; otherwise pack value.

    ``semantic_facets``
        Union of base, pack, and overlay ``additional_facets``.  Order is
        base → pack additions → overlay additions; duplicates are removed
        while preserving first-occurrence order.

    ``completion_rules``
        Base value is used if set; otherwise pack value; overlay
        ``custom_completion_rules`` as final fallback.

    ``evidence_policy``
        Pack provides defaults; base overrides those; overlay then overrides
        the result (deep merge: overlay wins per key).

    Args:
        base: The primary contract (highest precedence for most fields).
        pack: Optional department pack defaults.
        overlay: Optional tenant overlay.

    Returns:
        A new :class:`~clawinterview.models.InterviewContract` instance.
        Input objects are never mutated.
    """
    # --- required_inputs ---------------------------------------------------
    base_req_ids = {inp.id for inp in base.required_inputs}
    merged_required = list(base.required_inputs)
    if pack:
        for inp in pack.required_inputs:
            if inp.id not in base_req_ids:
                merged_required.append(inp)

    # --- optional_inputs ---------------------------------------------------
    base_opt_ids = {inp.id for inp in base.optional_inputs}
    # Also exclude any id already in required to prevent duplication
    all_base_ids = base_req_ids | base_opt_ids
    merged_optional = list(base.optional_inputs)
    if pack:
        for inp in pack.optional_inputs:
            if inp.id not in all_base_ids:
                merged_optional.append(inp)

    # --- resolution_strategies ---------------------------------------------
    if base.resolution_strategies:
        merged_strategies = list(base.resolution_strategies)
    elif pack and pack.resolution_strategies:
        merged_strategies = list(pack.resolution_strategies)
    else:
        merged_strategies = []

    # --- semantic_facets ---------------------------------------------------
    seen_facets: set[SemanticFacet] = set()
    merged_facets: list[SemanticFacet] = []

    def _add_facets(facets: list[SemanticFacet]) -> None:
        for f in facets:
            if f not in seen_facets:
                seen_facets.add(f)
                merged_facets.append(f)

    _add_facets(base.semantic_facets)
    if pack:
        _add_facets(pack.semantic_facets)
    if overlay:
        overlay_facets = _parse_facets(overlay.additional_facets)
        _add_facets(overlay_facets)

    # --- completion_rules --------------------------------------------------
    if base.completion_rules is not None:
        merged_rules: CompletionRule | None = base.completion_rules
    elif pack and pack.completion_rules is not None:
        merged_rules = pack.completion_rules
    elif overlay and overlay.custom_completion_rules is not None:
        merged_rules = overlay.custom_completion_rules
    else:
        merged_rules = None

    # --- evidence_policy ---------------------------------------------------
    merged_evidence: dict[str, Any] = {}
    if pack:
        merged_evidence.update(pack.evidence_policy)
    merged_evidence.update(base.evidence_policy)
    if overlay:
        merged_evidence.update(overlay.evidence_policy)

    # --- produces_outputs (pass through from base) -------------------------
    merged_outputs = list(base.produces_outputs)
    if pack:
        base_output_ids = {o.id for o in merged_outputs}
        for out in pack.produces_outputs:
            if out.id not in base_output_ids:
                merged_outputs.append(out)

    return InterviewContract(
        version=base.version,
        required_inputs=merged_required,
        optional_inputs=merged_optional,
        produces_outputs=merged_outputs,
        resolution_strategies=merged_strategies,
        completion_rules=merged_rules,
        semantic_facets=merged_facets,
        evidence_policy=merged_evidence,
    )
