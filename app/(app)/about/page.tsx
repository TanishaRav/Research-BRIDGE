"use client";

import { PageHeader } from "@/components/app-shell";
import { Panel, StatusCallout } from "@/components/ui";

export default function AboutPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="About"
        title="How ResearchBridge works"
        description="An independent prototype for transparent EUReCA research placement. Not an official Iowa State service."
      />

      <StatusCallout tone="warning" title="Synthetic data only">
        Every student is synthetic, every faculty identity is fictional, and every project opening
        is hypothetical. No real student data, credentials, or records are used anywhere.
      </StatusCallout>

      <Panel title="Batch allocation, not first-come assignment">
        <p className="text-sm leading-relaxed text-ink-secondary">
          Students build profiles and submit to a batch. An administrator then runs a single
          cohort-wide optimization that places everyone at once, subject to eligibility, project
          capacity, and a minimum compatibility threshold. Submission never allocates immediately.
        </p>
      </Panel>

      <Panel title="Explainable compatibility index">
        <p className="text-sm leading-relaxed text-ink-secondary">
          Each eligible student–project pair receives a 0–100 compatibility index from five
          normalized factors: research interest alignment, technical skill overlap, availability
          beyond the hard minimum, ranked preference, and learning-goal alignment with mentoring.
          The index is not a probability of acceptance. Names, demographics, GPA, prestige, prior
          research, and submission order never affect the score.
        </p>
      </Panel>

      <Panel title="Human approval and auditability">
        <p className="text-sm leading-relaxed text-ink-secondary">
          The optimizer proposes a placement; an administrator reviews and approves it. Editing a
          profile or project marks affected drafts stale, and approved runs never change silently.
          Every consequential action is recorded in an append-only audit timeline.
        </p>
      </Panel>

      <Panel title="Demo roles are not authentication">
        <p className="text-sm leading-relaxed text-ink-secondary">
          The role switcher selects seeded demo personas so you can explore the student, faculty,
          and admin journeys. It is not production authentication or authorization. Server-side
          checks guard role-restricted routes in this prototype, but production authentication is
          not implemented.
        </p>
      </Panel>

      <Panel title="What the evidence can and cannot show">
        <p className="text-sm leading-relaxed text-ink-secondary">
          The fairness view compares global allocation against greedy and first-come-first-served
          baselines on identical data, and a shuffle test confirms the result does not depend on
          input order. These are proxies on synthetic data. They cannot establish real-world
          rematching reduction or demographic fairness. A real pilot would need to measure
          acceptance, withdrawals, rematching rounds, and time-to-placement.
        </p>
      </Panel>
    </div>
  );
}
