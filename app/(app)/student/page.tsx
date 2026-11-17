"use client";

import { api } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { PageHeader } from "@/components/app-shell";
import { Badge, KeyValue, LinkButton, Panel, SkeletonText, StatusCallout } from "@/components/ui";
import { LoadError } from "@/components/states";
import { dash } from "@/lib/format";
import type { StudentProfileResponse } from "@/lib/types";

const STATUS_TONE: Record<StudentProfileResponse["batch_status"], { tone: "neutral" | "info" | "success" | "warning"; label: string }> = {
  draft: { tone: "warning", label: "Draft — not submitted" },
  submitted: { tone: "info", label: "Submitted to batch" },
  approved_placement: { tone: "success", label: "Approved placement" },
  approved_unplaced: { tone: "warning", label: "Approved batch — unplaced" },
};

export default function StudentDashboard() {
  const { data, loading, error, refetch } = useApiResource<StudentProfileResponse>(
    (identity, signal) => api.studentProfile(identity.personaId, identity, signal),
    [],
  );

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Student workspace"
        title="Dashboard"
        description="Review your synthetic profile readiness and the single next action before the batch runs."
      />

      {loading && !data ? (
        <Panel>
          <SkeletonText lines={4} />
        </Panel>
      ) : error ? (
        <LoadError error={error} onRetry={refetch} />
      ) : data ? (
        <DashboardBody data={data} />
      ) : null}
    </div>
  );
}

function DashboardBody({ data }: { data: StudentProfileResponse }) {
  const status = STATUS_TONE[data.batch_status];
  const complete = data.missing_required_fields.length === 0;
  const student = data.student;

  return (
    <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
      <Panel
        title="Next action"
        action={<Badge tone={status.tone}>{status.label}</Badge>}
      >
        <p className="text-sm text-ink">{data.next_action}</p>
        <div className="mt-4 flex flex-wrap gap-3">
          <LinkButton href="/student/profile" variant="primary">
            Edit profile
          </LinkButton>
          <LinkButton href="/student/projects">Browse projects</LinkButton>
          {data.batch_status !== "draft" ? (
            <LinkButton href="/student/outcome">View placement</LinkButton>
          ) : null}
        </div>
        {!complete ? (
          <div className="mt-4">
            <StatusCallout tone="warning" title="Profile incomplete">
              Missing required fields: {data.missing_required_fields.join(", ")}. Missing
              mandatory information is treated as unresolved, not eligible.
            </StatusCallout>
          </div>
        ) : null}
      </Panel>

      <Panel title="Profile summary">
        <dl className="grid grid-cols-2 gap-4">
          <KeyValue label="Name" value={student.display_name} />
          <KeyValue label="Major" value={student.major} />
          <KeyValue label="Hours / week" value={dash(student.hours_per_week)} />
          <KeyValue label="Ranked projects" value={student.preferences.length} />
          <KeyValue label="Skills listed" value={student.skills.length} />
          <KeyValue
            label="Accepts suggestions"
            value={student.accepts_suggestions ? "Yes" : "No"}
          />
          <KeyValue
            label="First-time researcher"
            value={student.first_time_researcher ? "Yes" : "No"}
          />
          <KeyValue
            label="Completeness"
            value={complete ? "Complete" : `${data.missing_required_fields.length} missing`}
          />
        </dl>
        <p className="mt-4 text-xs text-ink-muted">{student.synthetic_label}</p>
      </Panel>
    </div>
  );
}
