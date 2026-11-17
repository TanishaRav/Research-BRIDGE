# ResearchBridge implementation tasks

**Execution status:** demo-ready P0 vertical slice implemented and verified
**Status key:** `[x]` verified, `[!]` implemented with disclosed gap, `[ ]` optional/deferred
**Final verification:** 2026-11-17

## Milestone 0 — Product contract and repository baseline (P0)

- [x] Inspect greenfield repository, git state, and existing conventions.
- [x] Attempt supplied sources; record inaccessible Google document body and accessible EUReCA homepage.
- [x] Write testable EARS requirements, architecture/design, dependency-ordered tasks, assumptions, and open stakeholder questions.
- [x] Persist complete product-design and domain/security standards in `.kiro/steering/`.
- [x] Scaffold locked Next.js/TypeScript and FastAPI/Python applications without replacing useful work.
- [x] Verify toolchain, install, health baseline, frontend typecheck, lint, and production build.

## Milestone 1 — Deterministic domain engine and persistence (P0)

- [x] SQLite schema, numbered migration runner, WAL settings, schema versions, and timestamps.
- [x] Strict Pydantic domain/API models and repository protocols.
- [x] SQLite repositories, transaction boundaries, append-only audit, immutable snapshots, and stale-draft invalidation.
- [x] Versioned taxonomy, normalization, token similarity, Decimal scoring, evidence, gaps, and missing fields.
- [x] Separate eligibility matrix with unresolved mandatory evidence and stable reason codes.
- [x] Four-stage CP-SAT optimizer with count/quality/floor objectives, canonical SHA-256 tie fixing, one worker, seed 731, and honest status.
- [x] FCFS and greedy baselines, exact metrics, constraint checks, 20-run shuffle test, and required counterexample.
- [x] Reproducible seed 731 with exactly 60 students, 20 projects, 10 fictional faculty, 18 skills, and adversarial cases.
- [x] Backend unit/property/brute-force/migration/seed/config suite: 27 passed.

## Milestone 2 — API and complete state transitions (P0)

- [x] Liveness/readiness and demo-persona endpoints.
- [x] Server-side demo-role and record-level guards.
- [x] Student profile/submission/recommendations/outcome; project catalog; faculty project/approved-assignment endpoints.
- [x] Config preview, run stages/review/stale prevention/approval/compare/audit endpoints.
- [!] JSON import validation/apply, idempotency, and explicit reset are implemented. CSV import is not; CSV export is implemented.
- [x] Benchmark, shuffle, approved JSON/CSV exports with synthetic/run/source metadata.
- [x] Deterministic roadmap/progress and editable outreach/text download with no send path.
- [x] Live full API journey and structured error/role checks verified.

## Milestone 3 — Application foundation and design system (P0)

- [x] Responsive shell, skip link, role/persona switcher, role navigation, contextual headers, mobile navigation, and synthetic disclosure.
- [x] Semantic palette/type/spacing/radius/motion tokens with bundled Space Grotesk, Public Sans, and JetBrains Mono.
- [x] Accessible buttons, fields, status callouts, panels, skeletons, tables, filters, score bars, and empty/error states.
- [x] Typed API client, cancellation, error mapping, stable refresh, demo context, and error boundary.
- [x] About/privacy/methodology page and permission/offline messaging.
- [x] Typecheck/build pass; full automated axe matrix passes.

## Milestone 4 — Three working role journeys (P0)

- [x] Student dashboard, editable core profile, completeness, validation, and batch submission.
- [!] Search/filter catalog, URL state, responsive list/detail, provenance, and ranking work. Schedule-day UI filter and direct rank reordering remain disclosed gaps.
- [x] Student recommendations/outcome, compatibility decomposition, evidence/gaps, and global rationale.
- [!] Faculty project list/editor and approved candidates work. Prerequisites and full mentoring/schedule authoring remain API-only gaps.
- [!] Admin readiness, JSON import validation, and project/cohort evidence work. Dedicated student-management and CSV-import UI are not implemented.
- [!] Admin config/run/review/utilization/unmatched/approval/export/audit work. Run comparison exists in API/client but has no visible compare control.
- [x] Actual baseline metrics, exact denominators, 20/20 shuffle result, counterexample, limitations, and evidence files.
- [!] Placed-student roadmap/progress and outreach edit/copy/download work. The backend supports an unplaced aspirational roadmap, but the current UI does not render it.
- [x] Visible actions were exercised; authenticated exports replaced non-working direct links.

## Milestone 5 — Documentation, evidence, and demo operation (P0)

- [x] `.env.example`, native setup/start, deterministic seed/reset, health, troubleshooting, and deployment boundaries.
- [x] `USER_JOURNEYS.md`, `ALGORITHM.md`, `FAIRNESS.md`, `WORKDAY_ROADMAP.md`, and `DATA_PROVENANCE.md` with data dictionary/source manifest links.
- [x] 3–4 minute `DEMO.md` with reset and judge path.
- [x] Actual benchmark JSON/CSV regenerated from reset seed.
- [x] `LIMITATIONS.md` records unsupported claims, open questions, demo-auth boundary, and unimplemented work.
- [x] Root README documents verified setup, operation, tests, evidence, architecture, and privacy.
- [x] Frontend lockfile and fully resolved Python `requirements.lock` recorded.

## Milestone 6 — Full verification and visual refinement (P0/P1)

- [x] Backend suite: 27 passed, 1 dependency deprecation warning.
- [x] Frontend: 8 unit tests passed; typecheck, lint (0 errors/7 warnings), and production build passed.
- [x] Playwright: 6 passed, including student edit → faculty edit → batch → shuffle → export → audit → approval → outcome → roadmap → outreach.
- [x] Live API path verified validation, role denial, rerun lifecycle, persistence, approval, and JSON/CSV export.
- [!] 25 automated axe scans and automated keyboard smoke pass. Human screen-reader/manual keyboard certification remains pending and is not claimed.
- [x] 43 screenshots captured across 360, 390, 768, 1024, 1280, 1440, and 1920 targets; all routes covered at 390/1440.
- [x] Screenshot review found and fixed primary-button contrast, selected-row contrast, and skip-link focus transfer.
- [x] Five-run local production timing sample recorded; no unsupported field/p75 claim.
- [x] `TEST_REPORT.md`, screenshot report, quality report, benchmark evidence, and limitations updated with actual results.
- [x] Acceptance criteria rechecked; remaining gaps are explicitly listed here and in `docs/LIMITATIONS.md`.

## P1/P2 deferred after the demo-ready vertical slice

- [ ] Human assistive-technology review and hosted visual regression/CI.
- [ ] Full availability/mentoring authoring, direct preference reorder, run-comparison UI, CSV import, and richer cohort management.
- [ ] Larger-cohort load measurement and production identity design implementation.
- [ ] Optional local sentence-transformer adapter with cached/versioned fallback.
- [ ] Optional server-side LLM wording adapter with minimal synthetic context and deterministic fallback.
- [ ] Audited manual override with reason and eligibility/capacity validation.
- [ ] PostgreSQL/Supabase repository implementation.
