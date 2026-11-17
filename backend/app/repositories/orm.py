from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Integer, Numeric, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FacultyRow(TimestampMixin, Base):
    __tablename__ = "faculty"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    display_name: Mapped[str] = mapped_column(Text)
    department: Mapped[str] = mapped_column(Text)
    research_interests_json: Mapped[str] = mapped_column(Text)
    provenance_type: Mapped[str] = mapped_column(Text)
    provenance_label: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    source_retrieved_at: Mapped[str | None] = mapped_column(Text)


class SkillRow(TimestampMixin, Base):
    __tablename__ = "skills"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text)
    aliases_json: Mapped[str] = mapped_column(Text)


class StudentRow(TimestampMixin, Base):
    __tablename__ = "students"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    synthetic: Mapped[bool] = mapped_column(Boolean)
    synthetic_label: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text)
    major: Mapped[str] = mapped_column(Text)
    academic_year: Mapped[str] = mapped_column(Text)
    interests_json: Mapped[str] = mapped_column(Text)
    hours_per_week: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    learning_goals_json: Mapped[str] = mapped_column(Text)
    first_time_researcher: Mapped[bool] = mapped_column(Boolean)
    accepts_suggestions: Mapped[bool] = mapped_column(Boolean)
    profile_complete: Mapped[bool] = mapped_column(Boolean)
    submitted: Mapped[bool] = mapped_column(Boolean)
    synthetic_submission_order: Mapped[int] = mapped_column(Integer)


class ProjectRow(TimestampMixin, Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    faculty_id: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    department: Mapped[str] = mapped_column(Text)
    interests_json: Mapped[str] = mapped_column(Text)
    capacity: Mapped[int] = mapped_column(Integer)
    prerequisites_json: Mapped[str] = mapped_column(Text)
    mentoring_available: Mapped[bool] = mapped_column(Boolean)
    commitment_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    term: Mapped[str] = mapped_column(Text)
    modality: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean)
    provenance_type: Mapped[str] = mapped_column(Text)
    provenance_label: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    source_note: Mapped[str] = mapped_column(Text)


class StudentSkillRow(TimestampMixin, Base):
    __tablename__ = "student_skills"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    student_id: Mapped[str] = mapped_column(Text)
    skill_id: Mapped[str] = mapped_column(Text)
    proficiency: Mapped[int] = mapped_column(Integer)


class ProjectSkillRow(TimestampMixin, Base):
    __tablename__ = "project_skills"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(Text)
    skill_id: Mapped[str] = mapped_column(Text)
    required_proficiency: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(Text)


class PreferenceRow(TimestampMixin, Base):
    __tablename__ = "student_preferences"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    student_id: Mapped[str] = mapped_column(Text)
    project_id: Mapped[str] = mapped_column(Text)
    rank: Mapped[int] = mapped_column(Integer)


class AvailabilityRow(TimestampMixin, Base):
    __tablename__ = "availability_windows"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    owner_type: Mapped[str] = mapped_column(Text)
    owner_id: Mapped[str] = mapped_column(Text)
    day: Mapped[int] = mapped_column(Integer)
    start_minute: Mapped[int] = mapped_column(Integer)
    end_minute: Mapped[int] = mapped_column(Integer)
    fixed: Mapped[bool] = mapped_column(Boolean)
    purpose: Mapped[str] = mapped_column(Text)


class ConfigRow(TimestampMixin, Base):
    __tablename__ = "match_config"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    weights_json: Mapped[str] = mapped_column(Text)
    threshold_bp: Mapped[int] = mapped_column(Integer)
    score_version: Mapped[str] = mapped_column(Text)
    taxonomy_version: Mapped[str] = mapped_column(Text)
    solver_seed: Mapped[int] = mapped_column(Integer)
    worker_count: Mapped[int] = mapped_column(Integer)


class MatchRunRow(TimestampMixin, Base):
    __tablename__ = "match_runs"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    status: Mapped[str] = mapped_column(Text)
    stale: Mapped[bool] = mapped_column(Boolean)
    stale_reasons_json: Mapped[str] = mapped_column(Text)
    config_snapshot_json: Mapped[str] = mapped_column(Text)
    input_snapshot_hash: Mapped[str] = mapped_column(Text)
    input_snapshot_json: Mapped[str] = mapped_column(Text)
    result_snapshot_json: Mapped[str] = mapped_column(Text)
    stage_evidence_json: Mapped[str] = mapped_column(Text)
    benchmark_evidence_json: Mapped[str | None] = mapped_column(Text)
    shuffle_evidence_json: Mapped[str | None] = mapped_column(Text)
    runtime_ms: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    placement_count: Mapped[int] = mapped_column(Integer)
    total_score_bp: Mapped[int] = mapped_column(Integer)
    minimum_score_bp: Mapped[int | None] = mapped_column(Integer)
    solver_seed: Mapped[int] = mapped_column(Integer)
    worker_count: Mapped[int] = mapped_column(Integer)
    score_version: Mapped[str] = mapped_column(Text)
    optimality_limitation: Mapped[str | None] = mapped_column(Text)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PairScoreRow(TimestampMixin, Base):
    __tablename__ = "pair_scores"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    run_id: Mapped[str] = mapped_column(Text)
    student_id: Mapped[str] = mapped_column(Text)
    project_id: Mapped[str] = mapped_column(Text)
    eligible: Mapped[bool] = mapped_column(Boolean)
    eligibility_reasons_json: Mapped[str] = mapped_column(Text)
    factor_scores_json: Mapped[str] = mapped_column(Text)
    raw_weights_json: Mapped[str] = mapped_column(Text)
    normalized_weights_json: Mapped[str] = mapped_column(Text)
    contributions_json: Mapped[str] = mapped_column(Text)
    evidence_json: Mapped[str] = mapped_column(Text)
    gaps_json: Mapped[str] = mapped_column(Text)
    missing_fields_json: Mapped[str] = mapped_column(Text)
    total_bp: Mapped[int] = mapped_column(Integer)
    compatibility_index: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    score_version: Mapped[str] = mapped_column(Text)
    taxonomy_version: Mapped[str] = mapped_column(Text)
    config_snapshot_json: Mapped[str] = mapped_column(Text)


class AssignmentRow(TimestampMixin, Base):
    __tablename__ = "assignments"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    run_id: Mapped[str] = mapped_column(Text)
    student_id: Mapped[str] = mapped_column(Text)
    project_id: Mapped[str] = mapped_column(Text)
    score_bp: Mapped[int] = mapped_column(Integer)
    compatibility_index: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    canonical_tie_order: Mapped[int] = mapped_column(Integer)
    global_rationale: Mapped[str] = mapped_column(Text)


class AuditRow(TimestampMixin, Base):
    __tablename__ = "decision_audit"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    actor_role: Mapped[str] = mapped_column(Text)
    actor_persona_id: Mapped[str] = mapped_column(Text)
    event_type: Mapped[str] = mapped_column(Text)
    entity_type: Mapped[str] = mapped_column(Text)
    entity_id: Mapped[str | None] = mapped_column(Text)
    run_id: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[str] = mapped_column(Text)


class RoadmapRow(TimestampMixin, Base):
    __tablename__ = "roadmaps"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    student_id: Mapped[str] = mapped_column(Text)
    project_id: Mapped[str] = mapped_column(Text)
    run_id: Mapped[str | None] = mapped_column(Text)
    relationship: Mapped[str] = mapped_column(Text)
    weeks: Mapped[int] = mapped_column(Integer)
    tasks_json: Mapped[str] = mapped_column(Text)
    notice: Mapped[str] = mapped_column(Text)


class OutreachRow(TimestampMixin, Base):
    __tablename__ = "outreach_drafts"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    student_id: Mapped[str] = mapped_column(Text)
    project_id: Mapped[str] = mapped_column(Text)
    run_id: Mapped[str | None] = mapped_column(Text)
    deterministic_source: Mapped[str] = mapped_column(Text)
    subject: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    edited_body: Mapped[str] = mapped_column(Text)
    notice: Mapped[str] = mapped_column(Text)


class IdempotencyRow(TimestampMixin, Base):
    __tablename__ = "idempotency_records"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    scope: Mapped[str] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(Text)
    request_hash: Mapped[str] = mapped_column(Text)
    status_code: Mapped[int] = mapped_column(Integer)
    response_json: Mapped[str] = mapped_column(Text)
