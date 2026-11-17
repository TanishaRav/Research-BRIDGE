from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from statistics import median
from typing import Any

from backend.app.domain.models import (
    Assignment,
    BenchmarkEvidence,
    PairScore,
    Project,
    ShuffleEvidence,
    StrategyMetrics,
    Student,
)
from backend.app.services.optimizer import (
    derive_unplaced_reasons,
    optimize_pair_scores,
    tie_digest,
)


@dataclass(frozen=True)
class _Capacity:
    id: str
    capacity: int


def _milliseconds(start: float) -> Decimal:
    return Decimal(str((time.monotonic() - start) * 1000)).quantize(
        Decimal("0.001"), rounding=ROUND_HALF_UP
    )


def _assignment(
    student_id: str, project_id: str, score_bp: int, tie_order: int
) -> Assignment:
    return Assignment(
        student_id=student_id,
        project_id=project_id,
        score_bp=score_bp,
        compatibility_index=(Decimal(score_bp) / Decimal(100)).quantize(Decimal("0.01")),
        canonical_tie_order=tie_order,
        global_rationale="Baseline simulation assignment; not an approved placement.",
    )


def fcfs_allocate(
    students: list[Student],
    projects: list[Project],
    pair_scores: list[PairScore],
    threshold_bp: int,
) -> tuple[list[Assignment], Decimal]:
    start = time.monotonic()
    remaining = {project.id: project.capacity for project in projects}
    by_student: dict[str, list[PairScore]] = {}
    for pair in pair_scores:
        if pair.eligible and pair.total_bp >= threshold_bp:
            by_student.setdefault(pair.student_id, []).append(pair)
    assignments: list[Assignment] = []
    order = 0
    for student in sorted(students, key=lambda item: (item.synthetic_submission_order, item.id)):
        options = sorted(
            by_student.get(student.id, []), key=lambda item: (-item.total_bp, item.project_id)
        )
        selected = next((pair for pair in options if remaining.get(pair.project_id, 0) > 0), None)
        if selected is None:
            continue
        order += 1
        remaining[selected.project_id] -= 1
        assignments.append(
            _assignment(student.id, selected.project_id, selected.total_bp, order)
        )
    return assignments, _milliseconds(start)


def greedy_allocate(
    projects: list[Project], pair_scores: list[PairScore], threshold_bp: int
) -> tuple[list[Assignment], Decimal]:
    start = time.monotonic()
    remaining = {project.id: project.capacity for project in projects}
    used_students: set[str] = set()
    edges = sorted(
        (
            pair
            for pair in pair_scores
            if pair.eligible and pair.total_bp >= threshold_bp
        ),
        key=lambda item: (
            -item.total_bp,
            tie_digest(item.student_id, item.project_id),
            item.student_id,
            item.project_id,
        ),
    )
    assignments: list[Assignment] = []
    for order, pair in enumerate(edges, start=1):
        if pair.student_id in used_students or remaining.get(pair.project_id, 0) <= 0:
            continue
        used_students.add(pair.student_id)
        remaining[pair.project_id] -= 1
        assignments.append(
            _assignment(pair.student_id, pair.project_id, pair.total_bp, order)
        )
    return sorted(assignments, key=lambda item: item.student_id), _milliseconds(start)


def _rate(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return (Decimal(numerator) / Decimal(denominator)).quantize(
        Decimal("0.0001"), rounding=ROUND_HALF_UP
    )


def _constraint_violations(
    assignments: list[Assignment],
    projects: list[Project],
    pair_scores: list[PairScore],
    threshold_bp: int,
) -> dict[str, int]:
    student_ids = [assignment.student_id for assignment in assignments]
    duplicate_students = len(student_ids) - len(set(student_ids))
    capacity = {project.id: project.capacity for project in projects}
    counts: dict[str, int] = {}
    for assignment in assignments:
        counts[assignment.project_id] = counts.get(assignment.project_id, 0) + 1
    capacity_violations = sum(max(0, count - capacity.get(project_id, 0)) for project_id, count in counts.items())
    valid_edges = {
        (pair.student_id, pair.project_id)
        for pair in pair_scores
        if pair.eligible and pair.total_bp >= threshold_bp
    }
    eligibility_threshold = sum(
        (assignment.student_id, assignment.project_id) not in valid_edges
        for assignment in assignments
    )
    return {
        "duplicate_student": duplicate_students,
        "capacity": capacity_violations,
        "eligibility_or_threshold": eligibility_threshold,
        "total": duplicate_students + capacity_violations + eligibility_threshold,
    }


def calculate_metrics(
    strategy: str,
    label: str,
    students: list[Student],
    projects: list[Project],
    pair_scores: list[PairScore],
    assignments: list[Assignment],
    threshold_bp: int,
    runtime_ms: Decimal,
) -> StrategyMetrics:
    submitted = sorted(students, key=lambda item: item.id)
    eligible_ids = {
        pair.student_id
        for pair in pair_scores
        if pair.eligible and pair.total_bp >= threshold_bp
    }
    assigned_by_student = {assignment.student_id: assignment for assignment in assignments}
    scores = sorted(Decimal(assignment.score_bp) / Decimal(100) for assignment in assignments)
    mean_score = (
        (sum(scores, Decimal(0)) / Decimal(len(scores))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if scores
        else None
    )
    median_score = Decimal(str(median(scores))).quantize(Decimal("0.01")) if scores else None
    bottom_decile = scores[math.ceil(Decimal("0.10") * len(scores)) - 1] if scores else None

    student_map = {student.id: student for student in submitted}
    top_choice_denominator = 0
    top_choice_count = 0
    for assignment in assignments:
        student = student_map.get(assignment.student_id)
        if student is None or not student.preferences:
            continue
        top_choice_denominator += 1
        if any(
            preference.rank == 1 and preference.project_id == assignment.project_id
            for preference in student.preferences
        ):
            top_choice_count += 1

    first_time_students = [student for student in submitted if student.first_time_researcher]
    first_time_placed = sum(student.id in assigned_by_student for student in first_time_students)
    major_rates: dict[str, dict[str, Any]] = {}
    for major in sorted({student.major for student in submitted}):
        members = [student for student in submitted if student.major == major]
        placed = sum(student.id in assigned_by_student for student in members)
        major_rates[major] = {
            "placed": placed,
            "denominator": len(members),
            "rate": _rate(placed, len(members)),
            "small_group_warning": len(members) < 5,
        }

    unplaced = derive_unplaced_reasons(
        [student.id for student in submitted], pair_scores, assignments, threshold_bp
    )
    return StrategyMetrics(
        strategy=strategy,
        label=label,
        placement_count=len(assignments),
        submitted_count=len(submitted),
        eligible_count=len(eligible_ids),
        placement_rate_submitted=_rate(len(assignments), len(submitted)) or Decimal(0),
        placement_rate_eligible=_rate(len(assignments), len(eligible_ids)),
        mean_score=mean_score,
        median_score=median_score,
        bottom_decile_score=bottom_decile,
        minimum_score=min(scores) if scores else None,
        top_choice_count=top_choice_count,
        top_choice_denominator=top_choice_denominator,
        top_choice_rate=_rate(top_choice_count, top_choice_denominator),
        first_time_placed=first_time_placed,
        first_time_denominator=len(first_time_students),
        first_time_placement_rate=_rate(first_time_placed, len(first_time_students)),
        major_rates=major_rates,
        unplaced_count=len(submitted) - len(assignments),
        unplaced_reasons=unplaced,
        constraint_violations=_constraint_violations(
            assignments, projects, pair_scores, threshold_bp
        ),
        runtime_ms=runtime_ms,
    )


def _minimal_pair(student_id: str, project_id: str, score_bp: int) -> PairScore:
    return PairScore(
        student_id=student_id,
        project_id=project_id,
        eligible=True,
        factor_scores_bp={"interest": score_bp},
        raw_weights={"interest": "1"},
        normalized_weights={"interest": "1"},
        contributions_bp={"interest": score_bp},
        evidence={},
        gaps=[],
        missing_fields=[],
        total_bp=score_bp,
        compatibility_index=Decimal(score_bp) / Decimal(100),
        config_snapshot={},
    )


def counterexample_evidence(timeout_seconds: float = 10.0) -> dict[str, Any]:
    pairs = [
        _minimal_pair("counter-a", "counter-p1", 9500),
        _minimal_pair("counter-a", "counter-p2", 9000),
        _minimal_pair("counter-b", "counter-p1", 9400),
    ]
    projects = [_Capacity("counter-p1", 1), _Capacity("counter-p2", 1)]
    # Highest-edge greedy deliberately demonstrates the specified failure.
    remaining = {project.id: project.capacity for project in projects}
    used: set[str] = set()
    greedy: list[tuple[str, str]] = []
    for pair in sorted(pairs, key=lambda item: (-item.total_bp, item.student_id, item.project_id)):
        if pair.student_id not in used and remaining[pair.project_id] > 0:
            greedy.append((pair.student_id, pair.project_id))
            used.add(pair.student_id)
            remaining[pair.project_id] -= 1
    global_result = optimize_pair_scores(
        pairs,
        projects,  # type: ignore[arg-type]
        ["counter-a", "counter-b"],
        0,
        timeout_seconds=timeout_seconds,
    )
    return {
        "description": (
            "A has P1=95 and P2=90; B has only P1=94. Greedy selects A→P1, "
            "while count-first global allocation places both."
        ),
        "greedy_assignments": greedy,
        "greedy_placement_count": len(greedy),
        "global_assignments": [
            (assignment.student_id, assignment.project_id)
            for assignment in global_result.assignments
        ],
        "global_placement_count": global_result.placement_count,
        "global_proven_optimal": global_result.proven_optimal,
    }


def evaluate_strategies(
    students: list[Student],
    projects: list[Project],
    pair_scores: list[PairScore],
    global_assignments: list[Assignment],
    threshold_bp: int,
    global_runtime_ms: Decimal,
    *,
    timeout_seconds: float = 10.0,
) -> BenchmarkEvidence:
    fcfs_assignments, fcfs_runtime = fcfs_allocate(students, projects, pair_scores, threshold_bp)
    greedy_assignments, greedy_runtime = greedy_allocate(projects, pair_scores, threshold_bp)
    strategies = {
        "global": calculate_metrics(
            "global",
            "Cohort-wide lexicographic allocation",
            students,
            projects,
            pair_scores,
            global_assignments,
            threshold_bp,
            global_runtime_ms,
        ),
        "greedy": calculate_metrics(
            "greedy",
            "Greedy highest-score allocation",
            students,
            projects,
            pair_scores,
            greedy_assignments,
            threshold_bp,
            greedy_runtime,
        ),
        "fcfs": calculate_metrics(
            "fcfs",
            "First-come-first-served synthetic simulation",
            students,
            projects,
            pair_scores,
            fcfs_assignments,
            threshold_bp,
            fcfs_runtime,
        ),
    }
    return BenchmarkEvidence(
        strategies=strategies,
        counterexample=counterexample_evidence(timeout_seconds=timeout_seconds),
    )


def run_shuffle_test(
    students: list[Student],
    projects: list[Project],
    pair_scores: list[PairScore],
    threshold_bp: int,
    reference_assignments: list[Assignment],
    *,
    timeout_seconds: float = 10.0,
) -> ShuffleEvidence:
    reference = sorted(
        (assignment.student_id, assignment.project_id) for assignment in reference_assignments
    )
    failing: list[int] = []
    for seed in range(1, 21):
        rng = random.Random(seed)
        shuffled_students = list(students)
        shuffled_projects = list(projects)
        shuffled_pairs = list(pair_scores)
        rng.shuffle(shuffled_students)
        rng.shuffle(shuffled_projects)
        rng.shuffle(shuffled_pairs)
        result = optimize_pair_scores(
            shuffled_pairs,
            shuffled_projects,
            [student.id for student in shuffled_students],
            threshold_bp,
            timeout_seconds=timeout_seconds,
        )
        actual = sorted(
            (assignment.student_id, assignment.project_id) for assignment in result.assignments
        )
        if actual != reference:
            failing.append(seed)
    return ShuffleEvidence(
        identical_assignment_pass_count=20 - len(failing),
        seeds=list(range(1, 21)),
        failing_seeds=failing,
        reference_assignments=reference,
    )
