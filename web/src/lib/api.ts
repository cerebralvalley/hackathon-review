import type {
  Hackathon,
  HackathonListItem,
  PipelineRun,
  LeaderboardEntry,
  ProjectSummary,
  Flag,
  OutreachTeam,
  PatternBundle,
  PatternPreset,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "ngrok-skip-browser-warning": "1",
      ...init?.headers,
    },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// Hackathons
export const hackathons = {
  list: () => request<HackathonListItem[]>("/api/hackathons"),

  get: (id: string) => request<Hackathon>(`/api/hackathons/${id}`),

  create: (name: string, config: Record<string, unknown> = {}) =>
    request<Hackathon>("/api/hackathons", {
      method: "POST",
      body: JSON.stringify({ name, config }),
    }),

  update: (id: string, data: { name?: string; config?: Record<string, unknown> }) =>
    request<Hackathon>(`/api/hackathons/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  delete: (id: string) =>
    request<void>(`/api/hackathons/${id}`, { method: "DELETE" }),

  clearCache: (id: string) =>
    request<{ deleted_runs: number }>(`/api/hackathons/${id}/clear-cache`, {
      method: "POST",
    }),

  uploadCsv: async (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${API_BASE}/api/hackathons/${id}/csv`, {
      method: "POST",
      body: form,
      headers: { "ngrok-skip-browser-warning": "1" },
    });
    if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
    return res.json() as Promise<Hackathon>;
  },

  csvPreview: (id: string, offset = 0, limit = 10) =>
    request<{
      filename: string;
      headers: string[];
      rows: string[][];
      total_rows: number;
      offset: number;
      limit: number;
    }>(`/api/hackathons/${id}/csv/preview?offset=${offset}&limit=${limit}`),

  updateSubmission: (
    id: string,
    teamNumber: number,
    body: { github_url?: string; video_url?: string }
  ) =>
    request<{
      team_number: number;
      github?: { original: string; is_valid: boolean; issues: string[] };
      video?: {
        original: string;
        platform: string;
        is_valid: boolean;
        issues: string[];
      };
    }>(`/api/hackathons/${id}/submissions/${teamNumber}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
};

// Pipeline runs
export const runs = {
  list: (hackathonId: string) =>
    request<PipelineRun[]>(`/api/runs?hackathon_id=${hackathonId}`),

  get: (runId: string) => request<PipelineRun>(`/api/runs/${runId}`),

  create: (
    hackathonId: string,
    opts: { resume?: boolean; phase?: "acquisition" | "analysis" | "full" } = {}
  ) =>
    request<PipelineRun>(`/api/runs?hackathon_id=${hackathonId}`, {
      method: "POST",
      body: JSON.stringify({
        resume: opts.resume ?? true,
        phase: opts.phase ?? "full",
      }),
    }),

  resume: (runId: string) =>
    request<PipelineRun>(`/api/runs/${runId}/resume`, { method: "POST" }),

  stop: (runId: string) =>
    request<PipelineRun>(`/api/runs/${runId}/stop`, { method: "POST" }),

  retry: (runId: string, stage: string, teamNumbers: number[]) =>
    request<{ status: string }>(`/api/runs/${runId}/retry`, {
      method: "POST",
      body: JSON.stringify({ stage, team_numbers: teamNumbers }),
    }),

  streamUrl: (runId: string) => `${API_BASE}/api/runs/${runId}/stream`,

  videosZipUrl: (runId: string) => `${API_BASE}/api/runs/${runId}/videos.zip`,

  logs: (runId: string, stage: string) =>
    request<{ stage: string; exists: boolean; content: string; size: number }>(
      `/api/runs/${runId}/logs/${stage}`
    ),

  /**
   * Trigger a single-team retry and wait for the background worker to finish.
   *
   * The retry endpoint kicks off a FastAPI BackgroundTask and returns
   * immediately, so callers that want to refresh the UI on real completion
   * (rather than after a fixed delay) need to poll. retry_items removes the
   * team from stage_detail.failures whether it succeeded or failed, so we
   * watch for that as the "done" signal. 90s safety cap prevents hung
   * downloads from pinning the spinner forever.
   */
  async retryAndWait(
    runId: string,
    stage: "clone" | "video_download" | "code_review" | "video_analysis",
    teamNumber: number,
    timeoutMs = 90_000
  ): Promise<void> {
    await runs.retry(runId, stage, [teamNumber]);
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, 1500));
      try {
        const r = await runs.get(runId);
        const failures = r.stage_detail?.[stage]?.failures ?? [];
        if (!failures.some((f) => f.team_number === teamNumber)) {
          return;
        }
      } catch {
        // transient — keep polling
      }
    }
  },
};

// Parse rules
export const parseRules = (rulesText: string) =>
  request<Record<string, unknown>>("/api/parse-rules", {
    method: "POST",
    body: JSON.stringify({ rules_text: rulesText }),
  });

// Static analysis catalog (bundles + presets)
export const staticAnalysis = {
  bundles: () =>
    request<{ bundles: PatternBundle[]; presets: PatternPreset[] }>(
      "/api/static-analysis/bundles"
    ),
};

// Results
export const results = {
  leaderboard: (runId: string) =>
    request<LeaderboardEntry[]>(`/api/runs/${runId}/results/leaderboard`),

  projects: (runId: string) =>
    request<ProjectSummary[]>(`/api/runs/${runId}/results/projects`),

  project: (runId: string, teamNumber: number) =>
    request<Record<string, unknown>>(`/api/runs/${runId}/results/projects/${teamNumber}`),

  flags: (runId: string) =>
    request<Flag[]>(`/api/runs/${runId}/results/flags`),

  dismissFlag: (runId: string, teamNumber: number, flagType: string) =>
    request<string[]>(`/api/runs/${runId}/results/flags/dismiss`, {
      method: "POST",
      body: JSON.stringify({ team_number: teamNumber, flag_type: flagType }),
    }),

  undismissFlag: (runId: string, teamNumber: number, flagType: string) =>
    request<string[]>(`/api/runs/${runId}/results/flags/undismiss`, {
      method: "POST",
      body: JSON.stringify({ team_number: teamNumber, flag_type: flagType }),
    }),

  outreach: (runId: string) =>
    request<OutreachTeam[]>(`/api/runs/${runId}/results/outreach`),
};
