# ResearchBridge algorithm

ResearchBridge computes an explainable compatibility record for every submitted student–project pair, then proposes one cohort-wide allocation. Eligibility, compatibility, and allocation are separate steps.

Current versions:

- Score: `rb-score-v1`
- Taxonomy: `rb-taxonomy-v1`
- Solver seed: `731`
- Worker count: `1`
- Default threshold: `60.00`, stored as `6000` basis points

The output is a **compatibility index**, not an acceptance probability or a prediction of research potential.

## 1. Frozen run input

A run loads all submitted synthetic students, all project records, and the skill taxonomy. It validates stable IDs and project-skill references, serializes a canonical input snapshot, and records its SHA-256 hash. Profile, project, configuration, or import changes after this point mark a proposed run stale rather than changing it silently.

Pair scoring iterates students and projects by sorted stable ID. Names and ingestion order do not control iteration.

## 2. Eligibility

A pair is eligible only when every hard rule passes:

1. The project is active.
2. Capacity is positive.
3. The student ranked the project or explicitly accepted suggestions.
4. Every mandatory skill and prerequisite has known evidence at or above its required proficiency.
5. Student hours per week meet the project commitment.
6. Every fixed required project window is fully contained in a recorded student availability window.

Unknown mandatory evidence is recorded as unresolved and the pair is ineligible. ResearchBridge does not infer ability, availability, or potential. Trainable skills are not hard requirements.

The scorer still calculates compatibility factors for ineligible pairs so the run can explain evidence and gaps. Only eligible pairs at or above the threshold become optimizer edges.

## 3. Deterministic text evidence

Text is Unicode NFKC-normalized, case-folded, stripped to alphanumeric tokens, and matched against a versioned taxonomy and aliases. Common stop words are removed from tokenized narrative fields. Exact explicit taxonomy tags receive weight 2; other normalized matches receive weight 1.

For token-weight maps `A` and `B`, weighted Jaccard similarity is:

```text
J(A, B) = Σ min(A[t], B[t]) / Σ max(A[t], B[t])
```

If both sides are empty, the denominator is unresolved. The factor receives zero and a missing-evidence marker. If only one side is empty, similarity is zero.

## 4. Compatibility factors

Each factor is calculated as an integer from 0 to 10,000 basis points. One hundred basis points equal one displayed index point.

### Interest alignment: default weight 35

```text
interest = round_half_up(10000 × weighted_jaccard(student interests, project interests))
```

Matched tokens and both token maps are retained as evidence. No evidence on either side produces zero and `missing_interest_evidence`.

### Technical skill overlap: default weight 25

For project skill `k`, with target proficiency `r_k` and known student proficiency `p_k`:

```text
coverage_k = min(p_k / r_k, 1)
```

Mandatory skills have factor weight `1.0`; trainable skills have factor weight `0.75`.

```text
technical = round_half_up(
  10000 × Σ(factor_weight_k × coverage_k) / Σ(factor_weight_k)
)
```

Missing student proficiency contributes zero coverage and is recorded as a gap. A project with no listed skills receives a neutral 5,000 basis points and a `no_project_skill_evidence` marker rather than an automatic perfect score.

### Availability beyond the hard minimum: default weight 20

For an eligible hours relationship:

```text
hours_surplus = clamp(
  (student_hours - project_hours) / max(project_hours, 1),
  0,
  1
)

window_overlap = overlapping mentoring minutes / total mentoring minutes

availability = round_half_up(
  10000 × (0.6 × hours_surplus + 0.4 × window_overlap)
)
```

Fixed required windows are handled by eligibility. This factor uses non-fixed mentoring windows. If none are published, window overlap receives a neutral `0.5` and the handling is recorded. Missing student hours contributes zero surplus and a missing-field marker.

### Ranked preference: default weight 10

For `n` ranked projects and rank `r`:

```text
if n = 1: preference = 10000
otherwise: preference = round_half_up(10000 × (n - r) / (n - 1))
```

An unranked project receives 2,500 basis points only when the student accepted suggestions. If the student accepted suggestions but supplied no ranking, the score also records `unknown_preference`.

### Learning-goal alignment: default weight 10

```text
goal = round_half_up(
  10000 × weighted_jaccard(
    student learning-goal tokens,
    project trainable-skill and mentoring tokens
  )
)
```

Missing goals or missing trainable/mentoring evidence produces zero and records the missing side. No goal is inferred.

## 5. Weight normalization and rounding

Raw weights must be finite, nonnegative decimals, with at least one positive value. Negative values and an all-zero set are rejected with validation errors.

```text
normalized_weight_i = raw_weight_i / Σ raw_weights
contribution_i_bp = round_half_up(factor_i_bp × normalized_weight_i)
```

The total is calculated once from exact decimal products to avoid contribution-rounding drift:

```text
total_bp = round_half_up(
  Σ(factor_i_bp × raw_weight_i) / Σ raw_weights
)

display_index = total_bp / 100
```

No floating-point score enters optimization. A configuration preview returns normalized percentages but does not modify stored scores; changed scores belong to a new run.

## 6. Cohort-wide allocation

Create a Boolean decision variable `x[i,j]` only for an eligible pair whose score meets the threshold.

Constraints:

```text
for each student i:  Σ_j x[i,j] ≤ 1
for each project j:  Σ_i x[i,j] ≤ capacity[j]
```

Students may remain unplaced.

The optimizer solves four stages in strict order:

1. **Coverage:** maximize assignment count `C`.
2. **Total compatibility:** fix `C = C*`, then maximize total assigned basis points `S`.
3. **Score floor:** fix `C = C*` and `S = S*`, then maximize the minimum assigned score.
4. **Canonical tie resolution:** fix all previous optima, order edges by `SHA-256("rb-tie-v1|731|student_id|project_id")`, then sequentially fix each remaining variable to 1 when feasibility can be retained, otherwise 0.

Each optimization call uses seed 731, one worker, integer coefficients, sorted stable IDs, and randomized search disabled. Stable IDs, not names or submission timestamps, resolve genuine ties.

A stage is called optimal only when its optimum is proven. If a stage returns only a time-limited feasible result, later lexicographic claims are skipped and the run records an optimality limitation. The configured timeout applies per solve, including tie-feasibility checks.

## 7. Unplaced reasons

Reasons are deterministic and may be combined:

- `missing_data`: at least one hard requirement remains unresolved.
- `no_eligible_projects`: no project passes eligibility.
- `below_threshold`: eligible pairs exist, but none meet the score threshold.
- `capacity_competition`: an above-threshold edge exists, but none is selected under the cohort objectives.

Capacity explanations refer to cohort-level objectives and do not disclose another student’s details.

## 8. Baselines

All comparisons use the same frozen eligibility records, pair scores, capacities, and threshold.

- **Synthetic FCFS simulation:** process students by seeded synthetic submission order, then stable ID; choose the highest-scoring remaining edge.
- **Greedy:** process eligible above-threshold edges by descending score, then seeded canonical tie order.
- **Global:** use the staged cohort-wide process above.

Metrics include submitted- and eligible-cohort placement rates, mean, median, nearest-rank bottom decile, minimum score, top-choice rate, first-time-researcher rate, major rates with denominators, unplaced reasons, constraint violations, and measured runtime.

## 9. Recorded seed result

For seed 731:

| Strategy | Placements | Submitted rate | Eligible count | Mean | Median | Minimum | Violations |
|---|---:|---:|---:|---:|---:|---:|---:|
| Global | 27 | 45.0% | 47 | 88.37 | 89.59 | 82.64 | 0 |
| Greedy | 27 | 45.0% | 47 | 88.37 | 89.59 | 82.64 | 0 |
| Synthetic FCFS | 27 | 45.0% | 47 | 87.96 | 87.64 | 82.64 | 0 |

The global strategy does not improve placement count over greedy on this un-tuned seed. A 20-permutation shuffle check produced the exact same global assignments 20/20 times.

The explicit counterexample demonstrates why the global objective still matters:

```text
A → P1: 95
A → P2: 90
B → P1: 94
capacities: P1 = 1, P2 = 1
```

Highest-edge greedy selects A→P1 and places one student. Count-first global allocation selects A→P2 and B→P1 and places two.

Reproduce checked-in benchmark artifacts with:

```bash
npm run evidence:benchmark
```

See [`backend/evidence/seeded-benchmark.json`](../backend/evidence/seeded-benchmark.json) and [`backend/evidence/seeded-benchmark.csv`](../backend/evidence/seeded-benchmark.csv). These synthetic results establish mechanics only; they do not establish actual rematching reduction or demographic fairness.
