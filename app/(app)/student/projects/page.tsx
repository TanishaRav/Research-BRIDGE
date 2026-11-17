"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
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
  Panel,
  Select,
  Skeleton,
  SkeletonText,
  StatusCallout,
  TextInput,
} from "@/components/ui";
import { LoadError } from "@/components/states";
import { dayLabel } from "@/lib/format";
import type { Project, ProjectList, StudentProfileResponse } from "@/lib/types";

export default function StudentProjectsPage() {
  return (
    <Suspense fallback={<SkeletonText lines={6} />}>
      <ProjectCatalog />
    </Suspense>
  );
}

function ProjectCatalog() {
  const { identity } = useDemo();
  const router = useRouter();
  const params = useSearchParams();

  const q = params.get("q") ?? "";
  const department = params.get("department") ?? "";
  const skill = params.get("skill") ?? "";
  const maxHours = params.get("max_hours") ?? "";
  const selectedId = params.get("project") ?? "";

  const [queryDraft, setQueryDraft] = useState(q);
  useEffect(() => setQueryDraft(q), [q]);

  const setParam = useCallback(
    (key: string, value: string) => {
      const next = new URLSearchParams(params.toString());
      if (value) next.set(key, value);
      else next.delete(key);
      router.replace(`/student/projects?${next.toString()}`);
    },
    [params, router],
  );

  const profile = useApiResource<StudentProfileResponse>(
    (id, signal) => api.studentProfile(id.personaId, id, signal),
    [],
  );

  const list = useApiResource<ProjectList>(
    (id, signal) =>
      api.projects(
        id,
        {
          q: q || undefined,
          department: department || undefined,
          skill: skill || undefined,
          max_hours: maxHours || undefined,
        },
        signal,
      ),
    [q, department, skill, maxHours],
  );

  const departments = useMemo(() => {
    const set = new Set<string>();
    list.data?.items.forEach((p) => set.add(p.department));
    return Array.from(set).sort();
  }, [list.data]);

  const items = list.data?.items ?? [];
  const selected = items.find((p) => p.id === selectedId) ?? items[0] ?? null;

  const activeFilters = [
    q ? { key: "q", label: `Search: ${q}` } : null,
    department ? { key: "department", label: department } : null,
    skill ? { key: "skill", label: `Skill: ${skill}` } : null,
    maxHours ? { key: "max_hours", label: `≤ ${maxHours}h` } : null,
  ].filter((entry): entry is { key: string; label: string } => entry !== null);

  const rankedIds = new Set(profile.data?.student.preferences.map((p) => p.project_id));

  async function toggleRank(projectId: string) {
    if (!identity || !profile.data) return;
    const prefs = profile.data.student.preferences.map((p) => ({ ...p }));
    const exists = prefs.some((p) => p.project_id === projectId);
    let next = exists
      ? prefs.filter((p) => p.project_id !== projectId)
      : [...prefs, { project_id: projectId, rank: prefs.length + 1 }];
    next = next
      .sort((a, b) => a.rank - b.rank)
      .map((p, index) => ({ project_id: p.project_id, rank: index + 1 }));
    try {
      await api.patchStudent(identity.personaId, identity, { preferences: next });
      profile.refetch();
    } catch (err) {
      if (err instanceof ApiError) {
        // Surface the message inline via the profile error pathway on next load.
        alert(err.message);
      }
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Student workspace"
        title="Project catalog"
        description="Search and filter hypothetical openings, inspect provenance, and rank the projects you would accept."
      />

      <Panel>
        <form
          className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4"
          onSubmit={(e) => {
            e.preventDefault();
            setParam("q", queryDraft.trim());
          }}
        >
          <Field label="Search" htmlFor="q">
            <TextInput
              id="q"
              placeholder="Title, skill, interest…"
              value={queryDraft}
              onChange={(e) => setQueryDraft(e.target.value)}
            />
          </Field>
          <Field label="Department" htmlFor="department">
            <Select
              id="department"
              value={department}
              onChange={(e) => setParam("department", e.target.value)}
            >
              <option value="">All departments</option>
              {departments.map((dep) => (
                <option key={dep} value={dep}>
                  {dep}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Skill id" htmlFor="skill">
            <TextInput
              id="skill"
              placeholder="e.g. python"
              value={skill}
              onChange={(e) => setParam("skill", e.target.value.trim())}
            />
          </Field>
          <Field label="Max hours / week" htmlFor="maxhours">
            <TextInput
              id="maxhours"
              type="number"
              min={0}
              max={40}
              value={maxHours}
              onChange={(e) => setParam("max_hours", e.target.value)}
            />
          </Field>
        </form>

        {activeFilters.length > 0 ? (
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <span className="text-xs font-medium text-ink-muted">Active filters:</span>
            {activeFilters.map((filter) => (
              <button
                key={filter.key}
                type="button"
                onClick={() => setParam(filter.key, "")}
                className="inline-flex items-center gap-1 rounded-sm border border-divider bg-subtle px-2 py-0.5 text-xs text-ink-secondary hover:text-ink"
              >
                {filter.label}
                <span aria-hidden="true">×</span>
                <span className="sr-only">Remove filter</span>
              </button>
            ))}
            <button
              type="button"
              onClick={() => router.replace("/student/projects")}
              className="text-xs font-medium text-accent"
            >
              Reset all
            </button>
          </div>
        ) : null}
      </Panel>

      {list.error ? (
        <LoadError error={list.error} onRetry={list.refetch} />
      ) : (
        <div className="grid gap-6 lg:grid-cols-[1fr_1.3fr]">
          <Panel
            title="Openings"
            description={list.data ? `${list.data.count} match${list.data.count === 1 ? "" : "es"}` : undefined}
          >
            {list.loading && !list.data ? (
              <div className="space-y-3">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className="h-14" />
                ))}
              </div>
            ) : items.length === 0 ? (
              <EmptyState title="No projects match the current filters">
                Adjust or reset the filters to see hypothetical openings.
              </EmptyState>
            ) : (
              <ul className="divide-y divide-divider">
                {items.map((project) => (
                  <li key={project.id}>
                    <button
                      type="button"
                      onClick={() => setParam("project", project.id)}
                      aria-current={selected?.id === project.id ? "true" : undefined}
                      className={
                        selected?.id === project.id
                          ? "w-full rounded-md bg-accent-soft px-3 py-3 text-left"
                          : "w-full rounded-md px-3 py-3 text-left hover:bg-subtle"
                      }
                    >
                      <span className="flex items-center justify-between gap-2">
                        <span className="text-sm font-semibold text-ink">{project.title}</span>
                        {rankedIds.has(project.id) ? <Badge tone="accent">Ranked</Badge> : null}
                      </span>
                      <span className="mt-0.5 block text-xs text-ink-secondary">
                        {project.department} · {project.capacity} seat
                        {project.capacity === 1 ? "" : "s"} · {project.commitment_hours}h/wk
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Panel>

          {selected ? (
            <ProjectDetail
              project={selected}
              ranked={rankedIds.has(selected.id)}
              onToggleRank={() => toggleRank(selected.id)}
            />
          ) : null}
        </div>
      )}
    </div>
  );
}

function ProjectDetail({
  project,
  ranked,
  onToggleRank,
}: {
  project: Project;
  ranked: boolean;
  onToggleRank: () => void;
}) {
  const mandatory = project.skills.filter((s) => s.kind === "mandatory");
  const trainable = project.skills.filter((s) => s.kind === "trainable");

  return (
    <Panel
      title={project.title}
      action={
        <Button variant={ranked ? "secondary" : "primary"} onClick={onToggleRank}>
          {ranked ? "Remove from ranked" : "Rank this project"}
        </Button>
      }
    >
      <div className="space-y-4">
        <Badge tone="warning">{project.provenance_label}</Badge>
        <p className="text-sm leading-relaxed text-ink-secondary">{project.description}</p>

        <dl className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <dt className="text-xs uppercase tracking-wide text-ink-muted">Department</dt>
            <dd>{project.department}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-ink-muted">Capacity</dt>
            <dd>{project.capacity}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-ink-muted">Commitment</dt>
            <dd>{project.commitment_hours} hours / week</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-ink-muted">Modality</dt>
            <dd>{project.modality}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-ink-muted">Term</dt>
            <dd>{project.term}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-ink-muted">Active</dt>
            <dd>{project.active ? "Yes" : "No"}</dd>
          </div>
        </dl>

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <h3 className="text-sm font-semibold text-ink">Mandatory skills</h3>
            {mandatory.length === 0 ? (
              <p className="text-sm text-ink-muted">None listed.</p>
            ) : (
              <ul className="mt-1 space-y-1 text-sm text-ink-secondary">
                {mandatory.map((s) => (
                  <li key={s.skill_id}>
                    {s.skill_id} · min level {s.required_proficiency}
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <h3 className="text-sm font-semibold text-ink">Trainable skills</h3>
            {trainable.length === 0 ? (
              <p className="text-sm text-ink-muted">None listed.</p>
            ) : (
              <ul className="mt-1 space-y-1 text-sm text-ink-secondary">
                {trainable.map((s) => (
                  <li key={s.skill_id}>
                    {s.skill_id} · target {s.required_proficiency}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        {project.required_windows.length > 0 ? (
          <div>
            <h3 className="text-sm font-semibold text-ink">Fixed required windows</h3>
            <ul className="mt-1 space-y-1 text-sm text-ink-secondary">
              {project.required_windows.map((w, i) => (
                <li key={i}>
                  {dayLabel(w.day)} {Math.floor(w.start_minute / 60)}:00–
                  {Math.floor(w.end_minute / 60)}:00
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {project.source_url ? (
          <a
            className="inline-block text-sm font-medium text-accent"
            href={project.source_url}
            target="_blank"
            rel="noreferrer"
          >
            Source link
          </a>
        ) : (
          <StatusCallout tone="neutral">
            {project.source_note}
          </StatusCallout>
        )}
      </div>
    </Panel>
  );
}
