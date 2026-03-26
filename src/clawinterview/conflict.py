"""ClawInterview conflict detection and repair module (T032).

Detects semantic conflicts among CompiledInput objects that share the same
``original_id`` but originate from different targets.  Provides:

  - ``detect_conflicts`` — classify conflicts into EXACT_MATCH,
    COMPATIBLE_REFINEMENT, or INCOMPATIBLE.
  - ``attempt_repair`` — merge facets for COMPATIBLE_REFINEMENT conflicts;
    return None for INCOMPATIBLE.
"""

from __future__ import annotations

import logging
from itertools import combinations

from clawinterview.models import (
    CompiledInput,
    ConflictReport,
    ConflictSeverity,
)

logger = logging.getLogger("clawinterview.conflict")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_conflicts(inputs: list[CompiledInput]) -> list[ConflictReport]:
    """Detect semantic conflicts among compiled inputs.

    Groups inputs by ``original_id``.  For each group with more than one
    distinct owner target, classifies the conflict:

    - **EXACT_MATCH**: same ``type`` *and* same ``facets`` (order-insensitive).
      These are silently merged — no ConflictReport is emitted.
    - **COMPATIBLE_REFINEMENT**: same ``type`` but different ``facets``.
      A ConflictReport is emitted with a resolution suggestion.
    - **INCOMPATIBLE**: different ``type``.
      A ConflictReport is emitted.  The compiler should raise on these.

    Only one ConflictReport is emitted per unique ``original_id`` group
    (the pair with the highest severity wins when multiple pairs exist).

    Parameters
    ----------
    inputs:
        Flat list of CompiledInput objects from all participating targets.

    Returns
    -------
    list[ConflictReport]
        One report per conflicting ``original_id`` group (exact matches
        produce no report).
    """
    # Group by original_id.
    groups: dict[str, list[CompiledInput]] = {}
    for inp in inputs:
        groups.setdefault(inp.original_id, []).append(inp)

    reports: list[ConflictReport] = []

    for original_id, group in groups.items():
        # Filter to unique owner targets — deduplicate same-target entries.
        seen_owners: set[str] = set()
        unique: list[CompiledInput] = []
        for inp in group:
            if inp.owner_target not in seen_owners:
                seen_owners.add(inp.owner_target)
                unique.append(inp)

        if len(unique) < 2:
            continue  # No inter-target conflict possible.

        # Evaluate all pairs; keep the worst-severity report.
        worst_report: ConflictReport | None = None

        for a, b in combinations(unique, 2):
            report = _classify_pair(a, b)
            if report is None:
                # EXACT_MATCH — no conflict.
                continue
            if worst_report is None or _severity_rank(report.severity) > _severity_rank(
                worst_report.severity
            ):
                worst_report = report

        if worst_report is not None:
            reports.append(worst_report)

    return reports


def attempt_repair(conflict: ConflictReport, inputs: list[CompiledInput]) -> CompiledInput | None:
    """Attempt to repair a conflict by merging facets.

    For **COMPATIBLE_REFINEMENT** conflicts, merges the ``facets`` from all
    conflicting inputs into a single unified ``CompiledInput``.  The first
    input in the conflict group is used as the base; ownership is set to
    ``"merged"``.

    For **INCOMPATIBLE** conflicts, returns ``None`` (cannot be repaired
    automatically).

    Parameters
    ----------
    conflict:
        A ConflictReport produced by :func:`detect_conflicts`.
    inputs:
        The full list of CompiledInput objects (same list passed to
        ``detect_conflicts``).  Used to look up the conflicting inputs by ID.

    Returns
    -------
    CompiledInput | None
        A merged CompiledInput for COMPATIBLE_REFINEMENT; ``None`` for
        INCOMPATIBLE.
    """
    if conflict.severity == ConflictSeverity.INCOMPATIBLE:
        return None

    if conflict.severity != ConflictSeverity.COMPATIBLE_REFINEMENT:
        # EXACT_MATCH conflicts should not reach attempt_repair, but guard.
        return None

    # Collect all conflicting inputs by their compiled IDs.
    conflict_id_set = set(conflict.input_ids)
    conflicting = [inp for inp in inputs if inp.id in conflict_id_set]

    if not conflicting:
        logger.warning(
            "attempt_repair no matching inputs found for conflict input_ids=%s",
            conflict.input_ids,
        )
        return None

    base = conflicting[0]

    # Merge facets: union across all conflicting inputs (order-stable, deduped).
    merged_facets_seen: set = set()
    merged_facets = []
    for inp in conflicting:
        for facet in inp.facets:
            if facet not in merged_facets_seen:
                merged_facets_seen.add(facet)
                merged_facets.append(facet)

    # Merge resolution strategies (union, deduplicated).
    merged_strategies_seen: set = set()
    merged_strategies = []
    for inp in conflicting:
        for strategy in inp.resolution_strategies:
            if strategy not in merged_strategies_seen:
                merged_strategies_seen.add(strategy)
                merged_strategies.append(strategy)

    repaired = base.model_copy(
        update={
            "owner_target": "merged",
            "facets": merged_facets,
            "resolution_strategies": merged_strategies,
        }
    )

    logger.info(
        "conflict_repaired original_id=%s merged_facets=%s",
        base.original_id,
        [f.value for f in merged_facets],
    )

    return repaired


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _classify_pair(a: CompiledInput, b: CompiledInput) -> ConflictReport | None:
    """Classify the conflict between two inputs sharing the same original_id.

    Returns None for EXACT_MATCH (no conflict to report).
    Returns a ConflictReport for COMPATIBLE_REFINEMENT or INCOMPATIBLE.
    """
    if a.type != b.type:
        return ConflictReport(
            input_ids=[a.id, b.id],
            owner_targets=[a.owner_target, b.owner_target],
            severity=ConflictSeverity.INCOMPATIBLE,
            description=(
                f"Input '{a.original_id}' declared as type {a.type!r} by "
                f"'{a.owner_target}' but as type {b.type!r} by '{b.owner_target}'"
            ),
            resolution=None,
        )

    # Same type — compare facets (order-insensitive).
    if set(a.facets) == set(b.facets):
        # EXACT_MATCH — no conflict report.
        return None

    # Same type, different facets — compatible refinement.
    merged_facets = sorted(set(a.facets) | set(b.facets), key=lambda f: f.value)
    return ConflictReport(
        input_ids=[a.id, b.id],
        owner_targets=[a.owner_target, b.owner_target],
        severity=ConflictSeverity.COMPATIBLE_REFINEMENT,
        description=(
            f"Input '{a.original_id}' has compatible type {a.type!r} across "
            f"'{a.owner_target}' and '{b.owner_target}' but differing facets "
            f"({[f.value for f in a.facets]} vs {[f.value for f in b.facets]})"
        ),
        resolution=(
            f"Merge facets to {[f.value for f in merged_facets]} under a "
            f"unified input owned by 'merged'"
        ),
    )


def _severity_rank(severity: ConflictSeverity) -> int:
    """Return a numeric rank for conflict severity (higher = worse)."""
    return {
        ConflictSeverity.EXACT_MATCH: 0,
        ConflictSeverity.COMPATIBLE_REFINEMENT: 1,
        ConflictSeverity.INCOMPATIBLE: 2,
    }[severity]
