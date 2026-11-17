"use client";

import { api } from "@/lib/api";
import { useDemo } from "@/lib/demo-context";
import { useApiResource } from "@/lib/use-api";
import { PageHeader } from "@/components/app-shell";
import { Badge, KeyValue, LinkButton, Panel, SkeletonText } from "@/components/ui";
import { LoadError } from "@/components/states";
import type { ProjectList } from "@/lib/types";

export default function FacultyOverview() {
  const { identity, personaLabel } = useDemo();
  const projects = useApiResource<ProjectList>(
    (id, signal) => api.projects(id, undefined, signal),
    [],
  );

  const mine =
    projects.data?.items.filter((p) => p.faculty_id === identity?.personaId) ?? [];
  const activeCount = mine.filter((p) => p.active).length;
  const totalCapacity = mine.reduce((sum, p) => sum + p.capacity, 0);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Faculty workspace"
        title="Overview"
        description="Manage hypothetical project openings. Assigned candidates appear only after an admin approves a run."
        action={
          <LinkButton href="/faculty/projects" variant="primary">
            Manage projects
          </LinkButton>
        }
      />

      {projects.error ? (
        <LoadError error={projects.error} onRetry={projects.refetch} />
      ) : projects.loading && !projects.data ? (
        <Panel>
          <SkeletonText lines={4} />
        </Panel>
      ) : (
        <>
          <Panel title="Fictional faculty identity">
            <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <KeyValue label="Persona" value={personaLabel(identity)} />
              <KeyValue label="Projects" value={mine.length} />
              <KeyValue label="Active" value={activeCount} />
              <KeyValue label="Total capacity" value={totalCapacity} />
            </dl>
            <p className="mt-4 text-xs text-ink-muted">
              Fictional faculty identity created for the synthetic demo. Not a real Iowa State
              profile.
            </p>
          </Panel>

          <Panel title="Your projects" description="Hypothetical openings you can edit.">
            {mine.length === 0 ? (
              <p className="text-sm text-ink-secondary">
                No projects yet. Create one from the Projects page.
              </p>
            ) : (
              <ul className="divide-y divide-divider">
                {mine.map((p) => (
                  <li key={p.id} className="flex items-center justify-between gap-3 py-3">
                    <div>
                      <p className="text-sm font-semibold text-ink">{p.title}</p>
                      <p className="text-xs text-ink-muted">
                        {p.department} · capacity {p.capacity} · {p.commitment_hours}h/wk
                      </p>
                    </div>
                    <Badge tone={p.active ? "success" : "neutral"}>
                      {p.active ? "Active" : "Inactive"}
                    </Badge>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </>
      )}
    </div>
  );
}
