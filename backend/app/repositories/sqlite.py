from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from backend.app.db import Database
from backend.app.domain.models import (
    Assignment,
    BenchmarkEvidence,
    DecisionAudit,
    DemoRole,
    EligibilityReason,
    Faculty,
    ImportSnapshot,
    MatchConfig,
    MatchRun,
    OutreachDraft,
    PairScore,
    Project,
    ProjectSkill,
    Roadmap,
    RunStatus,
    SCHEMA_VERSION,
    ScoreWeights,
    ShuffleEvidence,
    Skill,
    Student,
    StudentPreference,
    StudentSkill,
    TimeWindow,
    utc_now,
)
from backend.app.repositories.orm import (
    AssignmentRow,
    AuditRow,
    AvailabilityRow,
    ConfigRow,
    FacultyRow,
    IdempotencyRow,
    MatchRunRow,
    OutreachRow,
    PairScoreRow,
    PreferenceRow,
    ProjectRow,
    ProjectSkillRow,
    RoadmapRow,
    SkillRow,
    StudentRow,
    StudentSkillRow,
)


def stable_runtime_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def _to_jsonable(value: Any) -> Any:
    """Recursively convert Pydantic models (including those nested in lists/dicts) to JSON-safe data."""
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    return value


def _json(value: Any) -> str:
    return json.dumps(_to_jsonable(value), sort_keys=True, separators=(",", ":"), default=str)


def _load(value: str | None, default: Any) -> Any:
    return default if value is None else json.loads(value)


def _entity_values(entity: Any) -> dict[str, Any]:
    return {
        "id": entity.id,
        "schema_version": entity.schema_version,
        "created_at": entity.created_at,
        "updated_at": entity.updated_at,
    }


class RepositoryConflict(ValueError):
    pass


class RepositoryNotFound(LookupError):
    pass


class SQLiteRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    # ---- seed/import base records -------------------------------------------------
    def load_snapshot(self, snapshot: ImportSnapshot, *, event_type: str = "seed_completed") -> None:
        with self.database.session() as session:
            self._upsert_snapshot(session, snapshot)
            self._append_audit(
                session,
                DecisionAudit(
                    id=stable_runtime_id("audit"),
                    actor_role=DemoRole.ADMIN,
                    actor_persona_id="admin-demo-001",
                    event_type=event_type,
                    entity_type="synthetic_snapshot",
                    reason="Validated synthetic fixture loaded into the local demo database.",
                    metadata={
                        "student_count": len(snapshot.students),
                        "faculty_count": len(snapshot.faculty),
                        "project_count": len(snapshot.projects),
                        "skill_count": len(snapshot.skills),
                        "synthetic_only": True,
                    },
                ),
            )

    def apply_import(self, snapshot: ImportSnapshot, *, actor_id: str) -> list[str]:
        with self.database.session() as session:
            self._upsert_snapshot(session, snapshot)
            stale_ids = self._mark_stale(session, "imported_data")
            self._append_audit(
                session,
                DecisionAudit(
                    id=stable_runtime_id("audit"),
                    actor_role=DemoRole.ADMIN,
                    actor_persona_id=actor_id,
                    event_type="import_applied",
                    entity_type="synthetic_snapshot",
                    metadata={
                        "student_count": len(snapshot.students),
                        "faculty_count": len(snapshot.faculty),
                        "project_count": len(snapshot.projects),
                        "skill_count": len(snapshot.skills),
                        "stale_run_ids": stale_ids,
                    },
                ),
            )
            return stale_ids

    def _upsert_snapshot(self, session: Session, snapshot: ImportSnapshot) -> None:
        for faculty in snapshot.faculty:
            session.merge(
                FacultyRow(
                    **_entity_values(faculty),
                    display_name=faculty.display_name,
                    department=faculty.department,
                    research_interests_json=_json(faculty.research_interests),
                    provenance_type=faculty.provenance_type.value,
                    provenance_label=faculty.provenance_label,
                    source_url=faculty.source_url,
                    source_retrieved_at=faculty.source_retrieved_at,
                )
            )
        for skill in snapshot.skills:
            session.merge(
                SkillRow(
                    **_entity_values(skill),
                    label=skill.label,
                    category=skill.category,
                    aliases_json=_json(skill.aliases),
                )
            )
        for student in snapshot.students:
            self._merge_student_base(session, student)
        session.flush()
        for project in snapshot.projects:
            self._merge_project_base(session, project)
        session.flush()
        for student in snapshot.students:
            self._replace_student_relations(session, student)
        for project in snapshot.projects:
            self._replace_project_relations(session, project)

    # ---- students ----------------------------------------------------------------
    def count_students(self) -> int:
        with self.database.session() as session:
            return int(session.scalar(select(func.count()).select_from(StudentRow)) or 0)

    def list_students(self, *, submitted_only: bool = False) -> list[Student]:
        with self.database.session() as session:
            statement = select(StudentRow).order_by(StudentRow.id)
            if submitted_only:
                statement = statement.where(StudentRow.submitted.is_(True))
            return [self._student_from_row(session, row) for row in session.scalars(statement)]

    def get_student(self, student_id: str) -> Student | None:
        with self.database.session() as session:
            row = session.get(StudentRow, student_id)
            return None if row is None else self._student_from_row(session, row)

    def save_student(
        self, student: Student, *, actor_role: str, actor_id: str, event_type: str = "profile_edited"
    ) -> list[str]:
        now = utc_now()
        student.updated_at = now
        with self.database.session() as session:
            existing = session.get(StudentRow, student.id)
            if existing is None:
                raise RepositoryNotFound(f"student {student.id} was not found")
            self._merge_student_base(session, student)
            self._replace_student_relations(session, student)
            stale_ids = self._mark_stale(session, "student_data")
            self._append_audit(
                session,
                DecisionAudit(
                    id=stable_runtime_id("audit"),
                    actor_role=DemoRole(actor_role),
                    actor_persona_id=actor_id,
                    event_type=event_type,
                    entity_type="student",
                    entity_id=student.id,
                    metadata={"stale_run_ids": stale_ids},
                ),
            )
            return stale_ids

    def _merge_student_base(self, session: Session, student: Student) -> None:
        session.merge(
            StudentRow(
                **_entity_values(student),
                synthetic=student.synthetic,
                synthetic_label=student.synthetic_label,
                display_name=student.display_name,
                major=student.major,
                academic_year=student.academic_year,
                interests_json=_json(student.interests),
                hours_per_week=student.hours_per_week,
                learning_goals_json=_json(student.learning_goals),
                first_time_researcher=student.first_time_researcher,
                accepts_suggestions=student.accepts_suggestions,
                profile_complete=student.profile_complete,
                submitted=student.submitted,
                synthetic_submission_order=student.synthetic_submission_order,
            )
        )

    def _replace_student_relations(self, session: Session, student: Student) -> None:
        session.execute(delete(StudentSkillRow).where(StudentSkillRow.student_id == student.id))
        session.execute(delete(PreferenceRow).where(PreferenceRow.student_id == student.id))
        session.execute(
            delete(AvailabilityRow).where(
                AvailabilityRow.owner_type == "student", AvailabilityRow.owner_id == student.id
            )
        )
        now = student.updated_at
        for item in student.skills:
            session.add(
                StudentSkillRow(
                    id=f"student-skill-{student.id}-{item.skill_id}",
                    schema_version=student.schema_version,
                    student_id=student.id,
                    skill_id=item.skill_id,
                    proficiency=item.proficiency,
                    created_at=student.created_at,
                    updated_at=now,
                )
            )
        for item in student.preferences:
            session.add(
                PreferenceRow(
                    id=f"preference-{student.id}-{item.project_id}",
                    schema_version=student.schema_version,
                    student_id=student.id,
                    project_id=item.project_id,
                    rank=item.rank,
                    created_at=student.created_at,
                    updated_at=now,
                )
            )
        for index, item in enumerate(student.availability, start=1):
            session.add(
                AvailabilityRow(
                    id=item.id or f"window-{student.id}-{index:02d}",
                    schema_version=student.schema_version,
                    owner_type="student",
                    owner_id=student.id,
                    day=item.day,
                    start_minute=item.start_minute,
                    end_minute=item.end_minute,
                    fixed=item.fixed,
                    purpose=item.purpose.value,
                    created_at=student.created_at,
                    updated_at=now,
                )
            )

    def _student_from_row(self, session: Session, row: StudentRow) -> Student:
        skills = [
            StudentSkill(skill_id=item.skill_id, proficiency=item.proficiency)
            for item in session.scalars(
                select(StudentSkillRow)
                .where(StudentSkillRow.student_id == row.id)
                .order_by(StudentSkillRow.skill_id)
            )
        ]
        preferences = [
            StudentPreference(project_id=item.project_id, rank=item.rank)
            for item in session.scalars(
                select(PreferenceRow)
                .where(PreferenceRow.student_id == row.id)
                .order_by(PreferenceRow.rank)
            )
        ]
        availability = [
            TimeWindow(
                id=item.id,
                day=item.day,
                start_minute=item.start_minute,
                end_minute=item.end_minute,
                fixed=item.fixed,
                purpose=item.purpose,
            )
            for item in session.scalars(
                select(AvailabilityRow)
                .where(
                    AvailabilityRow.owner_type == "student",
                    AvailabilityRow.owner_id == row.id,
                )
                .order_by(AvailabilityRow.day, AvailabilityRow.start_minute, AvailabilityRow.id)
            )
        ]
        return Student(
            id=row.id,
            schema_version=row.schema_version,
            synthetic=True,
            synthetic_label=row.synthetic_label,
            display_name=row.display_name,
            major=row.major,
            academic_year=row.academic_year,
            interests=_load(row.interests_json, []),
            hours_per_week=row.hours_per_week,
            learning_goals=_load(row.learning_goals_json, []),
            first_time_researcher=row.first_time_researcher,
            accepts_suggestions=row.accepts_suggestions,
            profile_complete=row.profile_complete,
            submitted=row.submitted,
            synthetic_submission_order=row.synthetic_submission_order,
            skills=skills,
            preferences=preferences,
            availability=availability,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    # ---- faculty, skills, projects ------------------------------------------------
    def list_faculty(self) -> list[Faculty]:
        with self.database.session() as session:
            return [
                self._faculty_from_row(row)
                for row in session.scalars(select(FacultyRow).order_by(FacultyRow.id))
            ]

    def get_faculty(self, faculty_id: str) -> Faculty | None:
        with self.database.session() as session:
            row = session.get(FacultyRow, faculty_id)
            return None if row is None else self._faculty_from_row(row)

    @staticmethod
    def _faculty_from_row(row: FacultyRow) -> Faculty:
        return Faculty(
            id=row.id,
            schema_version=row.schema_version,
            display_name=row.display_name,
            department=row.department,
            research_interests=_load(row.research_interests_json, []),
            provenance_type=row.provenance_type,
            provenance_label=row.provenance_label,
            source_url=row.source_url,
            source_retrieved_at=row.source_retrieved_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def list_skills(self) -> list[Skill]:
        with self.database.session() as session:
            return [
                Skill(
                    id=row.id,
                    schema_version=row.schema_version,
                    label=row.label,
                    category=row.category,
                    aliases=_load(row.aliases_json, []),
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
                for row in session.scalars(select(SkillRow).order_by(SkillRow.id))
            ]

    def list_projects(self) -> list[Project]:
        with self.database.session() as session:
            return [
                self._project_from_row(session, row)
                for row in session.scalars(select(ProjectRow).order_by(ProjectRow.id))
            ]

    def get_project(self, project_id: str) -> Project | None:
        with self.database.session() as session:
            row = session.get(ProjectRow, project_id)
            return None if row is None else self._project_from_row(session, row)

    def save_project(
        self, project: Project, *, actor_role: str, actor_id: str, event_type: str = "project_edited"
    ) -> list[str]:
        project.updated_at = utc_now()
        with self.database.session() as session:
            self._merge_project_base(session, project)
            session.flush()
            self._replace_project_relations(session, project)
            stale_ids = self._mark_stale(session, "project_data")
            self._append_audit(
                session,
                DecisionAudit(
                    id=stable_runtime_id("audit"),
                    actor_role=DemoRole(actor_role),
                    actor_persona_id=actor_id,
                    event_type=event_type,
                    entity_type="project",
                    entity_id=project.id,
                    metadata={"stale_run_ids": stale_ids},
                ),
            )
            return stale_ids

    def _merge_project_base(self, session: Session, project: Project) -> None:
        session.merge(
            ProjectRow(
                **_entity_values(project),
                faculty_id=project.faculty_id,
                title=project.title,
                description=project.description,
                department=project.department,
                interests_json=_json(project.interests),
                capacity=project.capacity,
                prerequisites_json=_json(project.prerequisites),
                mentoring_available=project.mentoring_available,
                commitment_hours=project.commitment_hours,
                term=project.term,
                modality=project.modality,
                active=project.active,
                provenance_type=project.provenance_type.value,
                provenance_label=project.provenance_label,
                source_url=project.source_url,
                source_note=project.source_note,
            )
        )

    def _replace_project_relations(self, session: Session, project: Project) -> None:
        session.execute(delete(ProjectSkillRow).where(ProjectSkillRow.project_id == project.id))
        session.execute(
            delete(AvailabilityRow).where(
                AvailabilityRow.owner_type == "project", AvailabilityRow.owner_id == project.id
            )
        )
        for item in project.skills:
            session.add(
                ProjectSkillRow(
                    id=f"project-skill-{project.id}-{item.skill_id}",
                    schema_version=project.schema_version,
                    project_id=project.id,
                    skill_id=item.skill_id,
                    required_proficiency=item.required_proficiency,
                    kind=item.kind.value,
                    created_at=project.created_at,
                    updated_at=project.updated_at,
                )
            )
        all_windows = [*project.required_windows, *project.mentoring_windows]
        for index, item in enumerate(all_windows, start=1):
            session.add(
                AvailabilityRow(
                    id=item.id or f"window-{project.id}-{index:02d}",
                    schema_version=project.schema_version,
                    owner_type="project",
                    owner_id=project.id,
                    day=item.day,
                    start_minute=item.start_minute,
                    end_minute=item.end_minute,
                    fixed=item.fixed,
                    purpose=item.purpose.value,
                    created_at=project.created_at,
                    updated_at=project.updated_at,
                )
            )

    def _project_from_row(self, session: Session, row: ProjectRow) -> Project:
        skills = [
            ProjectSkill(
                skill_id=item.skill_id,
                required_proficiency=item.required_proficiency,
                kind=item.kind,
            )
            for item in session.scalars(
                select(ProjectSkillRow)
                .where(ProjectSkillRow.project_id == row.id)
                .order_by(ProjectSkillRow.skill_id)
            )
        ]
        windows = [
            TimeWindow(
                id=item.id,
                day=item.day,
                start_minute=item.start_minute,
                end_minute=item.end_minute,
                fixed=item.fixed,
                purpose=item.purpose,
            )
            for item in session.scalars(
                select(AvailabilityRow)
                .where(
                    AvailabilityRow.owner_type == "project",
                    AvailabilityRow.owner_id == row.id,
                )
                .order_by(AvailabilityRow.purpose, AvailabilityRow.day, AvailabilityRow.start_minute)
            )
        ]
        return Project(
            id=row.id,
            schema_version=row.schema_version,
            faculty_id=row.faculty_id,
            title=row.title,
            description=row.description,
            department=row.department,
            interests=_load(row.interests_json, []),
            capacity=row.capacity,
            prerequisites=_load(row.prerequisites_json, []),
            mentoring_available=row.mentoring_available,
            commitment_hours=row.commitment_hours,
            term=row.term,
            modality=row.modality,
            active=row.active,
            provenance_type=row.provenance_type,
            provenance_label=row.provenance_label,
            source_url=row.source_url,
            source_note=row.source_note,
            skills=skills,
            required_windows=[window for window in windows if window.purpose.value == "required"],
            mentoring_windows=[window for window in windows if window.purpose.value == "mentoring"],
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    # ---- configuration -------------------------------------------------------------
    def get_config(self) -> MatchConfig:
        with self.database.session() as session:
            row = session.get(ConfigRow, "global")
            if row is None:
                config = MatchConfig()
                now = utc_now()
                session.add(
                    ConfigRow(
                        id="global",
                        schema_version=SCHEMA_VERSION,
                        weights_json=_json(config.weights),
                        threshold_bp=config.threshold_bp,
                        score_version=config.score_version,
                        taxonomy_version=config.taxonomy_version,
                        solver_seed=config.solver_seed,
                        worker_count=config.worker_count,
                        created_at=now,
                        updated_at=now,
                    )
                )
                return config
            return MatchConfig(
                weights=ScoreWeights.model_validate(_load(row.weights_json, {})),
                threshold=Decimal(row.threshold_bp) / Decimal(100),
                score_version=row.score_version,
                taxonomy_version=row.taxonomy_version,
                solver_seed=row.solver_seed,
                worker_count=row.worker_count,
            )

    def save_config(self, config: MatchConfig, *, actor_id: str) -> list[str]:
        now = utc_now()
        with self.database.session() as session:
            existing = session.get(ConfigRow, "global")
            created = existing.created_at if existing else now
            session.merge(
                ConfigRow(
                    id="global",
                    schema_version=SCHEMA_VERSION,
                    weights_json=_json(config.weights),
                    threshold_bp=config.threshold_bp,
                    score_version=config.score_version,
                    taxonomy_version=config.taxonomy_version,
                    solver_seed=config.solver_seed,
                    worker_count=config.worker_count,
                    created_at=created,
                    updated_at=now,
                )
            )
            stale_ids = self._mark_stale(session, "configuration")
            self._append_audit(
                session,
                DecisionAudit(
                    id=stable_runtime_id("audit"),
                    actor_role=DemoRole.ADMIN,
                    actor_persona_id=actor_id,
                    event_type="configuration_changed",
                    entity_type="match_config",
                    entity_id="global",
                    metadata={
                        "threshold_bp": config.threshold_bp,
                        "score_version": config.score_version,
                        "stale_run_ids": stale_ids,
                    },
                ),
            )
            return stale_ids

    # ---- immutable runs ------------------------------------------------------------
    def save_run(
        self, run: MatchRun, pair_scores: Sequence[PairScore], assignments: Sequence[Assignment]
    ) -> None:
        with self.database.session() as session:
            session.add(
                MatchRunRow(
                    **_entity_values(run),
                    status=run.status.value,
                    stale=run.stale,
                    stale_reasons_json=_json(run.stale_reasons),
                    config_snapshot_json=_json(run.config_snapshot),
                    input_snapshot_hash=run.input_snapshot_hash,
                    input_snapshot_json=_json(run.input_snapshot),
                    result_snapshot_json=_json(run.result_snapshot),
                    stage_evidence_json=_json(run.stage_evidence),
                    benchmark_evidence_json=(
                        _json(run.benchmark_evidence) if run.benchmark_evidence else None
                    ),
                    shuffle_evidence_json=(
                        _json(run.shuffle_evidence) if run.shuffle_evidence else None
                    ),
                    runtime_ms=run.runtime_ms,
                    placement_count=run.placement_count,
                    total_score_bp=run.total_score_bp,
                    minimum_score_bp=run.minimum_score_bp,
                    solver_seed=run.solver_seed,
                    worker_count=run.worker_count,
                    score_version=run.score_version,
                    optimality_limitation=run.optimality_limitation,
                    approved_at=run.approved_at,
                )
            )
            session.flush()
            for pair in pair_scores:
                session.add(self._pair_row(run.id, pair, run.created_at))
            for assignment in assignments:
                session.add(self._assignment_row(run.id, assignment, run.created_at))
            self._append_audit(
                session,
                DecisionAudit(
                    id=stable_runtime_id("audit"),
                    actor_role=DemoRole.ADMIN,
                    actor_persona_id="admin-demo-001",
                    event_type="run_created",
                    entity_type="match_run",
                    entity_id=run.id,
                    run_id=run.id,
                    metadata={
                        "status": run.status.value,
                        "placement_count": run.placement_count,
                        "input_snapshot_hash": run.input_snapshot_hash,
                    },
                ),
            )

    @staticmethod
    def _pair_row(run_id: str, pair: PairScore, created_at: datetime) -> PairScoreRow:
        return PairScoreRow(
            id=f"pair-{run_id}-{pair.student_id}-{pair.project_id}",
            schema_version=SCHEMA_VERSION,
            run_id=run_id,
            student_id=pair.student_id,
            project_id=pair.project_id,
            eligible=pair.eligible,
            eligibility_reasons_json=_json(pair.eligibility_reasons),
            factor_scores_json=_json(pair.factor_scores_bp),
            raw_weights_json=_json(pair.raw_weights),
            normalized_weights_json=_json(pair.normalized_weights),
            contributions_json=_json(pair.contributions_bp),
            evidence_json=_json(pair.evidence),
            gaps_json=_json(pair.gaps),
            missing_fields_json=_json(pair.missing_fields),
            total_bp=pair.total_bp,
            compatibility_index=pair.compatibility_index,
            score_version=pair.score_version,
            taxonomy_version=pair.taxonomy_version,
            config_snapshot_json=_json(pair.config_snapshot),
            created_at=created_at,
            updated_at=created_at,
        )

    @staticmethod
    def _assignment_row(
        run_id: str, assignment: Assignment, created_at: datetime
    ) -> AssignmentRow:
        return AssignmentRow(
            id=f"assignment-{run_id}-{assignment.student_id}",
            schema_version=SCHEMA_VERSION,
            run_id=run_id,
            student_id=assignment.student_id,
            project_id=assignment.project_id,
            score_bp=assignment.score_bp,
            compatibility_index=assignment.compatibility_index,
            canonical_tie_order=assignment.canonical_tie_order,
            global_rationale=assignment.global_rationale,
            created_at=created_at,
            updated_at=created_at,
        )

    def list_runs(self) -> list[MatchRun]:
        with self.database.session() as session:
            return [
                self._run_from_row(row)
                for row in session.scalars(
                    select(MatchRunRow).order_by(MatchRunRow.created_at.desc(), MatchRunRow.id)
                )
            ]

    def get_run(self, run_id: str) -> MatchRun | None:
        with self.database.session() as session:
            row = session.get(MatchRunRow, run_id)
            return None if row is None else self._run_from_row(row)

    @staticmethod
    def _run_from_row(row: MatchRunRow) -> MatchRun:
        return MatchRun(
            id=row.id,
            schema_version=row.schema_version,
            status=row.status,
            stale=row.stale,
            stale_reasons=_load(row.stale_reasons_json, []),
            config_snapshot=_load(row.config_snapshot_json, {}),
            input_snapshot_hash=row.input_snapshot_hash,
            input_snapshot=_load(row.input_snapshot_json, {}),
            result_snapshot=_load(row.result_snapshot_json, {}),
            stage_evidence=_load(row.stage_evidence_json, []),
            benchmark_evidence=(
                BenchmarkEvidence.model_validate(_load(row.benchmark_evidence_json, {}))
                if row.benchmark_evidence_json
                else None
            ),
            shuffle_evidence=(
                ShuffleEvidence.model_validate(_load(row.shuffle_evidence_json, {}))
                if row.shuffle_evidence_json
                else None
            ),
            runtime_ms=row.runtime_ms,
            placement_count=row.placement_count,
            total_score_bp=row.total_score_bp,
            minimum_score_bp=row.minimum_score_bp,
            solver_seed=row.solver_seed,
            worker_count=row.worker_count,
            score_version=row.score_version,
            optimality_limitation=row.optimality_limitation,
            approved_at=row.approved_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def list_pair_scores(self, run_id: str, student_id: str | None = None) -> list[PairScore]:
        with self.database.session() as session:
            statement = select(PairScoreRow).where(PairScoreRow.run_id == run_id)
            if student_id is not None:
                statement = statement.where(PairScoreRow.student_id == student_id)
            statement = statement.order_by(PairScoreRow.student_id, PairScoreRow.project_id)
            return [self._pair_from_row(row) for row in session.scalars(statement)]

    @staticmethod
    def _pair_from_row(row: PairScoreRow) -> PairScore:
        return PairScore(
            run_id=row.run_id,
            student_id=row.student_id,
            project_id=row.project_id,
            eligible=row.eligible,
            eligibility_reasons=[
                EligibilityReason.model_validate(reason)
                for reason in _load(row.eligibility_reasons_json, [])
            ],
            factor_scores_bp=_load(row.factor_scores_json, {}),
            raw_weights=_load(row.raw_weights_json, {}),
            normalized_weights=_load(row.normalized_weights_json, {}),
            contributions_bp=_load(row.contributions_json, {}),
            evidence=_load(row.evidence_json, {}),
            gaps=_load(row.gaps_json, []),
            missing_fields=_load(row.missing_fields_json, []),
            total_bp=row.total_bp,
            compatibility_index=row.compatibility_index,
            score_version=row.score_version,
            taxonomy_version=row.taxonomy_version,
            config_snapshot=_load(row.config_snapshot_json, {}),
        )

    def list_assignments(self, run_id: str) -> list[Assignment]:
        with self.database.session() as session:
            run = session.get(MatchRunRow, run_id)
            if run is None:
                return []
            state = "approved" if run.status == RunStatus.APPROVED.value else "proposed"
            return [
                Assignment(
                    run_id=row.run_id,
                    student_id=row.student_id,
                    project_id=row.project_id,
                    score_bp=row.score_bp,
                    compatibility_index=row.compatibility_index,
                    canonical_tie_order=row.canonical_tie_order,
                    state=state,
                    global_rationale=row.global_rationale,
                )
                for row in session.scalars(
                    select(AssignmentRow)
                    .where(AssignmentRow.run_id == run_id)
                    .order_by(AssignmentRow.student_id)
                )
            ]

    def approve_run(self, run_id: str, *, actor_id: str) -> MatchRun:
        with self.database.session() as session:
            row = session.get(MatchRunRow, run_id)
            if row is None:
                raise RepositoryNotFound(f"run {run_id} was not found")
            if row.status == RunStatus.APPROVED.value:
                return self._run_from_row(row)
            if row.status != RunStatus.PROPOSED.value:
                raise RepositoryConflict("only a proposed run can be approved")
            if row.stale:
                reasons = ", ".join(_load(row.stale_reasons_json, []))
                raise RepositoryConflict(f"stale run cannot be approved; changed data: {reasons}")
            now = utc_now()
            row.status = RunStatus.APPROVED.value
            row.approved_at = now
            row.updated_at = now
            self._append_audit(
                session,
                DecisionAudit(
                    id=stable_runtime_id("audit"),
                    actor_role=DemoRole.ADMIN,
                    actor_persona_id=actor_id,
                    event_type="run_approved",
                    entity_type="match_run",
                    entity_id=run_id,
                    run_id=run_id,
                    metadata={"placement_count": row.placement_count},
                ),
            )
            session.flush()
            return self._run_from_row(row)

    def latest_approved_run(self) -> MatchRun | None:
        with self.database.session() as session:
            row = session.scalar(
                select(MatchRunRow)
                .where(MatchRunRow.status == RunStatus.APPROVED.value)
                .order_by(MatchRunRow.approved_at.desc(), MatchRunRow.id)
                .limit(1)
            )
            return None if row is None else self._run_from_row(row)

    def save_shuffle_evidence(self, run_id: str, evidence: ShuffleEvidence) -> MatchRun:
        with self.database.session() as session:
            row = session.get(MatchRunRow, run_id)
            if row is None:
                raise RepositoryNotFound(f"run {run_id} was not found")
            if row.shuffle_evidence_json is not None:
                existing = ShuffleEvidence.model_validate(_load(row.shuffle_evidence_json, {}))
                if existing != evidence:
                    raise RepositoryConflict("shuffle evidence is immutable once recorded")
                return self._run_from_row(row)
            row.shuffle_evidence_json = _json(evidence)
            row.updated_at = utc_now()
            session.flush()
            return self._run_from_row(row)

    def _mark_stale(self, session: Session, data_class: str) -> list[str]:
        rows = list(
            session.scalars(
                select(MatchRunRow).where(
                    MatchRunRow.status == RunStatus.PROPOSED.value,
                    MatchRunRow.stale.is_(False),
                )
            )
        )
        now = utc_now()
        stale_ids: list[str] = []
        for row in rows:
            row.stale = True
            row.stale_reasons_json = _json([data_class])
            row.updated_at = now
            stale_ids.append(row.id)
            self._append_audit(
                session,
                DecisionAudit(
                    id=stable_runtime_id("audit"),
                    actor_role=DemoRole.ADMIN,
                    actor_persona_id="system",
                    event_type="run_marked_stale",
                    entity_type="match_run",
                    entity_id=row.id,
                    run_id=row.id,
                    reason=f"{data_class} changed after the immutable snapshot was created.",
                    metadata={"changed_data_class": data_class},
                ),
            )
        return sorted(stale_ids)

    # ---- audit ---------------------------------------------------------------------
    def append_audit(self, event: DecisionAudit) -> None:
        with self.database.session() as session:
            self._append_audit(session, event)

    @staticmethod
    def _append_audit(session: Session, event: DecisionAudit) -> None:
        session.add(
            AuditRow(
                **_entity_values(event),
                actor_role=event.actor_role.value,
                actor_persona_id=event.actor_persona_id,
                event_type=event.event_type,
                entity_type=event.entity_type,
                entity_id=event.entity_id,
                run_id=event.run_id,
                reason=event.reason,
                metadata_json=_json(event.metadata),
            )
        )

    def list_audit(self) -> list[DecisionAudit]:
        with self.database.session() as session:
            return [
                DecisionAudit(
                    id=row.id,
                    schema_version=row.schema_version,
                    actor_role=row.actor_role,
                    actor_persona_id=row.actor_persona_id,
                    event_type=row.event_type,
                    entity_type=row.entity_type,
                    entity_id=row.entity_id,
                    run_id=row.run_id,
                    reason=row.reason,
                    metadata=_load(row.metadata_json, {}),
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
                for row in session.scalars(
                    select(AuditRow).order_by(AuditRow.created_at.desc(), AuditRow.id.desc())
                )
            ]

    # ---- roadmap and outreach ------------------------------------------------------
    def get_roadmap(self, student_id: str) -> Roadmap | None:
        with self.database.session() as session:
            row = session.scalar(
                select(RoadmapRow)
                .where(RoadmapRow.student_id == student_id)
                .order_by(RoadmapRow.updated_at.desc(), RoadmapRow.id)
                .limit(1)
            )
            return None if row is None else self._roadmap_from_row(row)

    def save_roadmap(self, roadmap: Roadmap) -> Roadmap:
        roadmap.updated_at = utc_now()
        with self.database.session() as session:
            session.merge(
                RoadmapRow(
                    **_entity_values(roadmap),
                    student_id=roadmap.student_id,
                    project_id=roadmap.project_id,
                    run_id=roadmap.run_id,
                    relationship=roadmap.relationship,
                    weeks=roadmap.weeks,
                    tasks_json=_json(roadmap.tasks),
                    notice=roadmap.notice,
                )
            )
        return roadmap

    @staticmethod
    def _roadmap_from_row(row: RoadmapRow) -> Roadmap:
        return Roadmap(
            id=row.id,
            schema_version=row.schema_version,
            student_id=row.student_id,
            project_id=row.project_id,
            run_id=row.run_id,
            relationship=row.relationship,
            weeks=row.weeks,
            tasks=_load(row.tasks_json, []),
            notice=row.notice,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def get_outreach(self, student_id: str) -> OutreachDraft | None:
        with self.database.session() as session:
            row = session.scalar(
                select(OutreachRow)
                .where(OutreachRow.student_id == student_id)
                .order_by(OutreachRow.updated_at.desc(), OutreachRow.id)
                .limit(1)
            )
            return None if row is None else self._outreach_from_row(row)

    def save_outreach(self, draft: OutreachDraft) -> OutreachDraft:
        draft.updated_at = utc_now()
        with self.database.session() as session:
            session.merge(
                OutreachRow(
                    **_entity_values(draft),
                    student_id=draft.student_id,
                    project_id=draft.project_id,
                    run_id=draft.run_id,
                    deterministic_source=draft.deterministic_source,
                    subject=draft.subject,
                    body=draft.body,
                    edited_body=draft.edited_body,
                    notice=draft.notice,
                )
            )
        return draft

    @staticmethod
    def _outreach_from_row(row: OutreachRow) -> OutreachDraft:
        return OutreachDraft(
            id=row.id,
            schema_version=row.schema_version,
            student_id=row.student_id,
            project_id=row.project_id,
            run_id=row.run_id,
            deterministic_source=row.deterministic_source,
            subject=row.subject,
            body=row.body,
            edited_body=row.edited_body,
            notice=row.notice,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    # ---- idempotency ---------------------------------------------------------------
    def get_idempotency(self, scope: str, key: str) -> dict[str, Any] | None:
        with self.database.session() as session:
            row = session.scalar(
                select(IdempotencyRow).where(
                    IdempotencyRow.scope == scope, IdempotencyRow.idempotency_key == key
                )
            )
            if row is None:
                return None
            return {
                "request_hash": row.request_hash,
                "status_code": row.status_code,
                "response": _load(row.response_json, {}),
            }

    def save_idempotency(
        self,
        scope: str,
        key: str,
        request_hash: str,
        status_code: int,
        response: dict[str, Any],
    ) -> None:
        now = utc_now()
        identifier = "idem-" + hashlib.sha256(f"{scope}|{key}".encode()).hexdigest()[:32]
        with self.database.session() as session:
            existing = session.scalar(
                select(IdempotencyRow).where(
                    IdempotencyRow.scope == scope, IdempotencyRow.idempotency_key == key
                )
            )
            if existing is not None:
                if existing.request_hash != request_hash:
                    raise RepositoryConflict(
                        "idempotency key was already used with a different request"
                    )
                return
            session.add(
                IdempotencyRow(
                    id=identifier,
                    schema_version=SCHEMA_VERSION,
                    scope=scope,
                    idempotency_key=key,
                    request_hash=request_hash,
                    status_code=status_code,
                    response_json=_json(response),
                    created_at=now,
                    updated_at=now,
                )
            )
