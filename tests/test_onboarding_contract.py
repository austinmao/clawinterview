"""Regression tests for the onboarding interview contract and resolver wiring."""

from __future__ import annotations

import json
from pathlib import Path

from clawinterview.cli import cmd_validate
from clawinterview.models import InputSpec, PrimitiveType, ResolutionContext, ResolverKind
from clawinterview.resolvers import hyperspell_profile


def test_onboarding_contract_validates() -> None:
    contract_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "clawinterview"
        / "contracts"
        / "onboarding.yaml"
    )

    assert cmd_validate(contract_path) == 0


def test_hyperspell_profile_resolver_accepts_inline_json_string() -> None:
    spec = InputSpec(
        id="business_type",
        type=PrimitiveType.STRING,
        description="Business type",
        confidence_threshold=0.8,
        resolution_strategies=[ResolverKind.HYPERSPELL_PROFILE],
    )
    context = ResolutionContext(
        pipeline_args={
            "hyperspell_profile": json.dumps(
                {
                    "business_type": "agency",
                    "confidence": 0.91,
                }
            )
        }
    )

    result = hyperspell_profile.resolve(spec, context)

    assert result is not None
    assert result.value == "agency"
    assert result.confidence == 0.91


def test_hyperspell_profile_resolver_uses_aliases_for_inline_json_string() -> None:
    spec = InputSpec(
        id="team_involvement",
        type=PrimitiveType.STRING,
        description="Team involvement",
        confidence_threshold=0.7,
        resolution_strategies=[ResolverKind.HYPERSPELL_PROFILE],
    )
    context = ResolutionContext(
        pipeline_args={
            "hyperspell_profile": json.dumps(
                {
                    "team_size": 4,
                    "confidence": 0.88,
                }
            )
        }
    )

    result = hyperspell_profile.resolve(spec, context)

    assert result is not None
    assert result.value == 4
    assert result.evidence_source == "hyperspell_profile['team_size']"
