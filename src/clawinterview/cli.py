"""ClawInterview CLI — compile, run, and validate interview contracts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from clawinterview.compiler import compile_run_contract
from clawinterview.engine import InterviewEngine
from clawinterview.models import (
    InterviewContract,
    InterviewStatus,
    InterviewTurn,
    ResolutionContext,
)
from clawinterview.schema import validate_interview_contract
from clawinterview.state import load_interview_state, save_interview_state


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------


def cmd_validate(path: Path) -> int:
    """Validate a target's interview contract YAML.

    Loads the YAML file, extracts the ``contracts.interview`` sub-document
    (if present), and runs :func:`validate_interview_contract`.

    Parameters
    ----------
    path:
        Path to the contract YAML file.

    Returns
    -------
    int
        0 on success, 1 on validation failure or file error.
    """
    try:
        raw: dict[str, Any] = yaml.safe_load(path.read_text())
    except FileNotFoundError:
        print(f"Error: file not found: {path}", file=sys.stderr)
        return 1
    except yaml.YAMLError as exc:
        print(f"Error: invalid YAML in {path}: {exc}", file=sys.stderr)
        return 1

    # Extract interview sub-document when nested under contracts.interview.
    contract_dict: dict[str, Any]
    if "contracts" in raw and isinstance(raw.get("contracts"), dict):
        interview_section = raw["contracts"].get("interview")
        if interview_section is not None:
            contract_dict = interview_section
        else:
            contract_dict = raw
    else:
        contract_dict = raw

    result = validate_interview_contract(contract_dict)
    if result.is_valid:
        print(f"OK: {path} is valid")
        return 0

    print(f"INVALID: {path}")
    for error in result.errors:
        print(f"  [{error.get('path', '$')}] {error.get('message', '')}")
    return 1


def cmd_compile(path: Path) -> int:
    """Compile interview contracts for a pipeline.

    Loads the pipeline YAML, discovers participating targets that carry a
    ``contract_path`` pointing to a valid contract, compiles them into a
    single :class:`~clawinterview.models.CompiledRunContract`, and prints a
    human-readable summary.

    Parameters
    ----------
    path:
        Path to the pipeline YAML file.

    Returns
    -------
    int
        0 on success, 1 on error.
    """
    try:
        pipeline: dict[str, Any] = yaml.safe_load(path.read_text())
    except FileNotFoundError:
        print(f"Error: pipeline file not found: {path}", file=sys.stderr)
        return 1
    except yaml.YAMLError as exc:
        print(f"Error: invalid YAML in {path}: {exc}", file=sys.stderr)
        return 1

    pipeline_id: str = (
        pipeline.get("pipeline", {}).get("name", "unknown-pipeline")
        if isinstance(pipeline.get("pipeline"), dict)
        else "unknown-pipeline"
    )

    # Collect target contracts from participating_targets entries.
    participating_targets: list[dict[str, Any]] = pipeline.get(
        "participating_targets", []
    ) or []

    target_contracts: list[tuple[str, InterviewContract]] = []
    base_dir = path.parent

    for entry in participating_targets:
        contract_path_str: str | None = entry.get("contract_path")
        if not contract_path_str:
            continue

        contract_file = base_dir / contract_path_str
        try:
            raw = yaml.safe_load(contract_file.read_text())
        except (FileNotFoundError, yaml.YAMLError):
            continue

        # Extract interview sub-document when nested.
        if "contracts" in raw and isinstance(raw.get("contracts"), dict):
            interview_section = raw["contracts"].get("interview")
            if interview_section is not None:
                raw = interview_section

        try:
            contract = InterviewContract.model_validate(raw)
        except Exception:
            continue

        target_id: str = entry.get("id", entry.get("name", "unknown"))
        target_contracts.append((target_id, contract))

    if not target_contracts:
        print(
            "Warning: no participating targets with valid contracts found. "
            "Nothing compiled.",
            file=sys.stderr,
        )
        return 1

    import uuid

    run_id = str(uuid.uuid4())
    compiled = compile_run_contract(pipeline_id, run_id, target_contracts)

    n_inputs = len(compiled.inputs)
    n_outputs = len(compiled.outputs)
    n_targets = len(compiled.participating_targets)
    print(
        f"Compiled pipeline '{pipeline_id}': "
        f"{n_targets} target(s), {n_inputs} input(s), {n_outputs} output(s)"
    )
    return 0


def cmd_run(path: Path, bypass: bool = False) -> int:
    """Run the interview for a pipeline.

    Loads the pipeline YAML, discovers participating target contracts,
    compiles them, starts the :class:`~clawinterview.engine.InterviewEngine`,
    and prints the first question or the brief summary (when ``bypass`` is
    True).

    Parameters
    ----------
    path:
        Path to the pipeline YAML file.
    bypass:
        When ``True``, skip human questions (bypass mode).

    Returns
    -------
    int
        0 on success, 1 on error.
    """
    try:
        pipeline: dict[str, Any] = yaml.safe_load(path.read_text())
    except FileNotFoundError:
        print(f"Error: pipeline file not found: {path}", file=sys.stderr)
        return 1
    except yaml.YAMLError as exc:
        print(f"Error: invalid YAML in {path}: {exc}", file=sys.stderr)
        return 1

    pipeline_id: str = (
        pipeline.get("pipeline", {}).get("name", "unknown-pipeline")
        if isinstance(pipeline.get("pipeline"), dict)
        else "unknown-pipeline"
    )

    participating_targets: list[dict[str, Any]] = pipeline.get(
        "participating_targets", []
    ) or []

    target_contracts: list[tuple[str, InterviewContract]] = []
    base_dir = path.parent

    for entry in participating_targets:
        contract_path_str: str | None = entry.get("contract_path")
        if not contract_path_str:
            continue

        contract_file = base_dir / contract_path_str
        try:
            raw = yaml.safe_load(contract_file.read_text())
        except (FileNotFoundError, yaml.YAMLError):
            continue

        if "contracts" in raw and isinstance(raw.get("contracts"), dict):
            interview_section = raw["contracts"].get("interview")
            if interview_section is not None:
                raw = interview_section

        try:
            contract = InterviewContract.model_validate(raw)
        except Exception:
            continue

        target_id: str = entry.get("id", entry.get("name", "unknown"))
        target_contracts.append((target_id, contract))

    if not target_contracts:
        print(
            "Warning: no participating targets with valid contracts found.",
            file=sys.stderr,
        )
        return 1

    import uuid

    run_id = str(uuid.uuid4())
    context = ResolutionContext(run_id=run_id)
    engine = InterviewEngine()
    state = engine.start(
        pipeline_id=pipeline_id,
        run_id=run_id,
        target_contracts=target_contracts,
        context=context,
        bypass_mode=bypass,
    )

    if bypass or state.status == InterviewStatus.COMPLETE:
        print(f"Interview complete for pipeline '{pipeline_id}' (run: {run_id})")
        if state.brief is not None:
            ctx = state.brief.context_layer
            if ctx:
                print("Brief context:")
                for k, v in ctx.items():
                    print(f"  {k}: {v}")
    elif state.status == InterviewStatus.FAILED:
        print(
            f"Interview failed for pipeline '{pipeline_id}' — "
            "unresolved blocking inputs in bypass mode.",
            file=sys.stderr,
        )
        return 1
    else:
        # AWAITING_INPUT — print first question.
        current_turn = engine.get_current_turn(state)
        if current_turn is not None and current_turn.question:
            print(f"Q{current_turn.turn_number}: {current_turn.question}")
        else:
            print("Interview started. No question generated.")

    return 0


def _turn_to_dict(turn: InterviewTurn) -> dict[str, Any]:
    """Serialize an InterviewTurn to a JSON-friendly dict."""
    return {
        "number": turn.turn_number,
        "layer": turn.layer,
        "summary": turn.summary,
        "recommendation": turn.recommendation,
        "options": [opt.model_dump(mode="json") for opt in turn.options],
        "question": turn.question,
    }


def _state_to_json(state: Any, engine: InterviewEngine) -> dict[str, Any]:
    """Build the JSON output envelope from an InterviewState."""
    status_map = {
        InterviewStatus.AWAITING_INPUT: "awaiting_input",
        InterviewStatus.COMPLETE: "complete",
        InterviewStatus.FAILED: "failed",
    }
    status_str = status_map.get(state.status, state.status.value)

    turn_dict: dict[str, Any] | None = None
    current_turn = engine.get_current_turn(state)
    if current_turn is not None:
        turn_dict = _turn_to_dict(current_turn)

    brief_dict: dict[str, Any] | None = None
    if state.brief is not None:
        brief_dict = state.brief.model_dump(mode="json")

    return {
        "status": status_str,
        "run_id": state.run_id,
        "pipeline_id": state.pipeline_id,
        "turn": turn_dict,
        "brief": brief_dict,
    }


def _load_target_contracts(
    path: Path,
) -> tuple[str, list[tuple[str, InterviewContract]]] | None:
    """Load pipeline YAML and discover target contracts.

    Returns (pipeline_id, target_contracts) or None on error.
    """
    try:
        pipeline: dict[str, Any] = yaml.safe_load(path.read_text())
    except FileNotFoundError:
        print(
            json.dumps({"status": "failed", "error": f"pipeline file not found: {path}"}),
            file=sys.stderr,
        )
        return None
    except yaml.YAMLError as exc:
        print(
            json.dumps({"status": "failed", "error": f"invalid YAML in {path}: {exc}"}),
            file=sys.stderr,
        )
        return None

    pipeline_id: str = (
        pipeline.get("pipeline", {}).get("name", "unknown-pipeline")
        if isinstance(pipeline.get("pipeline"), dict)
        else "unknown-pipeline"
    )

    participating_targets: list[dict[str, Any]] = pipeline.get(
        "participating_targets", []
    ) or []

    target_contracts: list[tuple[str, InterviewContract]] = []
    base_dir = path.parent

    for entry in participating_targets:
        contract_path_str: str | None = entry.get("contract_path")
        if not contract_path_str:
            continue

        contract_file = base_dir / contract_path_str
        try:
            raw = yaml.safe_load(contract_file.read_text())
        except (FileNotFoundError, yaml.YAMLError):
            continue

        if "contracts" in raw and isinstance(raw.get("contracts"), dict):
            interview_section = raw["contracts"].get("interview")
            if interview_section is not None:
                raw = interview_section

        try:
            contract = InterviewContract.model_validate(raw)
        except Exception:
            continue

        target_id: str = entry.get("id", entry.get("name", "unknown"))
        target_contracts.append((target_id, contract))

    if not target_contracts:
        print(
            json.dumps({
                "status": "failed",
                "error": "no participating targets with valid contracts found",
            }),
            file=sys.stderr,
        )
        return None

    return pipeline_id, target_contracts


def cmd_start(path: Path, pipeline_args: dict[str, str] | None = None) -> int:
    """Start a multi-turn interview session and output JSON.

    Loads pipeline YAML, discovers target contracts, creates a
    ResolutionContext, starts the interview engine, persists state to
    ``memory/pipelines/<run_id>/``, and prints JSON to stdout.

    Parameters
    ----------
    path:
        Path to the pipeline YAML file.
    pipeline_args:
        Optional key=value pairs passed as pipeline_args in the context.

    Returns
    -------
    int
        0 on success, 1 on error.
    """
    result = _load_target_contracts(path)
    if result is None:
        return 1

    pipeline_id, target_contracts = result

    import uuid

    run_id = str(uuid.uuid4())[:8]
    run_dir = Path("memory/pipelines") / run_id

    context = ResolutionContext(
        run_id=run_id,
        pipeline_args=pipeline_args or {},
    )
    engine = InterviewEngine()
    state = engine.start(
        pipeline_id=pipeline_id,
        run_id=run_id,
        target_contracts=target_contracts,
        context=context,
        run_dir=run_dir,
    )

    output = _state_to_json(state, engine)
    print(json.dumps(output, indent=2))
    return 0


def cmd_respond(run_id: str, response: str) -> int:
    """Respond to an active interview turn and output JSON.

    Loads state from ``memory/pipelines/<run_id>/``, calls
    ``engine.process_response``, persists updated state, and prints
    JSON to stdout.

    Parameters
    ----------
    run_id:
        The run_id returned by ``cmd_start``.
    response:
        The operator's response text.

    Returns
    -------
    int
        0 on success, 1 on error.
    """
    run_dir = Path("memory/pipelines") / run_id

    state = load_interview_state(run_dir)
    if state is None:
        print(
            json.dumps({
                "status": "failed",
                "error": f"no interview state found for run_id={run_id}",
            }),
            file=sys.stderr,
        )
        return 1

    engine = InterviewEngine()
    state = engine.process_response(
        state=state,
        response=response,
        run_dir=run_dir,
    )

    output = _state_to_json(state, engine)
    print(json.dumps(output, indent=2))
    return 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch to the appropriate command.

    Parameters
    ----------
    argv:
        Argument list (``sys.argv[1:]`` by default).

    Returns
    -------
    int
        Exit code: 0 on success, 1 on failure.
    """
    parser = argparse.ArgumentParser(
        prog="clawinterview",
        description="ClawInterview CLI",
    )
    sub = parser.add_subparsers(dest="command")

    # compile command
    compile_p = sub.add_parser(
        "compile",
        help="Compile interview contracts for a pipeline",
    )
    compile_p.add_argument("pipeline", help="Path to pipeline YAML")

    # validate command
    validate_p = sub.add_parser(
        "validate",
        help="Validate a target's interview contract",
    )
    validate_p.add_argument("contract", help="Path to contract YAML")

    # run command
    run_p = sub.add_parser(
        "run",
        help="Run interview for a pipeline",
    )
    run_p.add_argument("pipeline", help="Path to pipeline YAML")
    run_p.add_argument(
        "--bypass",
        action="store_true",
        help="Skip human questions",
    )

    # start command — multi-turn, outputs JSON
    start_p = sub.add_parser(
        "start",
        help="Start a multi-turn interview session (outputs JSON)",
    )
    start_p.add_argument("pipeline", help="Path to pipeline YAML")
    start_p.add_argument(
        "--args",
        nargs="*",
        metavar="key=value",
        help="Pipeline arguments as key=value pairs",
    )

    # respond command — advance a multi-turn interview, outputs JSON
    respond_p = sub.add_parser(
        "respond",
        help="Respond to an active interview turn (outputs JSON)",
    )
    respond_p.add_argument("run_id", help="Run ID from a previous start")
    respond_p.add_argument("response", help="Operator response text")

    args = parser.parse_args(argv)

    if args.command == "validate":
        return cmd_validate(Path(args.contract))
    elif args.command == "compile":
        return cmd_compile(Path(args.pipeline))
    elif args.command == "run":
        return cmd_run(Path(args.pipeline), bypass=args.bypass)
    elif args.command == "start":
        pipeline_args: dict[str, str] = {}
        if args.args:
            for pair in args.args:
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    pipeline_args[k] = v
        return cmd_start(Path(args.pipeline), pipeline_args=pipeline_args or None)
    elif args.command == "respond":
        return cmd_respond(args.run_id, args.response)
    else:
        parser.print_help()
        return 1
