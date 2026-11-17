# ResearchBridge judge demo

This script is designed for 3–4 minutes. It demonstrates the product thesis without implying that the prototype is an official Iowa State service or that its synthetic results predict institutional outcomes.

## Before the demo

Complete the [native setup](../README.md#native-setup) once. Then reset to the reproducible baseline from the repository root:

```bash
npm run db:reset
```

Expected invariant: seed 731 reports 60 students, 20 projects, 10 faculty, and 18 skills, all synthetic/fictional/hypothetical.

Start the application:

```bash
npm run dev
```

In another terminal, verify the API:

```bash
curl --fail http://127.0.0.1:8000/health/live
curl --fail http://127.0.0.1:8000/health/ready
```

Open <http://127.0.0.1:3000>. If the development HMR WebSocket fails in a restricted sandbox, use the two-terminal production-UI path in the [README](../README.md#production-ui-local-check). That sandbox failure is not an application failure.

### Reset from the UI instead

If the app is already running:

1. Select **EUReCA Admin** in the demo role switcher.
2. Open **Data & import**.
3. Enter `RESET_SYNTHETIC_DEMO` in **Confirmation**.
4. Select **Reset to seeded data**.

This is destructive for the configured local SQLite demo database and has no backup step.

## Timed narrative

### 0:00–0:25 — State the thesis and boundaries

On `/`, say:

> ResearchBridge does not merely recommend research. It proposes a transparent allocation of limited research opportunities across the entire submitted cohort, subject to eligibility, capacity, and a minimum compatibility threshold. A human administrator must approve the result.

Point to the disclosure: all students are synthetic, all faculty identities are fictional, and all openings are hypothetical. The role switcher is a demo persona selector, not authentication. No email is sent and no university system is connected.

### 0:25–1:00 — Show student evidence and ranking

1. Select **Student**, then choose **Synthetic Learner 03**.
2. Open **Dashboard**. Point out profile completeness, batch status, and the specific next action.
3. Open **Profile**. Show interests, 0–4 skill proficiency, hours, learning goals, suggestion consent, and **Save & submit to batch**. Explain that submission joins a future batch; it does not allocate immediately.
4. Open **Projects**. Show search/filters, the hypothetical-opening label, capacity, mandatory versus trainable skills, schedule, and the ranked badge/button.

For the exact recorded benchmark, demonstrate these controls without saving changes or changing ranks. Any edit correctly changes the frozen input for a later run and may change the benchmark values.

### 1:00–1:25 — Show faculty-defined capacity

1. Select **Faculty**, keeping **Fictional Faculty Mentor 01 (demo)**.
2. Open **Projects** and select **Edit** on a project.
3. Show capacity, weekly commitment, active state, and mandatory/trainable skill classification.

Say that capacity is a hard allocation constraint and trainable skills are not hard eligibility requirements. Do not select **Save project** if you want the exact seed benchmark; saving would stale any proposed run and change later inputs.

### 1:25–2:15 — Run the cohort-wide allocation

1. Select **EUReCA Admin**.
2. Open **Configure & run**.
3. Show default weights: interests 35, technical skills 25, availability 20, ranked preference 10, and learning goals 10. Show the default minimum score of 60.
4. Select **Preview weights**. Explain that preview normalizes nonnegative weights but does not rewrite stored scores.
5. Select **Run batch**.
6. In **Run review**, show:
   - 27 placements;
   - minimum compatibility index 82.64;
   - proven stage status;
   - assignment rows and project capacity utilization;
   - the unmatched queue with specific reasons.
7. Select **Run shuffle test** and show `20/20` identical permutations.

Explain the lexicographic order: maximize placement count, then total compatibility, then the minimum assigned score, then resolve remaining ties through a seeded canonical order. The score is a compatibility index, not an acceptance probability.

### 2:15–2:50 — Be precise about evidence

Open **Fairness evidence**.

Point out:

- Global: 27 placements, mean 88.37, median 89.59.
- Greedy: 27 placements, mean 88.37, median 89.59.
- Synthetic FCFS: 27 placements, mean 87.96, median 87.64.
- Submitted placement rate: 45.0% for all three.
- Eligible count: 47; minimum assigned score: 82.64; constraint violations: 0.

Say plainly:

> Global allocation does not improve placement count over greedy on this un-tuned seed. The benefit is the mechanism and guarantee, not a fabricated win on every dataset.

Then show **Minimal counterexample**: A can use P1 or P2, while B can use only P1. Greedy takes A→P1 and places one; count-first global chooses A→P2 and B→P1 and places two. The shuffle evidence tests input-order invariance for this frozen synthetic dataset, not demographic fairness.

### 2:50–3:30 — Approve and show follow-through

1. Return to the run review with the browser **Back** action, or open **Overview → Review this run**.
2. Select **Approve run**. Before approval, students and faculty cannot see proposed assignments.
3. Select **Student**, choose **Synthetic Learner 03**, and open **Placement & roadmap**.
4. Show the approved placement, compatibility explanation, and factor breakdown under independent recommendations.
5. Show the 2–4 week **Skill roadmap**. Marking a task complete records progress; it does not verify mastery.
6. Show the editable **Outreach draft** and its **Save**, **Copy**, and **Download .txt** actions. Emphasize that there is no send action.

If time allows, switch to **Faculty → Assigned candidates** to show that fictional faculty see only candidates assigned to their projects after approval.

### 3:30–3:55 — Close with the adoption path

Summarize the [Workday roadmap](WORKDAY_ROADMAP.md):

1. synthetic local demo;
2. approved pilot imports;
3. authorized institutional integration with SSO, an approved Workday interface, field mapping, least privilege, consent/notice, and privacy review;
4. monitored production with retention, deletion, and audit controls.

The existing Workday class is only a hypothetical no-network contract. No stakeholder interview, Iowa State approval, or integration authorization is claimed.

Close with:

> This demo verifies transparent mechanics on synthetic data. A real pilot must measure acceptance, withdrawal, rematching rounds, and time-to-placement before making impact claims.

## Recovery notes

- **No runs appear:** reset, then create a run from **Configure & run**.
- **A run is stale:** a profile, project, configuration, or import changed. Create a new run; stale drafts cannot be approved.
- **Exports fail before approval:** JSON and CSV run exports intentionally require an approved run.
- **Wrong persona receives 403:** select the matching role/persona. The 403 is the expected server-side demo guard.
- **Exact metrics differ:** reset again and avoid saving profile, ranking, faculty, or configuration changes before the run.
