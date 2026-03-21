"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { results as api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

interface ProjectData {
  submission: Record<string, unknown>;
  repo_metadata: Record<string, unknown> | null;
  static_analysis: Record<string, unknown> | null;
  code_review: Record<string, unknown> | null;
  video_analysis: Record<string, unknown> | null;
  score: Record<string, unknown> | null;
}

function get(obj: Record<string, unknown> | null | undefined, ...keys: string[]): unknown {
  let cur: unknown = obj;
  for (const k of keys) {
    if (cur == null || typeof cur !== "object") return undefined;
    cur = (cur as Record<string, unknown>)[k];
  }
  return cur;
}

function ScoreBar({ value }: { value: number }) {
  const pct = Math.min(100, Math.max(0, value * 10));
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
        <div
          className="h-full rounded-full bg-primary transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-sm tabular-nums font-medium w-8 text-right">
        {value.toFixed(1)}
      </span>
    </div>
  );
}

export default function ProjectDetailPage() {
  const { id, runId, teamNumber } = useParams<{
    id: string;
    runId: string;
    teamNumber: string;
  }>();
  const [data, setData] = useState<ProjectData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .project(runId, parseInt(teamNumber))
      .then((d) => setData(d as unknown as ProjectData))
      .finally(() => setLoading(false));
  }, [runId, teamNumber]);

  if (loading) return <p className="text-muted-foreground">Loading...</p>;
  if (!data?.submission) return <p className="text-muted-foreground">Project not found.</p>;

  const sub = data.submission;
  const meta = data.repo_metadata;
  const staticA = data.static_analysis;
  const review = data.code_review;
  const video = data.video_analysis;
  const score = data.score;

  const projectName = String(get(sub, "project_name") || "");
  const teamName = String(get(sub, "team_name") || "");
  const description = String(get(sub, "description") || "");
  const githubUrl = String(get(sub, "github", "original") || "");
  const videoUrl = String(get(sub, "video", "original") || "");

  const scores = (score ? get(score, "scores") : null) as Record<
    string,
    { score: number; source: string }
  > | null;
  const weightedTotal = Number(get(score, "weighted_total") || 0);

  const files = meta ? (get(meta, "files") as Record<string, unknown>) : null;
  const gitHistory = meta ? (get(meta, "git_history") as Record<string, unknown>) : null;

  const patterns = staticA
    ? (get(staticA, "integration_patterns") as Record<
        string,
        { description: string; match_count: number; files: string[] }
      >)
    : null;

  const reviewText = String(get(review, "review_text") || "");
  const reviewSuccess = get(review, "success") === true;

  const transcript = String(get(video, "transcript_summary") || "");
  const demoClass = String(get(video, "demo_classification") || "");
  const videoReview = String(get(video, "review_text") || "");
  const videoSuccess = get(video, "analysis_success") === true;

  return (
    <div className="space-y-6 max-w-3xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{projectName}</h1>
          <p className="text-muted-foreground text-sm">
            Team #{teamNumber}: {teamName}
          </p>
        </div>
        <Link
          href={`/hackathons/${id}/runs/${runId}/leaderboard`}
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          Back to leaderboard
        </Link>
      </div>

      {/* Score summary */}
      {scores && Object.keys(scores).length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Scores</CardTitle>
              <span className="text-lg font-bold">{weightedTotal.toFixed(1)}/10</span>
            </div>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Criterion</TableHead>
                  <TableHead className="w-[200px]">Score</TableHead>
                  <TableHead className="text-right w-20">Source</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {Object.entries(scores).map(([key, val]) => (
                  <TableRow key={key}>
                    <TableCell className="font-medium">
                      {key.replace(/_/g, " ")}
                    </TableCell>
                    <TableCell>
                      <ScoreBar value={val.score} />
                    </TableCell>
                    <TableCell className="text-right">
                      <Badge variant="outline" className="text-xs">
                        {val.source}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* Links */}
      <div className="flex gap-4 text-sm">
        {githubUrl && (
          <a
            href={githubUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary hover:underline"
          >
            GitHub
          </a>
        )}
        {videoUrl && (
          <a
            href={videoUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary hover:underline"
          >
            Demo Video
          </a>
        )}
      </div>

      {/* Description */}
      {description && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Description</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm whitespace-pre-wrap">{description}</p>
          </CardContent>
        </Card>
      )}

      {/* Code Review */}
      {reviewSuccess && reviewText && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Code Review</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="prose prose-sm max-w-none dark:prose-invert whitespace-pre-wrap text-sm">
              {reviewText}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Video Analysis */}
      {videoSuccess && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Video Analysis</CardTitle>
              {demoClass && demoClass !== "unknown" && (
                <Badge variant="secondary">{demoClass.replace(/_/g, " ")}</Badge>
              )}
            </div>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            {transcript && (
              <div>
                <span className="font-medium">Transcript Summary: </span>
                {transcript}
              </div>
            )}
            {videoReview && <p>{videoReview}</p>}
          </CardContent>
        </Card>
      )}

      {/* Repository Stats */}
      {meta && get(meta, "clone_success") === true && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Repository</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 text-sm">
              <div>
                <span className="text-muted-foreground">LOC</span>
                <p className="font-medium">{Number(get(files, "total_loc") || 0).toLocaleString()}</p>
              </div>
              <div>
                <span className="text-muted-foreground">Language</span>
                <p className="font-medium">{String(get(files, "primary_language") || "unknown")}</p>
              </div>
              <div>
                <span className="text-muted-foreground">Commits</span>
                <p className="font-medium">{String(get(gitHistory, "total_commits") || 0)}</p>
              </div>
              <div>
                <span className="text-muted-foreground">README</span>
                <p className="font-medium">{get(files, "has_readme") ? "Yes" : "No"}</p>
              </div>
              <div>
                <span className="text-muted-foreground">Tests</span>
                <p className="font-medium">{get(files, "has_tests") ? "Yes" : "No"}</p>
              </div>
              <div>
                <span className="text-muted-foreground">Period</span>
                <p className="font-medium">
                  {String(get(gitHistory, "hackathon_period_flag") || "unknown").replace(/_/g, " ")}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Integration Patterns */}
      {patterns && Object.keys(patterns).length > 0 && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Integration Patterns</CardTitle>
              <Badge variant="outline">
                {String(get(staticA, "integration_depth") || "none")}
              </Badge>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-1 text-sm">
              {Object.entries(patterns).map(([key, p]) => (
                <div key={key} className="flex items-center justify-between py-1">
                  <span>{p.description}</span>
                  <span className="text-muted-foreground text-xs">
                    {p.match_count} matches in {p.files.length} files
                  </span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
