"""ClawInterview main orchestration engine.

Coordinates contract compilation, input resolution, question planning, and
brief assembly for pipeline interviews.  ``InterviewEngine`` is the single
entry point callers use to start, advance, and resume an interview session.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from clawinterview.brief import InterviewBriefAssembler
from clawinterview.compiler import compile_run_contract
from clawinterview.models import (
    InputResolution,
    InterviewContract,
    InterviewState,
    InterviewStatus,
    InterviewTurn,
    ResolutionContext,
    ResolutionStatus,
    ResolverKind,
)
from clawinterview.planner import plan_next_turn
from clawinterview.resolver import ResolverRegistry, check_freshness, resolve_input
from clawinterview.resolvers import register_all_resolvers
from clawinterview.state import (
    load_interview_state,
    save_brief,
    save_compiled_contract,
    save_interview_state,
    save_resolution_state,
    save_transcript,
)

logger = logging.getLogger("clawinterview.engine")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class InterviewEngine:
    """Main engine that orchestrates contract compilation, input resolution,
    question planning, and brief assembly for pipeline interviews."""

    def __init__(self, registry: ResolverRegistry | None = None) -> None:
        if registry is None:
            registry = ResolverRegistry()
            register_all_resolvers(registry)
        self._registry = registry

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(
        self,
        pipeline_id: str,
        run_id: str,
        target_contracts: list[tuple[str, InterviewContract]],
        context: ResolutionContext,
        bypass_mode: bool = False,
        run_dir: Path | None = None,
    ) -> InterviewState:
        """Start a new interview: compile → resolve → plan first turn.

        Parameters
        ----------
        pipeline_id:
            Stable pipeline identifier.
        run_id:
            Unique identifier for this execution run.
        target_contracts:
            Ordered ``(target_id, InterviewContract)`` pairs.
        context:
            Resolution context passed to all resolvers.
        bypass_mode:
            When ``True``, unresolved blocking inputs cause FAILED instead
            of entering the interactive turn loop.
        run_dir:
            Optional directory for state persistence.  Skipped when ``None``.

        Returns
        -------
        InterviewState
            Freshly created state, either COMPLETE, AWAITING_INPUT, or FAILED.
        """
        now = _now_iso()

        # 1. Compile run contract.
        compiled = compile_run_contract(pipeline_id, run_id, target_contracts)

        # 2. Create InterviewState.
        state = InterviewState(
            run_id=run_id,
            pipeline_id=pipeline_id,
            status=InterviewStatus.RESOLVING,
            compiled_contract=compiled,
            bypass_mode=bypass_mode,
            started_at=now,
            updated_at=now,
        )

        # 3. Resolve all inputs using the registry.
        assembler = InterviewBriefAssembler(run_id=run_id)
        for compiled_input in compiled.inputs:
            from clawinterview.models import InputSpec  # local to avoid circular

            spec = InputSpec(
                id=compiled_input.id,
                type=compiled_input.type,
                description=compiled_input.id.replace("_", " ").capitalize(),
                facets=list(compiled_input.facets),
                resolution_strategies=list(compiled_input.resolution_strategies),
                confidence_threshold=compiled_input.confidence_threshold,
            )
            resolution = resolve_input(self._registry, spec, context)
            state.resolutions[compiled_input.id] = resolution

            if resolution.status == ResolutionStatus.RESOLVED:
                assembler.update_layer(
                    state.current_layer,
                    {compiled_input.id: resolution.resolved_value},
                )

        state.brief = assembler.brief

        # 4. Check for unresolved blocking inputs.
        unresolved_blocking = [
            inp.id
            for inp in compiled.inputs
            if inp.blocking
            and state.resolutions.get(inp.id, InputResolution(input_id=inp.id)).status
            != ResolutionStatus.RESOLVED
        ]

        if not unresolved_blocking:
            # All blocking inputs resolved — complete immediately.
            state.status = InterviewStatus.COMPLETE
            state.completed_at = _now_iso()
        elif bypass_mode:
            # 5a. Bypass mode: fail with unresolved blockers report.
            logger.warning(
                "interview_bypass_failed run_id=%s unresolved=%s",
                run_id,
                unresolved_blocking,
            )
            state.status = InterviewStatus.FAILED
        else:
            # 5b. Plan first turn.
            state.status = InterviewStatus.AWAITING_INPUT
            first_turn = plan_next_turn(state)
            if first_turn is not None:
                first_turn = first_turn.model_copy(update={"timestamp": _now_iso()})
                state.turns.append(first_turn)

        state.updated_at = _now_iso()

        # 6. Persist state.
        if run_dir is not None:
            self._save_all(state, assembler, run_dir)

        return state

    def process_response(
        self,
        state: InterviewState,
        response: str,
        context: ResolutionContext | None = None,
        run_dir: Path | None = None,
    ) -> InterviewState:
        """Process operator response and advance the interview.

        Parameters
        ----------
        state:
            Current interview state with at least one unanswered turn.
        response:
            The operator's response to the current question.
        context:
            Optional resolution context for re-resolution after response.
        run_dir:
            Optional directory for state persistence.

        Returns
        -------
        InterviewState
            Updated state: either AWAITING_INPUT (more questions) or COMPLETE.
        """
        # 1. Find the current turn (last turn with no response).
        current_turn = self.get_current_turn(state)
        if current_turn is None:
            logger.warning("process_response called with no unanswered turn run_id=%s", state.run_id)
            return state

        # 2. Record the response on the turn.
        turn_index = state.turns.index(current_turn)
        updated_turn = current_turn.model_copy(update={"response": response})
        state.turns[turn_index] = updated_turn

        # 3. Resolve the input that was asked about (confidence=1.0 — human-provided).
        #    The current turn's question corresponds to the first unresolved blocking input
        #    in the current layer. We identify it from `resolved_inputs` if set, or fall
        #    back to finding the first unresolved blocking input.
        target_input_id: str | None = None
        if updated_turn.resolved_inputs:
            target_input_id = updated_turn.resolved_inputs[0]
        else:
            # Derive from state: first unresolved blocking input in layer order.
            if state.compiled_contract is not None:
                for compiled_input in state.compiled_contract.inputs:
                    if not compiled_input.blocking:
                        continue
                    res = state.resolutions.get(compiled_input.id)
                    if res is None or res.status != ResolutionStatus.RESOLVED:
                        target_input_id = compiled_input.id
                        break

        if target_input_id is not None:
            human_resolution = InputResolution(
                input_id=target_input_id,
                status=ResolutionStatus.RESOLVED,
                resolver_used=ResolverKind.ASK,
                confidence=1.0,
                evidence_source="operator_response",
                resolved_value=response,
                resolved_at=_now_iso(),
            )
            state.resolutions[target_input_id] = human_resolution

            # 4. Update brief with newly resolved input.
            assembler = InterviewBriefAssembler(run_id=state.run_id)
            # Repopulate assembler from existing resolutions.
            if state.brief is not None:
                assembler._brief = state.brief  # type: ignore[attr-defined]
            assembler.update_layer(
                updated_turn.layer,
                {target_input_id: response},
            )
            state.brief = assembler.brief

        state.updated_at = _now_iso()

        # 5. Plan next turn.
        next_turn = plan_next_turn(state)

        if next_turn is None:
            # 6. No more turns needed — complete.
            state.status = InterviewStatus.COMPLETE
            state.completed_at = _now_iso()
        else:
            # 7. More questions remain.
            state.status = InterviewStatus.AWAITING_INPUT
            next_turn = next_turn.model_copy(update={"timestamp": _now_iso()})
            state.turns.append(next_turn)

        state.updated_at = _now_iso()

        if run_dir is not None:
            assembler_for_save = InterviewBriefAssembler(run_id=state.run_id)
            if state.brief is not None:
                assembler_for_save._brief = state.brief  # type: ignore[attr-defined]
            self._save_all(state, assembler_for_save, run_dir)

        return state

    def resume(
        self,
        run_dir: Path,
        context: ResolutionContext,
    ) -> InterviewState:
        """Resume an interrupted interview from persisted state.

        Parameters
        ----------
        run_dir:
            Directory containing the persisted ``interview-state.yaml``.
        context:
            Fresh resolution context for re-resolving stale inputs.

        Returns
        -------
        InterviewState
            Updated state continuing from where it left off.

        Raises
        ------
        FileNotFoundError
            If no persisted state exists in ``run_dir``.
        """
        # 1. Load state from run_dir.
        state = load_interview_state(run_dir)
        if state is None:
            raise FileNotFoundError(f"No interview state found in {run_dir}")

        if state.compiled_contract is None:
            logger.warning("resume called but compiled_contract is None run_id=%s", state.run_id)
            return state

        # 2. Check freshness and re-resolve stale inputs.
        for compiled_input in state.compiled_contract.inputs:
            resolution = state.resolutions.get(compiled_input.id)
            if resolution is None or resolution.status != ResolutionStatus.RESOLVED:
                continue

            from clawinterview.models import InputSpec

            spec = InputSpec(
                id=compiled_input.id,
                type=compiled_input.type,
                description=compiled_input.id.replace("_", " ").capitalize(),
                facets=list(compiled_input.facets),
                resolution_strategies=list(compiled_input.resolution_strategies),
                confidence_threshold=compiled_input.confidence_threshold,
                freshness_policy=None,
            )

            # 3. Re-resolve stale inputs.
            if not check_freshness(resolution, spec):
                logger.info(
                    "resume_stale_resolution input_id=%s run_id=%s",
                    compiled_input.id,
                    state.run_id,
                )
                fresh_resolution = resolve_input(self._registry, spec, context)
                state.resolutions[compiled_input.id] = fresh_resolution

        state.updated_at = _now_iso()

        # 4. Check overall blocking resolution status.
        unresolved_blocking = [
            inp.id
            for inp in state.compiled_contract.inputs
            if inp.blocking
            and state.resolutions.get(inp.id, InputResolution(input_id=inp.id)).status
            != ResolutionStatus.RESOLVED
        ]

        if not unresolved_blocking:
            # 4a. All blocking inputs now resolved — complete.
            state.status = InterviewStatus.COMPLETE
            state.completed_at = _now_iso()
        else:
            # 5. Plan next turn.
            state.status = InterviewStatus.AWAITING_INPUT
            # Only append a new turn if the last turn already has a response.
            if not state.turns or state.turns[-1].response is not None:
                next_turn = plan_next_turn(state)
                if next_turn is not None:
                    next_turn = next_turn.model_copy(update={"timestamp": _now_iso()})
                    state.turns.append(next_turn)

        state.updated_at = _now_iso()

        assembler = InterviewBriefAssembler(run_id=state.run_id)
        if state.brief is not None:
            assembler._brief = state.brief  # type: ignore[attr-defined]
        self._save_all(state, assembler, run_dir)

        return state

    def is_complete(self, state: InterviewState) -> bool:
        """Return True when the interview is fully complete."""
        return state.status == InterviewStatus.COMPLETE

    def get_current_turn(self, state: InterviewState) -> InterviewTurn | None:
        """Get the current unanswered turn, if any."""
        if state.turns and state.turns[-1].response is None:
            return state.turns[-1]
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _save_all(
        self,
        state: InterviewState,
        assembler: InterviewBriefAssembler,
        run_dir: Path,
    ) -> None:
        """Persist all interview artifacts to run_dir."""
        save_interview_state(state, run_dir)
        if state.compiled_contract is not None:
            save_compiled_contract(state.compiled_contract, run_dir)
        save_resolution_state(state.resolutions, run_dir)
        save_transcript(state.turns, run_dir)
        if state.brief is not None:
            save_brief(state.brief, run_dir)
