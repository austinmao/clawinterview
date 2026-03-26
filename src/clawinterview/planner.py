"""ClawInterview question planner.

Determines what question to ask next during an interactive interview.
Implements layer-ordered traversal, dependency-aware input selection,
mode detection, and turn generation.
"""

from __future__ import annotations

from .models import (
    BoundedOption,
    InputSpec,
    InterviewMode,
    InterviewState,
    InterviewTurn,
    ResolutionStatus,
    SemanticFacet,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LAYER_ORDER = ("context", "strategy", "constraints", "execution_brief")

# Facets that map each input to a layer.
_LAYER_FACETS: dict[str, set[SemanticFacet]] = {
    "context": {SemanticFacet.TOPIC, SemanticFacet.AUDIENCE, SemanticFacet.TENANT_CONTEXT},
    "strategy": {SemanticFacet.POSITIONING, SemanticFacet.BRAND, SemanticFacet.OFFER, SemanticFacet.CTA},
    "constraints": {
        SemanticFacet.SCHEDULE,
        SemanticFacet.COMPLIANCE,
        SemanticFacet.APPROVAL,
        SemanticFacet.BUDGET,
        SemanticFacet.TIMELINE,
    },
}

# Facets that trigger deep mode.
_DEEP_FACETS: set[str] = {"strategy", "compliance", "positioning"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def plan_next_turn(state: InterviewState) -> InterviewTurn | None:
    """Return the next interview turn, or None when the interview is complete.

    Traverses layers in LAYER_ORDER, advancing state.current_layer when the
    current layer has no remaining blocking unresolved inputs.  Within a layer
    inputs are ordered: dependencies-satisfied first, then declaration order.
    """
    if state.compiled_contract is None:
        return None

    # Check overall completion: no blocking unresolved inputs anywhere.
    if not _get_unresolved_blocking(state):
        return None

    # Walk layers until we find one with unresolved inputs.
    layer_index = list(LAYER_ORDER).index(state.current_layer) if state.current_layer in LAYER_ORDER else 0

    for idx in range(layer_index, len(LAYER_ORDER)):
        layer = LAYER_ORDER[idx]

        # Advance current_layer pointer if we moved forward.
        if layer != state.current_layer:
            state.current_layer = layer

        layer_input_ids = _get_layer_inputs(state, layer)
        unresolved_in_layer = [
            iid for iid in layer_input_ids if iid in _get_unresolved_blocking_set(state)
        ]

        if unresolved_in_layer:
            # Select the best candidate: prefer inputs whose dependencies are all resolved.
            resolved_ids = {
                iid
                for iid, res in state.resolutions.items()
                if res.status == ResolutionStatus.RESOLVED
            }

            ready = [
                iid
                for iid in unresolved_in_layer
                if _deps_satisfied(state, iid, resolved_ids)
            ]
            candidates = ready if ready else unresolved_in_layer
            target_id = candidates[0]

            # Look up the InputSpec from the compiled contract.
            input_spec = _find_input_spec(state, target_id)
            if input_spec is None:
                continue

            mode = _determine_mode(input_spec)
            summary = _build_summary(state)
            question = _frame_question(input_spec)

            # Recommendation: suggest partial resolution value when medium-confidence.
            recommendation: str | None = None
            resolution = state.resolutions.get(target_id)
            if resolution and resolution.confidence >= 0.4 and resolution.resolved_value is not None:
                recommendation = (
                    f"Based on {resolution.evidence_source}, I suggest: "
                    f"{resolution.resolved_value!r}"
                )

            # Options: generate for enum-typed inputs or inputs with a default_value.
            options: list[BoundedOption] = []
            if input_spec.type.value == "enum":
                options = _default_enum_options(input_spec)
            elif input_spec.default_value is not None:
                options = [
                    BoundedOption(
                        value=str(input_spec.default_value),
                        label=str(input_spec.default_value),
                        description="Recommended default",
                        is_recommended=True,
                    )
                ]

            return InterviewTurn(
                turn_number=len(state.turns) + 1,
                layer=layer,
                mode=mode,
                summary=summary,
                recommendation=recommendation,
                options=options,
                question=question,
            )

    return None


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _get_unresolved_blocking(state: InterviewState) -> list[str]:
    """Return input_ids of blocking inputs that are unresolved."""
    return list(_get_unresolved_blocking_set(state))


def _get_unresolved_blocking_set(state: InterviewState) -> set[str]:
    """Return the set of blocking unresolved input ids."""
    if state.compiled_contract is None:
        return set()
    result: set[str] = set()
    for compiled_input in state.compiled_contract.inputs:
        if not compiled_input.blocking:
            continue
        resolution = state.resolutions.get(compiled_input.id)
        if resolution is None or resolution.status != ResolutionStatus.RESOLVED:
            result.add(compiled_input.id)
    return result


def _get_layer_inputs(state: InterviewState, layer: str) -> list[str]:
    """Return ordered input_ids belonging to the given layer.

    Membership is determined by facet intersection with _LAYER_FACETS.
    Inputs not matching any named layer fall into 'execution_brief'.
    """
    if state.compiled_contract is None:
        return []

    layer_facets = _LAYER_FACETS.get(layer, set())
    is_execution_brief = layer == "execution_brief"

    result: list[str] = []
    for compiled_input in state.compiled_contract.inputs:
        input_facet_set = set(compiled_input.facets)
        matched_layer = _facets_to_layer(input_facet_set)
        if matched_layer == layer:
            result.append(compiled_input.id)
        elif is_execution_brief and matched_layer == "execution_brief":
            result.append(compiled_input.id)

    return result


def _facets_to_layer(facets: set[SemanticFacet]) -> str:
    """Determine which layer an input belongs to based on its facets."""
    for layer_name in ("context", "strategy", "constraints"):
        if facets & _LAYER_FACETS[layer_name]:
            return layer_name
    return "execution_brief"


def _build_summary(state: InterviewState) -> str:
    """Build a readable summary of all resolved inputs with provenance."""
    if state.compiled_contract is None:
        return ""

    lines: list[str] = []
    for compiled_input in state.compiled_contract.inputs:
        resolution = state.resolutions.get(compiled_input.id)
        if resolution and resolution.status == ResolutionStatus.RESOLVED:
            source = resolution.evidence_source or "unknown source"
            lines.append(
                f"- {compiled_input.id}: {resolution.resolved_value!r} (via {source})"
            )

    if not lines:
        return "No inputs resolved yet."
    return "Resolved so far:\n" + "\n".join(lines)


def _determine_mode(input_spec: InputSpec) -> InterviewMode:
    """Return LIGHT or DEEP based on the input's semantic facets.

    LIGHT: input has a default_value or none of its facets are strategically deep.
    DEEP: no default and at least one facet maps to strategy/compliance/positioning.
    """
    if input_spec.default_value is not None:
        return InterviewMode.LIGHT

    facet_names = {f.value for f in input_spec.facets}
    if facet_names & _DEEP_FACETS:
        return InterviewMode.DEEP

    return InterviewMode.LIGHT


def _frame_question(input_spec: InputSpec) -> str:
    """Frame an InputSpec as a design-decision question rather than a raw field prompt."""
    description = input_spec.description.rstrip(".")
    facet_names = {f.value for f in input_spec.facets}

    if "positioning" in facet_names:
        return f"How do you want to position this? {description}."
    if "compliance" in facet_names:
        return f"Any compliance constraints to keep in mind? {description}."
    if "audience" in facet_names:
        return f"Who is the target audience? {description}."
    if "offer" in facet_names:
        return f"What's the core offer being presented? {description}."
    if "cta" in facet_names:
        return f"What action do you want the audience to take? {description}."
    if "schedule" in facet_names:
        return f"What are the timing constraints? {description}."
    if "budget" in facet_names:
        return f"What budget parameters apply here? {description}."
    if "brand" in facet_names:
        return f"What brand direction should guide this? {description}."
    if "topic" in facet_names:
        return f"What's the central topic or theme? {description}."

    return f"What's your decision on: {description}?"


def _deps_satisfied(state: InterviewState, input_id: str, resolved_ids: set[str]) -> bool:
    """Return True if all declared depends_on inputs are resolved."""
    input_spec = _find_input_spec(state, input_id)
    if input_spec is None:
        return True
    return all(dep in resolved_ids for dep in input_spec.depends_on)


def _find_input_spec(state: InterviewState, input_id: str) -> InputSpec | None:
    """Locate an InputSpec by id across required and optional inputs in the contract.

    Compiled inputs carry facets and strategies but not default_value or depends_on,
    so we return a synthetic InputSpec populated from CompiledInput fields.
    """
    if state.compiled_contract is None:
        return None
    for compiled_input in state.compiled_contract.inputs:
        if compiled_input.id == input_id:
            return InputSpec(
                id=compiled_input.id,
                type=compiled_input.type,
                description=compiled_input.id.replace("_", " ").capitalize(),
                facets=list(compiled_input.facets),
                resolution_strategies=list(compiled_input.resolution_strategies),
                confidence_threshold=compiled_input.confidence_threshold,
            )
    return None


def _default_enum_options(input_spec: InputSpec) -> list[BoundedOption]:
    """Generate placeholder bounded options for enum-typed inputs."""
    if input_spec.default_value is not None:
        return [
            BoundedOption(
                value=str(input_spec.default_value),
                label=str(input_spec.default_value),
                description="Default option",
                is_recommended=True,
            )
        ]
    return []
