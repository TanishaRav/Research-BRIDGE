"""SPARK matching engine.

Isolated capacitated two-sided assignment. Imports ONLY the Python standard
library (R6.1, R13.4): no `app` imports, no third-party solver. Inputs and
outputs are plain dataclasses so the engine is unit-testable in isolation and
swappable later.

Algorithm overview
------------------
* Hard constraints produce the set of feasible (student, project) edges.
* Each feasible edge carries a cost derived from the two-sided preference
  ranks, combined per the configured weighting.
* Each project is expanded into `capacity` slots and a min-cost bipartite
  matching is computed with a from-scratch successive-shortest-augmenting-path
  min-cost flow (Bellman-Ford/SPFA shortest paths, which tolerate the negative
  reduced costs that arise from the favorable-rank rule).
* The result is deterministic for sorted/stable inputs (R6.7).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# Large penalty applied to an unranked pairing. Kept finite so that a feasible
# but unranked edge is always preferred over leaving a student unmatched.
UNRANKED_PENALTY = 1000

# Cost used for a favorable prefer-major pairing when a project has no faculty
# preference list of its own (R6.4). Small so it beats a plain unranked edge
# but does not out-rank an explicitly listed top choice.
PREFER_MAJOR_RANK = 1

# Weighting coefficients: weighting name -> (student_weight, faculty_weight).
WEIGHTINGS = {
    "equal": (0.5, 0.5),
    "faculty_heavy": (0.35, 0.65),
}


@dataclass
class StudentIn:
    id: int
    major_ids: set[int] = field(default_factory=set)
    noncitizen: bool = False
    prefs: list[int] = field(default_factory=list)


@dataclass
class ProjectIn:
    id: int
    capacity: int = 1
    noncitizen_ok: bool = True
    must_majors: set[int] = field(default_factory=set)
    prefer_majors: set[int] = field(default_factory=set)
    prefs: list[int] = field(default_factory=list)


@dataclass
class Config:
    weighting: str = "equal"
    top_k_target: int = 5


@dataclass
class Assignment:
    student_id: int
    project_id: int
    student_fit: float = 0.0
    project_fit: float = 0.0


@dataclass
class Result:
    assignments: list[Assignment] = field(default_factory=list)
    unmatched_students: list[int] = field(default_factory=list)
    overall_fit: float = 0.0
    per_project_fit: dict[int, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Hard constraints and edge costs
# ---------------------------------------------------------------------------

def _eligible(student: StudentIn, project: ProjectIn) -> bool:
    """Return True if the (student, project) pair satisfies all hard
    constraints: must-majors membership, citizenship, and positive capacity
    (R6.5)."""
    if project.capacity <= 0:
        return False
    if project.must_majors and not (student.major_ids & project.must_majors):
        return False
    if student.noncitizen and not project.noncitizen_ok:
        return False
    return True


def _rank_cost(order: list[int], target: int) -> Optional[int]:
    """0-based rank of `target` in preference list `order`, or None if absent."""
    try:
        return order.index(target)
    except ValueError:
        return None


def _edge_cost(student: StudentIn, project: ProjectIn, weighting: str) -> float:
    """Combined cost of assigning `student` to `project` (lower is better)."""
    s_rank = _rank_cost(student.prefs, project.id)
    student_cost = UNRANKED_PENALTY if s_rank is None else s_rank

    f_rank = _rank_cost(project.prefs, student.id)
    if f_rank is not None:
        faculty_cost: float = f_rank
    elif not project.prefs and (student.major_ids & project.prefer_majors):
        # R6.4: project expressed no faculty ranking, but the student is in a
        # preferred major, so treat it as a favorable rank.
        faculty_cost = PREFER_MAJOR_RANK
    else:
        faculty_cost = UNRANKED_PENALTY

    sw, fw = WEIGHTINGS.get(weighting, WEIGHTINGS["equal"])
    return sw * student_cost + fw * faculty_cost


def _ai_edge_cost(student: StudentIn, project: ProjectIn, weighting: str) -> float:
    """AI-match cost variant (R6.2 method b): when preferences are absent,
    derive cost from major/department/keyword overlap. Here overlap is measured
    by shared major ids (must + prefer). More overlap => lower cost."""
    pool = project.must_majors | project.prefer_majors
    overlap = len(student.major_ids & pool)
    # Scale so that strong overlap approaches the quality of a top-ranked edge
    # while zero overlap behaves like an unranked pairing.
    return float(UNRANKED_PENALTY) / (1 + overlap)


def _has_preferences(students: list[StudentIn], projects: list[ProjectIn]) -> bool:
    """True if any two-sided preference data exists at all."""
    if any(s.prefs for s in students):
        return True
    if any(p.prefs for p in projects):
        return True
    return False


# ---------------------------------------------------------------------------
# Min-cost bipartite matching via successive-shortest-path min-cost flow
# ---------------------------------------------------------------------------

class _MinCostFlow:
    """Successive-shortest-augmenting-path min-cost max-flow.

    Uses SPFA (queue-based Bellman-Ford) for shortest paths so that negative
    edge costs (from favorable ranks) are handled correctly. Edge iteration is
    insertion-ordered, which keeps the result deterministic for stable inputs.
    """

    def __init__(self, n: int) -> None:
        self.n = n
        # graph[u] = list of edge indices in self.edges
        self.graph: list[list[int]] = [[] for _ in range(n)]
        # each edge: [to, capacity, cost, rev_index]
        self.edges: list[list] = []

    def add_edge(self, u: int, v: int, cap: int, cost: float) -> None:
        # Forward and reverse edges are appended as a pair, so the reverse of
        # edge `eid` is always `eid ^ 1`.
        self.graph[u].append(len(self.edges))
        self.edges.append([v, cap, cost])
        self.graph[v].append(len(self.edges))
        self.edges.append([u, 0, -cost])

    def min_cost_flow(self, source: int, sink: int) -> None:
        INF = float("inf")
        while True:
            dist = [INF] * self.n
            in_queue = [False] * self.n
            prev_edge = [-1] * self.n
            dist[source] = 0.0
            queue = [source]
            in_queue[source] = True
            while queue:
                u = queue.pop(0)
                in_queue[u] = False
                for eid in self.graph[u]:
                    to, cap, cost = self.edges[eid]
                    if cap > 0 and dist[u] + cost < dist[to] - 1e-12:
                        dist[to] = dist[u] + cost
                        prev_edge[to] = eid
                        if not in_queue[to]:
                            queue.append(to)
                            in_queue[to] = True
            if dist[sink] == INF:
                break  # no augmenting path remains
            # Augment one unit along the discovered shortest path.
            v = sink
            while v != source:
                eid = prev_edge[v]
                self.edges[eid][1] -= 1
                self.edges[eid ^ 1][1] += 1
                v = self.edges[eid ^ 1][0]


def _solve_assignment(
    students: list[StudentIn],
    projects: list[ProjectIn],
    cost_of,
    weighting: str,
) -> list[tuple[int, int]]:
    """Return a list of (student_id, project_id) matches minimizing total cost.

    Nodes: source(0), one node per student, one node per project slot bucket,
    sink. Each project keeps `capacity` units of flow. Only feasible edges
    (positive, finite cost) are added.
    """
    source = 0
    student_base = 1
    project_base = student_base + len(students)
    sink = project_base + len(projects)
    mcf = _MinCostFlow(sink + 1)

    for si, s in enumerate(students):
        mcf.add_edge(source, student_base + si, 1, 0.0)
    for pi, p in enumerate(projects):
        cap = max(p.capacity, 0)
        if cap > 0:
            mcf.add_edge(project_base + pi, sink, cap, 0.0)

    # Feasible student->project edges.
    for si, s in enumerate(students):
        for pi, p in enumerate(projects):
            if not _eligible(s, p):
                continue
            cost = cost_of(s, p, weighting)
            mcf.add_edge(student_base + si, project_base + pi, 1, cost)

    mcf.min_cost_flow(source, sink)

    matches: list[tuple[int, int]] = []
    for si, s in enumerate(students):
        for eid in mcf.graph[student_base + si]:
            to, cap, cost = mcf.edges[eid]
            if project_base <= to < sink and cap == 0:
                # Original capacity was 1 and it is now consumed => matched.
                pi = to - project_base
                matches.append((s.id, projects[pi].id))
                break
    return matches


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def match(
    students: list[StudentIn],
    projects: list[ProjectIn],
    config: Config,
) -> Result:
    """Compute a capacitated two-sided assignment.

    Deterministic for sorted/stable inputs. Picks the preference-based cost
    function when any preferences exist, otherwise the AI-match overlap variant
    (R6.2 method b).
    """
    # Stable, deterministic ordering (R6.7).
    students = sorted(students, key=lambda s: s.id)
    projects = sorted(projects, key=lambda p: p.id)

    cost_of = _edge_cost if _has_preferences(students, projects) else _ai_edge_cost

    matches = _solve_assignment(students, projects, cost_of, config.weighting)
    matched_by_student = {sid: pid for sid, pid in matches}

    # Import here to avoid any import cycle concerns; stats is stdlib-only too.
    from matching import stats as _stats

    student_by_id = {s.id: s for s in students}
    project_by_id = {p.id: p for p in projects}

    assignments: list[Assignment] = []
    for sid in sorted(matched_by_student):
        pid = matched_by_student[sid]
        a = Assignment(student_id=sid, project_id=pid)
        a.student_fit = _stats.student_fit(student_by_id[sid], pid)
        assignments.append(a)

    unmatched = sorted(s.id for s in students if s.id not in matched_by_student)

    per_project_fit = _stats.per_project_fit(assignments, student_by_id, project_by_id)
    for a in assignments:
        a.project_fit = per_project_fit.get(a.project_id, 0.0)

    overall = _stats.overall_fit(assignments, student_by_id, project_by_id, config)

    return Result(
        assignments=assignments,
        unmatched_students=unmatched,
        overall_fit=overall,
        per_project_fit=per_project_fit,
    )
