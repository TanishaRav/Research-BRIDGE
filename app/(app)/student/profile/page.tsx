"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useDemo } from "@/lib/demo-context";
import { useApiResource } from "@/lib/use-api";
import { PageHeader } from "@/components/app-shell";
import {
  Badge,
  Button,
  Field,
  Panel,
  Select,
  SkeletonText,
  StatusCallout,
  TextArea,
  TextInput,
} from "@/components/ui";
import { LoadError } from "@/components/states";
import { newIdempotencyKey } from "@/lib/format";
import type { Student, StudentProfileResponse, StudentSkill } from "@/lib/types";

interface FormState {
  interests: string;
  learning_goals: string;
  hours_per_week: string;
  first_time_researcher: boolean;
  accepts_suggestions: boolean;
  skills: StudentSkill[];
}

function toForm(student: Student): FormState {
  return {
    interests: student.interests.join(", "),
    learning_goals: student.learning_goals.join("\n"),
    hours_per_week: student.hours_per_week ?? "",
    first_time_researcher: student.first_time_researcher,
    accepts_suggestions: student.accepts_suggestions,
    skills: student.skills.map((item) => ({ ...item })),
  };
}

export default function StudentProfilePage() {
  const { identity } = useDemo();
  const { data, loading, error, refetch } = useApiResource<StudentProfileResponse>(
    (id, signal) => api.studentProfile(id.personaId, id, signal),
    [],
  );
  const [form, setForm] = useState<FormState | null>(null);
  const [saving, setSaving] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  useEffect(() => {
    if (data) setForm(toForm(data.student));
  }, [data]);

  if (loading && !data) {
    return (
      <Panel>
        <SkeletonText lines={6} />
      </Panel>
    );
  }
  if (error) return <LoadError error={error} onRetry={refetch} />;
  if (!data || !form || !identity) return null;

  const update = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((prev) => (prev ? { ...prev, [key]: value } : prev));

  const buildPatch = () => ({
    interests: form.interests
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean),
    learning_goals: form.learning_goals
      .split("\n")
      .map((item) => item.trim())
      .filter(Boolean),
    hours_per_week: form.hours_per_week === "" ? null : form.hours_per_week,
    first_time_researcher: form.first_time_researcher,
    accepts_suggestions: form.accepts_suggestions,
    skills: form.skills,
  });

  async function save() {
    if (!identity) return;
    setSaving(true);
    setMessage(null);
    setFieldErrors({});
    try {
      await api.patchStudent(identity.personaId, identity, buildPatch());
      setMessage({ tone: "success", text: "Profile saved. Any proposed run using your data is now stale." });
      refetch();
    } catch (err) {
      if (err instanceof ApiError) {
        setFieldErrors(err.fieldErrors ?? {});
        setMessage({ tone: "error", text: err.message });
      }
    } finally {
      setSaving(false);
    }
  }

  async function submitToBatch() {
    if (!identity) return;
    setSubmitting(true);
    setMessage(null);
    try {
      await api.patchStudent(identity.personaId, identity, buildPatch());
      await api.submitStudent(identity.personaId, identity, newIdempotencyKey("submit"));
      setMessage({
        tone: "success",
        text: "Submitted to the next batch. Submission does not allocate immediately.",
      });
      refetch();
    } catch (err) {
      if (err instanceof ApiError) {
        setFieldErrors(err.fieldErrors ?? {});
        setMessage({ tone: "error", text: err.message });
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Student workspace"
        title="Edit profile"
        description="Interests, skills, availability, and goals feed the compatibility score. Names never do."
        action={<Badge tone={data.student.submitted ? "info" : "warning"}>
          {data.student.submitted ? "Submitted" : "Not submitted"}
        </Badge>}
      />

      {message ? (
        <StatusCallout tone={message.tone}>{message.text}</StatusCallout>
      ) : null}

      <Panel title="Interests & goals">
        <div className="grid gap-5">
          <Field
            label="Research interests"
            htmlFor="interests"
            required
            hint="Comma-separated. These drive interest alignment (35% default weight)."
            error={fieldErrors.interests?.join(" ")}
          >
            <TextInput
              id="interests"
              value={form.interests}
              onChange={(e) => update("interests", e.target.value)}
            />
          </Field>
          <Field
            label="Learning goals"
            htmlFor="goals"
            hint="One per line. Matched against trainable skills and mentoring (10% default weight)."
          >
            <TextArea
              id="goals"
              value={form.learning_goals}
              onChange={(e) => update("learning_goals", e.target.value)}
            />
          </Field>
        </div>
      </Panel>

      <Panel title="Availability & preferences">
        <div className="grid gap-5 sm:grid-cols-2">
          <Field
            label="Hours per week"
            htmlFor="hours"
            required
            hint="0–40. Must meet a project's commitment to be eligible."
            error={fieldErrors.hours_per_week?.join(" ")}
          >
            <TextInput
              id="hours"
              type="number"
              min={0}
              max={40}
              value={form.hours_per_week}
              onChange={(e) => update("hours_per_week", e.target.value)}
            />
          </Field>
          <Field label="First-time researcher" htmlFor="firsttime">
            <Select
              id="firsttime"
              value={form.first_time_researcher ? "yes" : "no"}
              onChange={(e) => update("first_time_researcher", e.target.value === "yes")}
            >
              <option value="yes">Yes</option>
              <option value="no">No</option>
            </Select>
          </Field>
          <Field
            label="Accept suggestions outside ranked projects"
            htmlFor="suggest"
            hint="Consent to be considered for feasible projects you did not rank."
          >
            <Select
              id="suggest"
              value={form.accepts_suggestions ? "yes" : "no"}
              onChange={(e) => update("accepts_suggestions", e.target.value === "yes")}
            >
              <option value="no">No, only my ranked projects</option>
              <option value="yes">Yes, consider suggestions</option>
            </Select>
          </Field>
        </div>
        <p className="mt-4 text-sm text-ink-secondary">
          Rank acceptable projects from the{" "}
          <a className="font-medium text-accent" href="/student/projects">
            project catalog
          </a>
          . You have ranked {data.student.preferences.length} project
          {data.student.preferences.length === 1 ? "" : "s"}.
        </p>
      </Panel>

      <Panel title="Skill proficiency" description="0 = none, 4 = advanced. Missing proficiency counts as a gap, not an exclusion for trainable skills.">
        {form.skills.length === 0 ? (
          <p className="text-sm text-ink-secondary">
            No skills recorded yet. Add skills that match the projects you are interested in.
          </p>
        ) : (
          <ul className="divide-y divide-divider">
            {form.skills.map((skill, index) => (
              <li key={skill.skill_id} className="flex items-center justify-between gap-4 py-2.5">
                <span className="text-sm text-ink">{skill.skill_id}</span>
                <Select
                  aria-label={`Proficiency for ${skill.skill_id}`}
                  className="w-28"
                  value={String(skill.proficiency)}
                  onChange={(e) => {
                    const next = [...form.skills];
                    next[index] = { ...skill, proficiency: Number(e.target.value) };
                    update("skills", next);
                  }}
                >
                  {[0, 1, 2, 3, 4].map((level) => (
                    <option key={level} value={level}>
                      {level}
                    </option>
                  ))}
                </Select>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <div className="flex flex-wrap gap-3">
        <Button variant="secondary" loading={saving} onClick={save}>
          Save changes
        </Button>
        <Button variant="primary" loading={submitting} onClick={submitToBatch}>
          Save & submit to batch
        </Button>
      </div>
    </div>
  );
}
