from __future__ import annotations

import hashlib
import time
from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from ortools.sat.python import cp_model

from backend.app.domain.models import (
    Assignment,
    OptimizationResult,
    PairScore,
    Project,
    SolverStage,
)

SOLVER_SEED = 731
MAX_SCORE_BP = 10000


def tie_digest(student_id: str, project_id: str, seed: int = SOLVER_SEED) -> str:
    value = f"rb-tie-v1|{seed}|{student_id}|{project_id}".encode()
    return hashlib.sha256(value).hexdigest()


def _elapsed_ms(start: float) -> Decimal:
    return Decimal(str((time.monotonic() - start) * 1000)).quantize(
        Decimal("0.001"), rounding=ROUND_HALF_UP
    )


def _status_name(status: int) -> str:
    return {
        cp_model.OPTIMAL: "optimal",
        cp_model.FEASIBLE: "feasible_not_proven",
        cp_model.INFEASIBLE: "infeasible",
        cp_model.MODEL_INVALID: "model_invalid",
        cp_model.UNKNOWN: "unknown",
    }.get(status, f"solver_status_{status}")


def _new_solver(timeout_seconds: float, seed: int) -> cp_model.CpSolver:
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = timeout_seconds
    solver.parameters.random_seed = seed
    solver.parameters.num_search_workers = 1
    solver.parameters.randomize_search = False
    return solver


def _build_model(
    edge_scores: dict[tuple[str, str], int],
    capacities: dict[str, int],
    *,
    fixed: dict[tuple[str, str], int] | None = None,
    count_equals: int | None = None,
    total_equals: int | None = None,
    floor_equals: int | None = None,
    objective: Literal["count", "total", "floor", "none"] = "none",
) -> tuple[cp_model.CpModel, dict[tuple[str, str], cp_model.IntVar], cp_model.IntVar | None]:
    model = cp_model.CpModel()
    variables = {
        key: model.new_bool_var(f"x__{key[0]}__{key[1]}") for key in sorted(edge_scores)
    }
    student_ids = sorted({student_id for student_id, _ in edge_scores})
    project_ids = sorted({project_id for _, project_id in edge_scores})
    for student_id in student_ids:
        model.add(
            sum(variable for (sid, _), variable in variables.items() if sid == student_id) <= 1
        )
    for project_id in project_ids:
        model.add(
            sum(variable for (_, pid), variable in variables.items() if pid == project_id)
            <= capacities.get(project_id, 0)
        )
    for key, value in (fixed or {}).items():
        model.add(variables[key] == value)

    count_expression = sum(variables.values())
    total_expression = sum(edge_scores[key] * variable for key, variable in variables.items())
    if count_equals is not None:
        model.add(count_expression == count_equals)
    if total_equals is not None:
        model.add(total_expression == total_equals)

    floor_variable: cp_model.IntVar | None = None
    if objective == "floor" or floor_equals is not None:
        floor_variable = model.new_int_var(0, MAX_SCORE_BP, "minimum_assigned_score")
        for key, variable in variables.items():
            model.add(floor_variable <= edge_scores[key] + MAX_SCORE_BP * (1 - variable))
        if floor_equals is not None:
            model.add(floor_variable == floor_equals)

    if objective == "count":
        model.maximize(count_expression)
    elif objective == "total":
        model.maximize(total_expression)
    elif objective == "floor":
        assert floor_variable is not None
        model.maximize(floor_variable)
    return model, variables, floor_variable


def _selected(
    solver: cp_model.CpSolver, variables: dict[tuple[str, str], cp_model.IntVar]
) -> list[tuple[str, str]]:
    return sorted(key for key, variable in variables.items() if solver.value(variable) == 1)


def derive_unplaced_reasons(
    student_ids: Iterable[str],
    pair_scores: Iterable[PairScore],
    assignments: Iterable[Assignment],
    threshold_bp: int,
) -> dict[str, list[str]]:
    pairs_by_student: dict[str, list[PairScore]] = {student_id: [] for student_id in student_ids}
    for pair in pair_scores:
        pairs_by_student.setdefault(pair.student_id, []).append(pair)
    assigned_ids = {assignment.student_id for assignment in assignments}
    result: dict[str, list[str]] = {}
    for student_id in sorted(pairs_by_student):
        if student_id in assigned_ids:
            continue
        pairs = pairs_by_student[student_id]
        codes: list[str] = []
        if any(
            reason.resolution == "unresolved"
            for pair in pairs
            for reason in pair.eligibility_reasons
        ):
            codes.append("missing_data")
        eligible = [pair for pair in pairs if pair.eligible]
        if not eligible:
            codes.append("no_eligible_projects")
        elif not any(pair.total_bp >= threshold_bp for pair in eligible):
            codes.append("below_threshold")
        else:
            codes.append("capacity_competition")
        result[student_id] = codes
    return result


def optimize_pair_scores(
    pair_scores: list[PairScore],
    projects: Iterable[Project],
    student_ids: Iterable[str],
    threshold_bp: int,
    *,
    timeout_seconds: float = 10.0,
    seed: int = SOLVER_SEED,
) -> OptimizationResult:
    overall_start = time.monotonic()
    capacities = {project.id: project.capacity for project in projects}
    edge_scores = {
        (pair.student_id, pair.project_id): pair.total_bp
        for pair in pair_scores
        if pair.eligible and pair.total_bp >= threshold_bp
    }
    sorted_students = sorted(set(student_ids))
    stages: list[SolverStage] = []

    if not edge_scores:
        stage_start = time.monotonic()
        stages.append(
            SolverStage(
                name="optimizing_coverage",
                status="optimal",
                runtime_ms=_elapsed_ms(stage_start),
                objective=0,
                detail="No eligible pair met the configured threshold.",
            )
        )
        stages.append(
            SolverStage(
                name="optimizing_quality",
                status="optimal",
                runtime_ms=Decimal("0.000"),
                objective=0,
            )
        )
        assignments: list[Assignment] = []
        return OptimizationResult(
            assignments=assignments,
            unplaced_reasons=derive_unplaced_reasons(
                sorted_students, pair_scores, assignments, threshold_bp
            ),
            status="optimal",
            proven_optimal=True,
            placement_count=0,
            total_score_bp=0,
            minimum_score_bp=None,
            runtime_ms=_elapsed_ms(overall_start),
            stages=stages,
            solver_seed=seed,
            worker_count=1,
        )

    # Stage 1: maximize assignment count.
    stage_start = time.monotonic()
    model, variables, _ = _build_model(edge_scores, capacities, objective="count")
    solver = _new_solver(timeout_seconds, seed)
    status = solver.solve(model)
    stage_status = _status_name(status)
    count_value = int(solver.objective_value) if status in (cp_model.OPTIMAL, cp_model.FEASIBLE) else 0
    stages.append(
        SolverStage(
            name="optimizing_coverage",
            status=stage_status,
            runtime_ms=_elapsed_ms(stage_start),
            objective=count_value if status in (cp_model.OPTIMAL, cp_model.FEASIBLE) else None,
        )
    )
    if status != cp_model.OPTIMAL:
        selected = _selected(solver, variables) if status == cp_model.FEASIBLE else []
        return _partial_result(
            selected,
            edge_scores,
            pair_scores,
            sorted_students,
            threshold_bp,
            stages,
            overall_start,
            seed,
            "Coverage optimum was not proven; later lexicographic stages were skipped.",
        )

    # Stage 2: hold count and maximize total compatibility.
    stage_start = time.monotonic()
    model, variables, _ = _build_model(
        edge_scores, capacities, count_equals=count_value, objective="total"
    )
    solver = _new_solver(timeout_seconds, seed)
    status = solver.solve(model)
    stage_status = _status_name(status)
    total_value = int(solver.objective_value) if status in (cp_model.OPTIMAL, cp_model.FEASIBLE) else 0
    stages.append(
        SolverStage(
            name="optimizing_quality",
            status=stage_status,
            runtime_ms=_elapsed_ms(stage_start),
            objective=total_value if status in (cp_model.OPTIMAL, cp_model.FEASIBLE) else None,
        )
    )
    if status != cp_model.OPTIMAL:
        selected = _selected(solver, variables) if status == cp_model.FEASIBLE else []
        return _partial_result(
            selected,
            edge_scores,
            pair_scores,
            sorted_students,
            threshold_bp,
            stages,
            overall_start,
            seed,
            "Total-score optimum was not proven; later lexicographic stages were skipped.",
        )

    # Stage 3: hold count and total, then maximize the worst selected score.
    stage_start = time.monotonic()
    model, variables, floor_variable = _build_model(
        edge_scores,
        capacities,
        count_equals=count_value,
        total_equals=total_value,
        objective="floor",
    )
    solver = _new_solver(timeout_seconds, seed)
    status = solver.solve(model)
    stage_status = _status_name(status)
    floor_value = (
        int(solver.value(floor_variable))
        if floor_variable is not None and status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
        else None
    )
    stages.append(
        SolverStage(
            name="optimizing_floor",
            status=stage_status,
            runtime_ms=_elapsed_ms(stage_start),
            objective=floor_value,
        )
    )
    if status != cp_model.OPTIMAL:
        selected = _selected(solver, variables) if status == cp_model.FEASIBLE else []
        return _partial_result(
            selected,
            edge_scores,
            pair_scores,
            sorted_students,
            threshold_bp,
            stages,
            overall_start,
            seed,
            "Minimum-score optimum was not proven; deterministic tie fixing was skipped.",
        )
    fallback_selected = _selected(solver, variables)

    # Stage 4: sequentially fix every remaining binary edge in seeded digest order.
    tie_start = time.monotonic()
    tie_order = sorted(edge_scores, key=lambda key: (tie_digest(*key, seed), key[0], key[1]))
    fixed: dict[tuple[str, str], int] = {}
    selected_students: set[str] = set()
    selected_project_counts: dict[str, int] = {}
    unresolved_status: str | None = None
    for key in tie_order:
        student_id, project_id = key
        if len(selected_students) == count_value:
            fixed[key] = 0
            continue
        if student_id in selected_students:
            fixed[key] = 0
            continue
        if selected_project_counts.get(project_id, 0) >= capacities.get(project_id, 0):
            fixed[key] = 0
            continue
        trial_fixed = {**fixed, key: 1}
        model, trial_variables, _ = _build_model(
            edge_scores,
            capacities,
            fixed=trial_fixed,
            count_equals=count_value,
            total_equals=total_value,
            floor_equals=floor_value,
        )
        trial_solver = _new_solver(timeout_seconds, seed)
        trial_status = trial_solver.solve(model)
        if trial_status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            fixed[key] = 1
            selected_students.add(student_id)
            selected_project_counts[project_id] = selected_project_counts.get(project_id, 0) + 1
        elif trial_status == cp_model.INFEASIBLE:
            fixed[key] = 0
        else:
            unresolved_status = _status_name(trial_status)
            break

    if unresolved_status is not None:
        stages.append(
            SolverStage(
                name="resolving_ties",
                status=unresolved_status,
                runtime_ms=_elapsed_ms(tie_start),
                detail="A feasibility check timed out before every tie variable was fixed.",
            )
        )
        return _partial_result(
            fallback_selected,
            edge_scores,
            pair_scores,
            sorted_students,
            threshold_bp,
            stages,
            overall_start,
            seed,
            "Canonical tie fixing was not completed within the configured stage limit.",
        )

    chosen = sorted(key for key, value in fixed.items() if value == 1)
    stages.append(
        SolverStage(
            name="resolving_ties",
            status="optimal",
            runtime_ms=_elapsed_ms(tie_start),
            objective=len(chosen),
            detail=f"Fixed {len(edge_scores)} canonical binary decisions.",
        )
    )
    assignments = _assignments(chosen, edge_scores, tie_order)
    return OptimizationResult(
        assignments=assignments,
        unplaced_reasons=derive_unplaced_reasons(
            sorted_students, pair_scores, assignments, threshold_bp
        ),
        status="optimal",
        proven_optimal=True,
        placement_count=len(assignments),
        total_score_bp=sum(item.score_bp for item in assignments),
        minimum_score_bp=min((item.score_bp for item in assignments), default=None),
        runtime_ms=_elapsed_ms(overall_start),
        stages=stages,
        solver_seed=seed,
        worker_count=1,
    )


def _assignments(
    selected: Iterable[tuple[str, str]],
    edge_scores: dict[tuple[str, str], int],
    tie_order: list[tuple[str, str]],
) -> list[Assignment]:
    order = {key: index + 1 for index, key in enumerate(tie_order)}
    return [
        Assignment(
            student_id=student_id,
            project_id=project_id,
            score_bp=edge_scores[(student_id, project_id)],
            compatibility_index=(Decimal(edge_scores[(student_id, project_id)]) / Decimal(100)).quantize(
                Decimal("0.01")
            ),
            canonical_tie_order=order[(student_id, project_id)],
            global_rationale=(
                "The cohort-wide optimizer selected this edge after maximizing placement count, "
                "total compatibility, the minimum assigned compatibility, and canonical seeded ties."
            ),
        )
        for student_id, project_id in sorted(selected)
    ]


def _partial_result(
    selected: list[tuple[str, str]],
    edge_scores: dict[tuple[str, str], int],
    pair_scores: list[PairScore],
    student_ids: list[str],
    threshold_bp: int,
    stages: list[SolverStage],
    overall_start: float,
    seed: int,
    limitation: str,
) -> OptimizationResult:
    tie_order = sorted(edge_scores, key=lambda key: (tie_digest(*key, seed), key[0], key[1]))
    assignments = _assignments(selected, edge_scores, tie_order)
    return OptimizationResult(
        assignments=assignments,
        unplaced_reasons=derive_unplaced_reasons(
            student_ids, pair_scores, assignments, threshold_bp
        ),
        status="feasible_not_proven" if assignments else "failed",
        proven_optimal=False,
        placement_count=len(assignments),
        total_score_bp=sum(item.score_bp for item in assignments),
        minimum_score_bp=min((item.score_bp for item in assignments), default=None),
        runtime_ms=_elapsed_ms(overall_start),
        stages=stages,
        solver_seed=seed,
        worker_count=1,
        optimality_limitation=limitation,
    )
