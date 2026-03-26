"""Layered brief assembler for ClawInterview.

Assembles an :class:`InterviewBrief` incrementally as interview turns complete,
and renders it as Markdown or a structured dict for downstream consumption.
"""

from __future__ import annotations

from typing import Any

from clawinterview.models import InterviewBrief, InterviewTurn


# Map layer name → InterviewBrief attribute name
_LAYER_ATTR: dict[str, str] = {
    "context": "context_layer",
    "strategy": "strategy_layer",
    "constraints": "constraints_layer",
    "execution_brief": "execution_brief",
}


class InterviewBriefAssembler:
    """Assembles a layered interview brief turn by turn."""

    LAYERS = ("context", "strategy", "constraints", "execution_brief")

    def __init__(self, run_id: str) -> None:
        self._brief = InterviewBrief(
            run_id=run_id,
            layer_status={layer: "pending" for layer in self.LAYERS},
        )

    @property
    def brief(self) -> InterviewBrief:
        return self._brief

    def update_layer(self, layer: str, resolved_inputs: dict[str, Any]) -> None:
        """Update a layer with newly resolved input values.

        If the layer is currently ``pending`` it is transitioned to
        ``in_progress``.  The resolved key/value pairs are merged into the
        corresponding brief attribute.

        Args:
            layer: One of :attr:`LAYERS`.
            resolved_inputs: Mapping of input id → resolved value to merge.

        Raises:
            ValueError: If *layer* is not a recognised layer name.
        """
        if layer not in _LAYER_ATTR:
            raise ValueError(
                f"Unknown layer {layer!r}. Must be one of {list(_LAYER_ATTR)}"
            )

        # Transition pending → in_progress
        if self._brief.layer_status.get(layer) == "pending":
            self._brief.layer_status[layer] = "in_progress"

        # Merge resolved_inputs into the correct dict on the brief.
        attr = _LAYER_ATTR[layer]
        current: dict[str, Any] = getattr(self._brief, attr)
        current.update(resolved_inputs)

    def mark_layer_complete(self, layer: str) -> None:
        """Mark a layer as complete.

        Args:
            layer: One of :attr:`LAYERS`.
        """
        self._brief.layer_status[layer] = "complete"

    def is_layer_complete(self, layer: str) -> bool:
        """Return ``True`` when *layer* has status ``complete``."""
        return self._brief.layer_status.get(layer) == "complete"

    def render_layer_summary(self, layer: str) -> str:
        """Render a human-readable Markdown summary of a layer.

        Args:
            layer: One of :attr:`LAYERS`.

        Returns:
            A Markdown string with a level-2 heading and bullet list of
            ``**key**: value`` pairs, or a placeholder when the layer is empty.
        """
        attr = _LAYER_ATTR.get(layer, layer)
        data: dict[str, Any] = getattr(self._brief, attr, {})
        heading = f"## {layer.replace('_', ' ').title()}\n\n"
        if not data:
            return heading + "_No inputs resolved yet._\n"
        lines = "\n".join(f"- **{k}**: {v}" for k, v in data.items())
        return heading + lines + "\n"

    def render_execution_brief(self) -> dict[str, Any]:
        """Render the final execution brief combining all layers.

        Returns:
            A plain dict with keys ``context``, ``strategy``,
            ``constraints``, and ``execution``.
        """
        return {
            "context": dict(self._brief.context_layer),
            "strategy": dict(self._brief.strategy_layer),
            "constraints": dict(self._brief.constraints_layer),
            "execution": dict(self._brief.execution_brief),
        }

    def render_markdown(self) -> str:
        """Render the full brief as Markdown.

        Concatenates the summary for every layer in canonical order,
        prefixed by a level-1 heading that includes the run ID.

        Returns:
            A Markdown string covering all four layers.
        """
        header = f"# Interview Brief — {self._brief.run_id}\n\n"
        sections = "".join(self.render_layer_summary(layer) + "\n" for layer in self.LAYERS)
        return header + sections

    def render_transcript(self, turns: list[InterviewTurn]) -> str:
        """Render the interview transcript as Markdown (FR-012).

        Each turn is formatted as::

            ## Turn {n} — {layer} ({mode})

            **Summary**: {summary}

            **Recommendation**: {recommendation or "None"}

            **Question**: {question}

            **Response**: {response or "(awaiting)"}

            ---

        Args:
            turns: Ordered list of :class:`~clawinterview.models.InterviewTurn`
                instances from the interview session.

        Returns:
            A Markdown string containing all turns.
        """
        if not turns:
            return "_No turns recorded._\n"

        blocks: list[str] = []
        for turn in turns:
            recommendation = turn.recommendation if turn.recommendation is not None else "None"
            response = turn.response if turn.response is not None else "(awaiting)"
            block = (
                f"## Turn {turn.turn_number} — {turn.layer} ({turn.mode.value})\n\n"
                f"**Summary**: {turn.summary}\n\n"
                f"**Recommendation**: {recommendation}\n\n"
                f"**Question**: {turn.question}\n\n"
                f"**Response**: {response}\n\n"
                "---\n"
            )
            blocks.append(block)

        return "\n".join(blocks)
