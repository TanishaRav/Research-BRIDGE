from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

import pytest
from pydantic import ValidationError

from backend.app.domain.models import MatchConfig, ScoreWeights, SkillKind
from backend.app.seed.generator import generate_snapshot
from backend.app.services.scoring import (
    evaluate_eligibility,
    normalize_weights,
    profile_missing_fields,
    score_pair,
)
from backend.app.services.taxonomy import Taxonomy, normalize_text, weighted_jaccard


@pytest.fixture(scope="module")
def snapshot():
    return generate_snapshot()


@pytest.fixture(scope="module")
def taxonomy(snapshot):
    return Taxonomy(snapshot.skills)


def test_unicode_normalization_and_alias_expansion(taxonomy):
    assert normalize_text("  PYTHON—Data!!! ") == "python data"
    assert taxonomy.token_weights(["Py"], explicit_tags=True) == {"python": Decimal(2)}
    assert taxonomy.token_weights(["I want ML feedback"], explicit_tags=False)["machine-learning"] == 1


def test_weighted_jaccard_zero_denominator_and_exact_value():
    assert weighted_jaccard({}, {}) == (None, [])
    ratio, matched = weighted_jaccard(
        {"a": Decimal(2), "b": Decimal(1)},
        {"a": Decimal(1), "c": Decimal(1)},
    )
    assert ratio == Decimal(1) / Decimal(4)
    assert matched == ["a"]


def test_default_weights_normalize_exactly_to_one():
    normalized = normalize_weights(MatchConfig())
    assert sum(normalized.values(), Decimal(0)) == 1
    assert normalized["interest"] == Decimal("0.35")
    assert normalized["technical_skill"] == Decimal("0.25")


@pytest.mark.parametrize(
    "weights",
    [
        {"interest": -1, "technical_skill": 1, "availability": 1, "preference": 1, "learning_goal": 1},
        {"interest": 0, "technical_skill": 0, "availability": 0, "preference": 0, "learning_goal": 0},
        {"interest": "NaN", "technical_skill": 1, "availability": 1, "preference": 1, "learning_goal": 1},
    ],
)
def test_invalid_weights_are_rejected(weights):
    with pytest.raises(ValidationError):
        ScoreWeights.model_validate(weights)


def test_total_uses_single_decimal_rounding(snapshot, taxonomy):
    student = snapshot.students[0]
    project = snapshot.projects[0]
    config = MatchConfig()
    pair = score_pair(student, project, config, taxonomy)
    raw = config.weights.as_dict()
    expected = int(
        (
            sum(
                Decimal(pair.factor_scores_bp[name]) * raw[name]
                for name in pair.factor_scores_bp
            )
            / sum(raw.values(), Decimal(0))
        ).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    )
    assert pair.total_bp == expected
    assert pair.compatibility_index == Decimal(pair.total_bp) / 100
    assert pair.score_version == "rb-score-v1"
    assert pair.config_snapshot["weights"]["interest"] == "35"


def test_unknown_mandatory_evidence_is_unresolved_and_ineligible(snapshot, taxonomy):
    student = snapshot.students[0].model_copy(deep=True)
    project = snapshot.projects[0]
    mandatory = {
        item.skill_id for item in project.skills if item.kind == SkillKind.MANDATORY
    }
    student.skills = [item for item in student.skills if item.skill_id not in mandatory]
    pair = score_pair(student, project, MatchConfig(), taxonomy)
    assert not pair.eligible
    assert "mandatory_evidence_unresolved" in {
        reason.code for reason in pair.eligibility_reasons
    }
    assert any(reason.resolution == "unresolved" for reason in pair.eligibility_reasons)
    assert any(gap["evidence_status"] == "missing" for gap in pair.gaps)


def test_trainable_skill_gap_is_not_a_hard_constraint(snapshot, taxonomy):
    student = snapshot.students[0].model_copy(deep=True)
    project = snapshot.projects[0]
    trainable = {
        item.skill_id for item in project.skills if item.kind == SkillKind.TRAINABLE
    }
    student.skills = [item for item in student.skills if item.skill_id not in trainable]
    pair = score_pair(student, project, MatchConfig(), taxonomy)
    assert pair.eligible
    assert not any(
        reason.field in {f"skills.{skill_id}" for skill_id in trainable}
        for reason in pair.eligibility_reasons
    )


def test_hours_below_minimum_is_ineligible(snapshot):
    student = snapshot.students[0].model_copy(deep=True)
    student.hours_per_week = Decimal(1)
    reasons = evaluate_eligibility(student, snapshot.projects[0])
    assert "insufficient_hours" in {reason.code for reason in reasons}


def test_missing_hours_is_unresolved(snapshot):
    student = snapshot.students[0].model_copy(deep=True)
    student.hours_per_week = None
    reasons = evaluate_eligibility(student, snapshot.projects[0])
    reason = next(item for item in reasons if item.code == "available_hours_unresolved")
    assert reason.resolution == "unresolved"


def test_fixed_window_requires_full_containment(snapshot):
    project = snapshot.projects[2]
    conflict_student = snapshot.students[11]
    assert any(reason.code == "fixed_window_conflict" for reason in evaluate_eligibility(conflict_student, project))
    matching_student = conflict_student.model_copy(deep=True)
    matching_student.availability = snapshot.students[0].availability
    assert not any(
        reason.code == "fixed_window_conflict"
        for reason in evaluate_eligibility(matching_student, project)
    )


def test_unranked_pair_requires_suggestion_consent(snapshot):
    student = snapshot.students[0].model_copy(deep=True)
    student.accepts_suggestions = False
    ranked = {item.project_id for item in student.preferences}
    project = next(item for item in snapshot.projects if item.id not in ranked)
    assert "not_acceptable_or_opted_in" in {
        reason.code for reason in evaluate_eligibility(student, project)
    }
    student.accepts_suggestions = True
    assert "not_acceptable_or_opted_in" not in {
        reason.code for reason in evaluate_eligibility(student, project)
    }


def test_inactive_and_zero_capacity_are_separate_reasons(snapshot):
    inactive = snapshot.projects[18]
    zero = snapshot.projects[19]
    student = snapshot.students[0].model_copy(deep=True)
    student.accepts_suggestions = True
    assert "project_inactive" in {reason.code for reason in evaluate_eligibility(student, inactive)}
    assert "nonpositive_capacity" in {reason.code for reason in evaluate_eligibility(student, zero)}


def test_zero_project_skills_receive_neutral_not_perfect(snapshot, taxonomy):
    student = snapshot.students[0]
    project = snapshot.projects[0].model_copy(deep=True)
    project.skills = []
    project.prerequisites = []
    pair = score_pair(student, project, MatchConfig(), taxonomy)
    assert pair.factor_scores_bp["technical_skill"] == 5000
    assert "no_project_skill_evidence" in pair.missing_fields


def test_preference_formula_and_suggestion_value(snapshot, taxonomy):
    student = snapshot.students[0]
    ranked_first = score_pair(student, snapshot.projects[0], MatchConfig(), taxonomy)
    ranked_second_project = next(
        project for project in snapshot.projects if project.id == student.preferences[1].project_id
    )
    ranked_second = score_pair(student, ranked_second_project, MatchConfig(), taxonomy)
    assert ranked_first.factor_scores_bp["preference"] == 10000
    assert ranked_second.factor_scores_bp["preference"] == 5000
    suggestion_student = student.model_copy(deep=True)
    suggestion_student.preferences = []
    suggestion_student.accepts_suggestions = True
    suggested = score_pair(suggestion_student, snapshot.projects[0], MatchConfig(), taxonomy)
    assert suggested.factor_scores_bp["preference"] == 2500
    assert "unknown_preference" in suggested.missing_fields


def test_profile_completeness_reports_each_missing_field(snapshot):
    student = snapshot.students[12]
    missing = profile_missing_fields(student)
    assert "hours_per_week" in missing
    student = snapshot.students[13]
    missing = profile_missing_fields(student)
    assert {"learning_goals", "availability"}.issubset(missing)
