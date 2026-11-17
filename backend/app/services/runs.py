from __future__ import annotations

import hashlib
import json
import time
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from backend.app.config import Settings
from backend.app.domain.models import (
    Assignment,
    MatchConfig,
    MatchRun,
    PairScore,
    RunComparison,
    RunStatus,
    SolverStage,
    utc_now,
)
from backend.app.repositories.sqlite import SQLiteRepository, stable_runtime_id
from backend.app.services.evaluation import evaluate_strategies
from backend.app.services.optimizer import optimize_pair_scores
from backend.app.services.scoring import score_matrix
from backend.app.services.taxonomy import Taxonomy


def _ms(start: float) -> Decimal:
    return Decimal(str((time.monotonic() - start) * 1000)).quantize(
        Decimal("0.001"), rounding=ROUND_HALF_UP
    )


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def create_match_run(
    repository: SQLiteRepository,
    settings: Settings,
    config: MatchConfig | None = None,
) -> MatchRun:
    overall_start = time.monotonic()
    now = utc_now()
    run_id = stable_runtime_id("run")
    selected_config = config or repository.get_config()
    stages: list[SolverStage] = []

    validate_start = time.monotonic()
    students = repository.list_students(submitted_only=True)
    projects = repository.list_projects()
    skills = repository.list_skills()
    student_ids = {student.id for student in students}
    project_ids = {project.id for project in projects}
    if len(student_ids) != len(students) or len(project_ids) != len(projects):
        raise ValueError("complete cohort validation found duplicate stable identifiers")
    skill_ids = {skill.id for skill in skills}
    invalid_references = [
        f"{project.id}:{relation.skill_id}"
        for project in projects
        for relation in project.skills
        if relation.skill_id not in skill_ids
    ]
    if invalid_references:
        raise ValueError(f"project skill references are invalid: {invalid_references}")
    stages.append(
        SolverStage(
            name="validating",
            status="completed",
            runtime_ms=_ms(validate_start),
            objective=len(students),
            detail=(
                f"Validated {len(students)} submitted synthetic students and "
                f"{len(projects)} project records before optimization."
            ),
        )
    )

    input_snapshot = {
        "schema_version": "1.0",
        "synthetic_only": True,
        "students": [student.model_dump(mode="json") for student in students],
        "projects": [project.model_dump(mode="json") for project in projects],
        "skills": [skill.model_dump(mode="json") for skill in skills],
    }
    input_hash = hashlib.sha256(_canonical_json(input_snapshot).encode()).hexdigest()

    scoring_start = time.monotonic()
    taxonomy = Taxonomy(skills, version=selected_config.taxonomy_version)
    pair_scores = score_matrix(students, projects, selected_config, taxonomy)
    pair_scores = [pair.model_copy(update={"run_id": run_id}) for pair in pair_scores]
    stages.append(
        SolverStage(
            name="scoring",
            status="completed",
            runtime_ms=_ms(scoring_start),
            objective=len(pair_scores),
            detail="Calculated separate eligibility and compatibility records for every pair.",
        )
    )

    result = optimize_pair_scores(
        pair_scores,
        projects,
        [student.id for student in students],
        selected_config.threshold_bp,
        timeout_seconds=settings.solver_timeout_seconds,
        seed=selected_config.solver_seed,
    )
    stages.extend(result.stages)
    assignments = _explain_assignments(result.assignments, pair_scores)
    assignments = [item.model_copy(update={"run_id": run_id}) for item in assignments]

    evaluation_start = time.monotonic()
    benchmark = evaluate_strategies(
        students,
        projects,
        pair_scores,
        assignments,
        selected_config.threshold_bp,
        result.runtime_ms,
        timeout_seconds=settings.solver_timeout_seconds,
    )
    stages.append(
        SolverStage(
            name="evaluating",
            status="completed",
            runtime_ms=_ms(evaluation_start),
            objective=len(benchmark.strategies),
            detail="Computed global, greedy, and first-come-first-served synthetic evidence.",
        )
    )
    utilization = {
        project.id: {
            "assigned": sum(item.project_id == project.id for item in assignments),
            "capacity": project.capacity,
        }
        for project in projects
    }
    result_snapshot = {
        "assignments": [assignment.model_dump(mode="json") for assignment in assignments],
        "unplaced_reasons": result.unplaced_reasons,
        "project_utilization": utilization,
        "compatibility_label": "compatibility index — not an acceptance probability",
    }
    run = MatchRun(
        id=run_id,
        status=RunStatus.PROPOSED if result.status != "failed" else RunStatus.FAILED,
        stale=False,
        config_snapshot=selected_config.model_dump(mode="json"),
        input_snapshot_hash=input_hash,
        input_snapshot=input_snapshot,
        result_snapshot=result_snapshot,
        stage_evidence=stages,
        benchmark_evidence=benchmark,
        runtime_ms=_ms(overall_start),
        placement_count=len(assignments),
        total_score_bp=sum(item.score_bp for item in assignments),
        minimum_score_bp=min((item.score_bp for item in assignments), default=None),
        solver_seed=selected_config.solver_seed,
        worker_count=selected_config.worker_count,
        score_version=selected_config.score_version,
        optimality_limitation=result.optimality_limitation,
        created_at=now,
        updated_at=now,
    )
    repository.save_run(run, pair_scores, assignments)
    return run


def _explain_assignments(
    assignments: list[Assignment], pair_scores: list[PairScore]
) -> list[Assignment]:
    candidates: dict[str, list[PairScore]] = {}
    for pair in pair_scores:
        if pair.eligible:
            candidates.setdefault(pair.student_id, []).append(pair)
    result: list[Assignment] = []
    for assignment in assignments:
        ranked = sorted(
            candidates.get(assignment.student_id, []),
            key=lambda pair: (-pair.total_bp, pair.project_id),
        )
        highest = ranked[0].project_id if ranked else None
        if highest is not None and highest != assignment.project_id:
            rationale = (
                "This differs from the student's highest independent recommendation because "
                "limited capacity was allocated across the whole cohort to maximize placement "
                "count before compatibility quality. No other student's details are disclosed."
            )
        else:
            rationale = (
                "This is the student's highest-scoring feasible independent recommendation and "
                "also satisfies the cohort-wide capacity objectives."
            )
        result.append(assignment.model_copy(update={"global_rationale": rationale}))
    return result


def compare_runs(first: MatchRun, second: MatchRun) -> RunComparison:
    first_outcomes = {
        item["student_id"]: item.get("project_id")
        for item in first.result_snapshot.get("assignments", [])
    }
    second_outcomes = {
        item["student_id"]: item.get("project_id")
        for item in second.result_snapshot.get("assignments", [])
    }
    changed = [
        {
            "student_id": student_id,
            "run_project_id": first_outcomes.get(student_id),
            "other_run_project_id": second_outcomes.get(student_id),
        }
        for student_id in sorted(set(first_outcomes) | set(second_outcomes))
        if first_outcomes.get(student_id) != second_outcomes.get(student_id)
    ]
    config_differences = {
        key: {"run": first.config_snapshot.get(key), "other": second.config_snapshot.get(key)}
        for key in sorted(set(first.config_snapshot) | set(second.config_snapshot))
        if first.config_snapshot.get(key) != second.config_snapshot.get(key)
    }
    return RunComparison(
        run_id=first.id,
        other_run_id=second.id,
        placement_count_difference=first.placement_count - second.placement_count,
        total_score_bp_difference=first.total_score_bp - second.total_score_bp,
        changed_outcomes=changed,
        configuration_differences=config_differences,
    )
