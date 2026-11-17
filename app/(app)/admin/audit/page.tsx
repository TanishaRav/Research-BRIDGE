"use client";

import { api } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { PageHeader } from "@/components/app-shell";
import { Badge, EmptyState, Panel, SkeletonText } from "@/components/ui";
import { LoadError } from "@/components/states";
import { formatDateTime, titleCase } from "@/lib/format";
import type { DecisionAudit } from "@/lib/types";

export default function AdminAuditPage() {
  const audit = useApiResource<DecisionAudit[]>((id, signal) => api.audit(id, signal), []);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="EUReCA admin"
        title="Audit timeline"
        description="Append-only record of imports, submissions, config changes, runs, approvals, and resets."
      />

      <Panel>
        {audit.error ? (
          <LoadError error={audit.error} onRetry={audit.refetch} />
        ) : audit.loading && !audit.data ? (
          <SkeletonText lines={6} />
        ) : !audit.data || audit.data.length === 0 ? (
          <EmptyState title="No audit events yet">
            Decision events appear here as the demo is used.
          </EmptyState>
        ) : (
          <ol className="space-y-3">
            {audit.data.map((event) => (
              <li key={event.id} className="flex gap-3 border-b border-divider pb-3 last:border-0">
                <span className="mt-1 h-2 w-2 flex-none rounded-full bg-accent" aria-hidden="true" />
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-semibold text-ink">
                      {titleCase(event.event_type)}
                    </span>
                    <Badge tone="neutral">{event.actor_role}</Badge>
                    <span className="text-xs text-ink-muted">
                      {formatDateTime(event.created_at)}
                    </span>
                  </div>
                  <p className="mt-0.5 text-xs text-ink-secondary">
                    {event.entity_type}
                    {event.entity_id ? `: ${event.entity_id}` : ""}
                    {event.reason ? ` — ${event.reason}` : ""}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        )}
      </Panel>
    </div>
  );
}
