"use client";

import { useState } from "react";
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
  SkeletonText,
  StatusCallout,
  TextArea,
  TextInput,
} from "@/components/ui";
import { LoadError } from "@/components/states";
import type { Project, ProjectList, ProjectSkill } from "@/lib/types";

type DraftSkill = ProjectSkill;

interface ProjectForm {
  title: string;
  description: string;
  department: string;
  interests: string;
  capacity: string;
  commitment_hours: string;
  term: string;
  modality: string;
  active: boolean;
  skills: DraftSkill[];
}

const EMPTY_FORM: ProjectForm = {
  title: "",
  description: "",
  department: "",
  interests: "",
  capacity: "1",
  commitment_hours: "6",
  term: "Synthetic Fall Term",
  modality: "In person",
  active: true,
  skills: [],
};

function fromProject(project: Project): ProjectForm {
  return {
    title: project.title,
    description: project.description,
    department: project.department,
    interests: project.interests.join(", "),
    capacity: String(project.capacity),
    commitment_hours: project.commitment_hours,
    term: project.term,
    modality: project.modality,
    active: project.active,
    skills: project.skills.map((s) => ({ ...s })),
  };
}

export default function FacultyProjectsPage() {
  const { identity } = useDemo();
  const projects = useApiResource<ProjectList>(
    (id, signal) => api.projects(id, undefined, signal),
    [],
  );
  const [editingId, setEditingId] = useState<string | "new" | null>(null);
  const [form, setForm] = useState<ProjectForm>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const mine =
    projects.data?.items.filter((p) => p.faculty_id === identity?.personaId) ?? [];

  function startNew() {
    setEditingId("new");
    setForm(EMPTY_FORM);
    setMessage(null);
    setFieldErrors({});
  }

  function startEdit(project: Project) {
    setEditingId(project.id);
    setForm(fromProject(project));
    setMessage(null);
    setFieldErrors({});
  }

  function buildBody() {
    return {
      title: form.title,
      description: form.description,
      department: form.department,
      interests: form.interests
        .split(",")
        .map((i) => i.trim())
        .filter(Boolean),
      capacity: Number(form.capacity),
      commitment_hours: form.commitment_hours,
      term: form.term,
      modality: form.modality,
      active: form.active,
      skills: form.skills,
    };
  }

  async function save() {
    if (!identity) return;
    setSaving(true);
    setMessage(null);
    setFieldErrors({});
    try {
      if (editingId === "new") {
        await api.createProject(identity, buildBody());
        setMessage({ tone: "success", text: "Project created." });
      } else if (editingId) {
        await api.patchProject(editingId, identity, buildBody());
        setMessage({ tone: "success", text: "Project updated." });
      }
      setEditingId(null);
      projects.refetch();
    } catch (err) {
      if (err instanceof ApiError) {
        setFieldErrors(err.fieldErrors ?? {});
        setMessage({ tone: "error", text: err.message });
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Faculty workspace"
        title="Projects"
        description="Create and edit hypothetical openings. Mandatory and trainable skills are validated and treated differently in scoring."
        action={<Button variant="primary" onClick={startNew}>New project</Button>}
      />

      {message ? <StatusCallout tone={message.tone}>{message.text}</StatusCallout> : null}

      {editingId ? (
        <Panel
          title={editingId === "new" ? "Create project" : "Edit project"}
          action={
            <Button variant="ghost" onClick={() => setEditingId(null)}>
              Cancel
            </Button>
          }
        >
          <ProjectEditor
            form={form}
            setForm={setForm}
            fieldErrors={fieldErrors}
            saving={saving}
            onSave={save}
          />
        </Panel>
      ) : null}

      <Panel title="Your projects">
        {projects.error ? (
          <LoadError error={projects.error} onRetry={projects.refetch} />
        ) : projects.loading && !projects.data ? (
          <SkeletonText lines={4} />
        ) : mine.length === 0 ? (
          <EmptyState title="No projects yet" action={<Button onClick={startNew}>Create a project</Button>}>
            Create a hypothetical opening to include it in the next matching run.
          </EmptyState>
        ) : (
          <ul className="divide-y divide-divider">
            {mine.map((project) => (
              <li key={project.id} className="flex items-center justify-between gap-3 py-3">
                <div>
                  <p className="text-sm font-semibold text-ink">{project.title}</p>
                  <p className="text-xs text-ink-muted">
                    {project.department} · capacity {project.capacity} ·{" "}
                    {project.skills.filter((s) => s.kind === "mandatory").length} mandatory /{" "}
                    {project.skills.filter((s) => s.kind === "trainable").length} trainable
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge tone={project.active ? "success" : "neutral"}>
                    {project.active ? "Active" : "Inactive"}
                  </Badge>
                  <Button variant="secondary" onClick={() => startEdit(project)}>
                    Edit
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}

function ProjectEditor({
  form,
  setForm,
  fieldErrors,
  saving,
  onSave,
}: {
  form: ProjectForm;
  setForm: React.Dispatch<React.SetStateAction<ProjectForm>>;
  fieldErrors: Record<string, string[]>;
  saving: boolean;
  onSave: () => void;
}) {
  const update = <K extends keyof ProjectForm>(key: K, value: ProjectForm[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  function addSkill() {
    update("skills", [
      ...form.skills,
      { skill_id: "", required_proficiency: 2, kind: "mandatory" },
    ]);
  }

  function updateSkill(index: number, patch: Partial<DraftSkill>) {
    const next = [...form.skills];
    next[index] = { ...next[index]!, ...patch };
    update("skills", next);
  }

  return (
    <div className="space-y-5">
      <div className="grid gap-5 sm:grid-cols-2">
        <Field label="Title" htmlFor="p-title" required error={fieldErrors.title?.join(" ")}>
          <TextInput id="p-title" value={form.title} onChange={(e) => update("title", e.target.value)} />
        </Field>
        <Field label="Department" htmlFor="p-dept" required error={fieldErrors.department?.join(" ")}>
          <TextInput id="p-dept" value={form.department} onChange={(e) => update("department", e.target.value)} />
        </Field>
      </div>

      <Field label="Description" htmlFor="p-desc" required error={fieldErrors.description?.join(" ")}>
        <TextArea id="p-desc" value={form.description} onChange={(e) => update("description", e.target.value)} />
      </Field>

      <Field label="Interests" htmlFor="p-int" hint="Comma-separated.">
        <TextInput id="p-int" value={form.interests} onChange={(e) => update("interests", e.target.value)} />
      </Field>

      <div className="grid gap-5 sm:grid-cols-3">
        <Field label="Capacity" htmlFor="p-cap" required error={fieldErrors.capacity?.join(" ")}>
          <TextInput
            id="p-cap"
            type="number"
            min={0}
            max={100}
            value={form.capacity}
            onChange={(e) => update("capacity", e.target.value)}
          />
        </Field>
        <Field label="Commitment hours/week" htmlFor="p-hrs" required error={fieldErrors.commitment_hours?.join(" ")}>
          <TextInput
            id="p-hrs"
            type="number"
            min={1}
            max={40}
            value={form.commitment_hours}
            onChange={(e) => update("commitment_hours", e.target.value)}
          />
        </Field>
        <Field label="Modality" htmlFor="p-mod">
          <Select id="p-mod" value={form.modality} onChange={(e) => update("modality", e.target.value)}>
            <option>In person</option>
            <option>Hybrid</option>
            <option>Remote demo</option>
          </Select>
        </Field>
      </div>

      <div className="grid gap-5 sm:grid-cols-2">
        <Field label="Term" htmlFor="p-term">
          <TextInput id="p-term" value={form.term} onChange={(e) => update("term", e.target.value)} />
        </Field>
        <Field label="Active" htmlFor="p-active">
          <Select
            id="p-active"
            value={form.active ? "yes" : "no"}
            onChange={(e) => update("active", e.target.value === "yes")}
          >
            <option value="yes">Active</option>
            <option value="no">Inactive</option>
          </Select>
        </Field>
      </div>

      <div>
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-ink">Skills</h3>
          <Button variant="ghost" onClick={addSkill}>
            Add skill
          </Button>
        </div>
        {form.skills.length === 0 ? (
          <p className="mt-1 text-sm text-ink-muted">
            No skills added. Mandatory skills are hard requirements; trainable skills are not.
          </p>
        ) : (
          <ul className="mt-2 space-y-2">
            {form.skills.map((skill, index) => (
              <li key={index} className="grid grid-cols-[1fr_7rem_9rem_auto] items-center gap-2">
                <TextInput
                  aria-label="Skill id"
                  placeholder="skill id"
                  value={skill.skill_id}
                  onChange={(e) => updateSkill(index, { skill_id: e.target.value.trim() })}
                />
                <Select
                  aria-label="Required proficiency"
                  value={String(skill.required_proficiency)}
                  onChange={(e) => updateSkill(index, { required_proficiency: Number(e.target.value) })}
                >
                  {[1, 2, 3, 4].map((level) => (
                    <option key={level} value={level}>
                      Level {level}
                    </option>
                  ))}
                </Select>
                <Select
                  aria-label="Skill kind"
                  value={skill.kind}
                  onChange={(e) => updateSkill(index, { kind: e.target.value as ProjectSkill["kind"] })}
                >
                  <option value="mandatory">Mandatory</option>
                  <option value="trainable">Trainable</option>
                </Select>
                <Button
                  variant="ghost"
                  onClick={() => update("skills", form.skills.filter((_, i) => i !== index))}
                >
                  Remove
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <Button variant="primary" loading={saving} onClick={onSave}>
        Save project
      </Button>
    </div>
  );
}
