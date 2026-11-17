"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useApiResource } from "@/lib/use-api";
import { PageHeader } from "@/components/app-shell";
import { Badge, EmptyState, Panel, Select, SkeletonText, StatusCallout } from "@/components/ui";
import { LoadError } from "@/components/states";
import { percentFromRatio } from "@/lib/format";
import type { MatchRun, RunEvidenceResponse, StrategyMetrics } from "@/lib/types";

const STRATEGY_ORDER = ["global", "greedy", "fcfs"];
const STRATEGY_LABEL: Record<string, string> = {
  global: "Global (cohort-wide)",
  greedy: "Greedy (highest score)",
  fcfs: "FCFS (simulation)",
};

export default function AdminEvidencePage() {
  const runs = useApiResource<MatchRun[]>((id, signal) => api.runs(id, signal), []);
  const [runId, setRunId] = useState<string | null>(null);

  useEffect(() => {
    if (runs.data && runs.data.length > 0 && runId === null) {
      setRunId(runs.data[0]!.id);
    }
  }, [runs.data, runId]);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="EUReCA admin"
        title="Fairness evidence"
        description="Measured comparison of global allocation against greedy and FCFS baselines on identical data, plus order-invariance proof."
        action={
          runs.data && runs.data.length > 0 ? (
            <Select
              aria-label="Select run"
              value={runId ?? ""}
              onChange={(e) => setRunId(e.target.value)}
            >
              {runs.data.map((run) => (
                <option key={run.id} value={run.id}>
                  {run.id.slice(0, 16)}… ({run.status})
                </option>
              ))}
            </Select>
          ) : undefined
        }
      />

      {runs.error ? (
        <LoadError error={runs.error} onRetry={runs.refetch} />
      ) : runs.loading && !runs.data ? (
        <Panel>
          <SkeletonText lines={5} />
        </Panel>
      ) : !runs.data || runs.data.length === 0 ? (
        <EmptyState title="No runs to evaluate">
          Create a run from Configure &amp; run to generate fairness evidence.
        </EmptyState>
      ) : runId ? (
        <EvidenceForRun runId={runId} />
      ) : null}
    </div>
  );
}

function EvidenceForRun({ runId }: { runId: string }) {
  const evidence = useApiResource<RunEvidenceResponse>(
    (id, signal) => api.runEvidence(runId, id, signal),
    [runId],
  );

  if (evidence.error) return <LoadError error={evidence.error} onRetry={evidence.refetch} />;
  if (evidence.loading && !evidence.data) {
    return (
      <Panel>
        <SkeletonText lines={6} />
      </Panel>
    );
  }
  if (!evidence.data) return null;

  const benchmark = evidence.data.benchmark;
  const shuffle = evidence.data.shuffle;

  return (
    <div className="space-y-6">
      <StatusCallout tone="warning" title="What this evidence can and cannot show">
        {evidence.data.limitation}
      </StatusCallout>

      {benchmark ? (
        <Panel title="Strategy comparison" description="Identical eligibility, scores, capacities, and threshold.">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead>
                <tr className="border-b border-divider text-left text-xs uppercase tracking-wide text-ink-muted">
                  <th className="py-2 pr-4 font-medium">Metric</th>
                  {STRATEGY_ORDER.map((key) => (
                    <th key={key} className="py-2 pr-4 text-right font-medium">
                      {STRATEGY_LABEL[key]}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <MetricRow label="Placements" strategies={benchmark.strategies} render={(m) => m.placement_count} />
                <MetricRow
                  label="Placement rate (submitted)"
                  strategies={benchmark.strategies}
                  render={(m) => percentFromRatio(m.placement_rate_submitted)}
                />
                <MetricRow label="Mean score" strategies={benchmark.strategies} render={(m) => m.mean_score ?? "—"} />
                <MetricRow label="Median score" strategies={benchmark.strategies} render={(m) => m.median_score ?? "—"} />
                <MetricRow
                  label="Bottom-decile score"
                  strategies={benchmark.strategies}
                  render={(m) => m.bottom_decile_score ?? "—"}
                />
                <MetricRow label="Minimum score" strategies={benchmark.strategies} render={(m) => m.minimum_score ?? "—"} />
                <MetricRow
                  label="Top-choice rate"
                  strategies={benchmark.strategies}
                  render={(m) => percentFromRatio(m.top_choice_rate)}
                />
                <MetricRow
                  label="First-time placed"
                  strategies={benchmark.strategies}
                  render={(m) => `${m.first_time_placed}/${m.first_time_denominator}`}
                />
                <MetricRow label="Unplaced" strategies={benchmark.strategies} render={(m) => m.unplaced_count} />
                <MetricRow
                  label="Constraint violations"
                  strategies={benchmark.strategies}
                  render={(m) => m.constraint_violations.total}
                />
                <MetricRow label="Runtime (ms)" strategies={benchmark.strategies} render={(m) => m.runtime_ms} />
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-xs text-ink-muted">
            Preference satisfaction and acceptable-placement coverage are proxies, not causal
            impact.
          </p>
        </Panel>
      ) : null}

      {benchmark ? (
        <Panel title="Minimal counterexample" description="Why count-first global allocation can beat greedy.">
          <p className="text-sm text-ink-secondary">{benchmark.counterexample.description}</p>
          <div className="mt-3 grid gap-4 sm:grid-cols-2">
            <div className="rounded-md border border-divider p-3">
              <p className="text-sm font-semibold text-ink">
                Greedy: {benchmark.counterexample.greedy_placement_count} placed
              </p>
              <ul className="mt-1 space-y-0.5 font-mono text-xs text-ink-secondary">
                {benchmark.counterexample.greedy_assignments.map(([s, p]) => (
                  <li key={`${s}-${p}`}>{s} → {p}</li>
                ))}
              </ul>
            </div>
            <div className="rounded-md border border-accent/30 bg-accent-soft p-3">
              <p className="text-sm font-semibold text-accent-pressed">
                Global: {benchmark.counterexample.global_placement_count} placed
              </p>
              <ul className="mt-1 space-y-0.5 font-mono text-xs text-accent-pressed">
                {benchmark.counterexample.global_assignments.map(([s, p]) => (
                  <li key={`${s}-${p}`}>{s} → {p}</li>
                ))}
              </ul>
            </div>
          </div>
        </Panel>
      ) : null}

      <Panel title="Shuffle / order-invariance test">
        {!shuffle ? (
          <p className="text-sm text-ink-secondary">
            Run the shuffle test from the run review to populate this evidence.
          </p>
        ) : (
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <Badge tone={shuffle.identical_assignment_pass_count === 20 ? "success" : "error"}>
                {shuffle.identical_assignment_pass_count}/20 identical
              </Badge>
              {shuffle.failing_seeds.length > 0 ? (
                <span className="text-xs text-error">
                  Failing seeds: {shuffle.failing_seeds.join(", ")}
                </span>
              ) : null}
            </div>
            <p className="text-sm text-ink-secondary">{shuffle.statement}</p>
          </div>
        )}
      </Panel>
    </div>
  );
}

function MetricRow({
  label,
  strategies,
  render,
}: {
  label: string;
  strategies: Record<string, StrategyMetrics>;
  render: (metrics: StrategyMetrics) => React.ReactNode;
}) {
  return (
    <tr className="border-b border-divider last:border-0">
      <td className="py-2 pr-4 text-ink">{label}</td>
      {STRATEGY_ORDER.map((key) => {
        const metrics = strategies[key];
        return (
          <td key={key} className="tnum py-2 pr-4 text-right text-ink-secondary">
            {metrics ? render(metrics) : "—"}
          </td>
        );
      })}
    </tr>
  );
}
