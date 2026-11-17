# ResearchBridge design

**Status:** Implementation baseline  
**Last updated:** 2026-11-17

## 1. Product strategy

ResearchBridge is an offline-capable, explainable batch-allocation prototype. The demo’s proof is a complete path from editable cohort data to an approved, auditable placement and student follow-through. The product thesis is:

> We do not merely recommend research; we allocate limited research opportunities transparently across the entire cohort.

The implementation favors a dependable P0 vertical slice over optional AI, production identity, or live integrations.

## 2. Primary journeys and information architecture

### Student

1. Dashboard → inspect completeness and next action.
2. Profile → edit interests, skills, goals, hours, schedule, and suggestion consent.
3. Projects → search/filter → inspect a split-pane detail → rank acceptable projects.
4. Submit → enter next batch without immediate allocation.
5. Outcome → inspect approved placement or a specific unplaced reason.
6. Explanation → inspect factor contributions, evidence, gaps, and global-allocation rationale.
7. Roadmap → track 2–4 week tasks without implying mastery.
8. Outreach → edit, copy, or download a grounded draft; never send.

### Faculty

1. Faculty overview → inspect public/fictional provenance and active projects.
2. Project editor → set capacity, requirements, trainable skills, commitment, and schedule.
3. Approved cohort → inspect only approved assigned candidates and match evidence.

### Admin

1. Overview → inspect readiness, submitted cohort, project capacity, and stale state.
2. Data → import/validate, manage profiles/projects, inspect actionable errors.
3. Configuration → set threshold and weights; preview normalization.
4. Run → execute actual scoring and optimizer stages.
5. Review → inspect assignments, unmatched queue, utilization, and explanations.
6. Evidence → compare global, greedy, and FCFS; run 20 shuffles; inspect counterexample.
7. Compare → inspect immutable run differences.
8. Approve → human decision with audit event.
9. Export → download approved results and benchmark evidence.
10. Roadmap → understand hypothetical Workday adoption stages.

### Global navigation

Desktop uses a compact left sidebar with wordmark, synthetic-demo disclosure, role switcher, role-specific primary routes, and About. A contextual top toolbar contains page title, persona context, and the single dominant action. Mobile uses a disclosure-controlled navigation sheet and preserves role context. Deep links use stable entity/run IDs; catalog filters use URL search parameters.

## 3. Architecture

```text
Browser / Playwright
       |
       | JSON over HTTP (typed OpenAPI contract)
       v
Next.js App Router (TypeScript strict)
- server-rendered shell and pages
- client islands for forms, filters, run status, charts
- semantic Tailwind token system
- Radix primitives only where native HTML is insufficient
       |
       | NEXT_PUBLIC_API_URL / server proxy
       v
FastAPI + Pydantic
- role/header checks for demo authorization
- application services
- scoring service
- optimizer and baselines
- roadmap/email deterministic generators
- import/export and audit services
       |
       v
Repository interfaces
- SQLite implementation (demo)
- future PostgreSQL/Supabase adapter seam
       |
       v
SQLite + numbered migrations
```

### Repository layout

```text
/
  app/                     Next.js routes
  components/              shared and feature UI
  lib/                     typed client, demo context, formatting
  public/                  static assets
  backend/
    app/
      api/                 FastAPI routers
      domain/              models and policies
      services/            scoring, matching, evaluation, roadmap
      repositories/        protocols and SQLite implementation
      seed/                deterministic generation and fixtures
    migrations/            ordered SQL migrations
    tests/                 pytest unit/integration/property tests
  e2e/                     Playwright + axe journeys
  docs/                    evidence and operating documentation
  evidence/                generated benchmark JSON/CSV/screenshots
  .kiro/specs/researchbridge/
```

### Runtime choices

- Frontend: Next.js App Router, React, TypeScript strict, Tailwind CSS, Lucide, Recharts.
- Backend: Python FastAPI, Pydantic 2, SQLAlchemy 2, OR-Tools CP-SAT.
- Database: SQLite in WAL mode for local reliability; migrations are explicit SQL and recorded in `schema_migrations`.
- Tests: Vitest for frontend logic where needed, pytest for domain/API, Playwright and axe for end-to-end/accessibility.
- Startup: Docker Compose for one command; documented native `npm` + Python virtual environment alternative.

## 4. Domain schema

All persisted entities use stable string IDs, `schema_version`, `created_at`, and `updated_at`. Run-owned records are immutable after creation except a constrained status transition and stale metadata.

### Core entities

- **Student**: `id`, synthetic marker, display name, major, academic year (display only), interests, hours/week, learning goals, first-time researcher flag, accepts suggestions, profile completeness, batch submission status, synthetic submission order.
- **Faculty**: `id`, display name, department, research interests, provenance type (`public` or `fictional`), source URL, source retrieval date.
- **Project**: `id`, faculty ID, title, description, department, capacity, prerequisites, mentoring availability, commitment hours, term, modality, fixed windows, active, provenance type, source URL/note.
- **Skill**: canonical ID, label, category, aliases.
- **StudentSkill**: student ID, skill ID, proficiency 0–4.
- **ProjectSkill**: project ID, skill ID, required proficiency 0–4, kind (`mandatory` or `trainable`).
- **StudentPreference**: student ID, project ID, positive rank.
- **Availability**: owner type/ID, day, start minute, end minute, fixed flag.
- **MatchRun**: immutable config/input hashes and snapshots, status, stale state, solver evidence, timestamps.
- **PairScore**: run/student/project, eligible, eligibility reasons, five factor scores, contributions, evidence, gaps, missing fields, total quantized score.
- **Assignment**: run/student/project, score integer, canonical tie order, proposed/approved state, global rationale.
- **DecisionAudit**: append-only actor role/persona, event type, entity type/ID, run ID, reason/metadata, timestamp.
- **Roadmap**: student/project/run, placement relationship, week plan, tasks and persisted completion.
- **OutreachDraft**: student/project/run, deterministic source, subject/body, edited body, timestamps.

### Persistence decisions

- Domain services depend on repository protocols rather than SQLAlchemy sessions.
- JSON columns store immutable score evidence/config snapshots; normalized tables store queryable entities and relations.
- Approved run records are never updated by profile edits. New edits add an audit event and stale every affected proposed run.
- Reset requires exact confirmation text and replaces only the local synthetic demo database.
- Names are presentation fields and never used in scoring or tie resolution.

## 5. Deterministic taxonomy and token similarity

The offline baseline uses a versioned taxonomy with canonical skills/interests and aliases. Text is Unicode-normalized, lowercased, punctuation-stripped, tokenized, alias-expanded, de-duplicated, and sorted. Stop words are removed from narrative fields. No demographic/name tokens enter the feature set.

For two token sets `A` and `B`, weighted Jaccard similarity is:

`J(A,B) = sum_t min(w_A(t), w_B(t)) / sum_t max(w_A(t), w_B(t))`

If both sets are empty, the factor is unresolved and receives 0 with a missing-evidence marker. If exactly one set is empty, similarity is 0. Taxonomy-tag exact matches receive weight 2; normalized narrative-token matches receive weight 1. The taxonomy/version and evidence tokens are stored.

## 6. Eligibility

Eligibility is evaluated before compatibility. A pair is eligible only when all checks pass:

1. Project is active.
2. Capacity > 0.
3. Student ranked the project, or `accepts_suggestions=true`.
4. Every mandatory skill/prerequisite has known student evidence at or above required proficiency.
5. Student hours/week ≥ project commitment hours/week.
6. Every genuinely fixed required project window has a student window that fully contains it.
7. Required profile fields used by hard constraints are present.

Unknown mandatory evidence is `unresolved`, not failure by assumption and not eligible. Eligibility reasons use stable machine codes plus natural-language detail. Trainable skills are omitted from hard constraints.

## 7. Compatibility formula

Factor scores are calculated for every pair where sufficient evidence exists, including ineligible pairs for explanation, but only eligible above-threshold pairs enter the optimizer. Each factor is an integer from 0 through 10,000 basis points.

### Interest alignment (default weight 35)

`interest = round_half_up(10000 × weighted_jaccard(student_interest_tokens, project_interest_tokens))`

Zero denominator: 0 and `missing_interest_evidence`.

### Technical skill overlap (default weight 25)

This factor measures all listed project skills, mandatory and trainable, without turning trainable gaps into exclusions.

For each project skill `k` with target `r_k` in 1–4 and known student proficiency `p_k` in 0–4:

`coverage_k = min(p_k / r_k, 1)`

Mandatory skills have factor weight 1.0 and trainable skills 0.75. Missing student proficiency is treated as 0 for compatibility and recorded as a gap. Then:

`skill = round_half_up(10000 × sum(weight_k × coverage_k) / sum(weight_k))`

Zero project skills: 5,000 neutral basis points and `no_project_skill_evidence`, avoiding an automatic perfect score.

### Availability beyond hard minimum (default weight 20)

For eligible pairs:

- `hours_surplus = clamp((student_hours - project_hours) / max(project_hours, 1), 0, 1)`
- `window_overlap = overlap_minutes(student_windows, mentoring_windows) / max(total_mentoring_minutes, 1)`
- If no non-fixed mentoring windows are published, `window_overlap = 0.5` and a neutral-evidence marker is recorded.
- `availability = round_half_up(10000 × (0.6 × hours_surplus + 0.4 × window_overlap))`

Ineligible hard-hour/window pairs keep the measured value for explanation but cannot enter allocation.

### Ranked preference (default weight 10)

For `n` ranked acceptable projects and rank `r`:

- if `n=1`, ranked project score = 10,000;
- otherwise `preference = round_half_up(10000 × (n-r)/(n-1))`.

An unranked suggestion receives 2,500 if suggestions are accepted. If no preferences exist and suggestions are accepted, all suggestions receive 2,500 plus `unknown_preference`.

### Learning-goal alignment (default weight 10)

`goal = round_half_up(10000 × weighted_jaccard(student_goal_tokens, project_trainable_skill_and_mentoring_tokens))`

When no student goals or no trainable/mentoring evidence exists, score 0 and record the missing side. The system does not infer a goal.

### Weight normalization and total

Raw weights must be finite nonnegative decimals with a positive sum. For each factor:

`normalized_weight_i = raw_weight_i / sum(raw_weights)`

`contribution_i_bp = round_half_up(factor_i_bp × normalized_weight_i)`

To prevent component rounding drift, total basis points are calculated once from exact `Decimal` products and rounded half-up:

`total_bp = round_half_up(sum(factor_i_bp × raw_weight_i) / sum(raw_weights))`

Display score is `total_bp / 100` with two decimals. The optimizer coefficient is `total_bp` (0–10,000), so no floating-point value enters CP-SAT. Threshold 60 becomes 6,000 basis points. Score version is `rb-score-v1`.

## 8. Optimizer

For canonical sorted students `i` and projects `j`, create binary `x_ij` only for eligible edges with `total_bp >= threshold_bp`.

Constraints:

- Student: `sum_j x_ij <= 1`.
- Project: `sum_i x_ij <= capacity_j`.
- Unplaced students are allowed.

### Staged lexicographic process

Each stage receives sorted input, CP-SAT random seed `731`, `num_search_workers=1`, no random branching, and an explicit time limit. A stage result is only called optimal when CP-SAT returns `OPTIMAL`.

1. **Coverage:** maximize `C = sum_ij x_ij`. Record `C*`. Add `C = C*` only if proven optimal. If merely feasible at timeout, stop and retain status `feasible_not_proven`; later lexicographic claims are skipped.
2. **Total compatibility:** maximize `S = sum_ij total_bp_ij × x_ij` subject to `C=C*`. Record `S*`; continue only if optimal.
3. **Floor:** when `C*>0`, introduce integer `m` and constrain `m <= score_ij + M(1-x_ij)` for each edge (`M=10000`), then maximize `m` with `C=C*`, `S=S*`. Record `m*`; continue only if optimal. Empty assignments use `m*=null`.
4. **Canonical seeded lottery:** derive each student-project edge key from `SHA-256("rb-tie-v1|731|student_id|project_id")`; sort by digest then stable IDs. With all prior optimum equalities fixed, iterate edges in that order. For each edge, test whether `x_ij=1` remains feasible. Fix to 1 if feasible; otherwise fix to 0. This sequential variable fixing produces one fully specified assignment independent of ingestion order without using names or submission times.

The run records every status, wall time, objective, timeout, seed, worker count, and input/config hash. Feasible time-limited results are reviewable but visibly not proven optimal.

## 9. Unplaced reasons

Reason derivation is deterministic and may provide multiple codes in priority order:

1. `missing_data`: unresolved hard-constraint fields exist.
2. `no_eligible_projects`: no pair passed eligibility.
3. `below_threshold`: one or more eligible pairs exist but all score below threshold.
4. `capacity_competition`: at least one above-threshold feasible edge exists but none selected.

For capacity competition, the explanation says the batch optimizer used limited capacity to improve the stated cohort objectives. It does not identify or compare against another student.

## 10. Baselines and metrics

All strategies use the same frozen run snapshot.

- **FCFS simulation:** process students by synthetic submission order, then stable ID. Select each student’s highest-scoring feasible edge, breaking ties by project stable ID. This is labeled simulation and is not used as a claim about current EUReCA operations.
- **Greedy:** sort all feasible above-threshold edges by descending score, then canonical tie key; accept when student and capacity remain.
- **Global:** staged CP-SAT result above.

Metrics:

- Placement rate submitted = assigned / submitted students.
- Placement rate eligible = assigned / students with ≥1 eligible above-threshold edge.
- Mean = arithmetic mean assigned score.
- Median = conventional midpoint median.
- Bottom decile = nearest-rank 10th percentile: sorted ascending value at `ceil(0.10n)`, 1-indexed.
- Minimum = minimum assigned score; null for empty assignment.
- Top-choice rate = assigned to rank 1 / assigned students who supplied at least one rank.
- First-time placement rate = assigned first-time students / submitted first-time students, with counts.
- Major rate = assigned in major / submitted in major, with counts; groups `<5` receive a small-group warning.
- Constraint violations = count of capacity, eligibility/threshold, and duplicate-student violations, expected zero.
- Runtime = measured monotonic wall-clock milliseconds for each strategy.

### Shuffle evidence

Generate 20 deterministic permutations with seeds 1–20, rerun global allocation against each, canonicalize `(student_id, project_id)` pairs, and compare with the reference. Persist and display actual pass count and failing seeds. This establishes input-order invariance for this dataset, not comprehensive fairness.

### Counterexample

Capacities P1=P2=1. A has P1=95, P2=90. B has P1=94 and no P2 edge. Greedy edge order selects A→P1 and places one. Global maximizes count first, selecting A→P2 and B→P1, placing two.

## 11. Run lifecycle and consistency

`validating → scoring → optimizing_coverage → optimizing_quality → optimizing_floor → resolving_ties → evaluating → proposed`

Stages are emitted only when actually reached. Failures end in `failed` with a useful message. Approval is a transaction from `proposed` to `approved`. New profile/project changes mark relevant proposed runs `stale`; stale drafts cannot be approved. Approved snapshots remain readable and unchanged.

Idempotency keys protect import, run creation, approval, export recording, and reset. Duplicate keys return the original result where safe.

## 12. API outline

All endpoints are prefixed `/api/v1`; health endpoints do not require role headers. Demo requests use `X-Demo-Role` and `X-Demo-Persona-Id`; the server checks permitted route/record access. The role mechanism is a demo guard, not production authentication.

- `GET /health/live`, `GET /health/ready`
- `GET /demo/personas`
- `GET/PATCH /students/{id}`, `POST /students/{id}/submit`
- `GET /students/{id}/recommendations`, `GET /students/{id}/outcome`
- `GET /projects`, `GET /projects/{id}`, `POST/PATCH /projects`
- `GET /faculty/{id}/assignments`
- `GET/PATCH /config`, `POST /config/preview`
- `POST /runs`, `GET /runs`, `GET /runs/{id}`, `POST /runs/{id}/approve`
- `GET /runs/{id}/comparison/{other_id}`
- `POST /runs/{id}/shuffle-test`, `GET /runs/{id}/evidence`
- `GET /runs/{id}/export.csv`, `GET /runs/{id}/export.json`
- `GET /students/{id}/roadmap`, `PATCH /roadmaps/{id}/tasks/{task_id}`
- `GET/PATCH /students/{id}/outreach`, `GET /students/{id}/outreach.txt`
- `POST /imports/validate`, `POST /imports`
- `GET /audit`
- `POST /demo/reset` (confirmation required)

OpenAPI is the source for generated or hand-maintained matching TypeScript contracts. Errors use `{code, message, field_errors?, request_id}` and contain no sensitive payload.

## 13. Source adapter seam

```python
class SourceAdapter(Protocol):
    source_name: str
    schema_version: str
    def validate(self, payload: bytes, media_type: str) -> ValidationReport: ...
    def load_snapshot(self, payload: bytes, media_type: str) -> SourceSnapshot: ...
```

The demo adapter reads local JSON/CSV. A `MockWorkdayAdapter` demonstrates a hypothetical contract only: opaque external person/project IDs, effective term, enrollment/affiliation status, approved fields, and change cursor. It never performs network calls. Any real adapter requires approved interfaces, SSO/service identity, field mapping, least privilege, consent/notice, privacy review, retention/deletion policy, monitoring, and audit controls.

## 14. Roadmap and outreach

Roadmap generation compares actual student proficiency to project mandatory/trainable targets. A gap records source requirement and never asserts mastery. Tasks use deterministic templates selected by skill category, target level, and hours/week. Total effort is capped at four weeks of student availability and split into weekly deliverables. Verified public resources include source/retrieval date; otherwise copy says “Generic learning suggestion.”

The outreach template uses only persisted synthetic facts. It includes a subject, salutation, interest connection, demonstrated skills, an honest gap/learning plan when present, recorded availability, and a request to discuss. It never states acceptance. Editing persists locally; copy uses Clipboard API with accessible status; download returns plain text. There is no recipient field or send endpoint.

## 15. Visual system

- Canvas `#FBFBF9`, surface `#FFFFFF`, secondary `#F4F4F0`.
- Text `#191919`, secondary `#525252`, muted `#6B6B6B`, divider `#E5E5E0`.
- Brand accent `#A6192E` with separately tested hover/pressed/focus tokens.
- Semantic success, warning, error, and info colors are independent and paired with text/icon/pattern labels.
- Space Grotesk headings; Public Sans body; JetBrains Mono for solver IDs and numerical evidence.
- 4px spacing foundation; compact content width; radii 6/8/12px; shadows only for overlays.
- Directly labeled horizontal bars, tables, and text alternatives instead of decorative chart dashboards.
- One dominant action per task area. No gradients, glass, ornamental blobs, sparkle/AI motifs, oversized stats, gratuitous cards, or routine spinners.

## 16. Responsive and state behavior

- 360/390: mobile header, navigation sheet, single primary column, project list/detail routes rather than cramped split pane, tables become labeled row groups or controlled horizontal regions with explicit affordance.
- 768: compact navigation and two-column forms where fields fit.
- 1024+: fixed compact sidebar and contextual toolbar; project catalog uses list/detail split pane.
- 1280–1920: content width and columns expand selectively; line lengths remain controlled.

Every primary view designs default, focus, loading skeleton, empty, partial, recoverable error, success/status, offline, and permission states. Existing content remains during refresh. Reduced motion disables pulses/transitions. All common mobile targets are at least 44×44px.

## 17. Security and privacy

- Synthetic-only banners and provenance labels are visible in app, exports, screenshots, and docs.
- Pydantic validates request boundaries; SQL uses ORM/parameters; React escapes text by default; no unsanitized HTML.
- Secrets live in environment variables and never in `NEXT_PUBLIC_*` unless truly public configuration.
- Logs use stable IDs, request IDs, counts, and timings, not names/profile bodies.
- URLs carry filters and opaque IDs, not profile details.
- Role checks happen in API dependencies, while documentation clearly states production authorization is absent.
- No email sending, external record mutation, automated faculty contact, or live Workday call exists.
- Reset and any future destructive action require explicit confirmation.
- These are FERPA-conscious safeguards, not a legal-compliance or certification claim.

## 18. Validation strategy

### Backend

- Scoring formula/unknown/zero denominator/weight validation tests.
- Eligibility reason and hard-vs-trainable tests.
- Counterexample, thresholds, ties, empty cohort, no capacity, infeasible edges.
- Randomized seeded capacity/eligibility/no-duplicate property tests.
- Brute-force cross-check on small instances.
- Input order/shuffle determinism.
- API journey, approval/stale lifecycle, export, import errors, reset confirmation, persistence.

### Frontend and end to end

- Typecheck, lint, production build.
- Student edit → faculty edit → admin run → audit → approval → student outcome → roadmap → outreach.
- Search/filter/deep link, validation/error states, rerun/compare, export.
- Playwright keyboard checks and axe scans.
- Screenshots at 360, 390, 768, 1024, 1280, 1440, 1920; inspect overflow, contrast, wrapping, focus, state geometry, and consistency.

Only executed evidence is recorded in `docs/TEST_REPORT.md` and `evidence/`.

## 19. Key trade-offs

- A single root Next app plus contained Python service is simpler for a hackathon than a workspace orchestrator, while preserving clear contracts.
- SQLite maximizes reproducibility; repository protocols postpone PostgreSQL complexity.
- Deterministic taxonomy similarity is less semantically rich than embeddings but inspectable and offline.
- Sequential tie fixing costs solver calls but produces a defensible complete canonical result at this cohort size.
- Synthetic benchmark evidence validates mechanics and proxies, not causal operational impact or demographic fairness.
