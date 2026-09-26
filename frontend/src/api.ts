import type {
  Activity,
  AIRecommendation,
  CaseAnalysisDraft,
  Case,
  Redaction,
  RedactionType,
} from "./types";

const base = import.meta.env.VITE_API_BASE_URL ?? "";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${base}${path}`, init);
  if (!response.ok) {
    let detail = "Request failed";
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Non-JSON error responses use the same fallback message.
    }
    throw new ApiError(response.status, detail);
  }
  return response.status === 204
    ? (undefined as T)
    : (response.json() as Promise<T>);
}

function post<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    ...(body === undefined
      ? {}
      : {
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }),
  });
}

export const api = {
  listCases: () => request<Case[]>("/cases"),
  getCase: (id: string) => request<Case>(`/cases/${id}`),
  listActivities: (id: string) =>
    request<Activity[]>(`/cases/${id}/activities`),
  listTypes: () => request<RedactionType[]>("/redaction-types"),
  closeCase: (id: number) => post<Case>(`/cases/${id}/close`),
  reopenCase: (id: number) => post<Case>(`/cases/${id}/reopen`),
  analyzeCase: (id: number) => post<CaseAnalysisDraft>(`/cases/${id}/analyze`),
  approveSummary: (
    id: number,
    summary: string,
    expected_summary: string | null,
  ) =>
    post<Case>(`/cases/${id}/summary/approve`, { summary, expected_summary }),
  createRedaction: (
    id: number,
    body: {
      redaction_type_id: number;
      redaction_text: string;
      starting_position: number;
    },
  ) => post<Redaction>(`/activities/${id}/redactions`, body),
  deleteRedaction: (id: number) =>
    request<void>(`/redactions/${id}`, { method: "DELETE" }),
  aiRecommendations: (id: number) =>
    post<{ recommendations: AIRecommendation[] }>(
      `/activities/${id}/ai-recommendations`,
    ),
  acceptRecommendation: (id: number, recommendation: AIRecommendation) =>
    post<Redaction>(
      `/activities/${id}/ai-recommendations/accept`,
      recommendation,
    ),
};
