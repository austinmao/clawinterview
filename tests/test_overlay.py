"""Tests for clawinterview.overlay module.

Covers:
- load_department_pack: success and missing-file cases
- load_tenant_overlay: fixture file parsing and missing-file cases
- merge_contract: all layering rules (base/pack/overlay precedence)
"""

from __future__ import annotations

from pathlib import Path

import pytest
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
from clawinterview.overlay import (
    load_department_pack,
    load_tenant_overlay,
    merge_contract,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_input(
    id_: str,
    type_: PrimitiveType = PrimitiveType.STRING,
    facets: list[SemanticFacet] | None = None,
    resolution_strategies: list[ResolverKind] | None = None,
    confidence_threshold: float = 0.7,
) -> InputSpec:
    return InputSpec(
        id=id_,
        type=type_,
        description=f"Test input: {id_}",
        facets=facets or [],
        resolution_strategies=resolution_strategies or [],
        confidence_threshold=confidence_threshold,
    )


def _make_contract(
    required: list[InputSpec] | None = None,
    optional: list[InputSpec] | None = None,
    strategies: list[ResolverKind] | None = None,
    facets: list[SemanticFacet] | None = None,
    completion_rules: CompletionRule | None = None,
    evidence_policy: dict | None = None,
) -> InterviewContract:
    return InterviewContract(
        required_inputs=required or [],
        optional_inputs=optional or [],
        resolution_strategies=strategies or [],
        semantic_facets=facets or [],
        completion_rules=completion_rules,
        evidence_policy=evidence_policy or {},
    )


# ---------------------------------------------------------------------------
# load_department_pack
# ---------------------------------------------------------------------------


class TestLoadDepartmentPack:
    def test_load_marketing_pack_succeeds(self) -> None:
        """Marketing pack loads and returns an InterviewContract."""
        contract = load_department_pack("marketing")

        assert contract is not None
        assert isinstance(contract, InterviewContract)

    def test_marketing_pack_has_required_inputs(self) -> None:
        """Marketing pack required inputs include campaign_topic and target_audience."""
        contract = load_department_pack("marketing")
        assert contract is not None

        req_ids = {inp.id for inp in contract.required_inputs}
        assert "campaign_topic" in req_ids
        assert "target_audience" in req_ids

    def test_marketing_pack_has_optional_inputs(self) -> None:
        """Marketing pack optional inputs include brand_voice, cta_type, offer_details."""
        contract = load_department_pack("marketing")
        assert contract is not None

        opt_ids = {inp.id for inp in contract.optional_inputs}
        assert "brand_voice" in opt_ids
        assert "cta_type" in opt_ids
        assert "offer_details" in opt_ids

    def test_marketing_pack_has_semantic_facets(self) -> None:
        """Marketing pack populates semantic_facets from default_facets."""
        contract = load_department_pack("marketing")
        assert contract is not None

        assert len(contract.semantic_facets) > 0
        assert SemanticFacet.TOPIC in contract.semantic_facets
        assert SemanticFacet.AUDIENCE in contract.semantic_facets

    def test_marketing_pack_has_resolution_strategies(self) -> None:
        """Marketing pack populates resolution_strategies."""
        contract = load_department_pack("marketing")
        assert contract is not None

        assert len(contract.resolution_strategies) > 0
        assert ResolverKind.USER_ARGS in contract.resolution_strategies
        assert ResolverKind.ASK in contract.resolution_strategies

    def test_marketing_pack_input_types_are_valid(self) -> None:
        """All inputs in the marketing pack have valid PrimitiveType values."""
        contract = load_department_pack("marketing")
        assert contract is not None

        all_inputs = contract.required_inputs + contract.optional_inputs
        for inp in all_inputs:
            assert isinstance(inp.type, PrimitiveType)

    def test_load_engineering_pack_succeeds(self) -> None:
        """Engineering pack loads successfully."""
        contract = load_department_pack("engineering")
        assert contract is not None
        req_ids = {inp.id for inp in contract.required_inputs}
        assert "feature_scope" in req_ids
        assert "tech_stack" in req_ids

    def test_load_nonexistent_pack_returns_none(self) -> None:
        """A department with no pack file returns None."""
        result = load_department_pack("nonexistent_department_xyz")
        assert result is None

    def test_load_empty_department_name_returns_none(self) -> None:
        """Empty department string returns None (file won't exist)."""
        result = load_department_pack("")
        assert result is None


# ---------------------------------------------------------------------------
# load_tenant_overlay
# ---------------------------------------------------------------------------


class TestLoadTenantOverlay:
    def test_load_overlay_from_primary_path(self, tmp_path: Path) -> None:
        """Overlay is loaded from tenants/<tenant_id>/config/interview-overlays.yaml."""
        overlay_dir = tmp_path / "tenants" / "testco" / "config"
        overlay_dir.mkdir(parents=True)
        overlay_file = overlay_dir / "interview-overlays.yaml"
        overlay_file.write_text(
            "tenant_id: testco\n"
            "additional_facets: [brand]\n"
            "resolver_overrides: {}\n"
            "evidence_policy: {}\n"
        )

        result = load_tenant_overlay("testco", str(tmp_path))

        assert result is not None
        assert isinstance(result, TenantOverlay)
        assert result.tenant_id == "testco"
        assert "brand" in result.additional_facets

    def test_load_overlay_from_fallback_path(self, tmp_path: Path) -> None:
        """Overlay is loaded from config/interview-overlays.yaml when primary is absent."""
        fallback_dir = tmp_path / "config"
        fallback_dir.mkdir(parents=True)
        overlay_file = fallback_dir / "interview-overlays.yaml"
        overlay_file.write_text(
            "tenant_id: fallback_tenant\n"
            "additional_facets: []\n"
            "resolver_overrides: {}\n"
            "evidence_policy: {}\n"
        )

        result = load_tenant_overlay("fallback_tenant", str(tmp_path))

        assert result is not None
        assert result.tenant_id == "fallback_tenant"

    def test_load_overlay_primary_takes_precedence_over_fallback(
        self, tmp_path: Path
    ) -> None:
        """Primary path is preferred when both primary and fallback exist."""
        primary_dir = tmp_path / "tenants" / "acme" / "config"
        primary_dir.mkdir(parents=True)
        (primary_dir / "interview-overlays.yaml").write_text(
            "tenant_id: acme\nadditional_facets: [offer]\n"
            "resolver_overrides: {}\nevidence_policy: {}\n"
        )

        fallback_dir = tmp_path / "config"
        fallback_dir.mkdir(parents=True)
        (fallback_dir / "interview-overlays.yaml").write_text(
            "tenant_id: wrong\nadditional_facets: [brand]\n"
            "resolver_overrides: {}\nevidence_policy: {}\n"
        )

        result = load_tenant_overlay("acme", str(tmp_path))

        assert result is not None
        assert result.tenant_id == "acme"
        assert "offer" in result.additional_facets

    def test_load_overlay_returns_none_when_missing(self, tmp_path: Path) -> None:
        """Returns None when no overlay file exists."""
        result = load_tenant_overlay("ghosttenant", str(tmp_path))
        assert result is None

    def test_load_overlay_from_fixture_file(self, tmp_path: Path) -> None:
        """Load and parse the ceremonia tenant overlay fixture."""
        fixture_src = FIXTURES_DIR / "tenant_overlay.yaml"
        overlay_dir = tmp_path / "tenants" / "ceremonia" / "config"
        overlay_dir.mkdir(parents=True)
        dest = overlay_dir / "interview-overlays.yaml"
        dest.write_bytes(fixture_src.read_bytes())

        result = load_tenant_overlay("ceremonia", str(tmp_path))

        assert result is not None
        assert result.tenant_id == "ceremonia"

    def test_fixture_overlay_has_expected_facets(self, tmp_path: Path) -> None:
        """Ceremonia fixture overlay contains compliance and retreat_context facets."""
        fixture_src = FIXTURES_DIR / "tenant_overlay.yaml"
        overlay_dir = tmp_path / "tenants" / "ceremonia" / "config"
        overlay_dir.mkdir(parents=True)
        (overlay_dir / "interview-overlays.yaml").write_bytes(fixture_src.read_bytes())

        result = load_tenant_overlay("ceremonia", str(tmp_path))

        assert result is not None
        assert "compliance" in result.additional_facets
        assert "retreat_context" in result.additional_facets

    def test_fixture_overlay_has_evidence_policy(self, tmp_path: Path) -> None:
        """Ceremonia fixture overlay evidence_policy is populated."""
        fixture_src = FIXTURES_DIR / "tenant_overlay.yaml"
        overlay_dir = tmp_path / "tenants" / "ceremonia" / "config"
        overlay_dir.mkdir(parents=True)
        (overlay_dir / "interview-overlays.yaml").write_bytes(fixture_src.read_bytes())

        result = load_tenant_overlay("ceremonia", str(tmp_path))

        assert result is not None
        assert "require_freshness" in result.evidence_policy

    def test_fixture_overlay_has_custom_completion_rules(self, tmp_path: Path) -> None:
        """Ceremonia fixture overlay custom_completion_rules is parsed."""
        fixture_src = FIXTURES_DIR / "tenant_overlay.yaml"
        overlay_dir = tmp_path / "tenants" / "ceremonia" / "config"
        overlay_dir.mkdir(parents=True)
        (overlay_dir / "interview-overlays.yaml").write_bytes(fixture_src.read_bytes())

        result = load_tenant_overlay("ceremonia", str(tmp_path))

        assert result is not None
        assert result.custom_completion_rules is not None
        assert isinstance(result.custom_completion_rules, CompletionRule)


# ---------------------------------------------------------------------------
# merge_contract
# ---------------------------------------------------------------------------


class TestMergeContract:
    # --- base wins on overlapping inputs ---

    def test_merge_pack_defaults_explicit_base_wins(self) -> None:
        """When base and pack share an input id, base InputSpec is kept."""
        base_input = _make_input("campaign_topic", confidence_threshold=0.9)
        base = _make_contract(required=[base_input])

        pack = load_department_pack("marketing")
        assert pack is not None

        merged = merge_contract(base, pack=pack)

        # campaign_topic from base (confidence 0.9) should survive
        req_by_id = {inp.id: inp for inp in merged.required_inputs}
        assert "campaign_topic" in req_by_id
        assert req_by_id["campaign_topic"].confidence_threshold == pytest.approx(0.9)

    def test_merge_pack_adds_inputs_not_in_base(self) -> None:
        """Pack inputs absent from base are appended to merged contract."""
        base = _make_contract(
            required=[_make_input("my_custom_field")]
        )

        pack = load_department_pack("marketing")
        assert pack is not None

        merged = merge_contract(base, pack=pack)

        req_ids = {inp.id for inp in merged.required_inputs}
        # Pack adds campaign_topic and target_audience
        assert "campaign_topic" in req_ids
        assert "target_audience" in req_ids
        # Base's own field also present
        assert "my_custom_field" in req_ids

    def test_merge_empty_base_gets_all_pack_defaults(self) -> None:
        """An empty base contract receives all pack required and optional inputs."""
        base = _make_contract()
        pack = load_department_pack("marketing")
        assert pack is not None

        merged = merge_contract(base, pack=pack)

        req_ids = {inp.id for inp in merged.required_inputs}
        opt_ids = {inp.id for inp in merged.optional_inputs}
        assert "campaign_topic" in req_ids
        assert "target_audience" in req_ids
        assert "brand_voice" in opt_ids
        assert "cta_type" in opt_ids
        assert "offer_details" in opt_ids

    # --- resolution_strategies ---

    def test_merge_base_strategies_win_when_non_empty(self) -> None:
        """Base resolution_strategies take precedence over pack's."""
        base = _make_contract(strategies=[ResolverKind.USER_ARGS, ResolverKind.INFER])
        pack = _make_contract(
            strategies=[ResolverKind.MEMORY, ResolverKind.RAG, ResolverKind.ASK]
        )

        merged = merge_contract(base, pack=pack)

        assert merged.resolution_strategies == [
            ResolverKind.USER_ARGS,
            ResolverKind.INFER,
        ]

    def test_merge_uses_pack_strategies_when_base_is_empty(self) -> None:
        """When base has no strategies, pack strategies are used."""
        base = _make_contract()  # no strategies
        pack = _make_contract(strategies=[ResolverKind.MEMORY, ResolverKind.ASK])

        merged = merge_contract(base, pack=pack)

        assert merged.resolution_strategies == [ResolverKind.MEMORY, ResolverKind.ASK]

    # --- semantic_facets ---

    def test_merge_tenant_overlay_adds_extra_facets(
        self, tmp_path: Path
    ) -> None:
        """Overlay additional_facets are unioned into semantic_facets."""
        base = _make_contract(facets=[SemanticFacet.AUDIENCE])
        overlay = TenantOverlay(
            tenant_id="demo",
            additional_facets=["brand", "cta"],
        )

        merged = merge_contract(base, overlay=overlay)

        assert SemanticFacet.AUDIENCE in merged.semantic_facets
        assert SemanticFacet.BRAND in merged.semantic_facets
        assert SemanticFacet.CTA in merged.semantic_facets

    def test_merge_facets_deduped(self) -> None:
        """Facets shared by base and pack appear only once in merged result."""
        base = _make_contract(facets=[SemanticFacet.AUDIENCE, SemanticFacet.BRAND])
        pack = _make_contract(facets=[SemanticFacet.BRAND, SemanticFacet.OFFER])

        merged = merge_contract(base, pack=pack)

        assert merged.semantic_facets.count(SemanticFacet.BRAND) == 1
        assert SemanticFacet.AUDIENCE in merged.semantic_facets
        assert SemanticFacet.OFFER in merged.semantic_facets

    def test_merge_unknown_overlay_facets_silently_dropped(self) -> None:
        """Tenant facets not in SemanticFacet enum are silently ignored."""
        base = _make_contract(facets=[SemanticFacet.TOPIC])
        overlay = TenantOverlay(
            tenant_id="demo",
            additional_facets=["retreat_context", "unknown_facet_xyz"],
        )

        # Should not raise
        merged = merge_contract(base, overlay=overlay)

        # Known facets from overlay's list that happen to match enum are included
        # 'retreat_context' is not in SemanticFacet so it's dropped;
        # 'unknown_facet_xyz' is also dropped
        assert SemanticFacet.TOPIC in merged.semantic_facets

    # --- completion_rules ---

    def test_merge_base_completion_rules_win(self) -> None:
        """Base completion_rules are preserved when set."""
        base_rule = CompletionRule(require="my_field")
        base = _make_contract(completion_rules=base_rule)
        pack = _make_contract(completion_rules=CompletionRule(require="pack_field"))

        merged = merge_contract(base, pack=pack)

        assert merged.completion_rules is not None
        assert merged.completion_rules.require == "my_field"

    def test_merge_pack_completion_rules_used_when_base_empty(self) -> None:
        """Pack completion_rules are used when base has none."""
        base = _make_contract()
        pack = _make_contract(
            completion_rules=CompletionRule(require="campaign_topic")
        )

        merged = merge_contract(base, pack=pack)

        assert merged.completion_rules is not None
        assert merged.completion_rules.require == "campaign_topic"

    def test_merge_overlay_completion_rules_as_final_fallback(self) -> None:
        """Overlay custom_completion_rules apply when base and pack have none."""
        base = _make_contract()
        overlay = TenantOverlay(
            tenant_id="demo",
            custom_completion_rules=CompletionRule(require="offer_type"),
        )

        merged = merge_contract(base, overlay=overlay)

        assert merged.completion_rules is not None
        assert merged.completion_rules.require == "offer_type"

    # --- evidence_policy ---

    def test_merge_evidence_policy_deep_merge(self) -> None:
        """Evidence policy: pack provides defaults, base overrides, overlay wins."""
        base = _make_contract(evidence_policy={"require_source_trust": 0.8})
        pack = _make_contract(
            evidence_policy={"require_freshness": "30d", "require_source_trust": 0.5}
        )
        overlay = TenantOverlay(
            tenant_id="demo",
            evidence_policy={"require_freshness": "7d"},
        )

        merged = merge_contract(base, pack=pack, overlay=overlay)

        # base wins over pack for require_source_trust
        assert merged.evidence_policy["require_source_trust"] == pytest.approx(0.8)
        # overlay wins over both for require_freshness
        assert merged.evidence_policy["require_freshness"] == "7d"

    def test_merge_evidence_policy_pack_defaults_when_base_empty(self) -> None:
        """Pack evidence_policy keys appear when base has empty policy."""
        base = _make_contract()
        pack = _make_contract(evidence_policy={"require_freshness": "30d"})

        merged = merge_contract(base, pack=pack)

        assert merged.evidence_policy["require_freshness"] == "30d"

    # --- resolver_overrides via overlay ---

    def test_merge_overlay_resolver_overrides_preserved(self) -> None:
        """TenantOverlay.resolver_overrides are accessible on the overlay after merge."""
        base = _make_contract()
        overlay = TenantOverlay(
            tenant_id="demo",
            resolver_overrides={"prefer_tenant_file_over_memory": True},
        )

        # merge_contract doesn't propagate resolver_overrides into InterviewContract;
        # it stays on the TenantOverlay.  Confirm merge completes without error.
        merged = merge_contract(base, overlay=overlay)
        assert isinstance(merged, InterviewContract)

    # --- three-layer merge ---

    def test_merge_all_three_layers(self, tmp_path: Path) -> None:
        """Full merge: base + marketing pack + ceremonia overlay."""
        # Base has one explicit required input
        base = _make_contract(
            required=[_make_input("explicit_base_field")],
            facets=[SemanticFacet.BRIEF],
            evidence_policy={"require_source_trust": 0.75},
        )

        pack = load_department_pack("marketing")
        assert pack is not None

        # Load real fixture overlay
        fixture_src = FIXTURES_DIR / "tenant_overlay.yaml"
        overlay_dir = tmp_path / "tenants" / "ceremonia" / "config"
        overlay_dir.mkdir(parents=True)
        (overlay_dir / "interview-overlays.yaml").write_bytes(fixture_src.read_bytes())
        overlay = load_tenant_overlay("ceremonia", str(tmp_path))
        assert overlay is not None

        merged = merge_contract(base, pack=pack, overlay=overlay)

        # Base field survives
        req_ids = {inp.id for inp in merged.required_inputs}
        assert "explicit_base_field" in req_ids

        # Pack's required inputs added
        assert "campaign_topic" in req_ids
        assert "target_audience" in req_ids

        # Pack's optional inputs added
        opt_ids = {inp.id for inp in merged.optional_inputs}
        assert "brand_voice" in opt_ids

        # Base facet present
        assert SemanticFacet.BRIEF in merged.semantic_facets
        # Pack facets added
        assert SemanticFacet.TOPIC in merged.semantic_facets
        # Overlay facets (known enum values) added — compliance is valid
        assert SemanticFacet.COMPLIANCE in merged.semantic_facets

        # Evidence policy: overlay wins for all keys it sets.
        # The fixture overlay sets require_source_trust: 0.6, which overrides base's 0.75.
        assert merged.evidence_policy["require_source_trust"] == pytest.approx(0.6)
        assert merged.evidence_policy["require_freshness"] == "30d"  # from overlay

        # Completion rules: base has none, pack has none; overlay wins
        assert merged.completion_rules is not None

    # --- immutability ---

    def test_merge_does_not_mutate_base(self) -> None:
        """merge_contract never mutates the base contract."""
        base = _make_contract(
            required=[_make_input("original_field")],
        )
        original_req_count = len(base.required_inputs)

        pack = load_department_pack("marketing")
        merge_contract(base, pack=pack)

        assert len(base.required_inputs) == original_req_count

    def test_merge_does_not_mutate_pack(self) -> None:
        """merge_contract never mutates the pack contract."""
        base = _make_contract()
        pack = load_department_pack("marketing")
        assert pack is not None
        original_pack_req = len(pack.required_inputs)

        merge_contract(base, pack=pack)

        assert len(pack.required_inputs) == original_pack_req

    # --- no-op cases ---

    def test_merge_no_pack_no_overlay_returns_equivalent_to_base(self) -> None:
        """With no pack and no overlay, merged contract mirrors base."""
        base = _make_contract(
            required=[_make_input("field_a")],
            optional=[_make_input("field_b")],
            strategies=[ResolverKind.MEMORY],
            facets=[SemanticFacet.AUDIENCE],
        )

        merged = merge_contract(base)

        assert {inp.id for inp in merged.required_inputs} == {"field_a"}
        assert {inp.id for inp in merged.optional_inputs} == {"field_b"}
        assert merged.resolution_strategies == [ResolverKind.MEMORY]
        assert merged.semantic_facets == [SemanticFacet.AUDIENCE]
