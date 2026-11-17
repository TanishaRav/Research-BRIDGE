# Fairness evidence and claim boundaries

ResearchBridge provides transparent allocation mechanics and comparative diagnostics. It does not claim that one synthetic benchmark establishes demographic fairness, equal opportunity, institutional impact, or reduced rematching.

## What the allocation policy does

The global policy applies the same staged objectives to the full submitted cohort:

1. maximize the number of eligible, above-threshold placements;
2. maximize total compatibility without reducing that count;
3. maximize the minimum assigned compatibility without reducing either prior objective;
4. resolve remaining ties deterministically from seed and stable IDs.

Each student receives at most one project, each project stays within capacity, and an ineligible or below-threshold edge cannot be assigned. An administrator must review and approve the proposal.

The compatibility score excludes names, protected attributes, GPA, prestige, prior research, academic year, and submission order. Major and first-time-researcher status are used only for synthetic evaluation, not scoring or global optimization. The FCFS baseline uses a seeded synthetic order solely to simulate that policy.

## Recorded synthetic benchmark

Seed 731 contains 60 submitted synthetic students. Forty-seven have at least one eligible pair at or above the default threshold. All three strategies place 27 students, which is 45.0% of the submitted cohort and 57.45% of the eligible cohort.

| Metric | Global | Greedy | Synthetic FCFS |
|---|---:|---:|---:|
| Placements | 27 | 27 | 27 |
| Mean compatibility | 88.37 | 88.37 | 87.96 |
| Median compatibility | 89.59 | 89.59 | 87.64 |
| Bottom-decile compatibility | 83.64 | 83.64 | 83.64 |
| Minimum compatibility | 82.64 | 82.64 | 82.64 |
| Top-choice rate | 100.0% | 100.0% | 100.0% |
| First-time students placed | 20/40 | 20/40 | 21/40 |
| Constraint violations | 0 | 0 | 0 |

The honest reading is limited:

- Global does **not** improve placement count over greedy on this un-tuned seed.
- Global and greedy produce the same aggregate score statistics here.
- FCFS has the same placement count and minimum, with a lower mean and median.
- These values describe one designed synthetic cohort, not expected university outcomes.

Per-major placement rates are reported with numerators and denominators. The seed’s major groups contain seven or eight records, so they are still small synthetic cells even though the implementation’s `<5` warning does not trigger.

## Why global allocation still matters

The design guarantee is visible in the two-student counterexample:

- A→P1 scores 95.
- A→P2 scores 90.
- B→P1 scores 94.
- P1 and P2 each have capacity one.

Greedy takes the highest edge, A→P1, leaving B unplaced. Count-first global allocation chooses A→P2 and B→P1, placing both. The counterexample proves a mechanism, not how frequently the advantage will occur in real cohorts.

## Order-invariance evidence

The recorded shuffle test permuted canonical inputs 20 times using seeds 1–20. All 20 produced assignments identical to the reference run, with no failing seed.

This supports input-order invariance for the frozen synthetic dataset. It does not test every possible input and does not establish demographic fairness. Stable opaque IDs participate in tie resolution, so changing IDs can change a genuine tie even when names and ingestion order do not.

## What is not measured

The prototype has no real applicant, acceptance, withdrawal, completion, or rematching data. It contains no protected-attribute data. It therefore cannot measure:

- demographic parity, equalized outcomes, or disparate impact;
- whether the compatibility formula predicts mentor/student success;
- whether students accept proposed placements;
- whether faculty accept proposed students;
- withdrawal or placement durability;
- reduced rematching rounds or administrator workload;
- long-term participation, learning, or retention effects.

A high compatibility index is not a probability of acceptance or a judgment of potential. Missing evidence receives explicit handling; it can still disadvantage profiles with less complete documentation. Human review can catch context the model lacks, but it can also introduce inconsistency unless decisions are governed and audited.

## Risks to monitor

- **Measurement choice:** taxonomy and weights encode policy judgments even without protected attributes.
- **Missing-data burden:** unresolved hard evidence blocks eligibility; missing soft evidence lowers some factors.
- **Opportunity definition:** student rankings, suggestion consent, capacity, and mandatory prerequisites determine which edges exist.
- **Proxy effects:** interests, skills, availability, or major-correlated opportunities may reproduce inequity even when protected attributes are absent.
- **Small denominators:** major and first-time summaries can move sharply with one synthetic record and should never be read as population estimates.
- **Tie policy:** stable-ID seeded tie resolution is reproducible but is not itself a substantive fairness policy.
- **Human decisions:** approval and any future override policy need reasons, conflict checks, and review.

## Proposed pilot evidence

An approved pilot should be prospective, time-bounded, and separate from production adoption. Before collecting institutional data, owners should define the allocation policy, minimum acceptable quality, consent language, access boundaries, retention period, and stop criteria.

At minimum, measure by cohort and stage:

1. invited, started, completed, submitted, eligible, proposed, approved, accepted, started placement, and completed placement counts;
2. explicit decline and withdrawal reasons;
3. number of rematching rounds and students affected;
4. time from cohort close to proposal, approval, acceptance, and placement;
5. faculty capacity changes and prerequisite disputes;
6. score, rank, and unplaced-reason distributions;
7. operational errors, manual interventions, and stale-run events.

Report both submitted- and eligible-cohort denominators. Predefine small-group suppression and privacy review before evaluating protected groups. Compare against an agreed baseline without claiming causation unless the study design supports it.

The checked-in evidence is available in [`backend/evidence/seeded-benchmark.json`](../backend/evidence/seeded-benchmark.json) and [`backend/evidence/seeded-benchmark.csv`](../backend/evidence/seeded-benchmark.csv). See [Algorithm](ALGORITHM.md) for formulas and [Limitations](LIMITATIONS.md) for unresolved policy questions.
