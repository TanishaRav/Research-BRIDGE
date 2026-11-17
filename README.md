# ResearchBridge

ResearchBridge is an independent prototype for transparent, cohort-wide undergraduate research placement. It is not an official Iowa State University service, an approved integration, or a production system.

Every student in the repository is synthetic. Every faculty identity is fictional. Every project opening is hypothetical. The in-app role switcher selects seeded personas; it is not authentication. ResearchBridge does not send email and does not call Workday or another university system.

## What the prototype demonstrates

ResearchBridge separates three decisions that are often blurred together:

1. **Eligibility:** whether a student–project pair satisfies hard requirements.
2. **Compatibility:** an explainable 0–100 index based on recorded evidence.
3. **Allocation:** a cohort-wide, capacity-constrained assignment proposed by a deterministic optimizer and exposed only after administrator approval.

The local vertical slice includes student profile and project-ranking views, fictional faculty project management, administrator scoring and batch review, baseline comparisons, deterministic shuffle evidence, approval-gated outcomes, skill roadmaps, editable outreach drafts with no send action, audit records, and approved-run JSON/CSV export.

The [EUReCA public homepage](https://www.undergradresearch.iastate.edu/) was accessible on 2026-11-17 and was used only for high-level program context. The supplied [“Student Faculty Project Matching System” Google document](https://docs.google.com/document/d/1Pbup4JBsbAJEQUJAjpAvLg0CZ2rhE6BA6T7deEVWXTU/edit) required sign-in on that date; only its title was visible, so no body content is assumed.

## Requirements

- Node.js 22 or newer
- npm 11 or newer
- Python 3.12 or 3.13. Python 3.14 is outside the declared range.
- macOS or Linux for the checked-in npm backend commands, which use `.venv/bin/python`

Docker is not installed in the development environment, and no Docker configuration is claimed as validated. The supported local path is the native setup below.

## Native setup

Run all commands from the repository root.

```bash
node --version
npm --version
python3 --version

python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r backend/requirements.txt
npm ci
cp .env.example .env
npm run db:migrate
npm run db:seed
```

Use a `python3` executable reporting Python 3.12 or 3.13. The frontend dependency graph is locked in `package-lock.json`. Backend direct requirements are pinned in `backend/requirements.txt`; the exact resolved macOS/Python 3.13 environment is recorded in `backend/requirements.lock`.

`npm run db:seed` deterministically upserts seed 731. A fresh API startup also migrates the database and seeds it when no students exist, but the explicit commands make setup state visible.

## One-command local startup

After setup, start both services with:

```bash
npm run dev
```

Open:

- Web application: <http://127.0.0.1:3000>
- API documentation: <http://127.0.0.1:8000/docs>
- API schema: <http://127.0.0.1:8000/openapi.json>

`npm run dev` starts Next.js and reload-mode Uvicorn together. The checked-in scripts bind both services to `0.0.0.0`; use this only on a trusted local network because the demo persona headers are not secure authentication.

### Production-UI local check

The verified production UI path used two terminals after `npm run build`:

```bash
# Terminal 1
.venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

```bash
# Terminal 2
npm run build
npm run start
```

This is a local verification arrangement, not a production deployment recipe. It was used because the sandbox could not maintain the development HMR WebSocket; that was a tooling/environment limitation rather than an application failure.

## Health checks

With the API running:

```bash
curl --fail http://127.0.0.1:8000/health/live
curl --fail http://127.0.0.1:8000/health/ready
.venv/bin/python -m backend.app.db status
```

`/health/live` confirms that the API process can answer. `/health/ready` and the database status command confirm that at least one migration is recorded. They do not perform a complete seed-integrity or solver check.

## Seed and reset

Seed 731 creates exactly:

- 60 synthetic students
- 20 hypothetical projects
- 10 fictional faculty identities
- 18 skills

It includes beginners, interdisciplinary interests, missing hours/windows/goals, duplicate display names, an explicit score tie, a fixed-window conflict, oversubscription, an inactive project, a zero-capacity project, and students with no feasible match.

Reapply the seed without deleting the database:

```bash
npm run db:seed
```

Replace the local SQLite demo database and recreate the seed:

```bash
npm run db:reset
```

Reset deletes only the configured SQLite demo database plus its WAL/SHM files, then runs migrations and seed generation. The npm command contains the required confirmation token `RESET_SYNTHETIC_DEMO`, so it runs immediately and has no backup or interactive prompt. Stop the app first if practical, and do not point `RESEARCHBRIDGE_DATABASE_URL` at data that must be retained.

The same reset is available in **EUReCA Admin → Data & import** after typing the exact confirmation phrase.

## Testing and evidence

Common commands:

```bash
npm run lint
npm run typecheck
npm run test
npm run test:backend
npm run test:e2e:install
npm run test:e2e
npm run build
npm run evidence:benchmark
```

The recorded benchmark artifacts are:

- [`backend/evidence/seeded-benchmark.json`](backend/evidence/seeded-benchmark.json)
- [`backend/evidence/seeded-benchmark.csv`](backend/evidence/seeded-benchmark.csv)

The current seeded benchmark places 27 of 60 submitted students under global, greedy, and synthetic FCFS strategies, a 45.0% submitted-cohort rate. Global does **not** improve placement count over greedy on this un-tuned seed. The explicit two-student counterexample demonstrates the mechanism: count-first global allocation places two while greedy places one. The run records zero constraint violations and 20/20 identical shuffle results.

See [`docs/TEST_REPORT.md`](docs/TEST_REPORT.md) for exact recorded test results, warnings, pending checks, and unavailable checks. Synthetic benchmark evidence cannot establish actual rematching reduction or demographic fairness.

## Architecture

```text
Browser
  └─ Next.js App Router UI (:3000)
       └─ JSON/HTTP with demo role headers
            └─ FastAPI service (:8000)
                 ├─ scoring, eligibility, allocation, evidence
                 ├─ roadmap/outreach templates
                 └─ SQLite repository and numbered migration
```

- **Frontend:** Next.js, React, strict TypeScript, Tailwind CSS
- **Backend:** FastAPI, Pydantic, SQLAlchemy, OR-Tools
- **Storage:** local SQLite in WAL mode
- **Tests:** Vitest, pytest/Hypothesis, Playwright, axe

The default database is `backend/data/researchbridge.db`. Environment settings are documented in [`.env.example`](.env.example). Keep secrets out of `NEXT_PUBLIC_*`; the current local configuration contains no secrets.

## Privacy and security boundaries

- No real student records, credentials, transcripts, GPA, or protected attributes belong in this prototype.
- Names, major, academic year, first-time-researcher status, and submission order do not enter the compatibility score. Major and first-time status appear only in aggregate synthetic evaluation.
- API role checks reject unauthorized demo-role access, but anyone who can reach the service can discover and replay seeded persona identifiers. This is not production authorization.
- Approved results require an administrator action. Profile, project, configuration, and import changes stale proposed runs rather than rewriting approved snapshots.
- Outreach is saved, copied, or downloaded locally. There is no recipient field, send endpoint, or email provider.
- The Workday adapter is a hypothetical, no-network contract. It has no approved interface or institutional authorization.

## Deployment limitations

ResearchBridge is intended for a local, trusted demonstration. It has no SSO, production identity management, TLS termination, reverse proxy, hardened process manager, production database adapter, retention automation, monitoring stack, or validated container deployment. Do not expose the current servers to an untrusted network or use them with institutional data.

## Documentation

- [Judge demo and exact reset path](docs/DEMO.md)
- [Student, faculty, and administrator journeys](docs/USER_JOURNEYS.md)
- [Scoring and allocation algorithm](docs/ALGORITHM.md)
- [Fairness evidence and claim boundaries](docs/FAIRNESS.md)
- [Hypothetical Workday adoption roadmap](docs/WORKDAY_ROADMAP.md)
- [Data provenance](docs/DATA_PROVENANCE.md)
- [Executed test record](docs/TEST_REPORT.md)
- [Known limitations and open questions](docs/LIMITATIONS.md)
