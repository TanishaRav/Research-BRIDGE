# Hypothetical Workday adoption roadmap

ResearchBridge has no live Workday connection. The current `SourceAdapter` protocol and `MockWorkdayAdapter` document a possible boundary only. The mock performs no network call, has no credentials, cannot load data, and does not imply Iowa State or Workday approval.

The supplied brief names Ben Boonstra, Stephen B. Gilbert, and Michelle L. Soupir as stakeholders. No interview, decision, endorsement, data-access approval, or integration approval from these people is claimed.

## Current contract seam

The repository defines a source adapter with two operations:

```python
class SourceAdapter(Protocol):
    source_name: str
    schema_version: str

    def validate(self, payload: bytes, media_type: str) -> ImportValidationReport: ...
    def load_snapshot(self, payload: bytes, media_type: str) -> ImportSnapshot: ...
```

The mock Workday contract names only these hypothetical fields:

- opaque external person ID;
- opaque external project ID;
- effective term;
- affiliation status;
- change cursor.

This is not a complete mapping. The production system would also need an approved definition for project ownership, capacity, requirements, schedules, eligibility status, consent, lifecycle states, and authoritative update timestamps. The current API does not route imports through the adapter interface; it directly validates local synthetic JSON.

## Stage 0 — Synthetic local demo

**Purpose:** verify mechanics without institutional access.

Current characteristics:

- deterministic synthetic JSON and SQLite only;
- fictional faculty and hypothetical openings;
- demo persona headers instead of authentication;
- no Workday, SSO, email, or external write;
- human approval before outcomes appear;
- local audit, immutable run snapshots, and synthetic exports.

**Exit criteria:** stakeholders agree that the workflow is worth piloting, resolve the policy questions below, and identify accountable product, data, privacy, security, and operational owners. A successful demo alone is not authorization to use real data.

## Stage 1 — Approved pilot imports

**Purpose:** test the operating process with a deliberately limited, approved dataset and no live Workday connection.

Required work before data is accepted:

1. Obtain written approval for the pilot purpose, participants, fields, and term.
2. Define the authoritative source and a signed/versioned mapping for every imported field.
3. Minimize fields. Do not import GPA, transcripts, credentials, or protected attributes into the matching service unless a separately approved analysis requires them.
4. Replace the pasted-JSON workflow with a controlled import channel, named operator, checksum, source timestamp, validation report, and quarantine/reject path.
5. Persist source manifests with imports and include them in frozen run snapshots and exports.
6. Define correction, withdrawal, retention, deletion, and incident procedures.
7. Provide participant notice and collect any required consent, including consent for suggestions beyond ranked projects.
8. Run the allocation in shadow mode; authorized staff remain responsible for decisions and communications.

**Pilot measures:** acceptance, decline, withdrawal, rematching rounds, time-to-placement, capacity changes, prerequisite disputes, stale runs, manual interventions, and operational errors. Report submitted- and eligible-cohort denominators.

**Exit criteria:** approved owners accept the field mapping and operating evidence; privacy and security reviews close material findings; the pilot meets predefined stop/go thresholds; and participants have a supported correction/deletion path.

## Stage 2 — Authorized institutional integration

**Purpose:** connect only through an approved Iowa State interface after the pilot justifies it.

Required controls:

- institutional SSO and production authorization with student, faculty, administrator, importer, approver, auditor, and service roles;
- an approved Workday/API/export interface, service identity, network path, rate limits, and support owner;
- least-privilege read scopes and an explicit decision about whether any write-back is allowed;
- canonical mapping for opaque IDs, effective term, affiliation/enrollment status, project ownership, capacity, schedules, requirements, and change cursor;
- reconciliation for deletions, corrections, late changes, duplicate identities, and out-of-order updates;
- clear consent/notice for profile use, rankings, suggestions, allocation, faculty visibility, and retention;
- privacy review, security review, threat model, accessibility review, and records-management approval;
- encrypted transport and storage, managed secrets, key rotation, environment separation, and redacted logs;
- idempotent ingestion, retry/dead-letter handling, source checksums, replay protection, and complete lineage;
- explicit human approval and rollback procedures for every consequential batch.

Prefer one-way, read-only ingestion at first. Do not add placement or email write-back until governance owners approve the exact effects, conflict behavior, and recovery plan.

**Exit criteria:** the interface and field scopes are formally authorized; SSO and least privilege are tested; data lineage and reconciliation pass; support/on-call ownership exists; and deployment, rollback, recovery, privacy, and accessibility evidence is accepted.

## Stage 3 — Monitored production

**Purpose:** operate a governed service rather than a demo.

Production controls must include:

- service-level objectives and health checks that cover database, migrations, queues/import freshness, and allocation dependencies;
- metrics and alerts for import failures, stale data, duplicate operations, run failures, time-limited optimization, approval latency, and export activity;
- append-only, access-controlled audit records with reviewed retention;
- automated retention and verified deletion for profiles, source files, run artifacts, exports, and backups;
- periodic access review, secret rotation, vulnerability management, dependency updates, incident exercises, and recovery tests;
- model/policy versioning, change review, regression benchmarks, and rollback;
- ongoing fairness and missing-data monitoring with approved group definitions and small-cell protection;
- participant correction, withdrawal, appeal, and support paths;
- regular review of acceptance, withdrawal, rematching rounds, time-to-placement, and capacity accuracy.

Production status should be revoked or paused when source freshness, authorization, data quality, solver evidence, or participant safeguards fall outside agreed limits.

## Open stakeholder questions

These questions remain unanswered and must be resolved by authorized owners rather than inferred from the prototype:

1. Which events cause most rematching today: schedule conflicts, declined offers, faculty capacity changes, prerequisite gaps, incomplete profiles, or another cause?
2. What fairness policy should govern ties, minimum quality, first-time researchers, and acceptable disparity across majors?
3. Is capacity counted per faculty member, per project, per term, or across all three?
4. Which skills are mandatory on day one, and which may be learned with mentoring?
5. Which time windows are genuinely fixed, and which are preferences?
6. What constitutes student consent to receive suggestions outside ranked projects?
7. Which institutional systems are authoritative for student, faculty, project, and placement data?

Additional integration decisions include who may approve a run, whether faculty can decline or request changes, how student appeals work, whether an approved placement writes back anywhere, and which office owns retention and deletion.

## Non-goals of the current prototype

- No live Workday or university-system call
- No production SSO or identity lifecycle
- No automatic email or faculty contact
- No external record mutation
- No claim of FERPA certification, legal compliance, institutional approval, or proven impact
- No use of the named stakeholders as implied approvers

See [Data provenance](DATA_PROVENANCE.md), [Fairness](FAIRNESS.md), and [Limitations](LIMITATIONS.md) before planning a pilot.
