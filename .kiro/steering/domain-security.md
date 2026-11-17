---
inclusion: always
---

# ResearchBridge domain and security rules

These rules bind every ResearchBridge change.

## Product truth

- ResearchBridge is an independent prototype for EUReCA. Never present it as an official Iowa State service or an approved integration.
- The core product is cohort-wide, explainable batch allocation, not immediate recommendation or first-come assignment.
- AI may assist extraction or wording. AI never chooses the final placement. An administrator approves a batch.
- The compatibility index is not a probability of acceptance and must be labeled accordingly.
- Never claim stakeholder interviews occurred unless the repository contains supplied answers.

## Data boundaries

- Use only clearly labeled synthetic students. Never add real student data, credentials, records, protected attributes, transcripts, GPA, or personal information to source, fixtures, logs, screenshots, exports, tests, or external calls.
- Public faculty facts require a source URL and retrieval date. Fictional identities and all hypothetical openings, capacities, prerequisites, schedules, and availability must be labeled fictional/hypothetical.
- Names, demographics, academic year, GPA, prestige, prior research, and submission order must not affect scores or tie resolution.
- Use stable opaque IDs, schema versions, timestamps, provenance, and immutable run snapshots.
- Do not tune seed data to exaggerate gains. Include difficult and adverse cases.

## Matching policy

- Load and validate the complete cohort before every run. Never allocate upon profile submission.
- Eligibility and compatibility are separate. Unknown mandatory evidence is unresolved and ineligible; trainable skills are never hard constraints.
- Enforce active project, positive capacity, opt-in/acceptable project, mandatory prerequisites, minimum hours, fixed required windows, threshold, one placement per student, and project capacity.
- Default compatibility weights are interest 35, technical skill 25, availability 20, preference 10, and learning goals 10. Normalize nonnegative weights; reject all-zero or negative inputs.
- Use Decimal/exactly documented rounding and integer coefficients for CP-SAT.
- Optimize lexicographically: placement count, total compatibility, minimum assigned score, complete deterministic tie resolution. Record status and never call a merely feasible result optimal.
- Explain exclusions, gaps, unplaced reasons, and cohort trade-offs without revealing other students’ details.
- Editing relevant data marks proposed runs stale. Approved snapshots never change silently.

## Security and privacy

- Treat the frontend and demo role switcher as non-security boundaries. Validate role and record access in FastAPI; state that production authentication is not implemented.
- Validate every request/import with Pydantic and parameterized persistence. Render content as text; do not inject untrusted HTML.
- Keep secrets in environment variables, never source, logs, screenshots, client bundles, or `NEXT_PUBLIC_*` unless truly public.
- Log request IDs, stable entity IDs, counts, statuses, and timings, not names or profile bodies.
- Keep personal/profile content out of URLs.
- Require idempotency for consequential operations and explicit confirmation for demo reset.
- Never send email, auto-contact faculty, call live Workday, mutate external records, or add credentials for institutional systems.
- Describe safeguards as FERPA-conscious; never claim legal compliance, certification, institutional approval, causal impact, or demographic fairness.

## Offline and dependency behavior

- Core seed, scoring, optimization, roadmap, outreach, evidence, and exports must work locally without network, paid service, or API key.
- Optional embeddings/LLM integrations require explicit configuration, minimal synthetic context, timeouts, validated outputs, version recording, and deterministic fallbacks.
- Preserve repository interfaces so SQLite may be replaced later; do not sacrifice the working local demo for speculative infrastructure.

## Verification truth

- Never claim a test, accessibility check, screenshot review, benchmark, optimization result, or performance target passed unless it was actually run and recorded.
- A zero exit code alone is not enough: verify requested counts, data labels, output files, state transitions, and rendered behavior.
- Synthetic benchmark preference satisfaction and acceptable-placement coverage are proxies. State that a real pilot must measure acceptance, withdrawal, rematching rounds, and time-to-placement.
