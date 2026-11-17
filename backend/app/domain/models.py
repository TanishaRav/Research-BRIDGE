from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "1.0"
SCORE_VERSION = "rb-score-v1"
TAXONOMY_VERSION = "rb-taxonomy-v1"
SYNTHETIC_LABEL = "Synthetic demo record — not an actual Iowa State student record"
HYPOTHETICAL_LABEL = "Hypothetical project opening for the independent ResearchBridge prototype"


def utc_now() -> datetime:
    return datetime.now(UTC)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class DemoRole(StrEnum):
    STUDENT = "student"
    FACULTY = "faculty"
    ADMIN = "admin"


class ProvenanceType(StrEnum):
    PUBLIC = "public"
    FICTIONAL = "fictional"
    HYPOTHETICAL = "hypothetical"


class SkillKind(StrEnum):
    MANDATORY = "mandatory"
    TRAINABLE = "trainable"


class WindowPurpose(StrEnum):
    AVAILABILITY = "availability"
    REQUIRED = "required"
    MENTORING = "mentoring"


class RunStatus(StrEnum):
    VALIDATING = "validating"
    SCORING = "scoring"
    OPTIMIZING_COVERAGE = "optimizing_coverage"
    OPTIMIZING_QUALITY = "optimizing_quality"
    OPTIMIZING_FLOOR = "optimizing_floor"
    RESOLVING_TIES = "resolving_ties"
    EVALUATING = "evaluating"
    PROPOSED = "proposed"
    APPROVED = "approved"
    FEASIBLE_NOT_PROVEN = "feasible_not_proven"
    FAILED = "failed"


class Entity(StrictModel):
    id: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    schema_version: str = SCHEMA_VERSION
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class TimeWindow(StrictModel):
    id: str | None = Field(default=None, max_length=100)
    day: int = Field(ge=0, le=6, description="Monday=0 through Sunday=6")
    start_minute: int = Field(ge=0, le=1439)
    end_minute: int = Field(ge=1, le=1440)
    fixed: bool = False
    purpose: WindowPurpose = WindowPurpose.AVAILABILITY

    @model_validator(mode="after")
    def end_after_start(self) -> TimeWindow:
        if self.end_minute <= self.start_minute:
            raise ValueError("end_minute must be greater than start_minute")
        return self


class StudentSkill(StrictModel):
    skill_id: str = Field(min_length=1, max_length=100)
    proficiency: int = Field(ge=0, le=4)


class ProjectSkill(StrictModel):
    skill_id: str = Field(min_length=1, max_length=100)
    required_proficiency: int = Field(ge=1, le=4)
    kind: SkillKind


class StudentPreference(StrictModel):
    project_id: str = Field(min_length=1, max_length=100)
    rank: int = Field(ge=1)


class Student(Entity):
    synthetic: Literal[True] = True
    synthetic_label: str = SYNTHETIC_LABEL
    display_name: str = Field(min_length=1, max_length=120)
    major: str = Field(min_length=1, max_length=120)
    academic_year: str = Field(min_length=1, max_length=50)
    interests: list[str] = Field(default_factory=list)
    hours_per_week: Decimal | None = Field(default=None, ge=0, le=40)
    learning_goals: list[str] = Field(default_factory=list)
    first_time_researcher: bool = True
    accepts_suggestions: bool = False
    profile_complete: bool = False
    submitted: bool = False
    synthetic_submission_order: int = Field(ge=1)
    skills: list[StudentSkill] = Field(default_factory=list)
    preferences: list[StudentPreference] = Field(default_factory=list)
    availability: list[TimeWindow] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_relations(self) -> Student:
        skill_ids = [item.skill_id for item in self.skills]
        if len(skill_ids) != len(set(skill_ids)):
            raise ValueError("student skills must use unique skill_id values")
        project_ids = [item.project_id for item in self.preferences]
        ranks = [item.rank for item in self.preferences]
        if len(project_ids) != len(set(project_ids)):
            raise ValueError("preferences must not contain duplicate projects")
        if len(ranks) != len(set(ranks)):
            raise ValueError("preferences must not contain duplicate ranks")
        if ranks and sorted(ranks) != list(range(1, len(ranks) + 1)):
            raise ValueError("preference ranks must be contiguous starting at 1")
        return self


class StudentPatch(StrictModel):
    interests: list[str] | None = None
    hours_per_week: Decimal | None = Field(default=None, ge=0, le=40)
    learning_goals: list[str] | None = None
    first_time_researcher: bool | None = None
    accepts_suggestions: bool | None = None
    skills: list[StudentSkill] | None = None
    preferences: list[StudentPreference] | None = None
    availability: list[TimeWindow] | None = None

    @model_validator(mode="after")
    def validate_unique_relations(self) -> StudentPatch:
        if self.skills is not None:
            skill_ids = [item.skill_id for item in self.skills]
            if len(skill_ids) != len(set(skill_ids)):
                raise ValueError("student skills must use unique skill_id values")
        if self.preferences is not None:
            project_ids = [item.project_id for item in self.preferences]
            ranks = [item.rank for item in self.preferences]
            if len(project_ids) != len(set(project_ids)):
                raise ValueError("preferences must not contain duplicate projects")
            if len(ranks) != len(set(ranks)):
                raise ValueError("preferences must not contain duplicate ranks")
            if sorted(ranks) != list(range(1, len(ranks) + 1)):
                raise ValueError("preference ranks must be contiguous starting at 1")
        return self


class Faculty(Entity):
    display_name: str = Field(min_length=1, max_length=120)
    department: str = Field(min_length=1, max_length=120)
    research_interests: list[str] = Field(default_factory=list)
    provenance_type: ProvenanceType
    provenance_label: str
    source_url: str | None = None
    source_retrieved_at: str | None = None


class Skill(Entity):
    label: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=80)
    aliases: list[str] = Field(default_factory=list)


class Project(Entity):
    faculty_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=4000)
    department: str = Field(min_length=1, max_length=120)
    interests: list[str] = Field(default_factory=list)
    capacity: int = Field(ge=0, le=100)
    prerequisites: list[str] = Field(default_factory=list)
    mentoring_available: bool = True
    commitment_hours: Decimal = Field(gt=0, le=40)
    term: str = Field(min_length=1, max_length=80)
    modality: str = Field(min_length=1, max_length=80)
    active: bool = True
    provenance_type: Literal[ProvenanceType.HYPOTHETICAL] = ProvenanceType.HYPOTHETICAL
    provenance_label: str = HYPOTHETICAL_LABEL
    source_url: str | None = None
    source_note: str = HYPOTHETICAL_LABEL
    skills: list[ProjectSkill] = Field(default_factory=list)
    required_windows: list[TimeWindow] = Field(default_factory=list)
    mentoring_windows: list[TimeWindow] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_skills(self) -> Project:
        skill_ids = [item.skill_id for item in self.skills]
        if len(skill_ids) != len(set(skill_ids)):
            raise ValueError("project skills must use unique skill_id values")
        return self


class ProjectCreate(StrictModel):
    id: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    faculty_id: str | None = None
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=4000)
    department: str = Field(min_length=1, max_length=120)
    interests: list[str] = Field(default_factory=list)
    capacity: int = Field(ge=0, le=100)
    prerequisites: list[str] = Field(default_factory=list)
    mentoring_available: bool = True
    commitment_hours: Decimal = Field(gt=0, le=40)
    term: str = Field(min_length=1, max_length=80)
    modality: str = Field(min_length=1, max_length=80)
    active: bool = True
    skills: list[ProjectSkill] = Field(default_factory=list)
    required_windows: list[TimeWindow] = Field(default_factory=list)
    mentoring_windows: list[TimeWindow] = Field(default_factory=list)


class ProjectPatch(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1, max_length=4000)
    department: str | None = Field(default=None, min_length=1, max_length=120)
    interests: list[str] | None = None
    capacity: int | None = Field(default=None, ge=0, le=100)
    prerequisites: list[str] | None = None
    mentoring_available: bool | None = None
    commitment_hours: Decimal | None = Field(default=None, gt=0, le=40)
    term: str | None = Field(default=None, min_length=1, max_length=80)
    modality: str | None = Field(default=None, min_length=1, max_length=80)
    active: bool | None = None
    skills: list[ProjectSkill] | None = None
    required_windows: list[TimeWindow] | None = None
    mentoring_windows: list[TimeWindow] | None = None


class ScoreWeights(StrictModel):
    interest: Decimal = Decimal("35")
    technical_skill: Decimal = Decimal("25")
    availability: Decimal = Decimal("20")
    preference: Decimal = Decimal("10")
    learning_goal: Decimal = Decimal("10")

    @model_validator(mode="after")
    def valid_weights(self) -> ScoreWeights:
        values = self.as_dict().values()
        invalid = [name for name, value in self.as_dict().items() if not value.is_finite()]
        if invalid:
            raise ValueError(f"weights must be finite: {', '.join(invalid)}")
        negative = [name for name, value in self.as_dict().items() if value < 0]
        if negative:
            raise ValueError(f"weights must be nonnegative: {', '.join(negative)}")
        if sum(values, Decimal(0)) == 0:
            raise ValueError("at least one weight must be positive")
        return self

    def as_dict(self) -> dict[str, Decimal]:
        return {
            "interest": self.interest,
            "technical_skill": self.technical_skill,
            "availability": self.availability,
            "preference": self.preference,
            "learning_goal": self.learning_goal,
        }


class MatchConfig(StrictModel):
    weights: ScoreWeights = Field(default_factory=ScoreWeights)
    threshold: Decimal = Field(default=Decimal("60"), ge=0, le=100)
    score_version: str = SCORE_VERSION
    taxonomy_version: str = TAXONOMY_VERSION
    solver_seed: int = 731
    worker_count: Literal[1] = 1

    @property
    def threshold_bp(self) -> int:
        return int((self.threshold * Decimal(100)).quantize(Decimal("1")))


class ConfigPatch(StrictModel):
    weights: ScoreWeights | None = None
    threshold: Decimal | None = Field(default=None, ge=0, le=100)


class NormalizedConfig(StrictModel):
    config: MatchConfig
    normalized_weights_percent: dict[str, Decimal]


class EligibilityReason(StrictModel):
    code: str
    detail: str
    field: str | None = None
    resolution: Literal["failed", "unresolved"] = "failed"


class PairScore(StrictModel):
    run_id: str | None = None
    student_id: str
    project_id: str
    eligible: bool
    eligibility_reasons: list[EligibilityReason] = Field(default_factory=list)
    factor_scores_bp: dict[str, int]
    raw_weights: dict[str, str]
    normalized_weights: dict[str, str]
    contributions_bp: dict[str, int]
    evidence: dict[str, Any]
    gaps: list[dict[str, Any]]
    missing_fields: list[str]
    total_bp: int = Field(ge=0, le=10000)
    compatibility_index: Decimal = Field(ge=0, le=100)
    score_version: str = SCORE_VERSION
    taxonomy_version: str = TAXONOMY_VERSION
    config_snapshot: dict[str, Any]


class OptimizerEdge(StrictModel):
    student_id: str
    project_id: str
    score_bp: int = Field(ge=0, le=10000)
    eligible: bool = True


class Assignment(StrictModel):
    run_id: str | None = None
    student_id: str
    project_id: str
    score_bp: int = Field(ge=0, le=10000)
    compatibility_index: Decimal
    canonical_tie_order: int
    state: Literal["proposed", "approved"] = "proposed"
    global_rationale: str


class SolverStage(StrictModel):
    name: str
    status: str
    runtime_ms: Decimal
    objective: int | None = None
    detail: str | None = None


class OptimizationResult(StrictModel):
    assignments: list[Assignment]
    unplaced_reasons: dict[str, list[str]]
    status: str
    proven_optimal: bool
    placement_count: int
    total_score_bp: int
    minimum_score_bp: int | None
    runtime_ms: Decimal
    stages: list[SolverStage]
    solver_seed: int = 731
    worker_count: int = 1
    optimality_limitation: str | None = None


class StrategyMetrics(StrictModel):
    strategy: str
    label: str
    placement_count: int
    submitted_count: int
    eligible_count: int
    placement_rate_submitted: Decimal
    placement_rate_eligible: Decimal | None
    mean_score: Decimal | None
    median_score: Decimal | None
    bottom_decile_score: Decimal | None
    minimum_score: Decimal | None
    top_choice_count: int
    top_choice_denominator: int
    top_choice_rate: Decimal | None
    first_time_placed: int
    first_time_denominator: int
    first_time_placement_rate: Decimal | None
    major_rates: dict[str, dict[str, Any]]
    unplaced_count: int
    unplaced_reasons: dict[str, list[str]]
    constraint_violations: dict[str, int]
    runtime_ms: Decimal


class BenchmarkEvidence(StrictModel):
    strategies: dict[str, StrategyMetrics]
    counterexample: dict[str, Any]
    limitation: str = (
        "Synthetic evaluation cannot establish actual rematching reduction or demographic "
        "fairness. A pilot must measure acceptance, withdrawal, rematching rounds, and "
        "time-to-placement."
    )


class ShuffleEvidence(StrictModel):
    requested_runs: Literal[20] = 20
    identical_assignment_pass_count: int = Field(ge=0, le=20)
    seeds: list[int]
    failing_seeds: list[int]
    reference_assignments: list[tuple[str, str]]
    statement: str = (
        "This checks input-order invariance for the frozen synthetic dataset; it does not "
        "establish demographic fairness."
    )


class MatchRun(Entity):
    status: RunStatus
    stale: bool = False
    stale_reasons: list[str] = Field(default_factory=list)
    config_snapshot: dict[str, Any]
    input_snapshot_hash: str
    input_snapshot: dict[str, Any]
    result_snapshot: dict[str, Any]
    stage_evidence: list[SolverStage]
    benchmark_evidence: BenchmarkEvidence | None = None
    shuffle_evidence: ShuffleEvidence | None = None
    runtime_ms: Decimal
    placement_count: int
    total_score_bp: int
    minimum_score_bp: int | None = None
    solver_seed: int = 731
    worker_count: int = 1
    score_version: str = SCORE_VERSION
    optimality_limitation: str | None = None
    approved_at: datetime | None = None


class RunCreateRequest(StrictModel):
    config: MatchConfig | None = None


class ApprovalRequest(StrictModel):
    confirmation: Literal["APPROVE_SYNTHETIC_RUN"]


class DecisionAudit(Entity):
    actor_role: DemoRole
    actor_persona_id: str
    event_type: str
    entity_type: str
    entity_id: str | None = None
    run_id: str | None = None
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RoadmapTask(StrictModel):
    id: str
    week: int = Field(ge=1, le=4)
    skill_id: str
    category: str
    priority: Literal["mandatory", "trainable"]
    current_proficiency: int = Field(ge=0, le=4)
    target_proficiency: int = Field(ge=1, le=4)
    concrete_task: str
    estimated_hours: Decimal = Field(gt=0)
    resource_label: str = "Generic learning suggestion"
    resource_url: str | None = None
    deliverable: str
    success_check: str
    complete: bool = False
    completion_notice: str = "Task completion does not verify mastery."


class Roadmap(Entity):
    student_id: str
    project_id: str
    run_id: str | None = None
    relationship: Literal["approved_placement", "not_a_placement"]
    weeks: int = Field(ge=2, le=4)
    tasks: list[RoadmapTask]
    notice: str = "Task completion records progress only and does not verify mastery."


class RoadmapTaskPatch(StrictModel):
    complete: bool


class OutreachDraft(Entity):
    student_id: str
    project_id: str
    run_id: str | None = None
    deterministic_source: Literal["offline-template"] = "offline-template"
    subject: str
    body: str
    edited_body: str
    notice: str = "Draft only. ResearchBridge does not send email or imply acceptance."


class OutreachPatch(StrictModel):
    subject: str | None = Field(default=None, min_length=1, max_length=200)
    edited_body: str | None = Field(default=None, min_length=1, max_length=10000)


class Persona(StrictModel):
    role: DemoRole
    persona_id: str
    label: str
    synthetic: bool = True


class PersonaList(StrictModel):
    demo_only_notice: str = (
        "The role switcher selects seeded demo personas. It is not authentication or "
        "production authorization."
    )
    personas: list[Persona]


class ProjectList(StrictModel):
    items: list[Project]
    count: int
    active_filters: dict[str, Any]


class Recommendation(StrictModel):
    project: Project
    pair_score: PairScore
    label: Literal["Independent recommendation — not an allocation result"] = (
        "Independent recommendation — not an allocation result"
    )


class StudentOutcome(StrictModel):
    student_id: str
    run_id: str | None
    status: Literal["pending", "placed", "unplaced"]
    assignment: Assignment | None = None
    reasons: list[str] = Field(default_factory=list)
    notice: str


class FacultyAssignment(StrictModel):
    run_id: str
    project_id: str
    student_id: str
    student_display_name: str
    synthetic_label: str = SYNTHETIC_LABEL
    compatibility_index: Decimal
    explanation: str


class ValidationIssue(StrictModel):
    path: str
    code: str
    message: str


class ImportSnapshot(StrictModel):
    schema_version: Literal["1.0"]
    students: list[Student]
    faculty: list[Faculty]
    projects: list[Project]
    skills: list[Skill]
    source_manifest: dict[str, Any]


class ImportValidationReport(StrictModel):
    valid: bool
    issues: list[ValidationIssue]
    counts: dict[str, int]
    schema_version: str | None = None


class ImportApplyResponse(StrictModel):
    imported: bool
    counts: dict[str, int]
    stale_run_ids: list[str]


class ResetRequest(StrictModel):
    confirmation: str


class ResetResponse(StrictModel):
    reset: bool
    confirmation: str
    counts: dict[str, int]


class RunComparison(StrictModel):
    run_id: str
    other_run_id: str
    placement_count_difference: int
    total_score_bp_difference: int
    changed_outcomes: list[dict[str, Any]]
    configuration_differences: dict[str, Any]


class ApiErrorBody(StrictModel):
    code: str
    message: str
    field_errors: dict[str, list[str]] | None = None
    request_id: str


class ExportEnvelope(StrictModel):
    schema_version: str = SCHEMA_VERSION
    synthetic_data_notice: str = SYNTHETIC_LABEL
    project_notice: str = HYPOTHETICAL_LABEL
    run: dict[str, Any]
    source_manifest: dict[str, Any]
    assignments: list[dict[str, Any]]
    unplaced: list[dict[str, Any]]
    benchmark: dict[str, Any]


class StudentProfileResponse(StrictModel):
    student: Student
    missing_required_fields: list[str]
    batch_status: Literal["draft", "submitted", "approved_placement", "approved_unplaced"]
    next_action: str
    notice: str = SYNTHETIC_LABEL


class RunReview(StrictModel):
    run: MatchRun
    assignments: list[Assignment]
    pair_scores: list[PairScore]
    unplaced: dict[str, list[str]]
    project_utilization: dict[str, dict[str, int]]


class RunEvidenceResponse(StrictModel):
    run_id: str
    input_snapshot_hash: str
    score_version: str
    solver_seed: int
    worker_count: int
    benchmark: BenchmarkEvidence | None
    shuffle: ShuffleEvidence | None
    limitation: str
