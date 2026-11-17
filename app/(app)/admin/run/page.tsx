"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { useDemo } from "@/lib/demo-context";
import { useApiResource } from "@/lib/use-api";
import { PageHeader } from "@/components/app-shell";
import {
  Badge,
  Button,
  EmptyState,
  Field,
  KeyValue,
  Panel,
  SkeletonText,
  StatusCallout,
  TextInput,
} from "@/components/ui";
import { LoadError } from "@/components/states";
import { bpToIndex, newIdempotencyKey, reasonLabel } from "@/lib/format";
import type { NormalizedConfig, RunReview } from "@/lib/types";

const FACTORS: Array<{ key: keyof NormalizedConfig["config"]["weights"]; label: string }> = [
  { key: "interest", label: "Research interest" },
  { key: "technical_skill", label: "Technical skill" },
  { key: "availability", label: "Availability" },
  { key: "preference", label: "Ranked preference" },
  { key: "learning_goal", label: "Learning goal" },
];

export default function AdminRunPage() {
  return (
    <Suspense fallback={<SkeletonText lines={6} />}>
      <AdminRun />
    </Suspense>
  );
}

function AdminRun() {
  const { identity } = useDemo();
  const router = useRouter();
  const params = useSearchParams();
  const selectedRunId = params.get("run");

  const config = useApiResource<NormalizedConfig>(
    (id, signal) => api.config(id, signal),
    [],
  );

  const [weights, setWeights] = useState<Record<string, string>>({});
  const [threshold, setThreshold] = useState("60");
  const [preview, setPreview] = useState<NormalizedConfig | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  useEffect(() => {
    if (config.data) {
      setWeights({ ...config.data.config.weights });
      setThreshold(config.data.config.threshold);
    }
  }, [config.data]);

  function buildConfig() {
    return {
      weights: {
        interest: weights.interest ?? "0",
        technical_skill: weights.technical_skill ?? "0",
        availability: weights.availability ?? "0",
        preference: weights.preference ?? "0",
        learning_goal: weights.learning_goal ?? "0",
      },
      threshold,
      score_version: config.data?.config.score_version ?? "rb-score-v1",
      taxonomy_version: config.data?.config.taxonomy_version ?? "rb-taxonomy-v1",
      solver_seed: 731,
      worker_count: 1 as const,
    };
  }

  async function doPreview() {
    if (!identity) return;
    setPreviewError(null);
    try {
      const result = await api.previewConfig(identity, buildConfig());
      setPreview(result);
    } catch (err) {
      if (err instanceof ApiError) {
        setPreview(null);
        setPreviewError(err.message);
      }
    }
  }

  async function runBatch() {
    if (!identity) return;
    setRunning(true);
    setRunError(null);
    try {
      await api.patchConfig(identity, {
        weights: buildConfig().weights,
        threshold,
      });
      const run = await api.createRun(identity, newIdempotencyKey("run"), {});
      router.replace(`/admin/run?run=${run.id}`);
    } catch (err) {
      if (err instanceof ApiError) setRunError(err.message);
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="EUReCA admin"
        title="Configure & run"
        description="Adjust nonnegative weights, preview normalization, run a batch, then review and approve. Scores change only for a new run."
      />

      <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
        <Panel title="Scoring configuration">
          {config.error ? (
            <LoadError error={config.error} onRetry={config.refetch} />
          ) : config.loading && !config.data ? (
            <SkeletonText lines={5} />
          ) : (
            <div className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2">
                {FACTORS.map((factor) => (
                  <Field key={factor.key} label={factor.label} htmlFor={`w-${factor.key}`}>
                    <TextInput
                      id={`w-${factor.key}`}
                      type="number"
                      min={0}
                      value={weights[factor.key] ?? ""}
                      onChange={(e) =>
                        setWeights((prev) => ({ ...prev, [factor.key]: e.target.value }))
                      }
                    />
                  </Field>
                ))}
                <Field label="Minimum score (0–100)" htmlFor="threshold">
                  <TextInput
                    id="threshold"
                    type="number"
                    min={0}
                    max={100}
                    value={threshold}
                    onChange={(e) => setThreshold(e.target.value)}
                  />
                </Field>
              </div>

              {previewError ? (
                <StatusCallout tone="error">{previewError}</StatusCallout>
              ) : null}

              {preview ? (
                <StatusCallout tone="info" title="Normalized weights (preview)">
                  <ul className="mt-1 space-y-0.5">
                    {Object.entries(preview.normalized_weights_percent).map(([key, value]) => (
                      <li key={key} className="tnum text-sm">
                        {key}: {Number(value).toFixed(1)}%
                      </li>
                    ))}
                  </ul>
                  <p className="mt-1 text-xs">Preview does not change stored scores.</p>
                </StatusCallout>
              ) : null}

              <div className="flex flex-wrap gap-3">
                <Button variant="secondary" onClick={doPreview}>
                  Preview weights
                </Button>
                <Button variant="primary" loading={running} onClick={runBatch}>
                  Run batch
                </Button>
              </div>
              {runError ? <StatusCallout tone="error">{runError}</StatusCallout> : null}
            </div>
          )}
        </Panel>

        <Panel title="How allocation works" description="Deterministic, staged, and human-approved.">
          <ol className="list-decimal space-y-2 pl-5 text-sm text-ink-secondary">
            <li>Load and validate the entire submitted cohort before optimizing.</li>
            <li>Maximize the number of acceptable placements.</li>
            <li>Within that, maximize total compatibility.</li>
            <li>Then raise the minimum assigned score where feasible.</li>
            <li>Resolve remaining ties with a canonical seeded order, independent of input order.</li>
          </ol>
          <p className="mt-3 text-xs text-ink-muted">
            A merely feasible, time-limited result is never labeled optimal.
          </p>
        </Panel>
      </div>

      {selectedRunId ? <RunReviewPanel runId={selectedRunId} /> : (
        <EmptyState title="No run selected">
          Run a batch or open one from the overview to review assignments, utilization, and
          approval.
        </EmptyState>
      )}
    </div>
  );
}

function RunReviewPanel({ runId }: { runId: string }) {
  const { identity } = useDemo();
  const review = useApiResource<RunReview>(
    (id, signal) => api.runReview(runId, id, signal),
    [runId],
  );
  const [busy, setBusy] = useState<string | null>(null);
  const [shuffle, setShuffle] = useState<number | null>(null);
  const [message, setMessage] = useState<{ tone: "success" | "error"; text: string } | null>(null);

  async function approve() {
    if (!identity) return;
    setBusy("approve");
    setMessage(null);
    try {
      await api.approveRun(runId, identity, newIdempotencyKey("approve"));
      setMessage({ tone: "success", text: "Run approved. Students and faculty can now see results." });
      review.refetch();
    } catch (err) {
      if (err instanceof ApiError) setMessage({ tone: "error", text: err.message });
    } finally {
      setBusy(null);
    }
  }

  async function runShuffle() {
    if (!identity) return;
    setBusy("shuffle");
    try {
      const result = (await api.shuffleTest(runId, identity, newIdempotencyKey("shuffle"))) as {
        identical_assignment_pass_count?: number;
      };
      setShuffle(result.identical_assignment_pass_count ?? null);
    } catch (err) {
      if (err instanceof ApiError) setMessage({ tone: "error", text: err.message });
    } finally {
      setBusy(null);
    }
  }

  async function downloadExport(format: "json" | "csv") {
    if (!identity) return;
    setBusy(`export-${format}`);
    setMessage(null);
    try {
      const { blob, filename } = await api.downloadRunExport(runId, format, identity);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setMessage({ tone: "success", text: `${format.toUpperCase()} export downloaded.` });
    } catch (err) {
      if (err instanceof ApiError) setMessage({ tone: "error", text: err.message });
    } finally {
      setBusy(null);
    }
  }

  if (review.error) return <LoadError error={review.error} onRetry={review.refetch} />;
  if (review.loading && !review.data) {
    return (
      <Panel title="Run review">
        <SkeletonText lines={6} />
      </Panel>
    );
  }
  if (!review.data) return null;

  const { run, assignments, unplaced, project_utilization } = review.data;
  const unplacedEntries = Object.entries(unplaced);
  const approved = run.status === "approved";

  return (
    <div className="space-y-6">
      <Panel
        title="Run review"
        description={`Run ${run.id.slice(0, 16)}… · seed ${run.solver_seed} · ${run.worker_count} worker`}
        action={
          <div className="flex items-center gap-2">
            {run.stale ? <Badge tone="warning">Stale</Badge> : null}
            <Badge tone={approved ? "success" : "info"}>{run.status}</Badge>
          </div>
        }
      >
        {message ? <StatusCallout tone={message.tone}>{message.text}</StatusCallout> : null}
        {run.stale ? (
          <StatusCallout tone="warning" title="This draft is stale">
            Underlying data changed: {run.stale_reasons.join(", ") || "profile or project edits"}.
            Run a new batch to approve current data.
          </StatusCallout>
        ) : null}
        <dl className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
          <KeyValue label="Placements" value={run.placement_count} />
          <KeyValue
            label="Min score"
            value={run.minimum_score_bp !== null ? bpToIndex(run.minimum_score_bp) : "—"}
          />
          <KeyValue label="Runtime (ms)" value={run.runtime_ms} />
          <KeyValue
            label="Optimality"
            value={run.optimality_limitation ? "Time-limited" : "Proven per stage"}
          />
        </dl>

        <div className="mt-5 border-t border-divider pt-4">
          <h3 className="text-sm font-semibold text-ink">Executed solver stages</h3>
          <ol className="mt-2 grid gap-2 sm:grid-cols-2">
            {run.stage_evidence.map((stage, index) => (
              <li key={`${stage.name}-${index}`} className="flex items-start justify-between gap-3 rounded-md bg-subtle px-3 py-2">
                <span>
                  <span className="block text-xs font-semibold text-ink">
                    {index + 1}. {stage.name.replaceAll("_", " ")}
                  </span>
                  {stage.detail ? (
                    <span className="mt-0.5 block text-xs text-ink-muted">{stage.detail}</span>
                  ) : null}
                </span>
                <span className="tnum text-right text-xs text-ink-secondary">
                  {stage.status} · {stage.runtime_ms} ms
                  {stage.objective !== null ? ` · obj ${stage.objective}` : ""}
                </span>
              </li>
            ))}
          </ol>
        </div>

        <div className="mt-4 flex flex-wrap gap-3">
          <Button variant="primary" loading={busy === "approve"} onClick={approve} disabled={approved || run.stale}>
            {approved ? "Approved" : "Approve run"}
          </Button>
          <Button variant="secondary" loading={busy === "shuffle"} onClick={runShuffle}>
            Run shuffle test
          </Button>
          <Button
            variant="secondary"
            loading={busy === "export-json"}
            onClick={() => downloadExport("json")}
          >
            Export JSON
          </Button>
          <Button
            variant="secondary"
            loading={busy === "export-csv"}
            onClick={() => downloadExport("csv")}
          >
            Export CSV
          </Button>
        </div>
        {shuffle !== null ? (
          <p className="mt-3 tnum text-sm text-success">
            Shuffle test: {shuffle}/20 permutations produced identical assignments.
          </p>
        ) : null}
      </Panel>

      <div className="grid gap-6 lg:grid-cols-[1.3fr_1fr]">
        <Panel title="Assignments" description={`${assignments.length} placed`}>
          {assignments.length === 0 ? (
            <p className="text-sm text-ink-secondary">No assignments in this run.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-divider text-left text-xs uppercase tracking-wide text-ink-muted">
                  <th className="py-2 pr-4 font-medium">Student</th>
                  <th className="py-2 pr-4 font-medium">Project</th>
                  <th className="py-2 pr-4 text-right font-medium">Index</th>
                </tr>
              </thead>
              <tbody>
                {assignments.map((a) => (
                  <tr key={a.student_id} className="border-b border-divider last:border-0">
                    <td className="py-2 pr-4 font-mono text-xs">{a.student_id}</td>
                    <td className="py-2 pr-4 font-mono text-xs">{a.project_id}</td>
                    <td className="tnum py-2 pr-4 text-right">{bpToIndex(a.score_bp)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>

        <Panel title="Project capacity utilization">
          <ul className="space-y-1.5 text-sm">
            {Object.entries(project_utilization).map(([projectId, util]) => (
              <li key={projectId} className="flex items-center justify-between gap-2">
                <span className="font-mono text-xs text-ink-secondary">{projectId}</span>
                <span className="tnum text-ink">
                  {util.assigned}/{util.capacity}
                </span>
              </li>
            ))}
          </ul>
        </Panel>
      </div>

      <Panel title="Unmatched queue" description={`${unplacedEntries.length} unplaced with specific reasons`}>
        {unplacedEntries.length === 0 ? (
          <p className="text-sm text-ink-secondary">All submitted students were placed.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-divider text-left text-xs uppercase tracking-wide text-ink-muted">
                <th className="py-2 pr-4 font-medium">Student</th>
                <th className="py-2 pr-4 font-medium">Reasons</th>
              </tr>
            </thead>
            <tbody>
              {unplacedEntries.map(([studentId, reasons]) => (
                <tr key={studentId} className="border-b border-divider last:border-0">
                  <td className="py-2 pr-4 font-mono text-xs">{studentId}</td>
                  <td className="py-2 pr-4 text-ink-secondary">
                    {reasons.map(reasonLabel).join("; ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}
