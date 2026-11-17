from __future__ import annotations

from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from backend.app.domain.models import (
    EligibilityReason,
    MatchConfig,
    PairScore,
    Project,
    SkillKind,
    Student,
    TimeWindow,
)
from backend.app.services.taxonomy import Taxonomy, weighted_jaccard

BP = Decimal(10000)
ONE = Decimal(1)


def round_half_up(value: Decimal) -> int:
    return int(value.quantize(ONE, rounding=ROUND_HALF_UP))


def decimal_string(value: Decimal) -> str:
    return format(value.normalize(), "f")


def normalize_weights(config: MatchConfig) -> dict[str, Decimal]:
    weights = config.weights.as_dict()
    total = sum(weights.values(), Decimal(0))
    # ScoreWeights enforces this; retain a defensive boundary for pure callers.
    if total <= 0 or any(not value.is_finite() or value < 0 for value in weights.values()):
        raise ValueError("weights must be finite and nonnegative with at least one positive value")
    return {name: value / total for name, value in weights.items()}


def normalized_weight_percent(config: MatchConfig) -> dict[str, Decimal]:
    normalized = normalize_weights(config)
    return {name: value * Decimal(100) for name, value in normalized.items()}


def profile_missing_fields(student: Student) -> list[str]:
    missing: list[str] = []
    if not student.interests:
        missing.append("interests")
    if student.hours_per_week is None:
        missing.append("hours_per_week")
    if not student.learning_goals:
        missing.append("learning_goals")
    if not student.availability:
        missing.append("availability")
    if not student.preferences and not student.accepts_suggestions:
        missing.append("preferences_or_suggestion_consent")
    return missing


def _contains(student_windows: Iterable[TimeWindow], required: TimeWindow) -> bool:
    return any(
        window.day == required.day
        and window.start_minute <= required.start_minute
        and window.end_minute >= required.end_minute
        for window in student_windows
    )


def evaluate_eligibility(student: Student, project: Project) -> list[EligibilityReason]:
    reasons: list[EligibilityReason] = []
    ranked_ids = {preference.project_id for preference in student.preferences}
    skill_levels = {skill.skill_id: skill.proficiency for skill in student.skills}

    if not project.active:
        reasons.append(
            EligibilityReason(code="project_inactive", detail="The project is not active.", field="active")
        )
    if project.capacity <= 0:
        reasons.append(
            EligibilityReason(
                code="nonpositive_capacity",
                detail="The project has no available synthetic-demo capacity.",
                field="capacity",
            )
        )
    if project.id not in ranked_ids and not student.accepts_suggestions:
        reasons.append(
            EligibilityReason(
                code="not_acceptable_or_opted_in",
                detail="The student neither ranked this project nor accepted suggestions.",
                field="preferences",
            )
        )

    requirements: dict[str, int] = {
        skill.skill_id: skill.required_proficiency
        for skill in project.skills
        if skill.kind == SkillKind.MANDATORY
    }
    for prerequisite in project.prerequisites:
        requirements.setdefault(prerequisite, 1)
    for skill_id, target in sorted(requirements.items()):
        level = skill_levels.get(skill_id)
        if level is None:
            reasons.append(
                EligibilityReason(
                    code="mandatory_evidence_unresolved",
                    detail=f"Required evidence for {skill_id} is missing; ability is not inferred.",
                    field=f"skills.{skill_id}",
                    resolution="unresolved",
                )
            )
        elif level < target:
            reasons.append(
                EligibilityReason(
                    code="mandatory_proficiency_unmet",
                    detail=f"Recorded proficiency for {skill_id} is {level}; {target} is required.",
                    field=f"skills.{skill_id}",
                )
            )

    if student.hours_per_week is None:
        reasons.append(
            EligibilityReason(
                code="available_hours_unresolved",
                detail="Available hours are missing; availability is not inferred.",
                field="hours_per_week",
                resolution="unresolved",
            )
        )
    elif student.hours_per_week < project.commitment_hours:
        reasons.append(
            EligibilityReason(
                code="insufficient_hours",
                detail=(
                    f"Recorded availability is {student.hours_per_week} hours; "
                    f"the project requires {project.commitment_hours}."
                ),
                field="hours_per_week",
            )
        )

    fixed_windows = [window for window in project.required_windows if window.fixed]
    if fixed_windows and not student.availability:
        reasons.append(
            EligibilityReason(
                code="fixed_window_evidence_unresolved",
                detail="Student time windows are missing for a fixed project requirement.",
                field="availability",
                resolution="unresolved",
            )
        )
    else:
        for index, required in enumerate(fixed_windows):
            if not _contains(student.availability, required):
                reasons.append(
                    EligibilityReason(
                        code="fixed_window_conflict",
                        detail=(
                            f"No recorded student window fully contains required window "
                            f"{required.day}:{required.start_minute}-{required.end_minute}."
                        ),
                        field=f"required_windows.{index}",
                    )
                )
    return reasons


def _merge_by_day(windows: Iterable[TimeWindow]) -> dict[int, list[tuple[int, int]]]:
    grouped: dict[int, list[tuple[int, int]]] = {}
    for window in windows:
        grouped.setdefault(window.day, []).append((window.start_minute, window.end_minute))
    merged: dict[int, list[tuple[int, int]]] = {}
    for day, intervals in grouped.items():
        day_result: list[tuple[int, int]] = []
        for start, end in sorted(intervals):
            if day_result and start <= day_result[-1][1]:
                day_result[-1] = (day_result[-1][0], max(end, day_result[-1][1]))
            else:
                day_result.append((start, end))
        merged[day] = day_result
    return merged


def _window_overlap_ratio(
    student_windows: Iterable[TimeWindow], mentoring_windows: Iterable[TimeWindow]
) -> Decimal:
    student_by_day = _merge_by_day(student_windows)
    mentor_by_day = _merge_by_day(mentoring_windows)
    total = sum(end - start for values in mentor_by_day.values() for start, end in values)
    if total == 0:
        return Decimal("0.5")
    overlap = 0
    for day, mentor_intervals in mentor_by_day.items():
        for mentor_start, mentor_end in mentor_intervals:
            for student_start, student_end in student_by_day.get(day, []):
                overlap += max(0, min(mentor_end, student_end) - max(mentor_start, student_start))
    return min(Decimal(overlap) / Decimal(total), ONE)


def _factor_interest(
    student: Student, project: Project, taxonomy: Taxonomy
) -> tuple[int, dict[str, Any], list[str]]:
    student_tokens = taxonomy.token_weights(student.interests, explicit_tags=True)
    project_tokens = taxonomy.token_weights(project.interests, explicit_tags=True)
    ratio, matched = weighted_jaccard(student_tokens, project_tokens)
    missing: list[str] = []
    if ratio is None:
        score = 0
        missing.append("missing_interest_evidence")
    else:
        score = round_half_up(BP * ratio)
    return (
        score,
        {
            "student_tokens": {key: decimal_string(value) for key, value in student_tokens.items()},
            "project_tokens": {key: decimal_string(value) for key, value in project_tokens.items()},
            "matched_tokens": matched,
        },
        missing,
    )


def _factor_skill(
    student: Student, project: Project
) -> tuple[int, dict[str, Any], list[dict[str, Any]], list[str]]:
    levels = {skill.skill_id: skill.proficiency for skill in student.skills}
    if not project.skills:
        return 5000, {"handling": "neutral_no_project_skill_evidence"}, [], [
            "no_project_skill_evidence"
        ]
    numerator = Decimal(0)
    denominator = Decimal(0)
    rows: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    missing: list[str] = []
    for requirement in sorted(project.skills, key=lambda item: item.skill_id):
        factor_weight = Decimal(1) if requirement.kind == SkillKind.MANDATORY else Decimal("0.75")
        current = levels.get(requirement.skill_id)
        if current is None:
            coverage = Decimal(0)
            missing.append(f"skills.{requirement.skill_id}")
        else:
            coverage = min(Decimal(current) / Decimal(requirement.required_proficiency), ONE)
        numerator += factor_weight * coverage
        denominator += factor_weight
        rows.append(
            {
                "skill_id": requirement.skill_id,
                "kind": requirement.kind.value,
                "current_proficiency": current,
                "target_proficiency": requirement.required_proficiency,
                "coverage": decimal_string(coverage),
                "factor_weight": decimal_string(factor_weight),
            }
        )
        if current is None or current < requirement.required_proficiency:
            gaps.append(
                {
                    "skill_id": requirement.skill_id,
                    "kind": requirement.kind.value,
                    "current_proficiency": current,
                    "target_proficiency": requirement.required_proficiency,
                    "evidence_status": "missing" if current is None else "recorded_gap",
                }
            )
    score = round_half_up(BP * numerator / denominator)
    return score, {"requirements": rows}, gaps, missing


def _factor_availability(student: Student, project: Project) -> tuple[int, dict[str, Any], list[str]]:
    missing: list[str] = []
    if student.hours_per_week is None:
        hours_surplus = Decimal(0)
        missing.append("hours_per_week")
    else:
        denominator = max(project.commitment_hours, ONE)
        hours_surplus = min(
            max((student.hours_per_week - project.commitment_hours) / denominator, Decimal(0)),
            ONE,
        )
    nonfixed_mentoring = [window for window in project.mentoring_windows if not window.fixed]
    if nonfixed_mentoring:
        window_overlap = _window_overlap_ratio(student.availability, nonfixed_mentoring)
        if not student.availability:
            missing.append("availability")
        handling = "measured"
    else:
        window_overlap = Decimal("0.5")
        handling = "neutral_no_nonfixed_mentoring_windows"
        missing.append("no_nonfixed_mentoring_window_evidence")
    score = round_half_up(BP * (Decimal("0.6") * hours_surplus + Decimal("0.4") * window_overlap))
    return (
        score,
        {
            "hours_surplus": decimal_string(hours_surplus),
            "window_overlap": decimal_string(window_overlap),
            "window_handling": handling,
        },
        missing,
    )


def _factor_preference(student: Student, project: Project) -> tuple[int, dict[str, Any], list[str]]:
    preferences = sorted(student.preferences, key=lambda item: item.rank)
    selected = next((item for item in preferences if item.project_id == project.id), None)
    missing: list[str] = []
    if selected is not None:
        if len(preferences) == 1:
            score = 10000
        else:
            score = round_half_up(
                BP * Decimal(len(preferences) - selected.rank) / Decimal(len(preferences) - 1)
            )
        evidence = {"rank": selected.rank, "ranked_count": len(preferences), "suggestion": False}
    elif student.accepts_suggestions:
        score = 2500
        evidence = {"rank": None, "ranked_count": len(preferences), "suggestion": True}
        if not preferences:
            missing.append("unknown_preference")
    else:
        score = 0
        evidence = {"rank": None, "ranked_count": len(preferences), "suggestion": False}
        missing.append("project_not_ranked")
    return score, evidence, missing


def _factor_goal(
    student: Student, project: Project, taxonomy: Taxonomy
) -> tuple[int, dict[str, Any], list[str]]:
    student_tokens = taxonomy.token_weights(student.learning_goals, explicit_tags=False)
    project_goal_values = [
        requirement.skill_id
        for requirement in project.skills
        if requirement.kind == SkillKind.TRAINABLE
    ]
    if project.mentoring_available:
        project_goal_values.extend(["mentoring", "guided practice", "feedback"])
    project_tokens = taxonomy.token_weights(project_goal_values, explicit_tags=True)
    ratio, matched = weighted_jaccard(student_tokens, project_tokens)
    missing: list[str] = []
    if not student_tokens:
        missing.append("missing_learning_goal_evidence")
    if not project_tokens:
        missing.append("missing_trainable_or_mentoring_evidence")
    score = 0 if ratio is None else round_half_up(BP * ratio)
    return (
        score,
        {
            "student_tokens": {key: decimal_string(value) for key, value in student_tokens.items()},
            "project_tokens": {key: decimal_string(value) for key, value in project_tokens.items()},
            "matched_tokens": matched,
        },
        missing,
    )


def score_pair(
    student: Student, project: Project, config: MatchConfig, taxonomy: Taxonomy
) -> PairScore:
    reasons = evaluate_eligibility(student, project)
    interest, interest_evidence, interest_missing = _factor_interest(student, project, taxonomy)
    technical, technical_evidence, gaps, technical_missing = _factor_skill(student, project)
    availability, availability_evidence, availability_missing = _factor_availability(student, project)
    preference, preference_evidence, preference_missing = _factor_preference(student, project)
    learning_goal, goal_evidence, goal_missing = _factor_goal(student, project, taxonomy)
    factor_scores = {
        "interest": interest,
        "technical_skill": technical,
        "availability": availability,
        "preference": preference,
        "learning_goal": learning_goal,
    }
    raw_weights = config.weights.as_dict()
    normalized = normalize_weights(config)
    contributions = {
        name: round_half_up(Decimal(score) * normalized[name])
        for name, score in factor_scores.items()
    }
    weighted_sum = sum(
        (Decimal(factor_scores[name]) * raw_weights[name] for name in factor_scores), Decimal(0)
    )
    total_weight = sum(raw_weights.values(), Decimal(0))
    total_bp = round_half_up(weighted_sum / total_weight)
    missing_fields = sorted(
        set(
            interest_missing
            + technical_missing
            + availability_missing
            + preference_missing
            + goal_missing
            + [reason.field for reason in reasons if reason.resolution == "unresolved" and reason.field]
        )
    )
    return PairScore(
        student_id=student.id,
        project_id=project.id,
        eligible=not reasons,
        eligibility_reasons=reasons,
        factor_scores_bp=factor_scores,
        raw_weights={name: decimal_string(value) for name, value in raw_weights.items()},
        normalized_weights={name: decimal_string(value) for name, value in normalized.items()},
        contributions_bp=contributions,
        evidence={
            "interest": interest_evidence,
            "technical_skill": technical_evidence,
            "availability": availability_evidence,
            "preference": preference_evidence,
            "learning_goal": goal_evidence,
            "taxonomy_version": taxonomy.version,
        },
        gaps=gaps,
        missing_fields=missing_fields,
        total_bp=total_bp,
        compatibility_index=(Decimal(total_bp) / Decimal(100)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        ),
        score_version=config.score_version,
        taxonomy_version=config.taxonomy_version,
        config_snapshot=config.model_dump(mode="json"),
    )


def score_matrix(
    students: Iterable[Student],
    projects: Iterable[Project],
    config: MatchConfig,
    taxonomy: Taxonomy,
) -> list[PairScore]:
    return [
        score_pair(student, project, config, taxonomy)
        for student in sorted(students, key=lambda item: item.id)
        for project in sorted(projects, key=lambda item: item.id)
    ]
