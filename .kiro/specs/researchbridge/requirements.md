# ResearchBridge requirements

**Status:** Approved for implementation from the supplied master brief  
**Product:** ResearchBridge, an independent EUReCA research-placement prototype  
**Audience:** Iowa State undergraduate students, faculty researchers, EUReCA administrators, and university stakeholders  
**Priorities:** P0 working vertical slice, P1 polish and robustness, P2 optional enhancements  
**Last updated:** 2026-11-17

## 1. Scope and source record

ResearchBridge collects a cohort before allocating limited research placements. It provides recommendations, but its defining function is transparent global batch allocation subject to eligibility, capacity, and a minimum compatibility threshold.

Public sources consulted on 2026-11-17:

- [EUReCA public website](https://www.undergradresearch.iastate.edu/): accessible. It describes EUReCA as supporting student collaboration with faculty and peers, exploration of academic interests, faculty-mentor discovery, application guidance, presentation opportunities, and funding discovery.
- [Supplied Google document](https://docs.google.com/document/d/1Pbup4JBsbAJEQUJAjpAvLg0CZ2rhE6BA6T7deEVWXTU/edit): document body inaccessible without sign-in. Only the title “Student Faculty Project Matching System” was visible. No contents from that document are assumed.

The prototype must never imply that it is an official Iowa State service, that fictional project openings are real, that stakeholder interviews occurred, or that Iowa State approved an integration.

### Open stakeholder questions

Answers have not been supplied. These remain explicit product questions:

1. Which events cause most rematching today: schedule conflicts, declined offers, faculty capacity changes, prerequisite gaps, incomplete profiles, or another cause?
2. What fairness policy should govern ties, minimum quality, first-time researchers, and acceptable disparity across majors?
3. Is capacity counted per faculty member, per project, per term, or across all three?
4. Which skills are truly mandatory on day one, and which may be learned with mentoring?
5. Which time windows are genuinely fixed, and which are preferences?
6. What constitutes student consent to receive suggestions outside ranked projects?
7. Which institutional systems are authoritative for student, faculty, project, and placement data?

### Implementation assumptions

- The demo uses only reproducibly generated synthetic students and explicitly fictional faculty/project openings.
- Student rankings define acceptable projects. A student may separately opt into suggestions.
- A score of 60/100 is the default assignment threshold.
- The demo role switcher is a persona selector, not authentication.
- All core behavior works locally without paid services, external AI, email delivery, Workday, or network access after installation.
- SQLite is authoritative for the local demo. Repository interfaces isolate persistence from domain logic.

## 2. P0 acceptance requirements

### R1 — Synthetic, traceable data

- **R1.1** WHEN the demo database is seeded, THE SYSTEM SHALL create exactly 60 synthetic students and exactly 20 explicitly hypothetical project openings using a fixed seed.
- **R1.2** WHEN a student record is rendered or exported, THE SYSTEM SHALL label the cohort as synthetic and SHALL NOT present it as an actual Iowa State student record.
- **R1.3** WHEN a project is rendered, THE SYSTEM SHALL distinguish public source facts from hypothetical title, availability, capacity, schedule, and prerequisites.
- **R1.4** WHERE a faculty identity is fictional, THE SYSTEM SHALL visibly label that identity as fictional.
- **R1.5** THE seeded cohort SHALL include beginners, interdisciplinary profiles, missing data, duplicate display names, students with no feasible match, zero-capacity projects, score ties, schedule conflicts, and oversubscribed projects.
- **R1.6** WHEN seed or fixture data is imported, THE SYSTEM SHALL validate schema version, stable identifiers, duplicate identifiers, ranges, references, capacities, and time windows and SHALL return actionable field-level errors.
- **R1.7** THE SYSTEM SHALL provide a data dictionary, source manifest with retrieval dates, and a small adversarial fixture.

### R2 — Role-specific demo access

- **R2.1** WHEN a user chooses Student, Faculty, or EUReCA Admin, THE SYSTEM SHALL switch to a seeded persona and role-appropriate navigation.
- **R2.2** THE SYSTEM SHALL identify the role switcher as demo-only and not authentication.
- **R2.3** WHEN a role-restricted API route is requested, THE SYSTEM SHALL validate the declared demo role server-side and reject unauthorized access.
- **R2.4** THE SYSTEM SHALL NOT expose actual credentials, student records, or claims of production authorization.

### R3 — Student profile and submission journey

- **R3.1** WHEN a student opens the dashboard, THE SYSTEM SHALL show profile completeness, batch status, and a specific next action.
- **R3.2** WHEN a student edits interests, skills with proficiency 0–4, available hours, time windows, learning goals, suggestion consent, or ranked acceptable projects, THE SYSTEM SHALL validate and persist the change.
- **R3.3** IF required profile fields are incomplete, THEN THE SYSTEM SHALL identify each missing field and SHALL NOT treat missing mandatory information as eligibility.
- **R3.4** WHEN a student submits a valid profile, THE SYSTEM SHALL add it to the next batch without allocating immediately.
- **R3.5** WHEN a submitted profile or relevant project changes, THE SYSTEM SHALL mark affected unapproved run drafts stale and SHALL NOT silently alter an approved run.

### R4 — Project discovery and preferences

- **R4.1** WHEN a student searches the catalog, THE SYSTEM SHALL search relevant title, description, department, interest, and skill fields.
- **R4.2** WHEN filters for department, skill, hours, or schedule are active, THE SYSTEM SHALL return the accurate result count, display active filters, support individual removal, and support reset-all.
- **R4.3** WHEN a project is selected, THE SYSTEM SHALL show description, faculty provenance, capacity, mandatory and trainable skills, prerequisites, mentoring availability, commitment, term, modality, schedule, active status, and source links.
- **R4.4** WHEN a student ranks projects, THE SYSTEM SHALL prevent duplicate ranks and persist canonical contiguous ranks.
- **R4.5** THE SYSTEM SHALL clearly distinguish an independent recommendation from an allocation result.

### R5 — Faculty project management

- **R5.1** WHEN a faculty persona creates or edits a project, THE SYSTEM SHALL validate capacity, schedule, commitment, term, active state, and skill categories.
- **R5.2** WHEN a skill is added to a project, THE SYSTEM SHALL require it to be classified as mandatory or trainable and SHALL validate the expected proficiency range.
- **R5.3** BEFORE an admin approves a run, THE SYSTEM SHALL NOT show proposed candidates as assigned to faculty.
- **R5.4** AFTER approval, THE SYSTEM SHALL show assigned synthetic candidates and a relevant explanation without exposing unrelated student details.

### R6 — Eligibility and compatibility scoring

- **R6.1** WHEN scoring a cohort, THE SYSTEM SHALL calculate an eligibility record and a separate compatibility record for every student-project pair.
- **R6.2** A pair SHALL be ineligible if the project is inactive, capacity is nonpositive, the student neither ranked it nor accepted suggestions, a mandatory prerequisite is unmet or unresolved, available hours are below the minimum, or a genuinely fixed required time window does not overlap.
- **R6.3** Preferred or trainable skills SHALL NOT be hard eligibility requirements.
- **R6.4** FOR an eligible pair, THE default compatibility score SHALL be 0–100 using normalized factors: interests 35%, technical skills 25%, availability beyond the hard minimum 20%, ranked preference 10%, and learning-goal-to-mentoring alignment 10%.
- **R6.5** WHEN a factor has missing evidence or a zero denominator, THE SYSTEM SHALL apply the formula documented in `design.md`, record the handling, and SHALL NOT infer ability or potential.
- **R6.6** THE SYSTEM SHALL store each factor score, configured raw weight, normalized contribution, matched evidence, gaps, missing fields, eligibility reasons, score version, and configuration snapshot.
- **R6.7** THE SYSTEM SHALL label the score “compatibility index,” not acceptance probability.
- **R6.8** WHEN an admin supplies nonnegative weights with at least one positive value, THE SYSTEM SHALL normalize them to sum to 100.
- **R6.9** IF all weights are zero or any weight is negative, THEN THE SYSTEM SHALL reject the configuration with a field-specific error.
- **R6.10** WHEN weights are previewed, THE SYSTEM SHALL NOT modify stored scores; changed scores SHALL only belong to a new run.
- **R6.11** THE SYSTEM SHALL NOT use names, protected attributes, GPA, prestige, prior research, submission order, or academic year as score factors.

### R7 — Deterministic global batch optimizer

- **R7.1** WHEN an admin starts a run, THE SYSTEM SHALL load and validate the complete submitted cohort and active project set before optimization.
- **R7.2** THE SYSTEM SHALL create decision variables only for eligible pairs at or above the configured threshold.
- **R7.3** THE SYSTEM SHALL assign each student to at most one project and SHALL not exceed any project capacity.
- **R7.4** THE SYSTEM SHALL allow students to remain unplaced.
- **R7.5** THE optimizer SHALL perform staged lexicographic optimization in this order: maximize placement count; fix that optimum and maximize quantized total score; fix both and maximize the minimum assigned score where assignments exist; then resolve every remaining ambiguity by canonical seeded-lottery variable fixing independent of ingestion order.
- **R7.6** THE solver SHALL use a fixed seed, one worker, sorted stable IDs, integer objective coefficients, and the rounding rule documented in `design.md`.
- **R7.7** WHEN the solver proves an optimum, THE SYSTEM SHALL record that status. WHEN only a time-limited feasible result exists, THE SYSTEM SHALL not label it optimal.
- **R7.8** THE run SHALL record status, stage outcomes, runtime, objective values, solver seed, worker count, score version, input snapshot hash, and any optimality limitation.
- **R7.9** FOR each unplaced student, THE SYSTEM SHALL record one or more specific reasons: missing data, no eligible projects, below threshold, or capacity competition.
- **R7.10** WHEN a global assignment differs from a student’s highest independent recommendation, THE SYSTEM SHALL explain the cohort-level capacity trade-off without revealing another student’s private data.
- **R7.11** WHEN identical canonical input is submitted in different orders, THE SYSTEM SHALL produce identical assignments.

### R8 — Run review, approval, audit, and export

- **R8.1** WHEN a run completes, THE SYSTEM SHALL persist an immutable input/config/result snapshot as a proposed draft.
- **R8.2** WHEN an admin reviews a run, THE SYSTEM SHALL show assignments, unplaced students and reasons, project utilization, score explanations, filters, and solver evidence.
- **R8.3** WHEN an admin approves a non-stale draft, THE SYSTEM SHALL atomically mark it approved and expose its assignments to students and faculty.
- **R8.4** IF a draft is stale, THEN THE SYSTEM SHALL prevent approval and explain which data class changed.
- **R8.5** WHEN an approved run is exported, THE SYSTEM SHALL produce CSV and JSON containing run/source metadata and no data outside the synthetic demo schema.
- **R8.6** THE SYSTEM SHALL record append-only decision audit events for imports, submissions, configuration changes, run creation, stale invalidation, approval, reset, and export.
- **R8.7** WHEN comparing two runs, THE SYSTEM SHALL display placement-count, score, outcome, and configuration differences.

### R9 — Baseline and fairness evidence

- **R9.1** WHEN evaluating a run, THE SYSTEM SHALL execute first-come-first-served simulation and greedy highest-score allocation against identical eligibility, scores, capacities, and threshold.
- **R9.2** THE SYSTEM SHALL label first-come-first-served order as synthetic simulation.
- **R9.3** FOR each strategy, THE SYSTEM SHALL compute exact placement count/rate, mean score, median score, nearest-rank bottom-decile score, minimum score, top-choice rate, first-time-researcher placement rate, major-specific rates with denominators, unplaced count/reasons, constraint violations, and measured runtime.
- **R9.4** THE SYSTEM SHALL show both submitted-cohort and eligible-cohort denominators where applicable and warn on small major groups.
- **R9.5** WHEN a shuffle test runs, THE SYSTEM SHALL reorder canonical input 20 times using recorded seeds and report the actual identical-assignment pass count.
- **R9.6** THE test suite and UI SHALL include the two-student counterexample in which global optimization places both students while greedy places one.
- **R9.7** THE SYSTEM SHALL export computed benchmark evidence as JSON and CSV.
- **R9.8** THE interface SHALL state that synthetic evaluation cannot establish actual rematching reduction or demographic fairness and SHALL describe a proposed pilot measuring acceptance, withdrawal, rematching rounds, and time-to-placement.

### R10 — Roadmap and outreach draft

- **R10.1** WHEN a student has an approved placement, THE SYSTEM SHALL derive mandatory and trainable skill gaps from the actual placement requirements and recorded proficiency.
- **R10.2** WHEN a student is unplaced, THE SYSTEM MAY create a roadmap for an explicitly identified preferred feasible or aspirational project and SHALL label it “not a placement.”
- **R10.3** FOR each gap, THE SYSTEM SHALL show category, priority, current and target proficiency, concrete task, estimated hours, resource link or generic-suggestion label, deliverable, and success check.
- **R10.4** THE roadmap SHALL distribute work across 2–4 weeks according to the student’s recorded available hours.
- **R10.5** WHEN a student marks a task complete, THE SYSTEM SHALL persist progress but SHALL state that completion does not verify mastery.
- **R10.6** WHEN generating an outreach draft, THE SYSTEM SHALL use only recorded synthetic interests, skills, honest gaps, faculty name, project title, and a discussion request.
- **R10.7** THE student SHALL be able to edit, copy, and download the draft; THE SYSTEM SHALL provide no send action.
- **R10.8** WITHOUT an AI provider or network, THE SYSTEM SHALL generate a complete deterministic roadmap and email draft.

### R11 — UX, responsive behavior, and accessibility

- **R11.1** THE application SHALL use a warm off-white canvas, restrained white/neutral surfaces, near-black text, deep cardinal red as the sole brand accent, and separate accessible semantic colors.
- **R11.2** THE application SHALL use Space Grotesk for headings, Public Sans for body text, and optional JetBrains Mono for technical data using licensed local or reliably bundled assets with metric-compatible fallbacks.
- **R11.3** THE application SHALL provide a compact desktop sidebar, contextual toolbar, role and active-route context, skip link, and functional mobile navigation.
- **R11.4** THE application SHALL use semantic HTML, logical headings, persistent labels, visible focus, complete keyboard operation, status live regions, reduced-motion support, and WCAG 2.2 AA contrast.
- **R11.5** THE application SHALL use structural skeletons rather than routine circular spinners and SHALL preserve layout geometry during loading/refresh.
- **R11.6** THE application SHALL provide specific loading, empty, partial, validation, error, success, offline, and permission-restricted states where relevant.
- **R11.7** AT 360, 390, 768, 1024, 1280, 1440, and 1920 CSS pixels, THE interface SHALL have no unintended horizontal page scroll, overlap, clipped controls, or hover-only actions.
- **R11.8** EVERY visible action SHALL work or be explicitly labeled unavailable; THE SYSTEM SHALL contain no placeholder pages, dead links, fake success, fabricated metrics, decorative charts, or send-email control.
- **R11.9** THE About view SHALL explain batch allocation, compatibility scoring, synthetic data, human approval, demo-role limitations, and privacy boundaries in plain language.

### R12 — Operations, privacy, and documentation

- **R12.1** THE repository SHALL provide locked frontend and backend dependencies, `.env.example`, database migrations, deterministic seed/reset commands, health endpoints, root setup documentation, and one-command local startup via Docker Compose or a documented equivalent.
- **R12.2** THE core demo SHALL not require paid services, external AI, Workday, email delivery, or production credentials.
- **R12.3** THE SYSTEM SHALL validate schemas server-side, render text safely, keep secrets server-side, avoid personal data in logs/URLs, prevent duplicate consequential operations, and require explicit confirmation for reset.
- **R12.4** THE repository SHALL document a `SourceAdapter` interface and a hypothetical mock Workday contract, with no live calls or approval claims.
- **R12.5** THE Workday roadmap SHALL cover synthetic demo, approved pilot imports, authorized institutional integration, and production monitoring/retention/deletion/audit controls.
- **R12.6** THE repository SHALL include `docs/DEMO.md`, `USER_JOURNEYS.md`, `ALGORITHM.md`, `FAIRNESS.md`, `WORKDAY_ROADMAP.md`, `DATA_PROVENANCE.md`, `TEST_REPORT.md`, and `LIMITATIONS.md`.
- **R12.7** WHEN final evidence is recorded, THE SYSTEM SHALL include actual commands and measured outputs only; unexecuted checks SHALL be marked not run.

## 3. P1 requirements

- **R13.1** WHEN data changes, THE interface SHALL preserve useful filters and existing content while refreshing.
- **R13.2** THE project catalog and run review SHALL provide deep links with relevant URL-backed filter state.
- **R13.3** THE application SHALL expose actionable retry paths for failed backend requests and a clear offline state.
- **R13.4** THE application SHALL include automated axe checks and manual keyboard-check documentation.
- **R13.5** THE application SHALL capture and inspect screenshots at all required viewport widths when browser tooling is available.
- **R13.6** THE system SHALL measure build output and browser performance where available without claiming unsupported field percentiles.
- **R13.7** THE API SHALL use idempotency controls for run, approval, reset, and import operations.

## 4. P2 optional requirements

- **R14.1** WHERE a locally available sentence-transformer model is configured, THE SYSTEM MAY cache versioned embeddings and SHALL fall back to deterministic token similarity on error or absence.
- **R14.2** WHERE a server-side language-model provider is configured, THE SYSTEM MAY improve roadmap/email wording using minimal synthetic context and validated structured output; deterministic templates SHALL remain authoritative fallback.
- **R14.3** THE SYSTEM MAY support audited manual override only if a reason is required and eligibility/capacity are revalidated without overwriting the baseline result.
- **R14.4** THE SYSTEM MAY provide PostgreSQL/Supabase repository implementations after the SQLite vertical slice remains fully working.

## 5. Out of scope

- Production authentication or SSO
- Live Workday or other institutional-system calls
- Sending email or changing external records
- Real student data, credentials, transcripts, GPA, protected attributes, or student records
- Chatbots
- Automatic final placement decisions without human approval
- Claims of legal compliance, institutional approval, causal impact, or proven demographic fairness
