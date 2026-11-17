"use client";

import Link from "next/link";
import { api } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { PageHeader } from "@/components/app-shell";
import { Badge, KeyValue, LinkButton, Panel, SkeletonText } from "@/components/ui";
import { LoadError } from "@/components/states";
import { formatDateTime } from "@/lib/format";
import type { MatchRun, ProjectList } from "@/lib/types";

const STATUS_TONE: Record<string, "neutral" | "info" | "success" | "warning" | "error"> = {
  proposed: "info",
  approved: "success",
  failed: "error",
  feasible_not_proven: "warning",
};

export default function AdminOverview() {
  const projects = useApiResource<ProjectList>(
    (id, signal) => api.projects(id, undefined, signal),
    [],
  );
  const runs = useApiResource<MatchRun[]>((id, signal) => api.runs(id, signal), []);

  const items = projects.data?.items ?? [];
  const activeProjects = items.filter((p) => p.active && p.capacity > 0);
  const totalCapacity = activeProjects.reduce((sum, p) => sum + p.capacity, 0);
  const latest = runs.data?.[0];

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="EUReCA admin"
        title="Overview"
        description="Cohort readiness, capacity, and the latest batch runs. Allocation requires your explicit approval."
        action={
          <LinkButton href="/admin/run" variant="primary">
            Configure & run
          </LinkButton>
        }
      />

      <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
        <Panel title="Data readiness">
          {projects.error ? (
            <LoadError error={projects.error} onRetry={projects.refetch} />
          ) : projects.loading && !projects.data ? (
            <SkeletonText lines={3} />
          ) : (
            <dl className="grid grid-cols-2 gap-4">
              <KeyValue label="Projects" value={items.length} />
              <KeyValue label="Active w/ capacity" value={activeProjects.length} />
              <KeyValue label="Total active capacity" value={totalCapacity} />
              <KeyValue
                label="Zero-capacity / inactive"
                value={items.length - activeProjects.length}
              />
            </dl>
          )}
        </Panel>

        <Panel title="Latest run">
          {runs.error ? (
            <LoadError error={runs.error} onRetry={runs.refetch} />
          ) : runs.loading && !runs.data ? (
            <SkeletonText lines={3} />
          ) : !latest ? (
            <p className="text-sm text-ink-secondary">
              No runs yet. Start one from Configure &amp; run.
            </p>
          ) : (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <Badge tone={STATUS_TONE[latest.status] ?? "neutral"}>{latest.status}</Badge>
                {latest.stale ? <Badge tone="warning">Stale</Badge> : null}
              </div>
              <dl className="grid grid-cols-2 gap-4">
                <KeyValue label="Placements" value={latest.placement_count} />
                <KeyValue label="Created" value={formatDateTime(latest.created_at)} />
              </dl>
              <LinkButton href={`/admin/run?run=${latest.id}`}>
                Review this run
              </LinkButton>
            </div>
          )}
        </Panel>
      </div>

      <Panel title="Recent runs">
        {runs.data && runs.data.length > 0 ? (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-divider text-left text-xs uppercase tracking-wide text-ink-muted">
                <th className="py-2 pr-4 font-medium">Run</th>
                <th className="py-2 pr-4 font-medium">Status</th>
                <th className="py-2 pr-4 text-right font-medium">Placements</th>
                <th className="py-2 pr-4 font-medium">Created</th>
              </tr>
            </thead>
            <tbody>
              {runs.data.map((run) => (
                <tr key={run.id} className="border-b border-divider last:border-0">
                  <td className="py-2 pr-4">
                    <Link className="font-mono text-xs text-accent" href={`/admin/run?run=${run.id}`}>
                      {run.id.slice(0, 16)}…
                    </Link>
                  </td>
                  <td className="py-2 pr-4">
                    <Badge tone={STATUS_TONE[run.status] ?? "neutral"}>{run.status}</Badge>
                  </td>
                  <td className="tnum py-2 pr-4 text-right">{run.placement_count}</td>
                  <td className="py-2 pr-4 text-ink-secondary">{formatDateTime(run.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-sm text-ink-secondary">No runs recorded yet.</p>
        )}
      </Panel>
    </div>
  );
}
