"""SPARK fit statistics.

Pure functions over the matching engine's dataclasses. Imports ONLY the Python
standard library (R6.1, R13.4): no `app` imports. All scores are on a 0-100
scale where 100 means a mutual first-choice outcome.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # avoid a runtime import cycle; types only
    from matching.engine import (
        Assignment,
        Config,
        ProjectIn,
        StudentIn,
    )


def _rank(order: list[int], target: int) -> int | None:
    """0-based rank of `target` in `order`, or None if absent."""
    try:
        return order.index(target)
    except ValueError:
        return None


def student_fit(student: "StudentIn", project_id: int) -> float:
    """Per-student fit, 0-100.

    fit = 100 * (1 - normalized_rank_cost), where normalized_rank_cost is the
    0-based rank of the matched project divided by the length of the student's
    preference list. Got #1 => 100. A match to a project the student did not
    rank (or a student with no list) normalizes to the full penalty => 0.
    An unmatched student is handled by the caller (fit 0, no Assignment).
    """
    prefs = student.prefs
    length = len(prefs)
    if length == 0:
        return 0.0
    rank = _rank(prefs, project_id)
    if rank is None:
        return 0.0
    normalized = rank / length
    return round(100.0 * (1.0 - normalized), 4)


def _faculty_placement_score(project: "ProjectIn", student_id: int) -> float:
    """How high `student_id` sat on `project`'s own list, 0-100.

    #1 on the faculty list => 100; absent (or no list) => 0.
    """
    prefs = project.prefs
    length = len(prefs)
    if length == 0:
        return 0.0
    rank = _rank(prefs, student_id)
    if rank is None:
        return 0.0
    return 100.0 * (1.0 - rank / length)


def per_project_fit(
    assignments: list["Assignment"],
    student_by_id: dict[int, "StudentIn"],
    project_by_id: dict[int, "ProjectIn"],
) -> dict[int, float]:
    """Per-project fit: average of received students' own fits, blended 50/50
    with how high those students sat on the project's faculty list. Returns a
    deterministic dict keyed by project id."""
    received: dict[int, list[tuple[float, float]]] = {}
    for a in assignments:
        s = student_by_id.get(a.student_id)
        p = project_by_id.get(a.project_id)
        if s is None or p is None:
            continue
        sfit = student_fit(s, a.project_id)
        fac = _faculty_placement_score(p, a.student_id)
        received.setdefault(a.project_id, []).append((sfit, fac))

    out: dict[int, float] = {}
    for pid in sorted(received):
        pairs = received[pid]
        blended = [0.5 * sfit + 0.5 * fac for sfit, fac in pairs]
        out[pid] = round(sum(blended) / len(blended), 4)
    return out


def overall_fit(
    assignments: list["Assignment"],
    student_by_id: dict[int, "StudentIn"],
    project_by_id: dict[int, "ProjectIn"],
    config: "Config",
) -> float:
    """Overall fit: capacity-weighted average of per-match satisfaction scaled
    0-100 (100 = everyone's mutual #1).

    Each match contributes a satisfaction score that blends the student's fit
    with the faculty placement score. The average is taken over all filled
    slots (each match is one slot, so this is already capacity-weighted since
    higher-capacity projects contribute proportionally more matches)."""
    if not assignments:
        return 0.0
    total = 0.0
    for a in assignments:
        s = student_by_id.get(a.student_id)
        p = project_by_id.get(a.project_id)
        if s is None or p is None:
            continue
        sfit = student_fit(s, a.project_id)
        fac = _faculty_placement_score(p, a.student_id)
        total += 0.5 * sfit + 0.5 * fac
    return round(total / len(assignments), 4)
