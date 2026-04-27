"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ChevronDown, ChevronRight, Undo2, X } from "lucide-react";
import { EditableUrl } from "@/components/editable-url";
import {
  hackathons as hackathonsApi,
  results as resultsApi,
  runs as runsApi,
} from "@/lib/api";
import type {
  Flag,
  Hackathon,
  LeaderboardEntry,
  OutreachTeam,
  PipelineRun,
} from "@/lib/types";
import { Button, buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  Card,
  CardContent,
  CardDescription,
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
import {
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
} from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { PipelineProgress } from "@/components/pipeline-progress";

export default function HackathonDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [hackathon, setHackathon] = useState<Hackathon | null>(null);
  const [pipelineRuns, setPipelineRuns] = useState<PipelineRun[]>([]);
  const [uploading, setUploading] = useState(false);
  const [triggering, setTriggering] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [clearingCache, setClearingCache] = useState(false);
  const [clearCacheOpen, setClearCacheOpen] = useState(false);
  // Bumped on every successful CSV upload so the preview re-fetches even
  // when the new file's name matches the old one.
  const [csvVersion, setCsvVersion] = useState(0);

  const load = useCallback(async () => {
    const [h, r] = await Promise.all([
      hackathonsApi.get(id),
      runsApi.list(id),
    ]);
    setHackathon(h);
    setPipelineRuns(r);
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const updated = await hackathonsApi.uploadCsv(id, file);
      setHackathon(updated);
      setCsvVersion((v) => v + 1);
    } catch (err) {
      alert(String(err));
    } finally {
      setUploading(false);
    }
  }

  async function handleRun(phase: "acquisition" | "analysis" | "full") {
    setTriggering(true);
    try {
      const run = await runsApi.create(id, { phase });
      setPipelineRuns((prev) => [run, ...prev]);
    } catch (err) {
      alert(String(err));
    } finally {
      setTriggering(false);
    }
  }

  async function handleDelete() {
    if (!confirm("Delete this hackathon and all its data?")) return;
    setDeleting(true);
    try {
      await hackathonsApi.delete(id);
      router.push("/");
    } catch (err) {
      alert(String(err));
      setDeleting(false);
    }
  }

  async function handleClearCache() {
    setClearingCache(true);
    try {
      const { deleted_runs } = await hackathonsApi.clearCache(id);
      setPipelineRuns([]);
      setClearCacheOpen(false);
      alert(
        deleted_runs > 0
          ? `Cleared ${deleted_runs} run${deleted_runs === 1 ? "" : "s"} and their cached data.`
          : "No cached data to clear."
      );
    } catch (err) {
      alert(String(err));
    } finally {
      setClearingCache(false);
    }
  }

  function handleRunUpdate(updatedRun: PipelineRun) {
    setPipelineRuns((prev) =>
      prev.map((r) => (r.id === updatedRun.id ? updatedRun : r))
    );
  }

  if (!hackathon) {
    return <p className="text-muted-foreground">Loading...</p>;
  }

  const hasActiveRun = pipelineRuns.some(
    (r) => r.status === "pending" || r.status === "running"
  );
  const latestCompletedRun = pipelineRuns.find(
    (r) => r.status === "completed"
  );
  // Most recent run whose acquisition stages are all completed — used as the
  // source of truth for Outreach and as the prerequisite for running analysis.
  const latestAcquisitionRun = pipelineRuns.find((r) =>
    ["parse", "clone", "video_download"].every(
      (s) => r.stage_progress?.[s] === "completed"
    )
  );
  const hasAcquisitionData = !!latestAcquisitionRun;

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            {hackathon.name}
          </h1>
          <p className="text-muted-foreground text-sm">
            Created{" "}
            {new Date(hackathon.created_at).toLocaleDateString(undefined, {
              month: "long",
              day: "numeric",
              year: "numeric",
            })}
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => router.push(`/hackathons/${id}/edit`)}
          >
            Edit Config
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setClearCacheOpen(true)}
            disabled={clearingCache || hasActiveRun}
            title={
              hasActiveRun
                ? "Cannot clear cache while a run is active"
                : undefined
            }
          >
            Clear Cache
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleDelete}
            disabled={deleting}
            className="text-destructive hover:text-destructive"
          >
            {deleting ? "Deleting..." : "Delete"}
          </Button>
        </div>
      </div>

      <Dialog open={clearCacheOpen} onOpenChange={setClearCacheOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Clear cached pipeline data?</DialogTitle>
            <DialogDescription>
              This permanently removes the run history and all on-disk artifacts
              for this hackathon. Cannot be undone.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3 text-sm">
            <div>
              <div className="font-medium text-destructive mb-1">
                Will be deleted
              </div>
              <ul className="list-disc list-inside space-y-0.5 text-muted-foreground">
                <li>Run history (every PipelineRun row in the DB)</li>
                <li>Hackathon-level shared cache: cloned repos, downloaded videos</li>
                <li>Cached LLM analysis (code reviews and video reviews)</li>
                <li>Per-stage logs and pipeline JSON outputs</li>
                <li>Generated reports and leaderboards</li>
              </ul>
            </div>
            <div>
              <div className="font-medium mb-1">Will be kept</div>
              <ul className="list-disc list-inside space-y-0.5 text-muted-foreground">
                <li>Hackathon name and configuration (scoring, prompts, bundles)</li>
                <li>The uploaded CSV file</li>
              </ul>
            </div>
            <p className="text-xs text-muted-foreground pt-1">
              The next pipeline run will start from scratch — repos will be
              re-cloned, videos re-downloaded, and code reviewed again.
            </p>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setClearCacheOpen(false)}
              disabled={clearingCache}
            >
              Cancel
            </Button>
            <Button
              onClick={handleClearCache}
              disabled={clearingCache}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {clearingCache ? "Clearing..." : "Clear Cache"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Results — primary view */}
      <ResultsSection
        hackathonId={id}
        latestCompletedRun={latestCompletedRun ?? null}
        hasActiveRun={hasActiveRun}
      />

      <Separator />

      {/* Setup & Pipeline — secondary */}
      <div>
        <h2 className="text-lg font-semibold tracking-tight">
          Setup &amp; Pipeline
        </h2>
        <p className="text-sm text-muted-foreground">
          Configure inputs and run the review pipeline
        </p>
      </div>

      {/* Configuration */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Configuration</CardTitle>
          <CardDescription>
            Scoring rubric, code review prompt, and parsing rules
          </CardDescription>
        </CardHeader>
        <CardContent>
          <details className="text-sm">
            <summary className="cursor-pointer text-muted-foreground hover:text-foreground inline-flex items-center gap-2">
              View raw JSON
            </summary>
            <pre className="mt-3 p-3 rounded-md bg-muted text-xs overflow-auto max-h-96">
              {JSON.stringify(hackathon.config, null, 2)}
            </pre>
          </details>
        </CardContent>
      </Card>

      {/* Submissions CSV */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Submissions CSV</CardTitle>
          <CardDescription>
            The CSV file containing hackathon submissions
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {hackathon.csv_filename ? (
            <>
              <div className="flex items-center gap-3">
                <Badge variant="outline" title={hackathon.csv_filename}>
                  <span className="truncate max-w-[400px]">
                    {hackathon.csv_filename}
                  </span>
                </Badge>
                <label className="text-sm text-muted-foreground hover:text-foreground cursor-pointer transition-colors">
                  {uploading ? "Uploading..." : "Replace"}
                  <input
                    type="file"
                    accept=".csv"
                    onChange={handleUpload}
                    onClick={(e) => {
                      (e.target as HTMLInputElement).value = "";
                    }}
                    className="hidden"
                  />
                </label>
              </div>
              <CsvPreview
                hackathonId={id}
                csvFilename={hackathon.csv_filename}
                version={csvVersion}
              />
            </>
          ) : (
            <label className="inline-flex items-center gap-2 cursor-pointer">
              <span className="inline-flex items-center justify-center rounded-md border border-input bg-background px-3 py-1.5 text-sm font-medium hover:bg-accent hover:text-accent-foreground transition-colors">
                {uploading ? "Uploading..." : "Upload CSV"}
              </span>
              <input
                type="file"
                accept=".csv"
                onChange={handleUpload}
                onClick={(e) => {
                  (e.target as HTMLInputElement).value = "";
                }}
                className="hidden"
              />
            </label>
          )}
        </CardContent>
      </Card>

      {/* Data Acquisition — clones repos, downloads videos, surfaces failures */}
      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-3">
            <div>
              <CardTitle className="text-base">Data Acquisition</CardTitle>
              <CardDescription>
                Clone repos, download videos, and identify teams that need
                outreach. Cheap to re-run — only changed teams re-fetch.
              </CardDescription>
            </div>
            <Button
              onClick={() => handleRun("acquisition")}
              disabled={triggering || !hackathon.csv_filename || hasActiveRun}
              size="sm"
            >
              {triggering
                ? "Starting..."
                : hasActiveRun
                  ? "Pipeline running..."
                  : hasAcquisitionData
                    ? "Refresh Data"
                    : "Acquire Data"}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <DataAcquisitionInline
            hackathonId={id}
            run={latestAcquisitionRun ?? null}
          />
        </CardContent>
      </Card>

      {/* Analysis — LLM cost. Only enabled once acquisition data exists. */}
      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-3">
            <div>
              <CardTitle className="text-base">Analysis</CardTitle>
              <CardDescription>
                Run static analysis, code review, video analysis, scoring, and
                reporting. Uses the LLM provider — only run when the data is in
                good shape.
              </CardDescription>
            </div>
            <Button
              onClick={() => handleRun("analysis")}
              disabled={
                triggering ||
                !hackathon.csv_filename ||
                hasActiveRun ||
                !hasAcquisitionData
              }
              size="sm"
              title={
                !hasAcquisitionData
                  ? "Run Data Acquisition first"
                  : undefined
              }
            >
              {triggering
                ? "Starting..."
                : hasActiveRun
                  ? "Running..."
                  : "Run Analysis"}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <p className="text-xs text-muted-foreground">
            {hasAcquisitionData
              ? "Data is ready. Running analysis will use cached results for any team whose repo or video hasn't changed since the last run."
              : "Acquire data first. The Analysis step reads the most recently completed Data Acquisition run."}
          </p>
        </CardContent>
      </Card>

      {/* Run history — link to dedicated page */}
      {pipelineRuns.length > 0 && (
        <div className="flex items-center justify-between rounded-md border p-3">
          <div>
            <h3 className="text-sm font-semibold">Run history</h3>
            <p className="text-xs text-muted-foreground">
              {pipelineRuns.length} run{pipelineRuns.length === 1 ? "" : "s"} ·
              latest{" "}
              <span className="font-mono">
                {pipelineRuns[0].id.slice(0, 8)}
              </span>{" "}
              {pipelineRuns[0].status}
            </p>
          </div>
          <Link
            href={`/hackathons/${id}/runs`}
            className={cn(buttonVariants({ variant: "outline", size: "sm" }))}
          >
            View runs →
          </Link>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Results section
// ---------------------------------------------------------------------------

function ResultsSection({
  hackathonId,
  latestCompletedRun,
  hasActiveRun,
}: {
  hackathonId: string;
  latestCompletedRun: PipelineRun | null;
  hasActiveRun: boolean;
}) {
  const [leaderboard, setLeaderboard] = useState<LeaderboardEntry[] | null>(null);
  const [flags, setFlags] = useState<Flag[] | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!latestCompletedRun) {
      setLeaderboard(null);
      setFlags(null);
      return;
    }
    setLoading(true);
    Promise.all([
      resultsApi.leaderboard(latestCompletedRun.id),
      resultsApi.flags(latestCompletedRun.id),
    ])
      .then(([lb, fl]) => {
        setLeaderboard(lb);
        setFlags(fl);
      })
      .finally(() => setLoading(false));
  }, [latestCompletedRun?.id]);

  if (!latestCompletedRun) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Results</CardTitle>
          <CardDescription>
            Leaderboard and flags from the latest completed pipeline run
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="py-8 text-center text-sm text-muted-foreground">
            {hasActiveRun
              ? "Pipeline running — results will appear here when it completes."
              : "No completed runs yet. Run the pipeline below to see results."}
          </div>
        </CardContent>
      </Card>
    );
  }

  const runId = latestCompletedRun.id;
  const activeFlags = (flags ?? []).filter((f) => !f.dismissed);
  const errorCount = activeFlags.filter((f) => f.severity === "error").length;
  const warningCount = activeFlags.filter((f) => f.severity === "warning").length;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-4">
          <div>
            <CardTitle className="text-lg">Results</CardTitle>
            <CardDescription>
              From run{" "}
              <span className="font-mono">{runId.slice(0, 8)}</span> ·{" "}
              {latestCompletedRun.completed_at
                ? new Date(latestCompletedRun.completed_at).toLocaleString()
                : "—"}
            </CardDescription>
          </div>
          <div className="flex flex-wrap gap-2 justify-end">
            <a
              href={runsApi.videosZipUrl(runId)}
              download={`videos-${runId.slice(0, 8)}.zip`}
              className={cn(buttonVariants({ variant: "outline", size: "sm" }))}
            >
              Download videos (.zip)
            </a>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue="leaderboard">
          <TabsList>
            <TabsTrigger value="leaderboard">
              Leaderboard
              {leaderboard && (
                <span className="ml-1.5 text-xs text-muted-foreground">
                  {leaderboard.length}
                </span>
              )}
            </TabsTrigger>
            <TabsTrigger value="flags">
              Flags
              {flags && (
                <span className="ml-1.5 text-xs text-muted-foreground">
                  {activeFlags.length}
                </span>
              )}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="leaderboard" className="mt-4">
            <Link
              href={`/hackathons/${hackathonId}/leaderboard`}
              className={cn(
                buttonVariants({ variant: "outline", size: "sm" }),
                "mb-3"
              )}
            >
              View full leaderboard →
            </Link>
            {loading ? (
              <p className="text-sm text-muted-foreground py-6">Loading...</p>
            ) : !leaderboard || leaderboard.length === 0 ? (
              <p className="text-sm text-muted-foreground py-6">
                No leaderboard entries (scoring stage may not have run).
              </p>
            ) : (
              <LeaderboardTable
                entries={leaderboard}
                hackathonId={hackathonId}
                runId={runId}
              />
            )}
          </TabsContent>

          <TabsContent value="flags" className="mt-4">
            <Link
              href={`/hackathons/${hackathonId}/flags`}
              className={cn(
                buttonVariants({ variant: "outline", size: "sm" }),
                "mb-3"
              )}
            >
              View full flags →
            </Link>
            {loading ? (
              <p className="text-sm text-muted-foreground py-6">Loading...</p>
            ) : !flags || flags.length === 0 ? (
              <p className="text-sm text-muted-foreground py-6">
                No flags raised — every submission is clean.
              </p>
            ) : (
              <>
                <div className="flex gap-3 mb-3 text-xs">
                  {errorCount > 0 && (
                    <span className="text-destructive">
                      {errorCount} error{errorCount === 1 ? "" : "s"}
                    </span>
                  )}
                  {warningCount > 0 && (
                    <span className="text-yellow-600 dark:text-yellow-500">
                      {warningCount} warning{warningCount === 1 ? "" : "s"}
                    </span>
                  )}
                </div>
                <FlagsList
                  flags={flags}
                  runId={runId}
                  onChange={(next) => setFlags(next)}
                />
              </>
            )}
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}

function LeaderboardTable({
  entries,
  hackathonId,
  runId,
}: {
  entries: LeaderboardEntry[];
  hackathonId: string;
  runId: string;
}) {
  const criteriaKeys = entries[0] ? Object.keys(entries[0].scores) : [];
  return (
    <div className="space-y-2">
      <p className="text-xs text-muted-foreground">
        Click a team to see the full code review, video analysis, and project
        details.
      </p>
      <div className="rounded-md border overflow-auto max-h-[480px]">
        <Table>
          <TableHeader className="sticky top-0 bg-background">
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
              <TableHead>Lang</TableHead>
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
                    `/hackathons/${hackathonId}/runs/${runId}/projects/${e.team_number}`
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
  );
}

const COMPACT_TEAM_LIMIT = 5;

function DataAcquisitionInline({
  hackathonId,
  run,
}: {
  hackathonId: string;
  run: PipelineRun | null;
}) {
  const [outreach, setOutreach] = useState<OutreachTeam[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [showAll, setShowAll] = useState(false);

  const refresh = useCallback(async () => {
    if (!run) {
      setOutreach(null);
      return;
    }
    setLoading(true);
    try {
      const data = await resultsApi.outreach(run.id);
      setOutreach(data);
    } catch {
      setOutreach([]);
    } finally {
      setLoading(false);
    }
  }, [run?.id]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  if (!run) {
    return (
      <p className="text-sm text-muted-foreground">
        No data acquired yet. Click <strong>Acquire Data</strong> to clone repos
        and download videos.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <div className="text-xs text-muted-foreground">
        Last acquisition: <span className="font-mono">{run.id.slice(0, 8)}</span>
        {" · "}
        {run.completed_at
          ? new Date(run.completed_at).toLocaleString()
          : run.status}
      </div>

      {loading && !outreach ? (
        <p className="text-sm text-muted-foreground">Checking outreach…</p>
      ) : !outreach || outreach.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Every team's repo and video acquired cleanly — no outreach needed.
        </p>
      ) : (
        <>
          <div className="flex items-center justify-between">
            <p className="text-sm">
              <span className="font-semibold text-destructive">
                {outreach.length}
              </span>{" "}
              team{outreach.length === 1 ? "" : "s"} need outreach (URL fixes)
            </p>
            <Link
              href={`/hackathons/${hackathonId}/outreach`}
              className={cn(
                buttonVariants({ variant: "outline", size: "sm" }),
              )}
            >
              Open full outreach view →
            </Link>
          </div>
          <OutreachInlineList
            teams={
              showAll ? outreach : outreach.slice(0, COMPACT_TEAM_LIMIT)
            }
            hackathonId={hackathonId}
            runId={run.id}
            onSaved={refresh}
          />
          {outreach.length > COMPACT_TEAM_LIMIT && (
            <button
              type="button"
              onClick={() => setShowAll((v) => !v)}
              className="text-xs text-muted-foreground hover:text-foreground inline-flex items-center gap-1"
            >
              {showAll
                ? `Show first ${COMPACT_TEAM_LIMIT}`
                : `Show all ${outreach.length} teams`}
            </button>
          )}
        </>
      )}
    </div>
  );
}

function OutreachInlineList({
  teams,
  hackathonId,
  runId,
  onSaved,
}: {
  teams: OutreachTeam[];
  hackathonId: string;
  runId: string;
  onSaved: () => void;
}) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [retrying, setRetrying] = useState<Set<string>>(new Set());

  function toggle(tn: number) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(tn)) next.delete(tn);
      else next.add(tn);
      return next;
    });
  }

  async function retry(team: OutreachTeam, stage: "clone" | "video_download") {
    const key = `${team.team_number}:${stage}`;
    setRetrying((p) => new Set([...p, key]));
    try {
      await runsApi.retry(runId, stage, [team.team_number]);
      // Retry runs in a FastAPI background thread, so the POST returns
      // before the actual fetch completes. Poll the run until the team
      // is no longer in stage_detail[stage].failures (the retry handler
      // removes it whether the retry succeeded or failed). Cap at 90s so
      // a hung yt-dlp doesn't pin the spinner forever.
      const deadline = Date.now() + 90_000;
      while (Date.now() < deadline) {
        await new Promise((resolve) => setTimeout(resolve, 1500));
        try {
          const r = await runsApi.get(runId);
          const failures = r.stage_detail?.[stage]?.failures ?? [];
          if (!failures.some((f) => f.team_number === team.team_number)) {
            break;
          }
        } catch {
          // transient — keep polling
        }
      }
      onSaved();
    } catch (err) {
      alert(String(err));
    } finally {
      setRetrying((p) => {
        const next = new Set(p);
        next.delete(key);
        return next;
      });
    }
  }

  return (
    <div className="rounded-md border divide-y max-h-[480px] overflow-auto">
      {teams.map((t) => {
        const issueLabels = t.issues.map((i) => i.label).join(", ");
        const memberCount = t.members.length;
        const isOpen = expanded.has(t.team_number);
        return (
          <div key={t.team_number} className="text-sm">
            <button
              type="button"
              onClick={() => toggle(t.team_number)}
              className="flex w-full items-start gap-3 p-3 text-left hover:bg-muted/30 transition-colors"
            >
              {isOpen ? (
                <ChevronDown className="size-4 mt-0.5 shrink-0 text-muted-foreground" />
              ) : (
                <ChevronRight className="size-4 mt-0.5 shrink-0 text-muted-foreground" />
              )}
              <span className="font-mono text-xs text-muted-foreground mt-0.5 shrink-0">
                #{t.team_number}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-medium truncate">{t.team_name}</span>
                  <span className="text-xs text-muted-foreground">
                    · {memberCount} member{memberCount === 1 ? "" : "s"}
                  </span>
                </div>
                {!isOpen && (
                  <p className="text-xs text-muted-foreground mt-0.5 truncate">
                    {issueLabels}
                  </p>
                )}
              </div>
              <div className="flex flex-wrap gap-1 justify-end shrink-0">
                {t.issues.map((i) => (
                  <Badge
                    key={i.type}
                    variant="destructive"
                    className="text-[10px]"
                  >
                    {i.type.replace(/_/g, " ")}
                  </Badge>
                ))}
              </div>
            </button>
            {isOpen && (
              <div className="px-4 pb-3 pl-12 space-y-2.5">
                {/* Detailed issue messages */}
                <div className="space-y-1">
                  {t.issues.map((issue) => (
                    <p
                      key={issue.type}
                      className="text-xs text-muted-foreground"
                    >
                      <span className="text-destructive font-medium">
                        {issue.label}:
                      </span>{" "}
                      {issue.description}
                    </p>
                  ))}
                </div>

                {/* Member emails */}
                {t.members.length > 0 && (
                  <div className="text-xs">
                    <span className="text-muted-foreground uppercase tracking-wide text-[10px]">
                      Members
                    </span>
                    <ul className="mt-0.5 space-y-0.5">
                      {t.members.map((m, i) => (
                        <li key={i} className="truncate">
                          {m.name}
                          {m.email && (
                            <span className="text-muted-foreground">
                              {" "}
                              &lt;{m.email}&gt;
                            </span>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Editable URLs */}
                <div className="space-y-1.5 pt-1">
                  <EditableUrl
                    hackathonId={hackathonId}
                    teamNumber={t.team_number}
                    field="github_url"
                    label="GitHub"
                    initialUrl={t.github_url}
                    onSaved={onSaved}
                  />
                  <EditableUrl
                    hackathonId={hackathonId}
                    teamNumber={t.team_number}
                    field="video_url"
                    label="Video"
                    initialUrl={t.video_url}
                    onSaved={onSaved}
                  />
                </div>

                {/* Retry buttons — only for stages that actually attempted
                    a fetch (invalid_*_url means we never tried, so retry
                    won't help; the user needs to fix the URL above). */}
                {(t.issues.some((i) => i.type === "clone_failed") ||
                  t.issues.some((i) => i.type === "video_download_failed")) && (
                  <div className="flex gap-2 pt-1">
                    {t.issues.some((i) => i.type === "clone_failed") && (
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        className="h-6 text-[11px] px-2"
                        disabled={retrying.has(`${t.team_number}:clone`)}
                        onClick={(e) => {
                          e.stopPropagation();
                          retry(t, "clone");
                        }}
                      >
                        {retrying.has(`${t.team_number}:clone`)
                          ? "Retrying clone…"
                          : "↻ Retry clone"}
                      </Button>
                    )}
                    {t.issues.some(
                      (i) => i.type === "video_download_failed",
                    ) && (
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        className="h-6 text-[11px] px-2"
                        disabled={retrying.has(
                          `${t.team_number}:video_download`,
                        )}
                        onClick={(e) => {
                          e.stopPropagation();
                          retry(t, "video_download");
                        }}
                      >
                        {retrying.has(`${t.team_number}:video_download`)
                          ? "Retrying download…"
                          : "↻ Retry video download"}
                      </Button>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function FlagsList({
  flags,
  runId,
  onChange,
}: {
  flags: Flag[];
  runId: string;
  onChange: (next: Flag[]) => void;
}) {
  const [pending, setPending] = useState<Set<string>>(new Set());

  const flagKey = (f: Flag) => `${f.team_number}:${f.flag_type}`;

  async function toggle(f: Flag, dismiss: boolean) {
    const k = flagKey(f);
    setPending((p) => new Set([...p, k]));
    try {
      if (dismiss) {
        await resultsApi.dismissFlag(runId, f.team_number, f.flag_type);
      } else {
        await resultsApi.undismissFlag(runId, f.team_number, f.flag_type);
      }
      onChange(
        flags.map((x) =>
          flagKey(x) === k ? { ...x, dismissed: dismiss } : x
        )
      );
    } catch (err) {
      alert(String(err));
    } finally {
      setPending((p) => {
        const next = new Set(p);
        next.delete(k);
        return next;
      });
    }
  }

  const active = flags.filter((f) => !f.dismissed);
  const dismissed = flags.filter((f) => f.dismissed);

  function row(f: Flag, isDismissed: boolean) {
    const k = flagKey(f);
    const busy = pending.has(k);
    return (
      <div
        key={k}
        className={`flex items-start gap-3 p-3 text-sm ${
          isDismissed ? "opacity-60" : ""
        }`}
      >
        <Badge
          variant={
            f.severity === "error"
              ? "destructive"
              : f.severity === "warning"
                ? "secondary"
                : "outline"
          }
          className="mt-0.5 shrink-0"
        >
          {f.severity}
        </Badge>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-mono text-xs text-muted-foreground">
              #{f.team_number}
            </span>
            <span
              className={`font-medium truncate ${isDismissed ? "line-through" : ""}`}
            >
              {f.project_name || f.team_name}
            </span>
            <Badge variant="outline" className="text-xs">
              {f.flag_type}
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">{f.description}</p>
        </div>
        <button
          type="button"
          onClick={() => toggle(f, !isDismissed)}
          disabled={busy}
          className="shrink-0 inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-muted-foreground hover:text-foreground hover:bg-muted disabled:opacity-50"
          title={isDismissed ? "Restore flag" : "Dismiss this flag"}
        >
          {isDismissed ? (
            <>
              <Undo2 className="size-3.5" />
              Restore
            </>
          ) : (
            <>
              <X className="size-3.5" />
              Dismiss
            </>
          )}
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {active.length === 0 ? (
        <p className="text-sm text-muted-foreground py-4 text-center rounded-md border">
          No active flags. {dismissed.length > 0 && "All current flags are dismissed."}
        </p>
      ) : (
        <div className="rounded-md border divide-y max-h-[480px] overflow-auto">
          {active.map((f) => row(f, false))}
        </div>
      )}

      {dismissed.length > 0 && (
        <details className="rounded-md border">
          <summary className="cursor-pointer px-3 py-2 text-xs text-muted-foreground hover:text-foreground">
            Dismissed ({dismissed.length})
          </summary>
          <div className="divide-y border-t">
            {dismissed.map((f) => row(f, true))}
          </div>
        </details>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// CSV preview
// ---------------------------------------------------------------------------

const CSV_PAGE_SIZE = 10;

function CsvPreview({
  hackathonId,
  csvFilename,
  version,
}: {
  hackathonId: string;
  csvFilename: string;
  version: number;
}) {
  const [data, setData] = useState<{
    headers: string[];
    rows: string[][];
    total_rows: number;
    offset: number;
    limit: number;
  } | null>(null);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setPage(0);
  }, [hackathonId, csvFilename, version]);

  useEffect(() => {
    setLoading(true);
    setError(null);
    hackathonsApi
      .csvPreview(hackathonId, page * CSV_PAGE_SIZE, CSV_PAGE_SIZE)
      .then(setData)
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false));
  }, [hackathonId, csvFilename, version, page]);

  if (error) {
    return <p className="text-sm text-destructive">Preview failed: {error}</p>;
  }
  if (!data && loading) {
    return <p className="text-sm text-muted-foreground">Loading preview...</p>;
  }
  if (!data || data.headers.length === 0) {
    return <p className="text-sm text-muted-foreground">CSV is empty.</p>;
  }

  const totalPages = Math.max(1, Math.ceil(data.total_rows / CSV_PAGE_SIZE));
  const firstRow = data.total_rows === 0 ? 0 : data.offset + 1;
  const lastRow = data.offset + data.rows.length;

  return (
    <div className="space-y-2">
      <div className="text-xs text-muted-foreground">
        Showing rows {firstRow}–{lastRow} of {data.total_rows}
      </div>
      <div className="rounded-md border overflow-auto max-h-[320px]">
        <Table>
          <TableHeader className="sticky top-0 bg-background">
            <TableRow>
              {data.headers.map((h, i) => (
                <TableHead key={i} className="whitespace-nowrap text-xs">
                  {h}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.rows.map((row, i) => (
              <TableRow key={i}>
                {row.map((cell, j) => (
                  <TableCell
                    key={j}
                    className="text-xs max-w-[280px] truncate"
                    title={cell}
                  >
                    {cell}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <div className="flex items-center justify-between pt-1">
        <Button
          variant="outline"
          size="sm"
          onClick={() => setPage((p) => Math.max(0, p - 1))}
          disabled={page === 0 || loading}
        >
          ← Prev
        </Button>
        <span className="text-xs text-muted-foreground tabular-nums">
          Page {page + 1} of {totalPages}
        </span>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
          disabled={page >= totalPages - 1 || loading}
        >
          Next →
        </Button>
      </div>
    </div>
  );
}
