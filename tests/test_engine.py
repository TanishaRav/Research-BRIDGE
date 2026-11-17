"""Unit tests for the isolated SPARK matching engine.

Written as plain ``unittest.TestCase`` classes so they run under BOTH
``pytest tests/`` and ``python -m unittest discover -s tests``. The engine
imports only the standard library, so these tests need no fixtures or DB.
"""

import unittest

from matching.engine import (
    Assignment,
    Config,
    ProjectIn,
    Result,
    StudentIn,
    match,
)


def _match_map(result: Result) -> dict[int, int]:
    """student_id -> project_id for the produced assignments."""
    return {a.student_id: a.project_id for a in result.assignments}


class TopChoiceTest(unittest.TestCase):
    def test_everyone_gets_a_top_ranked_project_when_feasible(self):
        # Three students, three single-slot projects, mutually first-choice.
        students = [
            StudentIn(1, {10}, False, [101, 102, 103]),
            StudentIn(2, {10}, False, [102, 103, 101]),
            StudentIn(3, {10}, False, [103, 101, 102]),
        ]
        projects = [
            ProjectIn(101, 1, True, set(), set(), [1, 2, 3]),
            ProjectIn(102, 1, True, set(), set(), [2, 3, 1]),
            ProjectIn(103, 1, True, set(), set(), [3, 1, 2]),
        ]
        result = match(students, projects, Config("equal"))
        got = _match_map(result)
        self.assertEqual(got, {1: 101, 2: 102, 3: 103})
        self.assertEqual(result.unmatched_students, [])
        # Everyone got their mutual #1 => overall fit is perfect.
        self.assertEqual(result.overall_fit, 100.0)


class CapacityTest(unittest.TestCase):
    def test_capacity_is_a_hard_limit(self):
        # One project with capacity 2, three students all want it.
        students = [
            StudentIn(1, {10}, False, [500]),
            StudentIn(2, {10}, False, [500]),
            StudentIn(3, {10}, False, [500]),
        ]
        projects = [ProjectIn(500, 2, True, set(), set(), [1, 2, 3])]
        result = match(students, projects, Config("equal"))
        matched = [a for a in result.assignments if a.project_id == 500]
        self.assertEqual(len(matched), 2)
        self.assertEqual(len(result.unmatched_students), 1)
        # Faculty top two (students 1 and 2) should be the ones placed.
        self.assertEqual(sorted(a.student_id for a in matched), [1, 2])

    def test_zero_capacity_project_receives_nobody(self):
        students = [StudentIn(1, {10}, False, [500])]
        projects = [ProjectIn(500, 0, True, set(), set(), [1])]
        result = match(students, projects, Config("equal"))
        self.assertEqual(result.assignments, [])
        self.assertEqual(result.unmatched_students, [1])


class EligibilityTest(unittest.TestCase):
    def test_must_major_is_enforced(self):
        # Student 1 lacks the required major, student 2 has it.
        students = [
            StudentIn(1, {99}, False, [700]),
            StudentIn(2, {10}, False, [700]),
        ]
        projects = [ProjectIn(700, 5, True, {10}, set(), [1, 2])]
        result = match(students, projects, Config("equal"))
        got = _match_map(result)
        self.assertNotIn(1, got)  # ineligible, never assigned
        self.assertEqual(got.get(2), 700)
        self.assertIn(1, result.unmatched_students)

    def test_citizenship_is_enforced(self):
        # Noncitizen student may only go to a noncitizen_ok project.
        students = [StudentIn(1, {10}, True, [700, 800])]
        projects = [
            ProjectIn(700, 1, False, set(), set(), [1]),  # not open
            ProjectIn(800, 1, True, set(), set(), [1]),   # open
        ]
        result = match(students, projects, Config("equal"))
        got = _match_map(result)
        self.assertEqual(got.get(1), 800)
        # Confirm the forbidden project is never used for a noncitizen.
        for a in result.assignments:
            if a.student_id == 1:
                self.assertNotEqual(a.project_id, 700)

    def test_no_constraints_output_violates_nothing(self):
        students = [
            StudentIn(1, {10}, True, [700]),
            StudentIn(2, {99}, False, [700]),
        ]
        projects = [ProjectIn(700, 1, False, {10}, set(), [1, 2])]
        result = match(students, projects, Config("equal"))
        for a in result.assignments:
            s = next(s for s in students if s.id == a.student_id)
            p = next(p for p in projects if p.id == a.project_id)
            self.assertTrue(not p.must_majors or (s.major_ids & p.must_majors))
            self.assertTrue(not s.noncitizen or p.noncitizen_ok)


class WeightingTest(unittest.TestCase):
    def test_faculty_heavy_changes_assignment(self):
        # Two students, two single-slot projects A(1001) and B(1002).
        # S1 strongly wants A; S2 prefers B but is faculty #1 on A.
        # Under "equal" weighting, honoring both students' top choices
        # (S1->A, S2->B) is cheapest. Under "faculty_heavy", A's faculty #1
        # (S2) is pulled onto A, flipping the assignment.
        students = [
            StudentIn(1, {10}, False, [1001, 1002]),  # wants A
            StudentIn(2, {10}, False, [1002, 1001]),  # wants B, faculty #1 on A
        ]

        def build():
            return [
                ProjectIn(1001, 1, True, set(), set(), [2, 1]),  # faculty wants S2 first
                ProjectIn(1002, 1, True, set(), set(), [1, 2]),
            ]

        equal_map = _match_map(match(students, build(), Config("equal")))
        heavy_map = _match_map(match(students, build(), Config("faculty_heavy")))
        self.assertNotEqual(equal_map, heavy_map)
        self.assertEqual(equal_map, {1: 1001, 2: 1002})
        self.assertEqual(heavy_map, {1: 1002, 2: 1001})


class DeterminismTest(unittest.TestCase):
    def test_identical_inputs_produce_identical_result(self):
        students = [
            StudentIn(3, {10}, False, [101, 102]),
            StudentIn(1, {10}, False, [102, 101]),
            StudentIn(2, {10}, False, [101, 102]),
        ]
        projects = [
            ProjectIn(102, 1, True, set(), set(), [1, 2, 3]),
            ProjectIn(101, 2, True, set(), set(), [3, 2, 1]),
        ]
        first = match(students, projects, Config("equal"))
        for _ in range(5):
            again = match(students, projects, Config("equal"))
            self.assertEqual(
                [(a.student_id, a.project_id, a.student_fit, a.project_fit)
                 for a in first.assignments],
                [(a.student_id, a.project_id, a.student_fit, a.project_fit)
                 for a in again.assignments],
            )
            self.assertEqual(first.unmatched_students, again.unmatched_students)
            self.assertEqual(first.overall_fit, again.overall_fit)
            self.assertEqual(first.per_project_fit, again.per_project_fit)

    def test_assignments_sorted_by_student_id(self):
        students = [
            StudentIn(5, {10}, False, [101]),
            StudentIn(2, {10}, False, [101]),
            StudentIn(9, {10}, False, [101]),
        ]
        projects = [ProjectIn(101, 3, True, set(), set(), [])]
        result = match(students, projects, Config("equal"))
        ids = [a.student_id for a in result.assignments]
        self.assertEqual(ids, sorted(ids))


class FitScoreTest(unittest.TestCase):
    def test_first_choice_scores_100(self):
        students = [StudentIn(1, {10}, False, [101, 102, 103])]
        projects = [ProjectIn(101, 1, True, set(), set(), [1])]
        result = match(students, projects, Config("equal"))
        self.assertEqual(result.assignments[0].student_fit, 100.0)

    def test_unmatched_student_has_no_assignment_and_zero_contribution(self):
        students = [
            StudentIn(1, {10}, False, [500]),
            StudentIn(2, {10}, False, [500]),
        ]
        projects = [ProjectIn(500, 1, True, set(), set(), [1, 2])]
        result = match(students, projects, Config("equal"))
        self.assertEqual(len(result.unmatched_students), 1)
        matched_ids = {a.student_id for a in result.assignments}
        for sid in result.unmatched_students:
            self.assertNotIn(sid, matched_ids)

    def test_all_fit_scores_within_bounds(self):
        students = [
            StudentIn(1, {10}, False, [101, 102]),
            StudentIn(2, {10}, False, [102, 101]),
            StudentIn(3, {10}, False, [101]),
        ]
        projects = [
            ProjectIn(101, 1, True, set(), set(), [1, 2, 3]),
            ProjectIn(102, 2, True, set(), set(), [2, 1]),
        ]
        result = match(students, projects, Config("faculty_heavy"))
        for a in result.assignments:
            self.assertGreaterEqual(a.student_fit, 0.0)
            self.assertLessEqual(a.student_fit, 100.0)
            self.assertGreaterEqual(a.project_fit, 0.0)
            self.assertLessEqual(a.project_fit, 100.0)
        self.assertGreaterEqual(result.overall_fit, 0.0)
        self.assertLessEqual(result.overall_fit, 100.0)
        for pid, fit in result.per_project_fit.items():
            self.assertGreaterEqual(fit, 0.0)
            self.assertLessEqual(fit, 100.0)


class AiMatchTest(unittest.TestCase):
    def test_ai_variant_runs_when_no_preferences_present(self):
        # No prefs anywhere => overlap-based costs. Student should land on the
        # project whose majors it overlaps.
        students = [
            StudentIn(1, {10, 11}, False, []),
            StudentIn(2, {20}, False, []),
        ]
        projects = [
            ProjectIn(101, 1, True, set(), {10, 11}, []),
            ProjectIn(102, 1, True, set(), {20}, []),
        ]
        result = match(students, projects, Config("equal"))
        got = _match_map(result)
        self.assertEqual(got.get(1), 101)
        self.assertEqual(got.get(2), 102)


if __name__ == "__main__":
    unittest.main()
