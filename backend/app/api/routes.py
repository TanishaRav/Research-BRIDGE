from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Header, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from backend.app.api.dependencies import (
    DemoPrincipal,
    get_principal,
    get_repository,
    require_idempotency_key,
    require_roles,
)
from backend.app.api.errors import ApiError
from backend.app.config import Settings
from backend.app.domain.models import (
    ApprovalRequest,
    ConfigPatch,
    DecisionAudit,
    DemoRole,
    ExportEnvelope,
    FacultyAssignment,
    HYPOTHETICAL_LABEL,
    ImportApplyResponse,
    ImportSnapshot,
    MatchConfig,
    MatchRun,
    NormalizedConfig,
    OutreachDraft,
    OutreachPatch,
    Persona,
    PersonaList,
    Project,
    ProjectCreate,
    ProjectList,
    ProjectPatch,
    ProvenanceType,
    Recommendation,
    ResetRequest,
    ResetResponse,
    Roadmap,
    RoadmapTaskPatch,
    RunCreateRequest,
    RunEvidenceResponse,
    RunReview,
    Student,
    StudentOutcome,
    StudentPatch,
    StudentProfileResponse,
    SYNTHETIC_LABEL,
    utc_now,
)
from backend.app.repositories.sqlite import (
    RepositoryConflict,
    RepositoryNotFound,
    SQLiteRepository,
    stable_runtime_id,
)
from backend.app.seed.generator import DATA_DIR
from backend.app.seed.seed_data import RESET_CONFIRMATION, seed_database
from backend.app.services.evaluation import run_shuffle_test
from backend.app.services.followthrough import build_outreach, build_roadmap
from backend.app.services.imports import validate_import_data
from backend.app.services.runs import compare_runs, create_match_run
from backend.app.services.scoring import (
    normalize_weights,
    normalized_weight_percent,
    profile_missing_fields,
    score_pair,
)
from backend.app.services.taxonomy import Taxonomy, normalize_text

router = APIRouter(prefix="/api/v1")


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _ensure_self(principal: DemoPrincipal, entity_id: str) -> None:
    if principal.persona_id != entity_id:
        raise ApiError(403, "record_forbidden", "This demo persona cannot access that record.")


def _not_found(entity: str) -> ApiError:
    return ApiError(404, "not_found", f"The requested {entity} was not found.")


def _hash_payload(value: Any) -> str:
    encoded = json.dumps(jsonable_encoder(value), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _idempotency_replay(
    repository: SQLiteRepository, scope: str, key: str, request_hash: str
) -> dict[str, Any] | None:
    existing = repository.get_idempotency(scope, key)
    if existing is None:
        return None
    if existing["request_hash"] != request_hash:
        raise ApiError(
            409,
            "idempotency_conflict",
            "The idempotency key was already used with a different request.",
        )
    return existing["response"]


def _profile_response(repository: SQLiteRepository, student: Student) -> StudentProfileResponse:
    missing = profile_missing_fields(student)
    approved = repository.latest_approved_run()
    assignment = None
    if approved is not None:
        assignment = next(
            (
                item
                for item in repository.list_assignments(approved.id)
                if item.student_id == student.id
            ),
            None,
        )
    if approved is not None and assignment is not None:
        batch_status = "approved_placement"
        next_action = "Review the approved synthetic placement and its explanation."
    elif approved is not None and student.submitted:
        batch_status = "approved_unplaced"
        next_action = "Review the specific unplaced reason and a clearly labeled roadmap."
    elif not student.submitted:
        batch_status = "draft"
        next_action = (
            f"Complete required fields: {', '.join(missing)}."
            if missing
            else "Submit the profile to the next batch; submission does not allocate immediately."
        )
    else:
        batch_status = "submitted"
        next_action = "Wait for an administrator to run and approve the next cohort batch."
    return StudentProfileResponse(
        student=student,
        missing_required_fields=missing,
        batch_status=batch_status,
        next_action=next_action,
    )


def _validate_project_references(repository: SQLiteRepository, project: Project) -> None:
    if repository.get_faculty(project.faculty_id) is None:
        raise ApiError(
            422,
            "invalid_project",
            "Project references an unknown fictional faculty persona.",
            field_errors={"faculty_id": ["Unknown faculty identifier."]},
        )
    skill_ids = {skill.id for skill in repository.list_skills()}
    unknown = sorted(
        {item.skill_id for item in project.skills if item.skill_id not in skill_ids}
        | {item for item in project.prerequisites if item not in skill_ids}
    )
    if unknown:
        raise ApiError(
            422,
            "invalid_project",
            "Project contains unknown taxonomy skill references.",
            field_errors={"skills": [f"Unknown identifiers: {', '.join(unknown)}"]},
        )


@router.get("/demo/personas", response_model=PersonaList, tags=["demo"])
def personas(
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> PersonaList:
    students = repository.list_students()[:5]
    faculty = repository.list_faculty()[:5]
    return PersonaList(
        personas=[
            Persona(role=DemoRole.ADMIN, persona_id="admin-demo-001", label="EUReCA Admin Demo"),
            *[
                Persona(role=DemoRole.STUDENT, persona_id=item.id, label=item.display_name)
                for item in students
            ],
            *[
                Persona(role=DemoRole.FACULTY, persona_id=item.id, label=item.display_name)
                for item in faculty
            ],
        ]
    )


@router.get("/students/{student_id}", response_model=StudentProfileResponse, tags=["students"])
def get_student_profile(
    student_id: str,
    principal: Annotated[DemoPrincipal, Depends(require_roles(DemoRole.STUDENT))],
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> StudentProfileResponse:
    _ensure_self(principal, student_id)
    student = repository.get_student(student_id)
    if student is None:
        raise _not_found("student")
    return _profile_response(repository, student)


@router.patch("/students/{student_id}", response_model=StudentProfileResponse, tags=["students"])
def patch_student_profile(
    student_id: str,
    patch: StudentPatch,
    principal: Annotated[DemoPrincipal, Depends(require_roles(DemoRole.STUDENT))],
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> StudentProfileResponse:
    _ensure_self(principal, student_id)
    student = repository.get_student(student_id)
    if student is None:
        raise _not_found("student")
    values = student.model_dump()
    for field_name in patch.model_fields_set:
        values[field_name] = getattr(patch, field_name)
    values["updated_at"] = utc_now()
    candidate = Student.model_validate(values)
    candidate.profile_complete = not profile_missing_fields(candidate)
    repository.save_student(candidate, actor_role=principal.role.value, actor_id=principal.persona_id)
    return _profile_response(repository, candidate)


@router.post("/students/{student_id}/submit", response_model=StudentProfileResponse, tags=["students"])
def submit_student_profile(
    student_id: str,
    principal: Annotated[DemoPrincipal, Depends(require_roles(DemoRole.STUDENT))],
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> StudentProfileResponse:
    _ensure_self(principal, student_id)
    student = repository.get_student(student_id)
    if student is None:
        raise _not_found("student")
    missing = profile_missing_fields(student)
    if missing:
        raise ApiError(
            422,
            "profile_incomplete",
            "The profile cannot enter a batch until all required fields are recorded.",
            field_errors={field: ["This required profile evidence is missing."] for field in missing},
        )
    student.submitted = True
    student.profile_complete = True
    repository.save_student(
        student,
        actor_role=principal.role.value,
        actor_id=principal.persona_id,
        event_type="profile_submitted",
    )
    return _profile_response(repository, student)


@router.get(
    "/students/{student_id}/recommendations",
    response_model=list[Recommendation],
    tags=["students"],
)
def get_recommendations(
    student_id: str,
    principal: Annotated[DemoPrincipal, Depends(require_roles(DemoRole.STUDENT))],
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> list[Recommendation]:
    _ensure_self(principal, student_id)
    student = repository.get_student(student_id)
    if student is None:
        raise _not_found("student")
    config = repository.get_config()
    taxonomy = Taxonomy(repository.list_skills(), config.taxonomy_version)
    recommendations = [
        Recommendation(project=project, pair_score=score_pair(student, project, config, taxonomy))
        for project in repository.list_projects()
    ]
    return sorted(
        [item for item in recommendations if item.pair_score.eligible],
        key=lambda item: (-item.pair_score.total_bp, item.project.id),
    )


@router.get("/students/{student_id}/outcome", response_model=StudentOutcome, tags=["students"])
def get_student_outcome(
    student_id: str,
    principal: Annotated[DemoPrincipal, Depends(require_roles(DemoRole.STUDENT))],
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> StudentOutcome:
    _ensure_self(principal, student_id)
    if repository.get_student(student_id) is None:
        raise _not_found("student")
    run = repository.latest_approved_run()
    if run is None:
        return StudentOutcome(
            student_id=student_id,
            run_id=None,
            status="pending",
            notice="No administrator-approved batch result is visible yet.",
        )
    assignment = next(
        (item for item in repository.list_assignments(run.id) if item.student_id == student_id),
        None,
    )
    if assignment is not None:
        return StudentOutcome(
            student_id=student_id,
            run_id=run.id,
            status="placed",
            assignment=assignment,
            notice="Administrator-approved synthetic placement; compatibility is not acceptance probability.",
        )
    reasons = run.result_snapshot.get("unplaced_reasons", {}).get(student_id, [])
    return StudentOutcome(
        student_id=student_id,
        run_id=run.id,
        status="unplaced",
        reasons=reasons,
        notice="Approved synthetic batch result. Any roadmap is labeled not a placement.",
    )


@router.get("/projects", response_model=ProjectList, tags=["projects"])
def list_projects(
    principal: Annotated[DemoPrincipal, Depends(get_principal)],
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
    q: str | None = None,
    department: str | None = None,
    skill: str | None = None,
    max_hours: Decimal | None = Query(default=None, ge=0, le=40),
    schedule_day: int | None = Query(default=None, ge=0, le=6),
) -> ProjectList:
    del principal
    skill_labels = {item.id: item.label for item in repository.list_skills()}
    items = repository.list_projects()
    if q:
        needle = normalize_text(q)

        def searchable(project: Project) -> bool:
            haystack = normalize_text(
                " ".join(
                    [
                        project.title,
                        project.description,
                        project.department,
                        *project.interests,
                        *[item.skill_id for item in project.skills],
                        *[skill_labels.get(item.skill_id, "") for item in project.skills],
                    ]
                )
            )
            return needle in haystack

        items = [item for item in items if searchable(item)]
    if department:
        items = [item for item in items if item.department == department]
    if skill:
        items = [item for item in items if any(relation.skill_id == skill for relation in item.skills)]
    if max_hours is not None:
        items = [item for item in items if item.commitment_hours <= max_hours]
    if schedule_day is not None:
        items = [
            item
            for item in items
            if any(
                window.day == schedule_day
                for window in [*item.required_windows, *item.mentoring_windows]
            )
        ]
    active_filters = {
        key: value
        for key, value in {
            "q": q,
            "department": department,
            "skill": skill,
            "max_hours": max_hours,
            "schedule_day": schedule_day,
        }.items()
        if value is not None
    }
    return ProjectList(items=items, count=len(items), active_filters=active_filters)


@router.get("/projects/{project_id}", response_model=Project, tags=["projects"])
def get_project(
    project_id: str,
    principal: Annotated[DemoPrincipal, Depends(get_principal)],
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> Project:
    del principal
    project = repository.get_project(project_id)
    if project is None:
        raise _not_found("project")
    return project


@router.post("/projects", response_model=Project, status_code=201, tags=["projects"])
def create_project(
    body: ProjectCreate,
    principal: Annotated[
        DemoPrincipal, Depends(require_roles(DemoRole.FACULTY, DemoRole.ADMIN))
    ],
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> Project:
    faculty_id = principal.persona_id if principal.role == DemoRole.FACULTY else body.faculty_id
    if not faculty_id:
        raise ApiError(
            422,
            "faculty_required",
            "An admin-created project must identify a seeded fictional faculty persona.",
            field_errors={"faculty_id": ["This field is required for an admin persona."]},
        )
    now = utc_now()
    values = body.model_dump(exclude={"id", "faculty_id"})
    project = Project(
        id=body.id or stable_runtime_id("project-hyp"),
        faculty_id=faculty_id,
        provenance_type=ProvenanceType.HYPOTHETICAL,
        provenance_label=HYPOTHETICAL_LABEL,
        source_note="User-created hypothetical opening in the synthetic demo; no real availability claim.",
        created_at=now,
        updated_at=now,
        **values,
    )
    _validate_project_references(repository, project)
    repository.save_project(
        project,
        actor_role=principal.role.value,
        actor_id=principal.persona_id,
        event_type="project_created",
    )
    return project


@router.patch("/projects/{project_id}", response_model=Project, tags=["projects"])
def patch_project(
    project_id: str,
    body: ProjectPatch,
    principal: Annotated[
        DemoPrincipal, Depends(require_roles(DemoRole.FACULTY, DemoRole.ADMIN))
    ],
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> Project:
    project = repository.get_project(project_id)
    if project is None:
        raise _not_found("project")
    if principal.role == DemoRole.FACULTY and project.faculty_id != principal.persona_id:
        raise ApiError(403, "record_forbidden", "Faculty may edit only their own hypothetical projects.")
    values = project.model_dump()
    for field_name in body.model_fields_set:
        values[field_name] = getattr(body, field_name)
    values["updated_at"] = utc_now()
    candidate = Project.model_validate(values)
    _validate_project_references(repository, candidate)
    repository.save_project(candidate, actor_role=principal.role.value, actor_id=principal.persona_id)
    return candidate


@router.get(
    "/faculty/{faculty_id}/assignments",
    response_model=list[FacultyAssignment],
    tags=["faculty"],
)
def get_faculty_assignments(
    faculty_id: str,
    principal: Annotated[DemoPrincipal, Depends(require_roles(DemoRole.FACULTY))],
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> list[FacultyAssignment]:
    _ensure_self(principal, faculty_id)
    run = repository.latest_approved_run()
    if run is None:
        return []
    faculty_projects = {
        project.id for project in repository.list_projects() if project.faculty_id == faculty_id
    }
    students = {student.id: student for student in repository.list_students()}
    result: list[FacultyAssignment] = []
    for assignment in repository.list_assignments(run.id):
        if assignment.project_id not in faculty_projects:
            continue
        student = students.get(assignment.student_id)
        if student is None:
            continue
        result.append(
            FacultyAssignment(
                run_id=run.id,
                project_id=assignment.project_id,
                student_id=student.id,
                student_display_name=student.display_name,
                compatibility_index=assignment.compatibility_index,
                explanation=assignment.global_rationale,
            )
        )
    return result


@router.get("/config", response_model=NormalizedConfig, tags=["admin"])
def get_config(
    principal: Annotated[DemoPrincipal, Depends(require_roles(DemoRole.ADMIN))],
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> NormalizedConfig:
    del principal
    config = repository.get_config()
    return NormalizedConfig(
        config=config, normalized_weights_percent=normalized_weight_percent(config)
    )


@router.post("/config/preview", response_model=NormalizedConfig, tags=["admin"])
def preview_config(
    config: MatchConfig,
    principal: Annotated[DemoPrincipal, Depends(require_roles(DemoRole.ADMIN))],
) -> NormalizedConfig:
    del principal
    normalize_weights(config)
    return NormalizedConfig(
        config=config, normalized_weights_percent=normalized_weight_percent(config)
    )


@router.patch("/config", response_model=NormalizedConfig, tags=["admin"])
def patch_config(
    patch: ConfigPatch,
    principal: Annotated[DemoPrincipal, Depends(require_roles(DemoRole.ADMIN))],
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> NormalizedConfig:
    current = repository.get_config()
    values = current.model_dump()
    for field_name in patch.model_fields_set:
        values[field_name] = getattr(patch, field_name)
    candidate = MatchConfig.model_validate(values)
    repository.save_config(candidate, actor_id=principal.persona_id)
    return NormalizedConfig(
        config=candidate, normalized_weights_percent=normalized_weight_percent(candidate)
    )


@router.post("/runs", response_model=MatchRun, status_code=201, tags=["admin"])
def create_run(
    request: Request,
    body: RunCreateRequest = Body(default_factory=RunCreateRequest),
    principal: DemoPrincipal = Depends(require_roles(DemoRole.ADMIN)),
    repository: SQLiteRepository = Depends(get_repository),
    idempotency_key: str = Depends(require_idempotency_key),
) -> MatchRun | dict[str, Any]:
    payload_hash = _hash_payload(body)
    replay = _idempotency_replay(repository, "create_run", idempotency_key, payload_hash)
    if replay is not None:
        return replay
    run = create_match_run(repository, _settings(request), body.config)
    response = run.model_dump(mode="json")
    repository.save_idempotency("create_run", idempotency_key, payload_hash, 201, response)
    return run


@router.get("/runs", response_model=list[MatchRun], tags=["admin"])
def list_runs(
    principal: Annotated[DemoPrincipal, Depends(require_roles(DemoRole.ADMIN))],
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> list[MatchRun]:
    del principal
    return repository.list_runs()


def _review(repository: SQLiteRepository, run: MatchRun) -> RunReview:
    assignments = repository.list_assignments(run.id)
    return RunReview(
        run=run,
        assignments=assignments,
        pair_scores=repository.list_pair_scores(run.id),
        unplaced=run.result_snapshot.get("unplaced_reasons", {}),
        project_utilization=run.result_snapshot.get("project_utilization", {}),
    )


@router.get("/runs/{run_id}", response_model=RunReview, tags=["admin"])
def get_run_review(
    run_id: str,
    principal: Annotated[DemoPrincipal, Depends(require_roles(DemoRole.ADMIN))],
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> RunReview:
    del principal
    run = repository.get_run(run_id)
    if run is None:
        raise _not_found("run")
    return _review(repository, run)


@router.post("/runs/{run_id}/approve", response_model=MatchRun, tags=["admin"])
def approve_run(
    run_id: str,
    body: ApprovalRequest,
    principal: Annotated[DemoPrincipal, Depends(require_roles(DemoRole.ADMIN))],
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> MatchRun | dict[str, Any]:
    payload_hash = _hash_payload({"run_id": run_id, **body.model_dump(mode="json")})
    scope = f"approve_run:{run_id}"
    replay = _idempotency_replay(repository, scope, idempotency_key, payload_hash)
    if replay is not None:
        return replay
    try:
        run = repository.approve_run(run_id, actor_id=principal.persona_id)
    except RepositoryNotFound as exc:
        raise _not_found("run") from exc
    except RepositoryConflict as exc:
        raise ApiError(409, "run_not_approvable", str(exc)) from exc
    response = run.model_dump(mode="json")
    repository.save_idempotency(scope, idempotency_key, payload_hash, 200, response)
    return run


@router.get("/runs/{run_id}/comparison/{other_id}", tags=["admin"])
def compare_run_endpoint(
    run_id: str,
    other_id: str,
    principal: Annotated[DemoPrincipal, Depends(require_roles(DemoRole.ADMIN))],
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
):
    del principal
    first = repository.get_run(run_id)
    second = repository.get_run(other_id)
    if first is None or second is None:
        raise _not_found("run")
    return compare_runs(first, second)


@router.post("/runs/{run_id}/shuffle-test", tags=["admin"])
def shuffle_run(
    run_id: str,
    request: Request,
    principal: Annotated[DemoPrincipal, Depends(require_roles(DemoRole.ADMIN))],
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
):
    del principal
    run = repository.get_run(run_id)
    if run is None:
        raise _not_found("run")
    if run.shuffle_evidence is not None:
        return run.shuffle_evidence
    students = [Student.model_validate(item) for item in run.input_snapshot.get("students", [])]
    projects = [Project.model_validate(item) for item in run.input_snapshot.get("projects", [])]
    config = MatchConfig.model_validate(run.config_snapshot)
    evidence = run_shuffle_test(
        students,
        projects,
        repository.list_pair_scores(run_id),
        config.threshold_bp,
        repository.list_assignments(run_id),
        timeout_seconds=_settings(request).solver_timeout_seconds,
    )
    repository.save_shuffle_evidence(run_id, evidence)
    return evidence


@router.get("/runs/{run_id}/evidence", response_model=RunEvidenceResponse, tags=["admin"])
def get_run_evidence(
    run_id: str,
    principal: Annotated[DemoPrincipal, Depends(require_roles(DemoRole.ADMIN))],
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> RunEvidenceResponse:
    del principal
    run = repository.get_run(run_id)
    if run is None:
        raise _not_found("run")
    return RunEvidenceResponse(
        run_id=run.id,
        input_snapshot_hash=run.input_snapshot_hash,
        score_version=run.score_version,
        solver_seed=run.solver_seed,
        worker_count=run.worker_count,
        benchmark=run.benchmark_evidence,
        shuffle=run.shuffle_evidence,
        limitation=(
            "Synthetic evaluation cannot establish actual rematching reduction or demographic "
            "fairness. A pilot must measure acceptance, withdrawal, rematching rounds, and "
            "time-to-placement."
        ),
    )


def _source_manifest() -> dict[str, Any]:
    return json.loads((DATA_DIR / "source_manifest.json").read_text(encoding="utf-8"))


def _approved_export(
    run_id: str, repository: SQLiteRepository
) -> tuple[MatchRun, list[Any], list[dict[str, Any]]]:
    run = repository.get_run(run_id)
    if run is None:
        raise _not_found("run")
    if run.status.value != "approved":
        raise ApiError(409, "approval_required", "Only an approved, immutable run may be exported.")
    assignments = repository.list_assignments(run_id)
    unplaced = [
        {"student_id": student_id, "reasons": reasons, "synthetic": True}
        for student_id, reasons in sorted(
            run.result_snapshot.get("unplaced_reasons", {}).items()
        )
    ]
    return run, assignments, unplaced


def _record_export(
    repository: SQLiteRepository,
    run_id: str,
    file_type: str,
    actor_id: str,
    idempotency_key: str | None,
) -> None:
    scope = f"export:{run_id}:{file_type}"
    request_hash = _hash_payload({"run_id": run_id, "format": file_type})
    if idempotency_key:
        replay = _idempotency_replay(repository, scope, idempotency_key, request_hash)
        if replay is not None:
            return
    repository.append_audit(
        DecisionAudit(
            id=stable_runtime_id("audit"),
            actor_role=DemoRole.ADMIN,
            actor_persona_id=actor_id,
            event_type="run_exported",
            entity_type="match_run",
            entity_id=run_id,
            run_id=run_id,
            metadata={"format": file_type, "synthetic_only": True},
        )
    )
    if idempotency_key:
        repository.save_idempotency(
            scope, idempotency_key, request_hash, 200, {"export_recorded": True}
        )


@router.get("/runs/{run_id}/export.json", tags=["admin"])
def export_run_json(
    run_id: str,
    principal: Annotated[DemoPrincipal, Depends(require_roles(DemoRole.ADMIN))],
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    run, assignments, unplaced = _approved_export(run_id, repository)
    _record_export(repository, run_id, "json", principal.persona_id, idempotency_key)
    envelope = ExportEnvelope(
        run={
            "id": run.id,
            "status": run.status.value,
            "approved_at": run.approved_at,
            "input_snapshot_hash": run.input_snapshot_hash,
            "score_version": run.score_version,
            "solver_seed": run.solver_seed,
            "worker_count": run.worker_count,
            "configuration": run.config_snapshot,
        },
        source_manifest=_source_manifest(),
        assignments=[item.model_dump(mode="json") for item in assignments],
        unplaced=unplaced,
        benchmark=(
            run.benchmark_evidence.model_dump(mode="json") if run.benchmark_evidence else {}
        ),
    )
    return JSONResponse(
        content=jsonable_encoder(envelope),
        headers={"Content-Disposition": f'attachment; filename="{run_id}.json"'},
    )


@router.get("/runs/{run_id}/export.csv", tags=["admin"])
def export_run_csv(
    run_id: str,
    principal: Annotated[DemoPrincipal, Depends(require_roles(DemoRole.ADMIN))],
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> Response:
    run, assignments, unplaced = _approved_export(run_id, repository)
    _record_export(repository, run_id, "csv", principal.persona_id, idempotency_key)
    output = io.StringIO()
    fields = [
        "record_type",
        "run_id",
        "student_id",
        "project_id",
        "compatibility_index",
        "reasons",
        "strategy",
        "placement_count",
        "synthetic_notice",
    ]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for assignment in assignments:
        writer.writerow(
            {
                "record_type": "assignment",
                "run_id": run.id,
                "student_id": assignment.student_id,
                "project_id": assignment.project_id,
                "compatibility_index": assignment.compatibility_index,
                "synthetic_notice": SYNTHETIC_LABEL,
            }
        )
    for item in unplaced:
        writer.writerow(
            {
                "record_type": "unplaced",
                "run_id": run.id,
                "student_id": item["student_id"],
                "reasons": "|".join(item["reasons"]),
                "synthetic_notice": SYNTHETIC_LABEL,
            }
        )
    if run.benchmark_evidence:
        for strategy, metrics in run.benchmark_evidence.strategies.items():
            writer.writerow(
                {
                    "record_type": "benchmark",
                    "run_id": run.id,
                    "strategy": strategy,
                    "placement_count": metrics.placement_count,
                    "synthetic_notice": "Synthetic evaluation; not evidence of actual demographic fairness.",
                }
            )
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{run_id}.csv"'},
    )


@router.post("/imports/validate", tags=["admin"])
def validate_import(
    body: dict[str, Any],
    principal: Annotated[DemoPrincipal, Depends(require_roles(DemoRole.ADMIN))],
):
    del principal
    return validate_import_data(body)


@router.post("/imports", response_model=ImportApplyResponse, tags=["admin"])
def apply_import(
    body: dict[str, Any],
    principal: Annotated[DemoPrincipal, Depends(require_roles(DemoRole.ADMIN))],
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> ImportApplyResponse | dict[str, Any]:
    payload_hash = _hash_payload(body)
    replay = _idempotency_replay(repository, "apply_import", idempotency_key, payload_hash)
    if replay is not None:
        return replay
    report = validate_import_data(body)
    if not report.valid:
        raise ApiError(
            422,
            "import_invalid",
            "The synthetic snapshot did not pass import validation.",
            field_errors={issue.path: [issue.message] for issue in report.issues},
        )
    snapshot = ImportSnapshot.model_validate(body)
    stale_ids = repository.apply_import(snapshot, actor_id=principal.persona_id)
    response = ImportApplyResponse(
        imported=True,
        counts=report.counts,
        stale_run_ids=stale_ids,
    )
    encoded = response.model_dump(mode="json")
    repository.save_idempotency("apply_import", idempotency_key, payload_hash, 200, encoded)
    return response


@router.get("/audit", response_model=list[DecisionAudit], tags=["admin"])
def list_audit(
    principal: Annotated[DemoPrincipal, Depends(require_roles(DemoRole.ADMIN))],
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> list[DecisionAudit]:
    del principal
    return repository.list_audit()


@router.post("/demo/reset", response_model=ResetResponse, tags=["demo"])
def reset_demo(
    body: ResetRequest,
    principal: Annotated[DemoPrincipal, Depends(require_roles(DemoRole.ADMIN))],
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> ResetResponse | dict[str, Any]:
    payload_hash = _hash_payload(body)
    replay = _idempotency_replay(repository, "reset_demo", idempotency_key, payload_hash)
    if replay is not None:
        return replay
    if body.confirmation != RESET_CONFIRMATION:
        raise ApiError(
            422,
            "reset_confirmation_invalid",
            "Reset requires the exact synthetic-demo confirmation text.",
            field_errors={"confirmation": [f"Enter exactly {RESET_CONFIRMATION}."]},
        )
    counts = seed_database(repository.database, reset=True)
    response = ResetResponse(reset=True, confirmation=RESET_CONFIRMATION, counts=counts)
    encoded = response.model_dump(mode="json")
    repository.save_idempotency("reset_demo", idempotency_key, payload_hash, 200, encoded)
    return response


@router.get("/students/{student_id}/roadmap", response_model=Roadmap, tags=["students"])
def get_roadmap(
    student_id: str,
    principal: Annotated[DemoPrincipal, Depends(require_roles(DemoRole.STUDENT))],
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> Roadmap:
    _ensure_self(principal, student_id)
    student = repository.get_student(student_id)
    if student is None:
        raise _not_found("student")
    roadmap = repository.get_roadmap(student_id)
    if roadmap is None:
        try:
            roadmap = build_roadmap(repository, student)
        except RepositoryNotFound as exc:
            raise ApiError(409, "approved_outcome_required", str(exc)) from exc
    return roadmap


@router.patch("/roadmaps/{roadmap_id}/tasks/{task_id}", response_model=Roadmap, tags=["students"])
def patch_roadmap_task(
    roadmap_id: str,
    task_id: str,
    body: RoadmapTaskPatch,
    principal: Annotated[DemoPrincipal, Depends(require_roles(DemoRole.STUDENT))],
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> Roadmap:
    roadmap = repository.get_roadmap(principal.persona_id)
    if roadmap is None or roadmap.id != roadmap_id:
        raise _not_found("roadmap")
    found = False
    for task in roadmap.tasks:
        if task.id == task_id:
            task.complete = body.complete
            found = True
            break
    if not found:
        raise _not_found("roadmap task")
    roadmap.updated_at = utc_now()
    return repository.save_roadmap(roadmap)


@router.get("/students/{student_id}/outreach", response_model=OutreachDraft, tags=["students"])
def get_outreach(
    student_id: str,
    principal: Annotated[DemoPrincipal, Depends(require_roles(DemoRole.STUDENT))],
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> OutreachDraft:
    _ensure_self(principal, student_id)
    student = repository.get_student(student_id)
    if student is None:
        raise _not_found("student")
    draft = repository.get_outreach(student_id)
    if draft is None:
        try:
            draft = build_outreach(repository, student)
        except RepositoryNotFound as exc:
            raise ApiError(409, "approved_outcome_required", str(exc)) from exc
    return draft


@router.patch("/students/{student_id}/outreach", response_model=OutreachDraft, tags=["students"])
def patch_outreach(
    student_id: str,
    body: OutreachPatch,
    principal: Annotated[DemoPrincipal, Depends(require_roles(DemoRole.STUDENT))],
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> OutreachDraft:
    draft = get_outreach(student_id, principal, repository)
    if body.subject is not None:
        draft.subject = body.subject
    if body.edited_body is not None:
        draft.edited_body = body.edited_body
    draft.updated_at = utc_now()
    return repository.save_outreach(draft)


@router.get("/students/{student_id}/outreach.txt", tags=["students"])
def download_outreach(
    student_id: str,
    principal: Annotated[DemoPrincipal, Depends(require_roles(DemoRole.STUDENT))],
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> PlainTextResponse:
    draft = get_outreach(student_id, principal, repository)
    content = f"Subject: {draft.subject}\n\n{draft.edited_body}\n\n{draft.notice}\n"
    return PlainTextResponse(
        content,
        headers={"Content-Disposition": f'attachment; filename="{student_id}-outreach.txt"'},
    )
