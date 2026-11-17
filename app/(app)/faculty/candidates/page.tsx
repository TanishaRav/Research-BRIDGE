"use client";

import { api } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { PageHeader } from "@/components/app-shell";
import { EmptyState, Panel, SkeletonText, StatusCallout } from "@/components/ui";
import { LoadError } from "@/components/states";
import type { FacultyAssignment } from "@/lib/types";

export default function FacultyCandidatesPage() {
  const assignments = useApiResource<FacultyAssignment[]>(
    (id, signal) => api.facultyAssignments(id.personaId, id, signal),
    [],
  );

  const grouped = new Map<string, FacultyAssignment[]>();
  (assignments.data ?? []).forEach((a) => {
    const list = grouped.get(a.project_id) ?? [];
    list.push(a);
    grouped.set(a.project_id, list);
  });

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Faculty workspace"
        title="Assigned candidates"
        description="Candidates are shown only after an EUReCA admin approves a batch run."
      />

      <StatusCallout tone="info">
        These are synthetic candidates from the latest approved run. No contact is made and no
        other students&rsquo; private data is shown.
      </StatusCallout>

      {assignments.error ? (
        <LoadError error={assignments.error} onRetry={assignments.refetch} />
      ) : assignments.loading && !assignments.data ? (
        <Panel>
          <SkeletonText lines={4} />
        </Panel>
      ) : (assignments.data ?? []).length === 0 ? (
        <EmptyState title="No assigned candidates yet">
          Either no batch has been approved, or none of your projects received assignments in the
          latest approved run.
        </EmptyState>
      ) : (
        Array.from(grouped.entries()).map(([projectId, items]) => (
          <Panel key={projectId} title={projectId} description={`${items.length} assigned candidate${items.length === 1 ? "" : "s"}`}>
            <ul className="divide-y divide-divider">
              {items.map((candidate) => (
                <li key={candidate.student_id} className="py-3">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-semibold text-ink">
                      {candidate.student_display_name}
                    </p>
                    <span className="tnum text-sm text-ink-secondary">
                      {candidate.compatibility_index}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-ink-secondary">{candidate.explanation}</p>
                  <p className="mt-1 text-xs text-ink-muted">{candidate.synthetic_label}</p>
                </li>
              ))}
            </ul>
          </Panel>
        ))
      )}
    </div>
  );
}
