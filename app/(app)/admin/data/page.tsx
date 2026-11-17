"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useDemo } from "@/lib/demo-context";
import { useApiResource } from "@/lib/use-api";
import { PageHeader } from "@/components/app-shell";
import {
  Button,
  Field,
  KeyValue,
  Panel,
  SkeletonText,
  StatusCallout,
  TextArea,
  TextInput,
} from "@/components/ui";
import { LoadError } from "@/components/states";
import { newIdempotencyKey } from "@/lib/format";
import type { ProjectList } from "@/lib/types";

const RESET_PHRASE = "RESET_SYNTHETIC_DEMO";

export default function AdminDataPage() {
  const { identity } = useDemo();
  const projects = useApiResource<ProjectList>(
    (id, signal) => api.projects(id, undefined, signal),
    [],
  );

  const [payload, setPayload] = useState("");
  const [validation, setValidation] = useState<
    { valid: boolean; issues: Array<{ path: string; message: string }>; counts: Record<string, number> } | null
  >(null);
  const [importMessage, setImportMessage] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const [resetText, setResetText] = useState("");
  const [resetMessage, setResetMessage] = useState<{ tone: "success" | "error"; text: string } | null>(null);

  function parsePayload(): unknown | null {
    try {
      return JSON.parse(payload);
    } catch {
      setImportMessage({ tone: "error", text: "The payload is not valid JSON." });
      return null;
    }
  }

  async function validate() {
    if (!identity) return;
    const parsed = parsePayload();
    if (parsed === null) return;
    setBusy("validate");
    setImportMessage(null);
    try {
      const report = await api.validateImport(identity, parsed);
      setValidation(report);
    } catch (err) {
      if (err instanceof ApiError) setImportMessage({ tone: "error", text: err.message });
    } finally {
      setBusy(null);
    }
  }

  async function applyImport() {
    if (!identity) return;
    const parsed = parsePayload();
    if (parsed === null) return;
    setBusy("import");
    setImportMessage(null);
    try {
      const result = await api.applyImport(identity, newIdempotencyKey("import"), parsed);
      setImportMessage({
        tone: "success",
        text: `Imported. ${Object.entries(result.counts)
          .map(([k, v]) => `${v} ${k}`)
          .join(", ")}. Stale runs: ${result.stale_run_ids.length}.`,
      });
      projects.refetch();
    } catch (err) {
      if (err instanceof ApiError) {
        const detail = err.fieldErrors
          ? ` ${Object.entries(err.fieldErrors)
              .map(([path, msgs]) => `${path}: ${msgs.join(" ")}`)
              .join("; ")}`
          : "";
        setImportMessage({ tone: "error", text: `${err.message}${detail}` });
      }
    } finally {
      setBusy(null);
    }
  }

  async function reset() {
    if (!identity) return;
    setBusy("reset");
    setResetMessage(null);
    try {
      const result = await api.reset(identity, newIdempotencyKey("reset"), resetText);
      setResetMessage({
        tone: "success",
        text: `Demo reset to seeded data: ${Object.entries(result.counts)
          .map(([k, v]) => `${v} ${k}`)
          .join(", ")}.`,
      });
      setResetText("");
      projects.refetch();
    } catch (err) {
      if (err instanceof ApiError) setResetMessage({ tone: "error", text: err.message });
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="EUReCA admin"
        title="Data & import"
        description="Validate and import a synthetic JSON snapshot, inspect readiness, and reset the demo with explicit confirmation."
      />

      <Panel title="Current data">
        {projects.error ? (
          <LoadError error={projects.error} onRetry={projects.refetch} />
        ) : projects.loading && !projects.data ? (
          <SkeletonText lines={2} />
        ) : (
          <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            <KeyValue label="Projects" value={projects.data?.count ?? 0} />
            <KeyValue
              label="Active"
              value={projects.data?.items.filter((p) => p.active).length ?? 0}
            />
            <KeyValue
              label="Zero-capacity"
              value={projects.data?.items.filter((p) => p.capacity === 0).length ?? 0}
            />
          </dl>
        )}
      </Panel>

      <Panel
        title="Import synthetic snapshot"
        description="Paste a JSON snapshot with schema_version 1.0. Validation runs server-side with field-level errors."
      >
        <Field label="Snapshot JSON" htmlFor="payload">
          <TextArea
            id="payload"
            className="min-h-40 font-mono text-xs"
            placeholder='{"schema_version":"1.0","students":[...],"projects":[...],...}'
            value={payload}
            onChange={(e) => setPayload(e.target.value)}
          />
        </Field>
        {importMessage ? (
          <div className="mt-3">
            <StatusCallout tone={importMessage.tone}>{importMessage.text}</StatusCallout>
          </div>
        ) : null}
        {validation ? (
          <div className="mt-3">
            <StatusCallout tone={validation.valid ? "success" : "error"} title={validation.valid ? "Valid snapshot" : "Validation issues"}>
              {validation.valid ? (
                <p>
                  Counts:{" "}
                  {Object.entries(validation.counts)
                    .map(([k, v]) => `${v} ${k}`)
                    .join(", ")}
                  .
                </p>
              ) : (
                <ul className="list-disc space-y-1 pl-4">
                  {validation.issues.map((issue, index) => (
                    <li key={index}>
                      <span className="font-mono text-xs">{issue.path}</span>: {issue.message}
                    </li>
                  ))}
                </ul>
              )}
            </StatusCallout>
          </div>
        ) : null}
        <div className="mt-4 flex flex-wrap gap-3">
          <Button variant="secondary" loading={busy === "validate"} onClick={validate}>
            Validate
          </Button>
          <Button variant="primary" loading={busy === "import"} onClick={applyImport}>
            Import
          </Button>
        </div>
      </Panel>

      <Panel title="Reset demo">
        <StatusCallout tone="warning" title="Destructive action">
          This replaces all synthetic demo data with the seeded cohort. Type{" "}
          <span className="font-mono">{RESET_PHRASE}</span> to confirm.
        </StatusCallout>
        <div className="mt-3 flex flex-wrap items-end gap-3">
          <Field label="Confirmation" htmlFor="reset">
            <TextInput
              id="reset"
              className="font-mono"
              value={resetText}
              onChange={(e) => setResetText(e.target.value)}
              placeholder={RESET_PHRASE}
            />
          </Field>
          <Button
            variant="destructive"
            loading={busy === "reset"}
            disabled={resetText !== RESET_PHRASE}
            onClick={reset}
          >
            Reset to seeded data
          </Button>
        </div>
        {resetMessage ? (
          <div className="mt-3">
            <StatusCallout tone={resetMessage.tone}>{resetMessage.text}</StatusCallout>
          </div>
        ) : null}
      </Panel>
    </div>
  );
}
