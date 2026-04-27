"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, ChevronRight } from "lucide-react";
import { results as resultsApi, runs as runsApi } from "@/lib/api";
import type { LeaderboardEntry, PipelineRun } from "@/lib/types";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

function exportCsv(entries: LeaderboardEntry[], criteriaKeys: string[]) {
  const headers = [
    "Rank",
    "Team",
    "Project",
    "Score",
    ...criteriaKeys.map((k) => k.replace(/_/g, " ")),
    "LOC",
    "Language",
    "Depth",
    "GitHub",
    "Video",
    "Summary",
  ];

  const rows = entries.map((e) => [
    e.rank,
    `"${e.team_name.replace(/"/g, '""')}"`,
    `"${e.project_name.replace(/"/g, '""')}"`,
    e.weighted_total.toFixed(1),
    ...criteriaKeys.map((k) => e.scores[k]?.toFixed(1) ?? ""),
    e.total_loc,
    e.primary_language,
    e.integration_depth,
    e.github_url,
    e.video_url,
    `"${(e.summary ?? "").replace(/"/g, '""').replace(/\n/g, " ")}"`,
  ]);

  const csv = [headers.join(","), ...rows.map((r) => r.join(","))].join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "leaderboard.csv";
  a.click();
  URL.revokeObjectURL(url);
}

export default function HackathonLeaderboardPage() {
  const { id } = useParams<{ id: string }>();
  const [run, setRun] = useState<PipelineRun | null>(null);
  const [entries, setEntries] = useState<LeaderboardEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    runsApi
      .list(id)
      .then((runs) => {
        const latest = runs.find((r) => r.status === "completed");
        if (!latest) {
          setRun(null);
          setEntries([]);
          return;
        }
        setRun(latest);
        return resultsApi.leaderboard(latest.id).then(setEntries);
      })
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false));
  }, [id]);

  const criteriaKeys = entries.length > 0 ? Object.keys(entries[0].scores) : [];

  return (
    <div className="space-y-6">
      <Link
        href={`/hackathons/${id}`}
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" />
        Back to hackathon
      </Link>

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Leaderboard</h1>
          {run && (
            <p className="text-muted-foreground text-sm">
              From run <span className="font-mono">{run.id.slice(0, 8)}</span>
              {run.completed_at && (
                <> · {new Date(run.completed_at).toLocaleString()}</>
              )}
            </p>
          )}
        </div>
        {entries.length > 0 && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => exportCsv(entries, criteriaKeys)}
          >
            Export CSV
          </Button>
        )}
      </div>

      {loading ? (
        <p className="text-muted-foreground">Loading...</p>
      ) : error ? (
        <p className="text-destructive">{error}</p>
      ) : !run ? (
        <p className="text-muted-foreground">
          No completed runs yet. Run the pipeline first.
        </p>
      ) : entries.length === 0 ? (
        <p className="text-muted-foreground">
          No scores yet. The pipeline may not have completed the scoring stage.
        </p>
      ) : (
        <div className="space-y-2">
          <p className="text-xs text-muted-foreground">
            Click a team to see the full code review, video analysis, and project
            details.
          </p>
          <div className="rounded-md border overflow-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-12">#</TableHead>
                  <TableHead>Team</TableHead>
                  <TableHead>Project</TableHead>
                  <TableHead className="text-right">Score</TableHead>
                  {criteriaKeys.map((k) => (
                    <TableHead key={k} className="text-right text-xs">
                      {k.replace(/_/g, " ")}
                    </TableHead>
                  ))}
                  <TableHead className="text-right">LOC</TableHead>
                  <TableHead>Language</TableHead>
                  <TableHead>Depth</TableHead>
                  <TableHead className="w-8" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {entries.map((e) => (
                  <TableRow
                    key={e.team_number}
                    className="cursor-pointer hover:bg-muted/50 group"
                    onClick={() =>
                      window.location.assign(
                        `/hackathons/${id}/runs/${run.id}/projects/${e.team_number}`
                      )
                    }
                  >
                    <TableCell className="font-medium">{e.rank}</TableCell>
                    <TableCell className="max-w-[150px] truncate">
                      {e.team_name}
                    </TableCell>
                    <TableCell className="max-w-[180px] truncate">
                      {e.project_name}
                    </TableCell>
                    <TableCell className="text-right font-semibold">
                      {e.weighted_total.toFixed(1)}
                    </TableCell>
                    {criteriaKeys.map((k) => (
                      <TableCell key={k} className="text-right tabular-nums">
                        {e.scores[k]?.toFixed(1) ?? "-"}
                      </TableCell>
                    ))}
                    <TableCell className="text-right tabular-nums">
                      {e.total_loc.toLocaleString()}
                    </TableCell>
                    <TableCell>{e.primary_language}</TableCell>
                    <TableCell>
                      <Badge variant="outline" className="text-xs">
                        {e.integration_depth}
                      </Badge>
                    </TableCell>
                    <TableCell className="w-8 text-muted-foreground/50 group-hover:text-foreground transition-colors">
                      <ChevronRight className="size-4" />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      )}
    </div>
  );
}
