"""YAML state persistence for ClawInterview.

Provides load/save functions for InterviewState, CompiledRunContract,
InputResolution, InterviewTurn transcripts, and InterviewBrief documents.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from clawinterview.models import (
    CompiledRunContract,
    InputResolution,
    InterviewBrief,
    InterviewState,
    InterviewTurn,
)

_INTERVIEW_STATE_FILE = "interview-state.yaml"
_COMPILED_CONTRACT_FILE = "compiled-interview.yaml"
_RESOLUTION_STATE_FILE = "input-resolution-state.yaml"
_TRANSCRIPT_FILE = "interview-transcript.md"
_BRIEF_FILE = "interview-brief.md"


def _dump(data: Any, path: Path) -> None:
    path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))


def save_interview_state(state: InterviewState, run_dir: Path) -> None:
    """Persist the full InterviewState to ``run_dir/interview-state.yaml``."""
    run_dir.mkdir(parents=True, exist_ok=True)
    _dump(state.model_dump(mode="json"), run_dir / _INTERVIEW_STATE_FILE)


def load_interview_state(run_dir: Path) -> InterviewState | None:
    """Load InterviewState from ``run_dir/interview-state.yaml``.

    Returns None if the file does not exist.
    """
    path = run_dir / _INTERVIEW_STATE_FILE
    if not path.exists():
        return None
    data = yaml.safe_load(path.read_text())
    return InterviewState.model_validate(data)


def save_compiled_contract(contract: CompiledRunContract, run_dir: Path) -> None:
    """Persist the CompiledRunContract to ``run_dir/compiled-interview.yaml``."""
    run_dir.mkdir(parents=True, exist_ok=True)
    _dump(contract.model_dump(mode="json"), run_dir / _COMPILED_CONTRACT_FILE)


def load_compiled_contract(run_dir: Path) -> CompiledRunContract | None:
    """Load CompiledRunContract from ``run_dir/compiled-interview.yaml``.

    Returns None if the file does not exist.
    """
    path = run_dir / _COMPILED_CONTRACT_FILE
    if not path.exists():
        return None
    data = yaml.safe_load(path.read_text())
    return CompiledRunContract.model_validate(data)


def save_resolution_state(
    resolutions: dict[str, InputResolution], run_dir: Path
) -> None:
    """Persist input resolutions to ``run_dir/input-resolution-state.yaml``."""
    run_dir.mkdir(parents=True, exist_ok=True)
    serialized = {k: v.model_dump(mode="json") for k, v in resolutions.items()}
    _dump(serialized, run_dir / _RESOLUTION_STATE_FILE)


def save_transcript(turns: list[InterviewTurn], run_dir: Path) -> None:
    """Write interview turns to ``run_dir/interview-transcript.md``."""
    run_dir.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for turn in turns:
        lines.append(f"## Turn {turn.turn_number} — {turn.layer}")
        lines.append("")
        lines.append(f"**Summary**: {turn.summary}")
        lines.append("")
        lines.append(f"**Recommendation**: {turn.recommendation or ''}")
        lines.append("")
        lines.append(f"**Question**: {turn.question}")
        lines.append("")
        lines.append(f"**Response**: {turn.response or ''}")
        lines.append("")
        lines.append("---")
        lines.append("")
    (run_dir / _TRANSCRIPT_FILE).write_text("\n".join(lines))


def save_brief(brief: InterviewBrief, run_dir: Path) -> None:
    """Write the layered InterviewBrief to ``run_dir/interview-brief.md``."""
    run_dir.mkdir(parents=True, exist_ok=True)
    layer_map = {
        "Context Layer": brief.context_layer,
        "Strategy Layer": brief.strategy_layer,
        "Constraints Layer": brief.constraints_layer,
        "Execution Brief": brief.execution_brief,
    }
    lines: list[str] = [f"# Interview Brief — {brief.run_id}", ""]
    for section_title, layer_data in layer_map.items():
        lines.append(f"## {section_title}")
        lines.append("")
        if layer_data:
            for key, value in layer_data.items():
                lines.append(f"- **{key}**: {value}")
        else:
            lines.append("_(empty)_")
        lines.append("")
    if brief.layer_status:
        lines.append("## Layer Status")
        lines.append("")
        for layer, status in brief.layer_status.items():
            lines.append(f"- **{layer}**: {status}")
        lines.append("")
    (run_dir / _BRIEF_FILE).write_text("\n".join(lines))
