# ResearchBridge limitations and open questions

ResearchBridge is a local demonstration of matching mechanics. It is not an official Iowa State service, an approved EUReCA workflow, a production authorization system, or evidence of institutional impact.

Every student is synthetic, every faculty identity is fictional, and every opening is hypothetical. The supplied brief names Ben Boonstra, Stephen B. Gilbert, and Michelle L. Soupir as stakeholders, but no interview, decision, approval, or endorsement from them is claimed.

## Product and integration boundaries

- The demo role switcher and `X-Demo-*` headers are not authentication. Persona identifiers are discoverable, unsigned, and unsuitable for real records.
- There is no SSO, account lifecycle, role provisioning, session security, production authorization, or participant identity verification.
- There is no live Workday or other institutional-system call. The Workday adapter is a hypothetical no-network contract that always refuses loading.
- There is no email delivery, recipient field, or send action. Outreach is only a deterministic draft that can be edited, copied, or downloaded.
- There is no optional embedding model or LLM integration. Matching uses deterministic taxonomy/token similarity; roadmap and outreach wording use local templates.
- There is no PostgreSQL/Supabase implementation, production queue, background worker, notification service, or external secrets integration.
- No legal-compliance, FERPA certification, Iowa State approval, vendor approval, causal impact, or demographic-fairness claim is supported.

## Data and provenance limits

- Import accepts JSON only. CSV is available for approved-run export, not import.
- The import operation upserts supplied entities; records omitted from a snapshot remain in the database.
- The imported source manifest is not persisted as a versioned lineage record.
- A frozen run input includes students, projects, and skills, but not faculty records or the source manifest.
- Approved JSON export loads the bundled seed source manifest rather than a manifest attached to a prior import. Imported fixtures can therefore be exported with incomplete or incorrect lineage.
- The source-manifest body is weakly typed beyond `synthetic_only=true`; individual source entries are not fully schema-validated.
- API startup seeds only when the student table is empty. A partially populated database is not automatically repaired.
- Reset deletes the configured SQLite database and WAL/SHM files without a backup. The npm command embeds the confirmation token and is not interactive.
- The local seed intentionally marks incomplete fixtures submitted so run explanations can exercise missing-data paths. That state bypasses the normal interactive submission gate by design.

The [EUReCA public homepage](https://www.undergradresearch.iastate.edu/) was accessible on 2026-11-17 and informed high-level context only. The supplied [Google document](https://docs.google.com/document/d/1Pbup4JBsbAJEQUJAjpAvLg0CZ2rhE6BA6T7deEVWXTU/edit) required sign-in on that date; only “Student Faculty Project Matching System” was visible, so its body did not inform the implementation.

## Matching and evidence limits

- The compatibility index is a configured similarity score, not acceptance probability, potential, qualification, or expected research success.
- Mandatory evidence that is missing remains unresolved and blocks eligibility. Missing soft evidence can lower scores. This transparent handling can still burden students whose profiles are less complete.
- Taxonomy terms, proficiency self-reports, project requirements, weights, threshold, suggestion consent, and capacity are policy choices that may encode bias or error.
- The global objective has no demographic parity or distributional fairness constraint. Major and first-time status are evaluation fields only.
- Stable IDs participate in deterministic tie resolution. Changing IDs can change a genuine tie even though names and ingestion order do not.
- A feasible-but-not-proven optimizer result is labeled with an optimality limitation, but the current approval repository does not prohibit approving that proposed run. Admins must inspect the optimality label.
- The configured solver timeout applies to each stage and each tie-feasibility check, not one total run budget.
- `missing_data` can be included for an unplaced student when any considered pair has unresolved hard evidence, even if another pair is fully resolved. Read the reason together with the pair details.
- Run comparison exists in the API but has no visible UI control.
- Admin run review receives pair-score records but the current page does not render the complete factor evidence for every pair.
- Global, greedy, and FCFS each place 27 students in the un-tuned seed. Global does not show a placement-count improvement on that dataset. The two-student counterexample demonstrates that the mechanism can outperform greedy, not how often it will.
- The 20/20 shuffle result applies to one frozen synthetic dataset. It is not a proof over all inputs.
- Synthetic evaluation cannot establish actual rematching reduction, demographic fairness, acceptance, withdrawal, placement durability, or time-to-placement.
- No scale or latency claim is supported beyond the 60-student, 20-project seed.

## User-interface gaps

- The role switcher exposes only the first five of 60 student personas and first five of 10 faculty personas. Several adversarial fixtures are not selectable through the normal UI.
- Students cannot edit availability windows in the profile UI, despite windows being required evidence for some submissions and eligibility checks.
- Students can change proficiency only for existing skills; they cannot add a missing skill in the UI.
- Project ranking supports append and remove, not direct reordering.
- The catalog API supports a schedule-day filter, but the current catalog UI does not expose it.
- Project detail does not display every backend field, including the full fictional faculty provenance and all mentoring evidence.
- The faculty editor does not expose prerequisites, mentoring availability, required windows, or mentoring windows.
- The backend supports a clearly labeled aspirational roadmap for an unplaced student, but the current student outcome UI displays follow-through only for placed students.
- Persisted roadmap/outreach records are returned by student ID without confirming that they correspond to the newest approved run. A later approval can leave older follow-through content visible until reset or data intervention.
- Export buttons are visible before approval; the API rejects those requests with `approval_required`.

## Operations and deployment limits

- Docker is unavailable in the local environment, and Docker startup has not been tested. No container validation is claimed.
- The documented native path assumes macOS/Linux-style `.venv/bin/python`. Windows needs equivalent commands and script changes.
- `npm run dev` runs Uvicorn with reload and both services bind to `0.0.0.0`. Use it only on a trusted local network.
- `npm run start` starts the frontend only. There is no checked-in production process manager, reverse proxy, TLS setup, hardened Uvicorn/Gunicorn command, deployment manifest, monitoring stack, or backup plan.
- Liveness does not touch the database. Readiness checks only that at least one migration is recorded; it does not validate seed counts, data integrity, solver availability, or frontend connectivity.
- Importing the FastAPI application can create/migrate the database and seed it when empty.
- SQLite and the migration are the only implemented persistence target.
- The screenshot helper now uses the repository working directory and covers every application route in its 390/1440 matrix; only the key student-dashboard/admin-run/admin-evidence views receive every intermediate target width.
- The sandbox development HMR WebSocket failed; production UI verification succeeded with `npm run build` and `npm run start` alongside Uvicorn. This is a tooling/environment limit, but the dev path should be retested outside that sandbox.

## Verification gaps

- The final automated axe matrix passed all 25 configured scans, but automated rules cannot replace human assistive-technology review.
- An automated keyboard-only smoke test passed skip-link focus transfer and mobile-menu Tab/Enter operation. A separate human keyboard and screen-reader review is still pending.
- Screen-reader behavior and browser zoom/text-growth behavior have not been manually certified.
- Browser p75 performance and other field percentiles have not been measured. The recorded five-run local production-build sample is lab evidence only.
- Docker validation is unavailable.
- ESLint and TypeScript pass, with seven documented React effect warnings remaining.
- The live API journey succeeded, and the final Playwright suite now retains an automated full three-role journey; broader import/error permutations remain primarily backend/manual evidence.
- Screenshot/axe and keyboard/timing outputs are retained in machine-readable JSON, but no hosted CI run is attached.

See [Test report](TEST_REPORT.md) for the exact passed, warning, pending, and unavailable status.

## Open stakeholder questions

Authorized stakeholders must answer these questions before a pilot or policy claim:

1. Which events cause most rematching today: schedule conflicts, declined offers, faculty capacity changes, prerequisite gaps, incomplete profiles, or another cause?
2. What fairness policy should govern ties, minimum quality, first-time researchers, and acceptable disparity across majors?
3. Is capacity counted per faculty member, per project, per term, or across all three?
4. Which skills are truly mandatory on day one, and which may be learned with mentoring?
5. Which time windows are genuinely fixed, and which are preferences?
6. What constitutes student consent to receive suggestions outside ranked projects?
7. Which institutional systems are authoritative for student, faculty, project, and placement data?

Further decisions are needed on approver authority, student/faculty decline and appeal paths, manual overrides, source corrections, retention/deletion, incident ownership, acceptable time-limited solver behavior, small-group reporting, and whether any external write-back should ever occur.
