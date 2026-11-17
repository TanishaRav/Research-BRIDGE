"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useDemo } from "@/lib/demo-context";
import { useApiResource } from "@/lib/use-api";
import { PageHeader } from "@/components/app-shell";
import {
  Badge,
  Button,
  EmptyState,
  Field,
  Panel,
  SkeletonText,
  StatusCallout,
  TextArea,
  TextInput,
} from "@/components/ui";
import { LoadError } from "@/components/states";
import { ScoreBreakdown } from "@/components/score-breakdown";
import { bpToIndex, reasonLabel } from "@/lib/format";
import type {
  OutreachDraft,
  Recommendation,
  Roadmap,
  RoadmapTask,
  StudentOutcome,
} from "@/lib/types";

export default function StudentOutcomePage() {
  const outcome = useApiResource<StudentOutcome>(
    (id, signal) => api.outcome(id.personaId, id, signal),
    [],
  );
  const recommendations = useApiResource<Recommendation[]>(
    (id, signal) => api.recommendations(id.personaId, id, signal),
    [],
  );

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Student workspace"
        title="Placement & roadmap"
        description="Your approved allocation is distinct from independent recommendations. Nothing here contacts faculty."
      />

      {outcome.error ? (
        <LoadError error={outcome.error} onRetry={outcome.refetch} />
      ) : outcome.loading && !outcome.data ? (
        <Panel>
          <SkeletonText lines={4} />
        </Panel>
      ) : outcome.data ? (
        <OutcomePanel outcome={outcome.data} />
      ) : null}

      {outcome.data?.status === "placed" ? <FollowThrough /> : null}

      <Panel
        title="Independent recommendations"
        description="Ranked by compatibility. These are not an allocation result."
      >
        {recommendations.error ? (
          <LoadError error={recommendations.error} onRetry={recommendations.refetch} />
        ) : recommendations.loading && !recommendations.data ? (
          <SkeletonText lines={4} />
        ) : !recommendations.data || recommendations.data.length === 0 ? (
          <EmptyState title="No eligible recommendations yet">
            Complete required profile fields and rank projects, or accept suggestions, to see
            eligible matches.
          </EmptyState>
        ) : (
          <Recommendations items={recommendations.data} />
        )}
      </Panel>
    </div>
  );
}

function OutcomePanel({ outcome }: { outcome: StudentOutcome }) {
  if (outcome.status === "pending") {
    return (
      <StatusCallout tone="info" title="No approved batch yet">
        {outcome.notice}
      </StatusCallout>
    );
  }
  if (outcome.status === "placed" && outcome.assignment) {
    return (
      <Panel
        title="Approved placement"
        action={<Badge tone="success">Placed</Badge>}
      >
        <p className="text-sm text-ink">
          Assigned to{" "}
          <span className="font-semibold">{outcome.assignment.project_id}</span> with a
          compatibility index of{" "}
          <span className="tnum">{bpToIndex(outcome.assignment.score_bp)}</span>.
        </p>
        <StatusCallout tone="info" title="Why this project">
          {outcome.assignment.global_rationale}
        </StatusCallout>
        <p className="mt-3 text-xs text-ink-muted">{outcome.notice}</p>
      </Panel>
    );
  }
  return (
    <Panel title="Batch outcome" action={<Badge tone="warning">Unplaced</Badge>}>
      <p className="text-sm text-ink">This cohort run did not place you. Specific reasons:</p>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-ink-secondary">
        {outcome.reasons.length === 0 ? (
          <li>No specific reason recorded.</li>
        ) : (
          outcome.reasons.map((reason) => <li key={reason}>{reasonLabel(reason)}</li>)
        )}
      </ul>
      <p className="mt-3 text-xs text-ink-muted">{outcome.notice}</p>
    </Panel>
  );
}

function Recommendations({ items }: { items: Recommendation[] }) {
  const [openId, setOpenId] = useState<string | null>(items[0]?.project.id ?? null);
  return (
    <div className="space-y-2">
      {items.map((rec) => {
        const open = openId === rec.project.id;
        return (
          <div key={rec.project.id} className="rounded-md border border-divider">
            <button
              type="button"
              className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
              aria-expanded={open}
              onClick={() => setOpenId(open ? null : rec.project.id)}
            >
              <span className="text-sm font-semibold text-ink">{rec.project.title}</span>
              <span className="tnum text-sm text-ink-secondary">
                {bpToIndex(rec.pair_score.total_bp)}
              </span>
            </button>
            {open ? (
              <div className="border-t border-divider px-4 py-4">
                <ScoreBreakdown pair={rec.pair_score} />
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

function FollowThrough() {
  const { identity } = useDemo();
  const roadmap = useApiResource<Roadmap>(
    (id, signal) => api.roadmap(id.personaId, id, signal),
    [],
  );
  const outreach = useApiResource<OutreachDraft>(
    (id, signal) => api.outreach(id.personaId, id, signal),
    [],
  );

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Panel title="Skill roadmap" description="Completion records progress only; it does not verify mastery.">
        {roadmap.error ? (
          <LoadError error={roadmap.error} onRetry={roadmap.refetch} />
        ) : roadmap.loading && !roadmap.data ? (
          <SkeletonText lines={5} />
        ) : roadmap.data ? (
          <RoadmapView roadmap={roadmap.data} onChange={roadmap.refetch} identityOk={!!identity} />
        ) : null}
      </Panel>

      <Panel title="Outreach draft" description="Draft only. ResearchBridge never sends email.">
        {outreach.error ? (
          <LoadError error={outreach.error} onRetry={outreach.refetch} />
        ) : outreach.loading && !outreach.data ? (
          <SkeletonText lines={6} />
        ) : outreach.data ? (
          <OutreachEditor draft={outreach.data} onSaved={outreach.refetch} />
        ) : null}
      </Panel>
    </div>
  );
}

function RoadmapView({
  roadmap,
  onChange,
  identityOk,
}: {
  roadmap: Roadmap;
  onChange: () => void;
  identityOk: boolean;
}) {
  const { identity } = useDemo();
  const weeks = Array.from({ length: roadmap.weeks }, (_, i) => i + 1);

  async function toggle(task: RoadmapTask) {
    if (!identity) return;
    try {
      await api.patchRoadmapTask(roadmap.id, task.id, identity, !task.complete);
      onChange();
    } catch (err) {
      if (err instanceof ApiError) alert(err.message);
    }
  }

  return (
    <div className="space-y-4">
      {roadmap.relationship === "not_a_placement" ? (
        <StatusCallout tone="warning">
          This roadmap targets a preferred or aspirational project. It is not a placement.
        </StatusCallout>
      ) : null}
      {weeks.map((week) => {
        const tasks = roadmap.tasks.filter((t) => t.week === week);
        if (tasks.length === 0) return null;
        return (
          <div key={week}>
            <h3 className="text-sm font-semibold text-ink">Week {week}</h3>
            <ul className="mt-1 space-y-2">
              {tasks.map((task) => (
                <li key={task.id} className="rounded-md border border-divider px-3 py-2.5">
                  <label className="flex items-start gap-2">
                    <input
                      type="checkbox"
                      checked={task.complete}
                      disabled={!identityOk}
                      onChange={() => toggle(task)}
                      className="mt-1"
                    />
                    <span>
                      <span className="text-sm font-medium text-ink">{task.concrete_task}</span>
                      <span className="mt-0.5 block text-xs text-ink-muted">
                        {task.skill_id} · {task.priority} · {task.estimated_hours}h · level{" "}
                        {task.current_proficiency}→{task.target_proficiency}
                      </span>
                      <span className="mt-1 block text-xs text-ink-secondary">
                        Deliverable: {task.deliverable}. Success check: {task.success_check}.
                      </span>
                      {task.resource_url ? (
                        <a
                          className="mt-1 inline-block text-xs font-medium text-accent"
                          href={task.resource_url}
                          target="_blank"
                          rel="noreferrer"
                        >
                          {task.resource_label}
                        </a>
                      ) : (
                        <span className="mt-1 block text-xs text-ink-muted">
                          {task.resource_label}
                        </span>
                      )}
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </div>
  );
}

function OutreachEditor({ draft, onSaved }: { draft: OutreachDraft; onSaved: () => void }) {
  const { identity } = useDemo();
  const [subject, setSubject] = useState(draft.subject);
  const [body, setBody] = useState(draft.edited_body || draft.body);
  const [status, setStatus] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setSubject(draft.subject);
    setBody(draft.edited_body || draft.body);
  }, [draft]);

  async function save() {
    if (!identity) return;
    setSaving(true);
    setStatus(null);
    try {
      await api.patchOutreach(identity.personaId, identity, {
        subject,
        edited_body: body,
      });
      setStatus("Saved locally.");
      onSaved();
    } catch (err) {
      if (err instanceof ApiError) setStatus(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(`${subject}\n\n${body}`);
      setStatus("Copied to clipboard.");
    } catch {
      setStatus("Copy is unavailable in this browser.");
    }
  }

  async function download() {
    if (!identity) return;
    try {
      const text = await api.outreachText(identity.personaId, identity);
      const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `outreach-${identity.personaId}.txt`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setStatus("Downloaded draft.");
    } catch (err) {
      if (err instanceof ApiError) setStatus(err.message);
    }
  }

  return (
    <div className="space-y-3">
      <Field label="Subject" htmlFor="subject">
        <TextInput id="subject" value={subject} onChange={(e) => setSubject(e.target.value)} />
      </Field>
      <Field label="Message" htmlFor="body">
        <TextArea
          id="body"
          className="min-h-48"
          value={body}
          onChange={(e) => setBody(e.target.value)}
        />
      </Field>
      <p className="text-xs text-ink-muted">{draft.notice}</p>
      {status ? (
        <p role="status" className="text-xs font-medium text-success">
          {status}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" loading={saving} onClick={save}>
          Save
        </Button>
        <Button variant="secondary" onClick={copy}>
          Copy
        </Button>
        <Button variant="secondary" onClick={download}>
          Download .txt
        </Button>
      </div>
    </div>
  );
}
