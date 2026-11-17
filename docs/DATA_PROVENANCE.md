# Data provenance

ResearchBridge is an independent prototype. Every student record is synthetic, every faculty identity is fictional, and every project opening is hypothetical. No seed record represents an actual Iowa State student, faculty member, or advertised opening.

## External source record

| Source | Access on 2026-11-17 | Use in this repository |
|---|---|---|
| [EUReCA public homepage](https://www.undergradresearch.iastate.edu/) | Accessible | High-level program context only. No faculty identity, student record, or opening was copied. |
| [“Student Faculty Project Matching System” Google document](https://docs.google.com/document/d/1Pbup4JBsbAJEQUJAjpAvLg0CZ2rhE6BA6T7deEVWXTU/edit) | Body inaccessible without sign-in; only the title was visible | No document-body statement is assumed or represented as a requirement. |
| ResearchBridge deterministic generator | Local code, no external source | All students, fictional faculty identities, hypothetical openings, capacity, schedules, prerequisites, preferences, and availability. |

The [EUReCA homepage](https://www.undergradresearch.iastate.edu/) describes broad undergraduate research support and mentor discovery. ResearchBridge uses that context only. It does not claim that EUReCA, Iowa State, or any named person approved this workflow.

The supplied brief names Ben Boonstra, Stephen B. Gilbert, and Michelle L. Soupir as stakeholders. The repository does not claim that interviews occurred, assign them decisions they did not make, or imply their approval.

## Deterministic seed

Seed `731` creates exactly:

| Entity | Count | Classification |
|---|---:|---|
| Students | 60 | Synthetic demo records |
| Projects | 20 | Hypothetical openings |
| Faculty | 10 | Fictional identities |
| Skills | 18 | Versioned local taxonomy entries |

The generator uses a fixed logical timestamp and stable identifiers. Reapplying the seed is reproducible; resetting removes the configured local SQLite database and regenerates the same baseline.

Seeded project descriptions state that titles, availability, capacity, schedules, and prerequisites are fictional. Faculty labels include “Fictional” and “(demo).” Student records include a synthetic marker and notice.

## Deliberate edge cases

The cohort is designed to exercise failure and explanation paths:

| Case | Seed record(s) | Expected behavior |
|---|---|---|
| Beginners | Students 51–60 | Recorded skill levels are zero; ability is not inferred. |
| Interdisciplinary interests | Student 7 | Interests span qualitative methods, accessible design, and ecology. |
| Duplicate display names | Students 5 and 6 | Stable IDs keep records distinct; names do not resolve ties. |
| Exact score tie | Students 10 and 11 | Seeded stable-ID digest resolves remaining ambiguity. |
| Fixed schedule conflict | Student 12 | Required window fails full-containment eligibility. |
| Missing hours | Student 13 | Hours evidence remains unresolved. |
| Missing windows and goals | Student 14 | Required profile evidence remains unresolved. |
| No feasible match | Student 15 and project 20 | The only ranked project has zero capacity. |
| Oversubscription | First 20 students and project 1 | Cohort allocation must respect capacity. |
| Inactive opening | Project 19 | Every pair is ineligible for that project. |
| Zero-capacity opening | Project 20 | Every pair is ineligible for that project. |
| Greedy counterexample | A/P1=95, A/P2=90, B/P1=94 | Global places two; greedy places one. |

The seed deliberately marks all generated students submitted, including incomplete fixtures, so administrator runs can exercise unresolved-data explanations. Normal interactive submission rejects an incomplete profile.

## Repository provenance artifacts

- [`backend/data/source_manifest.json`](../backend/data/source_manifest.json): source URLs, retrieval date, generator notice, and seed.
- [`backend/data/data_dictionary.json`](../backend/data/data_dictionary.json): entity classifications, key fields, excluded data, score meaning, proficiency scale, and time-window convention.
- [`backend/data/adversarial_fixture.json`](../backend/data/adversarial_fixture.json): compact registry of deliberate edge cases.
- [`backend/data/taxonomy.v1.json`](../backend/data/taxonomy.v1.json): local versioned skill taxonomy and aliases.
- [`backend/app/seed/generator.py`](../backend/app/seed/generator.py): deterministic entity construction.
- [`backend/evidence/seeded-benchmark.json`](../backend/evidence/seeded-benchmark.json) and [`seeded-benchmark.csv`](../backend/evidence/seeded-benchmark.csv): computed results for the frozen seed.

No source is fetched at runtime. The source URL and retrieval date are metadata, not proof that an opening or identity is current.

## Import boundary

The admin import path accepts JSON objects only. The payload must match schema version `1.0`, pass strict entity validation, use unique stable IDs, contain valid cross-references, respect field ranges/time-window rules, and set `source_manifest.synthetic_only=true`. Invalid payloads return field-level issues.

Current limitations matter for provenance review:

- CSV is supported for approved-run export, not import.
- Import applies upserts; omission from a payload does not delete an existing record.
- The imported source manifest is validated only as a dictionary with the synthetic-only boundary and is not persisted as a versioned source record.
- Run input snapshots include students, projects, and skills, but not faculty or the source manifest.
- Approved JSON export loads the bundled seed source manifest, not a source manifest associated with a prior import.

For those reasons, local imports should remain disposable synthetic fixtures. Do not use the current import path for institutional data or treat an export as complete lineage for an imported dataset.

## Reproduction

From the repository root after setup:

```bash
npm run db:reset
npm run evidence:benchmark
```

The first command is destructive for the configured local SQLite demo database. The second regenerates benchmark evidence from the current seeded data. See the [test report](TEST_REPORT.md) for recorded execution status and [limitations](LIMITATIONS.md) for claim boundaries.
