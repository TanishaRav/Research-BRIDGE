import type {
  DecisionAudit,
  DemoRole,
  FacultyAssignment,
  MatchConfig,
  MatchRun,
  NormalizedConfig,
  OutreachDraft,
  PersonaList,
  Project,
  ProjectList,
  Recommendation,
  Roadmap,
  RunEvidenceResponse,
  RunReview,
  StudentOutcome,
  StudentProfileResponse,
} from "./types";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export interface DemoIdentity {
  role: DemoRole;
  personaId: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly fieldErrors: Record<string, string[]> | undefined;
  readonly requestId: string | undefined;

  constructor(
    status: number,
    code: string,
    message: string,
    fieldErrors?: Record<string, string[]>,
    requestId?: string,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.fieldErrors = fieldErrors;
    this.requestId = requestId;
  }
}

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH";
  identity?: DemoIdentity | null | undefined;
  body?: unknown;
  idempotencyKey?: string | undefined;
  signal?: AbortSignal | undefined;
  query?: Record<string, string | number | undefined | null> | undefined;
}

function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const url = new URL(`${API_URL}/api/v1${path}`);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null && value !== "") {
        url.searchParams.set(key, String(value));
      }
    }
  }
  return url.toString();
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (options.identity) {
    headers["X-Demo-Role"] = options.identity.role;
    headers["X-Demo-Persona-Id"] = options.identity.personaId;
  }
  if (options.idempotencyKey) {
    headers["Idempotency-Key"] = options.idempotencyKey;
  }
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  const init: RequestInit = {
    method: options.method ?? "GET",
    headers,
    cache: "no-store",
  };
  if (options.body !== undefined) {
    init.body = JSON.stringify(options.body);
  }
  if (options.signal) {
    init.signal = options.signal;
  }

  let response: Response;
  try {
    response = await fetch(buildUrl(path, options.query), init);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }
    throw new ApiError(
      0,
      "network_unreachable",
      "Could not reach the ResearchBridge API. Confirm the local service is running.",
    );
  }

  const isJson = response.headers.get("content-type")?.includes("application/json");
  if (!response.ok) {
    if (isJson) {
      const payload = (await response.json()) as {
        code?: string;
        message?: string;
        field_errors?: Record<string, string[]>;
        request_id?: string;
      };
      throw new ApiError(
        response.status,
        payload.code ?? "error",
        payload.message ?? "The request could not be completed.",
        payload.field_errors,
        payload.request_id,
      );
    }
    throw new ApiError(response.status, "error", `Request failed with status ${response.status}.`);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  if (isJson) {
    return (await response.json()) as T;
  }
  return (await response.text()) as unknown as T;
}

async function requestText(path: string, identity: DemoIdentity): Promise<string> {
  return request<string>(path, { identity });
}

async function requestDownload(
  path: string,
  identity: DemoIdentity,
): Promise<{ blob: Blob; filename: string }> {
  let response: Response;
  try {
    response = await fetch(buildUrl(path), {
      headers: {
        Accept: "*/*",
        "X-Demo-Role": identity.role,
        "X-Demo-Persona-Id": identity.personaId,
      },
      cache: "no-store",
    });
  } catch {
    throw new ApiError(
      0,
      "network_unreachable",
      "Could not reach the ResearchBridge API. Confirm the local service is running.",
    );
  }
  if (!response.ok) {
    const isJson = response.headers.get("content-type")?.includes("application/json");
    const payload = isJson
      ? ((await response.json()) as { code?: string; message?: string; request_id?: string })
      : null;
    throw new ApiError(
      response.status,
      payload?.code ?? "download_failed",
      payload?.message ?? "The export could not be downloaded.",
      undefined,
      payload?.request_id,
    );
  }
  const disposition = response.headers.get("content-disposition") ?? "";
  const match = /filename="?([^";]+)"?/i.exec(disposition);
  return {
    blob: await response.blob(),
    filename: match?.[1] ?? "researchbridge-export",
  };
}

export const api = {
  health: () => fetch(`${API_URL}/health/ready`, { cache: "no-store" }),

  personas: (signal?: AbortSignal) => request<PersonaList>("/demo/personas", { signal }),

  studentProfile: (id: string, identity: DemoIdentity, signal?: AbortSignal) =>
    request<StudentProfileResponse>(`/students/${id}`, { identity, signal }),

  patchStudent: (id: string, identity: DemoIdentity, body: unknown) =>
    request<StudentProfileResponse>(`/students/${id}`, { method: "PATCH", identity, body }),

  submitStudent: (id: string, identity: DemoIdentity, idempotencyKey: string) =>
    request<StudentProfileResponse>(`/students/${id}/submit`, {
      method: "POST",
      identity,
      idempotencyKey,
    }),

  recommendations: (id: string, identity: DemoIdentity, signal?: AbortSignal) =>
    request<Recommendation[]>(`/students/${id}/recommendations`, { identity, signal }),

  outcome: (id: string, identity: DemoIdentity, signal?: AbortSignal) =>
    request<StudentOutcome>(`/students/${id}/outcome`, { identity, signal }),

  projects: (
    identity: DemoIdentity,
    query?: RequestOptions["query"],
    signal?: AbortSignal,
  ) => request<ProjectList>("/projects", { identity, query, signal }),

  project: (id: string, identity: DemoIdentity, signal?: AbortSignal) =>
    request<Project>(`/projects/${id}`, { identity, signal }),

  createProject: (identity: DemoIdentity, body: unknown) =>
    request<Project>("/projects", { method: "POST", identity, body }),

  patchProject: (id: string, identity: DemoIdentity, body: unknown) =>
    request<Project>(`/projects/${id}`, { method: "PATCH", identity, body }),

  facultyAssignments: (id: string, identity: DemoIdentity, signal?: AbortSignal) =>
    request<FacultyAssignment[]>(`/faculty/${id}/assignments`, { identity, signal }),

  config: (identity: DemoIdentity, signal?: AbortSignal) =>
    request<NormalizedConfig>("/config", { identity, signal }),

  previewConfig: (identity: DemoIdentity, body: MatchConfig) =>
    request<NormalizedConfig>("/config/preview", { method: "POST", identity, body }),

  patchConfig: (identity: DemoIdentity, body: unknown) =>
    request<NormalizedConfig>("/config", { method: "PATCH", identity, body }),

  createRun: (identity: DemoIdentity, idempotencyKey: string, body: unknown = {}) =>
    request<MatchRun>("/runs", { method: "POST", identity, idempotencyKey, body }),

  runs: (identity: DemoIdentity, signal?: AbortSignal) =>
    request<MatchRun[]>("/runs", { identity, signal }),

  runReview: (id: string, identity: DemoIdentity, signal?: AbortSignal) =>
    request<RunReview>(`/runs/${id}`, { identity, signal }),

  approveRun: (id: string, identity: DemoIdentity, idempotencyKey: string) =>
    request<MatchRun>(`/runs/${id}/approve`, {
      method: "POST",
      identity,
      idempotencyKey,
      body: { confirmation: "APPROVE_SYNTHETIC_RUN" },
    }),

  compareRuns: (id: string, otherId: string, identity: DemoIdentity, signal?: AbortSignal) =>
    request<Record<string, unknown>>(`/runs/${id}/comparison/${otherId}`, { identity, signal }),

  shuffleTest: (id: string, identity: DemoIdentity, idempotencyKey: string) =>
    request<Record<string, unknown>>(`/runs/${id}/shuffle-test`, {
      method: "POST",
      identity,
      idempotencyKey,
    }),

  runEvidence: (id: string, identity: DemoIdentity, signal?: AbortSignal) =>
    request<RunEvidenceResponse>(`/runs/${id}/evidence`, { identity, signal }),

  audit: (identity: DemoIdentity, signal?: AbortSignal) =>
    request<DecisionAudit[]>("/audit", { identity, signal }),

  roadmap: (id: string, identity: DemoIdentity, signal?: AbortSignal) =>
    request<Roadmap>(`/students/${id}/roadmap`, { identity, signal }),

  patchRoadmapTask: (
    roadmapId: string,
    taskId: string,
    identity: DemoIdentity,
    complete: boolean,
  ) =>
    request<Roadmap>(`/roadmaps/${roadmapId}/tasks/${taskId}`, {
      method: "PATCH",
      identity,
      body: { complete },
    }),

  outreach: (id: string, identity: DemoIdentity, signal?: AbortSignal) =>
    request<OutreachDraft>(`/students/${id}/outreach`, { identity, signal }),

  patchOutreach: (id: string, identity: DemoIdentity, body: unknown) =>
    request<OutreachDraft>(`/students/${id}/outreach`, { method: "PATCH", identity, body }),

  outreachText: (id: string, identity: DemoIdentity) =>
    requestText(`/students/${id}/outreach.txt`, identity),

  validateImport: (identity: DemoIdentity, body: unknown) =>
    request<{ valid: boolean; issues: Array<{ path: string; code: string; message: string }>; counts: Record<string, number> }>(
      "/imports/validate",
      { method: "POST", identity, body },
    ),

  applyImport: (identity: DemoIdentity, idempotencyKey: string, body: unknown) =>
    request<{ imported: boolean; counts: Record<string, number>; stale_run_ids: string[] }>(
      "/imports",
      { method: "POST", identity, idempotencyKey, body },
    ),

  reset: (identity: DemoIdentity, idempotencyKey: string, confirmation: string) =>
    request<{ reset: boolean; confirmation: string; counts: Record<string, number> }>(
      "/demo/reset",
      { method: "POST", identity, idempotencyKey, body: { confirmation } },
    ),

  downloadRunExport: (id: string, format: "json" | "csv", identity: DemoIdentity) =>
    requestDownload(`/runs/${id}/export.${format}`, identity),
};
