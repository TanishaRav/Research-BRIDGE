# ResearchBridge test report

**Final verification date:** 2026-11-17  
**Environment:** macOS arm64, Node 25.6.0, npm 11.8.0, Python 3.13.7, Chromium 159 via Playwright  
**Scope:** local synthetic-data prototype only

This report records commands that were actually executed. ResearchBridge is not an official Iowa State service, and these checks do not establish production readiness, legal compliance, real-world impact, or demographic fairness.

## Final results

| Check | Command | Result |
|---|---|---|
| TypeScript | `npm run typecheck` | **Passed**, 0 errors. |
| ESLint | `npm run lint` | **Passed**, 0 errors and 7 documented `react-hooks/set-state-in-effect` warnings for cancellation-guarded loader/form synchronization effects. |
| Frontend unit tests | `npm run test` | **8 passed** in 708 ms. One Vite config-loader warning. |
| Backend unit/property tests | `npm run test:backend` | **27 passed** in 1.35 s. One Starlette `TestClient`/httpx deprecation warning. |
| Production build | `npm run build` | **Passed**. 15 static application routes generated. |
| Browser end to end | `npm run test:e2e` | **6 passed** in 5.8 s. Includes the complete student edit → faculty edit → admin run/shuffle/export/approval/audit → approved student outcome/roadmap/outreach journey. |
| Responsive screenshot matrix | `node e2e/_shots.mjs` | **43 screenshots**, every navigation HTTP 200, **0 page errors**. |
| Automated axe matrix | `node e2e/_shots.mjs` | **25 scans**, **0 violations** for configured WCAG A/AA tags after fixes. |
| Keyboard smoke | `node e2e/_quality.mjs` | **Passed**: skip link first, focus transferred to `main-content`, mobile menu opened using Tab/Enter, focus sequence remained operable. This is automated, not a human screen-reader review. |
| Local timing sample | `node e2e/_quality.mjs` | Five production-build loads. Median navigation: DOMContentLoaded 18 ms, load 34 ms, first contentful paint 24 ms; median `networkidle` wall time 597 ms. Local lab data only, not p75 field Core Web Vitals. |
| Deterministic reset | `npm run db:reset` | **Passed**: 60 students, 20 projects, 10 faculty, 18 skills, seed 731. |
| Benchmark regeneration | `npm run evidence:benchmark` | **Passed**: JSON/CSV regenerated; global 27, greedy 27, FCFS 27; shuffle 20/20. |
| Live API journey | TestClient/live HTTP probe during development | **Passed**: profile, projects, invalid weights 422, run, review, evidence, shuffle, approval, outcome, roadmap, outreach text, faculty assignments, audit, JSON/CSV export; wrong role returned 403. |

## Browser journey coverage

The checked-in Playwright suite verifies:

1. Launch page and demo entry.
2. Student dashboard and seeded project catalog.
3. Admin overview and fairness evidence.
4. Faculty approved-candidate route.
5. Axe serious/critical assertion on the admin overview.
6. Full stateful workflow:
   - reset to deterministic synthetic seed;
   - edit and save student hours;
   - edit and save a fictional faculty project;
   - preview normalized weights;
   - run the actual cohort optimizer;
   - execute the 20-permutation shuffle test;
   - approve the proposed batch;
   - download authenticated JSON and CSV exports;
   - verify the audit event;
   - open an actually placed student outcome;
   - persist roadmap progress;
   - save and download the outreach draft.

## Production build routes

The successful build generated:

- `/` and `/about`
- `/student`, `/student/profile`, `/student/projects`, `/student/outcome`
- `/faculty`, `/faculty/projects`, `/faculty/candidates`
- `/admin`, `/admin/data`, `/admin/run`, `/admin/evidence`, `/admin/audit`
- framework `_not-found`

## Accessibility and visual findings fixed

The first rendered pass identified and fixed:

- primary-button text inheriting near-black on cardinal red (2.34:1);
- selected catalog metadata at 4.45:1, just below AA;
- skip-link destination not receiving focus.

The final matrix covered all application routes at 390 and 1440 CSS px. Student dashboard, admin run, and admin evidence also covered 360, 768, 1024, 1280, and 1920 px. The final report at [`evidence/screenshots/report.json`](../evidence/screenshots/report.json) records 43 successful screenshots, 25 axe scans, zero page errors, and zero axe violations. Screenshot PNGs are in `evidence/screenshots/`.

Automated keyboard smoke evidence and local navigation samples are in [`evidence/quality-report.json`](../evidence/quality-report.json).

## Seeded benchmark

Artifacts:

- [`backend/evidence/seeded-benchmark.json`](../backend/evidence/seeded-benchmark.json)
- [`backend/evidence/seeded-benchmark.csv`](../backend/evidence/seeded-benchmark.csv)

| Metric | Global | Greedy | Synthetic FCFS |
|---|---:|---:|---:|
| Placements | 27 | 27 | 27 |
| Submitted placement rate | 45.0% | 45.0% | 45.0% |
| Eligible count | 47 | 47 | 47 |
| Mean compatibility | 88.37 | 88.37 | 87.96 |
| Median compatibility | 89.59 | 89.59 | 87.64 |
| Bottom decile | 83.64 | 83.64 | 83.64 |
| Minimum | 82.64 | 82.64 | 82.64 |
| Constraint violations | 0 | 0 | 0 |

The un-tuned seed does not show a placement-count gain over greedy. The required minimal counterexample does: global places 2 while greedy places 1. The shuffle test returned 20/20 identical canonical assignments. This supports mechanics and input-order invariance on the frozen synthetic fixture; it does not establish actual rematching reduction or demographic fairness.

## Warnings and unavailable checks

- Pytest emitted one deprecation warning because FastAPI/Starlette's current `TestClient` compatibility path references the older httpx integration.
- Vitest emitted a future config-loader warning because `vitest.config.ts` uses ESM syntax without a root `type: module`; tests still passed.
- The restricted IDE sandbox's Next development HMR WebSocket failed, so rendered verification used the successful production build with `next start`. Native `npm run dev` should be retested outside that sandbox.
- Docker is not installed, so no container build or Compose claim is made.
- No human screen-reader session or assistive-technology certification was performed.
- Browser p75 LCP/INP/CLS are not measured because there is no field traffic. Local navigation timings above are not substitutes.
- No live Workday, SSO, email, institutional data, or real-data fairness test exists by design.

See [`LIMITATIONS.md`](LIMITATIONS.md) for functional gaps and claim boundaries.
