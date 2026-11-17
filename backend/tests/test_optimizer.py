from __future__ import annotations

import itertools
import random
from dataclasses import dataclass
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from backend.app.domain.models import Assignment, PairScore
from backend.app.seed.generator import generate_snapshot
from backend.app.services.evaluation import (
    calculate_metrics,
    counterexample_evidence,
    greedy_allocate,
    run_shuffle_test,
)
from backend.app.services.optimizer import optimize_pair_scores
from backend.app.services.scoring import score_matrix
from backend.app.services.taxonomy import Taxonomy
from backend.app.domain.models import MatchConfig


@dataclass(frozen=True)
class Capacity:
    id: str
    capacity: int


def pair(student_id: str, project_id: str, score: int, eligible: bool = True) -> PairScore:
    return PairScore(
        student_id=student_id,
        project_id=project_id,
        eligible=eligible,
        factor_scores_bp={"interest": score},
        raw_weights={"interest": "1"},
        normalized_weights={"interest": "1"},
        contributions_bp={"interest": score},
        evidence={},
        gaps=[],
        missing_fields=[],
        total_bp=score,
        compatibility_index=Decimal(score) / 100,
        config_snapshot={},
    )


def test_two_student_counterexample_places_two_globally_and_one_greedily():
    evidence = counterexample_evidence(timeout_seconds=2)
    assert evidence["greedy_placement_count"] == 1
    assert evidence["global_placement_count"] == 2
    assert sorted(evidence["global_assignments"]) == [
        ("counter-a", "counter-p2"),
        ("counter-b", "counter-p1"),
    ]
    assert evidence["global_proven_optimal"] is True


def test_empty_instance_is_optimal_and_allows_unplaced():
    result = optimize_pair_scores([], [], ["s1", "s2"], 6000, timeout_seconds=1)
    assert result.proven_optimal
    assert result.assignments == []
    assert result.placement_count == 0
    assert result.unplaced_reasons == {
        "s1": ["no_eligible_projects"],
        "s2": ["no_eligible_projects"],
    }


def test_threshold_excludes_below_threshold_edge():
    pairs = [pair("s1", "p1", 5999), pair("s1", "p2", 6000)]
    result = optimize_pair_scores(
        pairs, [Capacity("p1", 1), Capacity("p2", 1)], ["s1"], 6000, timeout_seconds=1
    )
    assert [(item.student_id, item.project_id) for item in result.assignments] == [("s1", "p2")]


def test_ineligible_and_no_capacity_edges_are_never_selected():
    pairs = [pair("s1", "p1", 9000, eligible=False), pair("s1", "p2", 9000)]
    result = optimize_pair_scores(
        pairs, [Capacity("p1", 1), Capacity("p2", 0)], ["s1"], 0, timeout_seconds=1
    )
    assert not result.assignments
    assert result.unplaced_reasons["s1"] == ["no_eligible_projects"] or result.unplaced_reasons["s1"] == ["capacity_competition"]


def test_score_ties_are_deterministic_under_reversed_input():
    pairs = [
        pair("s1", "p1", 8000),
        pair("s1", "p2", 8000),
        pair("s2", "p1", 8000),
        pair("s2", "p2", 8000),
    ]
    projects = [Capacity("p1", 1), Capacity("p2", 1)]
    first = optimize_pair_scores(pairs, projects, ["s1", "s2"], 0, timeout_seconds=2)
    second = optimize_pair_scores(
        list(reversed(pairs)), list(reversed(projects)), ["s2", "s1"], 0, timeout_seconds=2
    )
    first_edges = {(item.student_id, item.project_id) for item in first.assignments}
    second_edges = {(item.student_id, item.project_id) for item in second.assignments}
    assert first_edges == second_edges
    assert first.proven_optimal and second.proven_optimal


def _brute_objective(
    pairs: list[PairScore], capacities: list[Capacity], students: list[str], threshold: int
) -> tuple[int, int, int | None]:
    valid = {
        (item.student_id, item.project_id): item.total_bp
        for item in pairs
        if item.eligible and item.total_bp >= threshold
    }
    projects = [item.id for item in capacities]
    capacity = {item.id: item.capacity for item in capacities}
    best: tuple[int, int, int] = (-1, -1, -1)
    for choices in itertools.product([None, *projects], repeat=len(students)):
        counts = {project_id: choices.count(project_id) for project_id in projects}
        if any(counts[project_id] > capacity[project_id] for project_id in projects):
            continue
        selected_scores: list[int] = []
        feasible = True
        for student_id, project_id in zip(students, choices, strict=True):
            if project_id is None:
                continue
            score = valid.get((student_id, project_id))
            if score is None:
                feasible = False
                break
            selected_scores.append(score)
        if not feasible:
            continue
        objective = (
            len(selected_scores),
            sum(selected_scores),
            min(selected_scores) if selected_scores else -1,
        )
        best = max(best, objective)
    return best[0], best[1], None if best[2] == -1 else best[2]


def test_optimizer_matches_brute_force_lexicographic_objectives():
    rng = random.Random(731)
    students = ["s1", "s2", "s3"]
    projects = [Capacity("p1", 1), Capacity("p2", 2)]
    for _ in range(12):
        pairs = [
            pair(student_id, project.id, rng.randint(5000, 9500), rng.choice([True, True, False]))
            for student_id in students
            for project in projects
        ]
        expected = _brute_objective(pairs, projects, students, 6000)
        actual = optimize_pair_scores(pairs, projects, students, 6000, timeout_seconds=2)
        assert (actual.placement_count, actual.total_score_bp, actual.minimum_score_bp) == expected


@given(
    capacities=st.lists(st.integers(min_value=0, max_value=3), min_size=1, max_size=3),
    scores=st.lists(st.integers(min_value=0, max_value=10000), min_size=1, max_size=12),
)
@settings(max_examples=20, derandomize=True, deadline=None)
def test_seeded_randomized_assignments_respect_capacity_eligibility_and_uniqueness(
    capacities, scores
):
    students = [f"s{index}" for index in range(1, 5)]
    projects = [Capacity(f"p{index}", value) for index, value in enumerate(capacities, start=1)]
    pairs: list[PairScore] = []
    for index, (student_id, project) in enumerate(itertools.product(students, projects)):
        score = scores[index % len(scores)]
        pairs.append(pair(student_id, project.id, score, eligible=(index % 4 != 0)))
    result = optimize_pair_scores(pairs, projects, students, 5000, timeout_seconds=2)
    assigned_students = [item.student_id for item in result.assignments]
    assert len(assigned_students) == len(set(assigned_students))
    for project in projects:
        assert sum(item.project_id == project.id for item in result.assignments) <= project.capacity
    allowed = {
        (item.student_id, item.project_id)
        for item in pairs
        if item.eligible and item.total_bp >= 5000
    }
    assert all((item.student_id, item.project_id) in allowed for item in result.assignments)


def test_nearest_rank_bottom_decile_and_exact_denominators():
    snapshot = generate_snapshot()
    students = snapshot.students[:10]
    project = snapshot.projects[0]
    pairs = [pair(student.id, project.id, 6000 + index * 100) for index, student in enumerate(students)]
    assignments = [
        Assignment(
            student_id=item.student_id,
            project_id=item.project_id,
            score_bp=item.total_bp,
            compatibility_index=Decimal(item.total_bp) / 100,
            canonical_tie_order=index,
            global_rationale="test",
        )
        for index, item in enumerate(pairs, start=1)
    ]
    roomy_project = project.model_copy(update={"capacity": 10})
    metrics = calculate_metrics(
        "test", "test", students, [roomy_project], pairs, assignments, 0, Decimal("1.25")
    )
    assert metrics.bottom_decile_score == Decimal("60")
    assert metrics.placement_count == metrics.submitted_count == metrics.eligible_count == 10
    assert metrics.constraint_violations["total"] == 0


def test_full_seed_shuffle_is_input_order_invariant():
    snapshot = generate_snapshot()
    config = MatchConfig()
    pair_scores = score_matrix(
        snapshot.students,
        snapshot.projects,
        config,
        Taxonomy(snapshot.skills),
    )
    result = optimize_pair_scores(
        pair_scores,
        snapshot.projects,
        [student.id for student in snapshot.students],
        config.threshold_bp,
        timeout_seconds=3,
    )
    evidence = run_shuffle_test(
        snapshot.students,
        snapshot.projects,
        pair_scores,
        config.threshold_bp,
        result.assignments,
        timeout_seconds=3,
    )
    assert evidence.identical_assignment_pass_count == 20
    assert evidence.failing_seeds == []
