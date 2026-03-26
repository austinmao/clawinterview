"""ClawInterview core data layer.

Pydantic v2 models for the ClawInterview orchestrated pipeline interview
system. All entity definitions follow the canonical data model specification
in specs/069-clawinterview/data-model.md.

Models cover: interview contracts, compiled run contracts, input resolution
tracking, interactive turn history, layered briefs, tenant overlays, and
conflict reporting.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class PrimitiveType(str, Enum):
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    MONEY = "money"
    URL = "url"
    ENUM = "enum"
    ENTITY_REF = "entity_ref"
    LIST = "list"
    OBJECT = "object"


class ResolverKind(str, Enum):
    USER_ARGS = "user_args"
    USER_MESSAGE = "user_message"
    PIPELINE_STATE = "pipeline_state"
    MEMORY = "memory"
    TENANT_FILE = "tenant_file"
    UPSTREAM_OUTPUT = "upstream_output"
    RAG = "rag"
    WEB = "web"
    INFER = "infer"
    ASK = "ask"


class SemanticFacet(str, Enum):
    AUDIENCE = "audience"
    OFFER = "offer"
    SCHEDULE = "schedule"
    BRAND = "brand"
    PROOF = "proof"
    CTA = "cta"
    ASSET = "asset"
    TENANT_CONTEXT = "tenant_context"
    BRIEF = "brief"
    APPROVAL = "approval"
    COMPLIANCE = "compliance"
    TOPIC = "topic"
    POSITIONING = "positioning"
    PARTNER = "partner"
    BUDGET = "budget"
    TIMELINE = "timeline"


class InterviewStatus(str, Enum):
    PENDING = "pending"
    COMPILING = "compiling"
    RESOLVING = "resolving"
    IN_PROGRESS = "in_progress"
    AWAITING_INPUT = "awaiting_input"
    COMPLETE = "complete"
    FAILED = "failed"


class ResolutionStatus(str, Enum):
    UNRESOLVED = "unresolved"
    RESOLVED = "resolved"
    STALE = "stale"
    CONFLICT = "conflict"


class InterviewMode(str, Enum):
    LIGHT = "light"
    DEEP = "deep"


class ConflictSeverity(str, Enum):
    EXACT_MATCH = "exact_match"
    COMPATIBLE_REFINEMENT = "compatible_refinement"
    INCOMPATIBLE = "incompatible"


# ---------------------------------------------------------------------------
# Pydantic v2 Models
# ---------------------------------------------------------------------------


class InputSpec(BaseModel):
    """A single input declaration within an interview contract."""

    model_config = ConfigDict(extra="forbid")

    id: str
    type: PrimitiveType
    description: str
    facets: list[SemanticFacet] = []
    resolution_strategies: list[ResolverKind] = []
    confidence_threshold: float = 0.7
    freshness_policy: str | None = None
    ask_policy: str = "only_if_unresolved"
    depends_on: list[str] = []
    default_value: Any = None


class OutputSpec(BaseModel):
    """What a target produces for downstream consumption."""

    model_config = ConfigDict(extra="forbid")

    id: str
    type: PrimitiveType
    facets: list[SemanticFacet] = []


class CompletionRule(BaseModel):
    """Declarative constraint determining when interview is complete.

    Self-referential: ``all_of`` and ``any_of`` contain nested
    ``CompletionRule`` instances.  Call ``CompletionRule.model_rebuild()``
    after this class is defined to enable forward-reference resolution.
    """

    model_config = ConfigDict(extra="forbid")

    all_of: list[CompletionRule] | None = None
    any_of: list[CompletionRule] | None = None
    require: str | None = None
    min_items: int | None = None
    freshness_required: str | None = None
    confidence_threshold: float | None = None
    must_produce: str | None = None


# Resolve the self-referential forward references.
CompletionRule.model_rebuild()


class BoundedOption(BaseModel):
    """A selectable option in an interview turn."""

    model_config = ConfigDict(extra="forbid")

    value: str
    label: str
    description: str = ""
    is_recommended: bool = False


class InterviewContract(BaseModel):
    """Typed interview contract embedded in every scaffold-managed spec."""

    model_config = ConfigDict(extra="forbid")

    version: str = "1.0"
    required_inputs: list[InputSpec] = []
    optional_inputs: list[InputSpec] = []
    produces_outputs: list[OutputSpec] = []
    resolution_strategies: list[ResolverKind] = []
    completion_rules: CompletionRule | None = None
    semantic_facets: list[SemanticFacet] = []
    evidence_policy: dict[str, Any] = {}


class CompiledInput(BaseModel):
    """A single input in the compiled run contract."""

    model_config = ConfigDict(extra="forbid")

    id: str
    original_id: str
    owner_target: str
    type: PrimitiveType
    facets: list[SemanticFacet] = []
    resolution_strategies: list[ResolverKind] = []
    confidence_threshold: float = 0.7
    blocking: bool = True
    stage_needed_by: str = ""
    producer_mapping: str | None = None


class CompiledRunContract(BaseModel):
    """Pipeline-scoped compilation result."""

    model_config = ConfigDict(extra="forbid")

    pipeline_id: str
    run_id: str
    compiled_at: str
    participating_targets: list[str] = []
    inputs: list[CompiledInput] = []
    outputs: list[OutputSpec] = []
    completion_rules: CompletionRule | None = None
    conflicts: list[dict[str, Any]] = []


class ResolutionResult(BaseModel):
    """Result returned by a single resolver invocation."""

    model_config = ConfigDict(extra="forbid")

    value: Any
    confidence: float
    evidence_source: str
    resolver_kind: ResolverKind


class InputResolution(BaseModel):
    """Per-input resolution tracking."""

    model_config = ConfigDict(extra="forbid")

    input_id: str
    status: ResolutionStatus = ResolutionStatus.UNRESOLVED
    resolver_used: ResolverKind | None = None
    confidence: float = 0.0
    evidence_source: str = ""
    resolved_value: Any = None
    resolved_at: str | None = None
    stale_since: str | None = None


class InterviewTurn(BaseModel):
    """A single turn in the interactive interview."""

    model_config = ConfigDict(extra="forbid")

    turn_number: int
    layer: str
    mode: InterviewMode = InterviewMode.LIGHT
    summary: str = ""
    recommendation: str | None = None
    options: list[BoundedOption] = []
    question: str = ""
    response: str | None = None
    resolved_inputs: list[str] = []
    timestamp: str = ""


class InterviewBrief(BaseModel):
    """Layered brief assembled turn by turn."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    context_layer: dict[str, Any] = {}
    strategy_layer: dict[str, Any] = {}
    constraints_layer: dict[str, Any] = {}
    execution_brief: dict[str, Any] = {}
    layer_status: dict[str, str] = {}


class ResolutionContext(BaseModel):
    """Context passed to resolvers during the resolution phase."""

    model_config = ConfigDict(extra="forbid")

    pipeline_args: dict[str, Any] = {}
    user_message: str = ""
    prior_state: dict[str, Any] = {}
    tenant_id: str = ""
    workspace_path: str = ""
    run_id: str = ""
    upstream_outputs: dict[str, Any] = {}


class InterviewState(BaseModel):
    """Full persisted state of an in-progress or completed interview."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    pipeline_id: str
    status: InterviewStatus = InterviewStatus.PENDING
    compiled_contract: CompiledRunContract | None = None
    resolutions: dict[str, InputResolution] = {}
    turns: list[InterviewTurn] = []
    brief: InterviewBrief | None = None
    current_layer: str = "context"
    bypass_mode: bool = False
    started_at: str = ""
    updated_at: str = ""
    completed_at: str | None = None


class TenantOverlay(BaseModel):
    """Per-tenant overlay for interview customization."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    additional_facets: list[str] = []
    resolver_overrides: dict[str, Any] = {}
    evidence_policy: dict[str, Any] = {}
    custom_completion_rules: CompletionRule | None = None


class ConflictReport(BaseModel):
    """Report of a semantic conflict between target inputs."""

    model_config = ConfigDict(extra="forbid")

    input_ids: list[str]
    owner_targets: list[str]
    severity: ConflictSeverity
    description: str
    resolution: str | None = None
