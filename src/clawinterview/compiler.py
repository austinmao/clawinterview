"""ClawInterview contract compiler.

Compiles a list of per-target InterviewContracts into a single
CompiledRunContract for a pipeline run.  All input IDs are de-ambiguated,
producer→consumer mappings are resolved by semantic-facet overlap, and
completion rules are merged under an ``all_of`` wrapper.
"""

from __future__ import annotations

from datetime import datetime, timezone

from clawinterview.conflict import attempt_repair, detect_conflicts
from clawinterview.models import (
    CompletionRule,
    CompiledInput,
    CompiledRunContract,
    ConflictSeverity,
    InputSpec,
    InterviewContract,
    OutputSpec,
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compile_run_contract(
    pipeline_id: str,
    run_id: str,
    target_contracts: list[tuple[str, InterviewContract]],
) -> CompiledRunContract:
    """Compile per-target contracts into a single ``CompiledRunContract``.

    Parameters
    ----------
    pipeline_id:
        Stable identifier for the pipeline.
    run_id:
        Unique identifier for this execution run.
    target_contracts:
        Ordered list of ``(target_id, InterviewContract)`` pairs.

    Returns
    -------
    CompiledRunContract
        Merged, de-ambiguated contract ready for the resolution phase.

    Raises
    ------
    ValueError
        If ``target_contracts`` is empty, or if any individual contract
        carries no inputs at all.
    """
    if not target_contracts:
        raise ValueError("No target contracts to compile")

    for target_id, contract in target_contracts:
        if not contract.required_inputs and not contract.optional_inputs:
            raise ValueError(
                f"Target '{target_id}' has zero required_inputs and zero "
                "optional_inputs — nothing to compile"
            )

    # Collect all outputs once so producer-mapping resolution is O(inputs).
    all_outputs: list[tuple[str, OutputSpec]] = [
        (target_id, output)
        for target_id, contract in target_contracts
        for output in contract.produces_outputs
    ]

    # Track raw input_id → list[target_id] for ambiguity detection.
    id_owners: dict[str, list[str]] = {}
    for target_id, contract in target_contracts:
        for spec in (*contract.required_inputs, *contract.optional_inputs):
            id_owners.setdefault(spec.id, []).append(target_id)

    compiled_inputs: list[CompiledInput] = []

    for target_id, contract in target_contracts:
        for blocking, specs in (
            (True, contract.required_inputs),
            (False, contract.optional_inputs),
        ):
            for spec in specs:
                owners = id_owners[spec.id]

                # Qualify the compiled id when the raw id is ambiguous.
                compiled_id = (
                    spec.id
                    if len(owners) == 1
                    else _qualify_input_id(target_id, spec.id)
                )

                # Prefer input-level strategies; fall back to contract default.
                strategies = spec.resolution_strategies or contract.resolution_strategies

                producer = _find_producer_mapping(spec, all_outputs)

                compiled_inputs.append(
                    CompiledInput(
                        id=compiled_id,
                        original_id=spec.id,
                        owner_target=target_id,
                        type=spec.type,
                        description=spec.description,
                        facets=spec.facets,
                        resolution_strategies=strategies,
                        confidence_threshold=spec.confidence_threshold,
                        depends_on=spec.depends_on,
                        default_value=spec.default_value,
                        blocking=blocking,
                        producer_mapping=producer,
                    )
                )

    # ---------------------------------------------------------------------------
    # Conflict detection and repair (T031-T033)
    # ---------------------------------------------------------------------------
    conflict_reports = detect_conflicts(compiled_inputs)

    for report in conflict_reports:
        if report.severity == ConflictSeverity.INCOMPATIBLE:
            raise ValueError(
                f"Incompatible input conflict for '{report.input_ids}': "
                f"targets {report.owner_targets!r} declare incompatible types. "
                f"{report.description}"
            )

    # Repair COMPATIBLE_REFINEMENT conflicts: replace conflicting inputs with
    # a merged input.
    repaired_ids: set[str] = set()
    repaired_inputs: list[CompiledInput] = []

    for report in conflict_reports:
        if report.severity == ConflictSeverity.COMPATIBLE_REFINEMENT:
            repaired = attempt_repair(report, compiled_inputs)
            if repaired is not None:
                repaired_ids.update(report.input_ids)
                repaired_inputs.append(repaired)

    if repaired_ids:
        # Keep all inputs that were NOT part of a repair, then append repaired ones.
        compiled_inputs = [
            inp for inp in compiled_inputs if inp.id not in repaired_ids
        ] + repaired_inputs

    # Serialize conflict reports as dicts for the contract.
    conflicts_serialized = [r.model_dump(mode="json") for r in conflict_reports]

    all_outputs_flat: list[OutputSpec] = [out for _, out in all_outputs]
    merged_rules = _merge_completion_rules(
        [contract.completion_rules for _, contract in target_contracts]
    )

    return CompiledRunContract(
        pipeline_id=pipeline_id,
        run_id=run_id,
        compiled_at=datetime.now(timezone.utc).isoformat(),
        participating_targets=[t for t, _ in target_contracts],
        inputs=compiled_inputs,
        outputs=all_outputs_flat,
        completion_rules=merged_rules,
        conflicts=conflicts_serialized,
    )


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _qualify_input_id(target_id: str, input_id: str) -> str:
    """Return a target-qualified input ID: ``{target_id}.{input_id}``."""
    return f"{target_id}.{input_id}"


def _find_producer_mapping(
    input_spec: InputSpec,
    all_outputs: list[tuple[str, OutputSpec]],
) -> str | None:
    """Return the first output ID whose facets overlap with ``input_spec``.

    Matching is purely by semantic-facet intersection.  Returns ``None``
    when no overlap is found or when ``input_spec`` declares no facets.
    """
    if not input_spec.facets:
        return None

    input_facet_set = set(input_spec.facets)
    for _owner, output in all_outputs:
        if input_facet_set & set(output.facets):
            return output.id
    return None


def _merge_completion_rules(
    rules: list[CompletionRule | None],
) -> CompletionRule | None:
    """Wrap all non-None rules under a single ``all_of`` CompletionRule.

    Returns ``None`` when every element of *rules* is ``None``.
    Returns the single rule directly when only one non-None rule exists.
    """
    non_null = [r for r in rules if r is not None]
    if not non_null:
        return None
    if len(non_null) == 1:
        return non_null[0]
    return CompletionRule(all_of=non_null)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _check_conflict(
    spec: InputSpec,
    current_target: str,
    owners: list[str],
    target_contracts: list[tuple[str, InterviewContract]],
) -> dict | None:
    """Return a conflict dict if *spec* clashes with another owner's definition.

    A conflict is recorded when two targets share the same input ID but
    declare different ``PrimitiveType`` values.  Only emits one conflict
    record per unique (id, current_target) pair to avoid duplicates.
    """
    contract_map = {tid: c for tid, c in target_contracts}
    for other_target in owners:
        if other_target == current_target:
            continue
        other_contract = contract_map[other_target]
        for other_spec in (
            *other_contract.required_inputs,
            *other_contract.optional_inputs,
        ):
            if other_spec.id == spec.id and other_spec.type != spec.type:
                # Only record conflict for the first encounter (current < other).
                if current_target < other_target:
                    return {
                        "input_id": spec.id,
                        "targets": [current_target, other_target],
                        "types": [spec.type, other_spec.type],
                        "description": (
                            f"Input '{spec.id}' declared as {spec.type!r} by "
                            f"'{current_target}' but {other_spec.type!r} by "
                            f"'{other_target}'"
                        ),
                    }
    return None
