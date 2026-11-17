# ResearchBridge implementation tasks

**Execution mode:** dependency-ordered milestones  
**Status key:** `[ ]` queued, `[-]` active, `[x]` verified, `[!]` blocked/deferred  
**Last updated:** 2026-11-17

The vertical slice is P0. Each milestone ends with an executed verification command and fixes before the next milestone. Evidence is recorded rather than inferred.

## Milestone 0 — Product contract and repository baseline (P0)

- [x] 0.1 Inspect repository, git state, existing conventions, and preserve existing work.
- [x] 0.2 Attempt supplied requirement sources; record Google document access limitation and EUReCA public source.
- [x] 0.3 Write EARS-style `requirements.md` with assumptions, open stakeholder questions, priorities, and boundaries.
- [x] 0.4 Write `design.md` covering architecture, schema, formulas, optimizer, journeys, API, fairness, UX, privacy, and validation.
- [x] 0.5 Persist the complete product design standard and domain/security rules in `.kiro/steering/`.
- [-] 0.6 Scaffold locked Next.js/TypeScript and FastAPI/Python projects without replacing useful repository files.
- [ ] 0.7 Verify native toolchain, clean install, frontend baseline build, and backend import/health baseline.

## Milestone 1 — Deterministic domain engine and persistence (P0)

- [ ] 1.1 Create SQLite schema and migration runner for all required entities, schema versions, and timestamps.
- [ ] 1.2 Define Pydantic domain/API models and repository protocols.
- [ ] 1.3 Implement SQLite repositories, transaction boundaries, append-only audit, immutable run snapshots, and stale-draft invalidation.
- [ ] 1.4 Implement versioned skill taxonomy, normalization, deterministic token similarity, exact Decimal score arithmetic, and explanation evidence.
- [ ] 1.5 Implement eligibility matrix with unresolved mandatory information and stable reason codes.
- [ ] 1.6 Implement CP-SAT staged optimizer, proven-optimum handling, canonical seeded tie fixing, and unplaced reasons.
- [ ] 1.7 Implement FCFS and greedy baselines, metrics, constraint checks, 20-run shuffle test, and minimal counterexample.
- [ ] 1.8 Implement reproducible 60-student/20-project seed, adversarial fixture, source manifest, and import validation.
- [ ] 1.9 Run backend unit/property/brute-force/migration/seed tests and fix failures.

## Milestone 2 — API and complete state transitions (P0)

- [ ] 2.1 Implement live/readiness health and demo-persona endpoints.
- [ ] 2.2 Implement server-checked demo-role dependencies and record-level access checks.
- [ ] 2.3 Implement student profile, project catalog/preference, submission, faculty project, and approved-assignment endpoints.
- [ ] 2.4 Implement config preview, run lifecycle/stages, review, stale prevention, approval, compare, and audit endpoints.
- [ ] 2.5 Implement import validate/apply, idempotency, explicit reset, and useful structured errors.
- [ ] 2.6 Implement benchmark/shuffle and CSV/JSON exports with run/source metadata.
- [ ] 2.7 Implement deterministic roadmap/progress and outreach edit/copy/download data endpoints with no send path.
- [ ] 2.8 Run API integration journey and error-path tests; fix failures.

## Milestone 3 — Application foundation and design system (P0)

- [ ] 3.1 Build responsive application shell, skip link, role/persona switcher, role navigation, contextual toolbar, mobile navigation, and synthetic-data disclosure.
- [ ] 3.2 Establish semantic color/type/spacing/radius/motion tokens, local/bundled fonts, focus system, and reduced-motion behavior.
- [ ] 3.3 Build accessible buttons, fields, select/checkbox, status callout, dialog/sheet, skeleton, table, filter controls, score bar, and empty/error states.
- [ ] 3.4 Add typed API client, demo context, request cancellation/error mapping, stable refresh behavior, and error boundaries.
- [ ] 3.5 Implement About/privacy/methodology page and permission/offline messaging.
- [ ] 3.6 Run frontend lint/typecheck/build and component-level accessibility checks; fix failures.

## Milestone 4 — Three working role journeys (P0)

- [ ] 4.1 Student dashboard, editable profile, profile completeness, inline validation, and batch submission.
- [ ] 4.2 Searchable/filterable project catalog, URL state, responsive list/detail treatment, source links, and preference ranking.
- [ ] 4.3 Student recommendations/outcome, score decomposition, evidence/gaps, and global-allocation explanation.
- [ ] 4.4 Faculty profile/project list/editor with mandatory/trainable skills, capacity/schedule validation, and post-approval candidates.
- [ ] 4.5 Admin readiness overview, import validation, cohort/project management, and actionable state messaging.
- [ ] 4.6 Admin config preview, real run stages, run review, capacity utilization, unmatched queue, approval, compare, export, and audit.
- [ ] 4.7 Admin fairness evidence, actual baselines, exact denominators, shuffle pass count, counterexample, limitations, and downloadable evidence.
- [ ] 4.8 Student placement/unplaced roadmap, persisted task progress, grounded outreach editor, copy feedback, and plain-text download.
- [ ] 4.9 Verify every visible action works and remove placeholder/dead/fake controls.

## Milestone 5 — Documentation, evidence, and demo operation (P0)

- [ ] 5.1 Add `.env.example`, Docker Compose, native setup, seed/reset, one-command start, health, and troubleshooting documentation.
- [ ] 5.2 Write `docs/USER_JOURNEYS.md`, `ALGORITHM.md`, `FAIRNESS.md`, `WORKDAY_ROADMAP.md`, `DATA_PROVENANCE.md`, and data dictionary.
- [ ] 5.3 Write 3–4 minute `docs/DEMO.md` with exact reset and judge path.
- [ ] 5.4 Generate actual benchmark JSON/CSV and preserve reproducible command.
- [ ] 5.5 Document limitations, unsupported claims, open questions, demo auth boundary, and unimplemented P1/P2 work.
- [ ] 5.6 Replace root README with complete local/deployment guidance supported by actual configuration.

## Milestone 6 — Full verification and visual refinement (P0/P1)

- [ ] 6.1 Run backend unit/integration/property suite and record counts/duration.
- [ ] 6.2 Run frontend typecheck, lint, tests, and production build; record outcomes.
- [ ] 6.3 Run end-to-end student → faculty → admin run → audit → approval → outcome → roadmap → email journey.
- [ ] 6.4 Run exports, validation, failure, rerun, comparison, duplicate-action, reset-confirmation, and persistence journeys.
- [ ] 6.5 Run Playwright axe scans and manual keyboard navigation checklist.
- [ ] 6.6 Capture screenshots at 360, 390, 768, 1024, 1280, 1440, and 1920 widths.
- [ ] 6.7 Inspect screenshots for overflow, wrapping, alignment, typography, density, focus, contrast, z-index, loading geometry, and generic-template patterns; fix defects and repeat checks.
- [ ] 6.8 Measure supported performance/build evidence and avoid unsupported percentile claims.
- [ ] 6.9 Write `docs/TEST_REPORT.md` with actual commands/results and `docs/LIMITATIONS.md` with all known gaps.
- [ ] 6.10 Re-read master acceptance criteria and verify every claimed deliverable/path/value before completion report.

## P1 after the vertical slice is sound

- [ ] 7.1 Improve refresh preservation, URL-backed state, slow/offline behavior, and long-content handling.
- [ ] 7.2 Add visual regression baselines and CI when supported by the repository host.
- [ ] 7.3 Add stronger import UX, pagination, and larger-cohort performance measurement.
- [ ] 7.4 Add production-auth integration design details without pretending implementation.

## P2 optional, explicitly deferrable

- [ ] 8.1 Add local sentence-transformer adapter with versioned cached embeddings and deterministic fallback.
- [ ] 8.2 Add optional server-side LLM wording adapter with minimal synthetic context, schema validation, timeout, and template fallback.
- [ ] 8.3 Add audited manual override with reason and capacity/eligibility validation.
- [ ] 8.4 Add PostgreSQL/Supabase repository implementation only after SQLite remains fully verified.
