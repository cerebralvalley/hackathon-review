export interface Hackathon {
  id: string;
  name: string;
  config: Record<string, unknown>;
  csv_filename: string | null;
  created_at: string;
  updated_at: string;
}

export interface HackathonListItem {
  id: string;
  name: string;
  csv_filename: string | null;
  created_at: string;
  latest_run_status: string | null;
}

export interface PipelineRun {
  id: string;
  hackathon_id: string;
  status: "pending" | "running" | "completed" | "failed" | "interrupted";
  current_stage: string | null;
  stage_progress: Record<string, string>;
  stage_detail: Record<string, StageDetail>;
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface StageFailure {
  team_number: number;
  team_name: string;
  project_name: string;
  error: string;
}

export interface StageDetail {
  done: number;
  total: number;
  message?: string;
  failures?: StageFailure[];
}

export interface LeaderboardEntry {
  rank: number;
  team_number: number;
  team_name: string;
  project_name: string;
  weighted_total: number;
  scores: Record<string, number>;
  total_loc: number;
  primary_language: string;
  commits: number;
  integration_depth: string;
  github_url: string;
  video_url: string;
}

export interface ProjectSummary {
  team_number: number;
  team_name: string;
  project_name: string;
  weighted_total: number;
  flags_count: number;
}

export interface Flag {
  team_number: number;
  team_name: string;
  project_name: string;
  flag_type: string;
  description: string;
  severity: "error" | "warning" | "info";
}

export interface PatternBundle {
  id: string;
  label: string;
  description: string;
  pattern_count: number;
}

export interface PatternPreset {
  id: string;
  label: string;
  description: string;
  bundles: string[];
}

export const PIPELINE_STAGES = [
  "parse",
  "clone",
  "video_download",
  "static_analysis",
  "code_review",
  "video_analysis",
  "scoring",
  "reporting",
] as const;

export const STAGE_LABELS: Record<string, string> = {
  parse: "Parse CSV",
  clone: "Clone Repos",
  video_download: "Download Videos",
  static_analysis: "Static Analysis",
  code_review: "Code Review",
  video_analysis: "Video Analysis",
  scoring: "Scoring",
  reporting: "Generate Reports",
};
