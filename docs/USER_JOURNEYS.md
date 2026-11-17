# ResearchBridge user journeys

ResearchBridge is an independent, synthetic-data prototype. The role switcher selects seeded personas and is not production authentication. Server-side demo-role and record checks still reject mismatched access.

## Shared lifecycle

```text
profile/project data
    ↓
student submits to a future batch
    ↓
admin freezes inputs and creates a proposed run
    ↓
eligibility → compatibility → capacity-constrained allocation
    ↓
admin reviews evidence and either leaves or approves the draft
    ↓
approved outcomes become visible to the affected students and faculty
```

A recommendation is an independently scored eligible project. An allocation is the cohort-wide result after capacity competition. They can differ. Editing a profile, project, configuration, or imported dataset marks relevant proposed runs stale; approved snapshots remain readable and unchanged.

## Student journey

Routes: `/student`, `/student/profile`, `/student/projects`, `/student/outcome`.

1. **Select a synthetic persona.** The switcher exposes seeded demo identities. The API sends `X-Demo-Role` and `X-Demo-Persona-Id`; these headers are a demo guard, not credentials.
2. **Review readiness.** The dashboard shows profile completeness, batch status, and one next action.
3. **Edit recorded evidence.** The profile view supports interests, learning goals, hours per week, first-time-researcher display status, suggestion consent, and proficiency 0–4 for seeded skills.
4. **Discover hypothetical openings.** The project catalog searches title, description, department, interest, and skills. It filters by department, skill, and maximum hours and persists filters in the URL.
5. **Inspect provenance and requirements.** Project detail shows hypothetical status, capacity, commitment, modality, term, activity, mandatory/trainable skills, and fixed windows when present.
6. **Rank acceptable projects.** Adding or removing a project persists contiguous ranks. A student can separately consent to feasible suggestions outside the ranked list.
7. **Submit.** Submission validates required profile evidence and enters the next batch. It never allocates immediately.
8. **Wait for approval.** Before approval, the outcome is pending. A proposed assignment is not shown as final.
9. **Review an approved outcome.** A placed student sees the project ID, compatibility index, and a cohort-level rationale. An unplaced student sees one or more reason codes: missing data, no eligible projects, below threshold, or capacity competition.
10. **Follow through.** For a placed student, the UI shows a 2–4 week gap-based roadmap and an editable outreach draft. Task completion records progress only. The draft can be saved, copied, or downloaded, but never sent.

### Current student UI limits

- Availability windows are part of the model and eligibility logic but are not editable in the profile UI.
- Existing skill proficiency can be changed, but a student cannot add a missing skill in the UI.
- Ranking supports append/remove, not drag or direct rank reordering.
- The backend can generate a clearly labeled aspirational roadmap for an unplaced student, but the current outcome UI renders follow-through only for placed students.

## Faculty journey

Routes: `/faculty`, `/faculty/projects`, `/faculty/candidates`.

1. **Select a fictional faculty persona.** No seeded faculty identity represents a real person.
2. **Review owned hypothetical projects.** The overview summarizes project activity and capacity.
3. **Create or edit an opening.** The editor validates title, description, department, capacity, weekly commitment, term, modality, active state, and skill requirements.
4. **Classify each skill.** Mandatory skills can make a pair ineligible. Trainable skills contribute to compatibility and roadmap gaps but are not hard eligibility requirements.
5. **Trigger a fresh draft when data changes.** A saved project edit marks proposed runs stale. It does not rewrite an approved run.
6. **Wait for human approval.** The assigned-candidates page is empty until an administrator approves a run.
7. **Review assigned synthetic candidates.** After approval, faculty see only candidates assigned to their own projects, the compatibility index, and a relevant explanation.

### Current faculty UI limits

The backend project model includes prerequisites, mentoring availability, required windows, and mentoring windows. The current faculty editor does not expose those fields, so it cannot author the full project model through the UI.

## EUReCA administrator journey

Routes: `/admin`, `/admin/data`, `/admin/run`, `/admin/evidence`, `/admin/audit`.

1. **Review readiness.** The overview shows project counts, active capacity, and recent runs.
2. **Validate local data.** **Data & import** accepts a pasted schema-versioned synthetic JSON snapshot and shows field-level validation issues. CSV import is not implemented.
3. **Apply or reset data deliberately.** Applying a valid JSON snapshot uses an idempotency key and stales proposed runs. Reset requires `RESET_SYNTHETIC_DEMO` and replaces the local SQLite demo data.
4. **Configure scoring.** The admin can set a 0–100 threshold and nonnegative raw weights. Preview normalizes the weights without updating existing scores.
5. **Create a run.** The service loads the submitted cohort and projects, freezes a canonical input/configuration snapshot, scores every pair, and performs staged allocation.
6. **Review before approval.** The run view shows status, staleness, stage evidence, assignments, unplaced reasons, capacity utilization, minimum score, and runtime.
7. **Inspect comparative evidence.** The evidence view compares global allocation with greedy and synthetic FCFS on identical inputs. It shows exact denominators, quality metrics, the two-student counterexample, and optional 20-run shuffle evidence.
8. **Approve deliberately.** Only a non-stale proposed run can transition to approved. This makes its outcomes visible to students and faculty.
9. **Export approved results.** Approved runs can be downloaded as JSON or CSV with run metadata and synthetic notices. Proposed-run export is rejected by the API.
10. **Inspect the audit timeline.** Seed/import, profile/project/configuration changes, run creation, stale invalidation, approval, reset, and export actions are recorded.

### Current administrator UI limits

- A run-comparison endpoint and client method exist, but the UI has no visible compare control.
- Export buttons appear on proposed runs even though the API correctly rejects export until approval.
- Import applies upserts rather than replacing records omitted from the snapshot.

## Role and record boundaries

| Action | Student | Faculty | Admin |
|---|---:|---:|---:|
| Read/edit own student profile | Yes | No | No route | 
| Browse projects | Yes | Yes | Yes |
| Create/edit owned project | No | Yes | Yes |
| See proposed assignments | No | No | Yes |
| Approve a run | No | No | Yes |
| See approved own outcome | Yes | No | Yes in review |
| See approved project candidates | No | Own projects only | Yes in run review |
| Import/reset/export/audit | No | No | Yes |

These checks prevent accidental cross-role access in the demo. They do not provide production identity assurance because persona IDs are discoverable and unsigned.

## Verified live API journey

A live local API journey completed the following successfully: profile read/update, project listing, invalid configuration weights returning `422`, run creation, run review, evidence retrieval, 20/20 shuffle test, approval, student outcome, roadmap, outreach text download, faculty assignments, audit retrieval, and approved JSON/CSV export. A mismatched role request returned `403` as expected.

The journey is evidence that these local paths worked together in the tested environment. It is not a production security assessment or institutional integration test.
