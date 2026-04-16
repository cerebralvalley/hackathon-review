"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  hackathons as hackathonsApi,
  runs as runsApi,
} from "@/lib/api";
import type { Hackathon, PipelineRun } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { PipelineProgress } from "@/components/pipeline-progress";

export default function HackathonDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [hackathon, setHackathon] = useState<Hackathon | null>(null);
  const [pipelineRuns, setPipelineRuns] = useState<PipelineRun[]>([]);
  const [uploading, setUploading] = useState(false);
  const [triggering, setTriggering] = useState(false);
  const [deleting, setDeleting] = useState(false);

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
    } catch (err) {
      alert(String(err));
    } finally {
      setUploading(false);
    }
  }

  async function handleTrigger() {
    setTriggering(true);
    try {
      const run = await runsApi.create(id);
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

  return (
    <div className="space-y-6">
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
            onClick={handleDelete}
            disabled={deleting}
            className="text-destructive hover:text-destructive"
          >
            {deleting ? "Deleting..." : "Delete"}
          </Button>
        </div>
      </div>

      {/* CSV upload */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Submissions CSV</CardTitle>
          <CardDescription>
            Upload the CSV file containing hackathon submissions
          </CardDescription>
        </CardHeader>
        <CardContent>
          {hackathon.csv_filename ? (
            <div className="flex items-center gap-3">
              <Badge variant="outline">{hackathon.csv_filename}</Badge>
              <label className="text-sm text-muted-foreground hover:text-foreground cursor-pointer transition-colors">
                Replace
                <input
                  type="file"
                  accept=".csv"
                  onChange={handleUpload}
                  className="hidden"
                />
              </label>
            </div>
          ) : (
            <label className="inline-flex items-center gap-2 cursor-pointer">
              <span className="inline-flex items-center justify-center rounded-md border border-input bg-background px-3 py-1.5 text-sm font-medium hover:bg-accent hover:text-accent-foreground transition-colors">
                {uploading ? "Uploading..." : "Upload CSV"}
              </span>
              <input
                type="file"
                accept=".csv"
                onChange={handleUpload}
                className="hidden"
              />
            </label>
          )}
        </CardContent>
      </Card>

      {/* Run pipeline */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Pipeline</CardTitle>
          <CardDescription>
            Run the full review pipeline on the uploaded CSV
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Button
            onClick={handleTrigger}
            disabled={
              triggering || !hackathon.csv_filename || hasActiveRun
            }
          >
            {triggering
              ? "Starting..."
              : hasActiveRun
                ? "Pipeline running..."
                : "Run Pipeline"}
          </Button>

          {latestCompletedRun && (
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  router.push(`/hackathons/${id}/runs/${latestCompletedRun.id}/leaderboard`)
                }
              >
                View Leaderboard
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  router.push(`/hackathons/${id}/runs/${latestCompletedRun.id}/flags`)
                }
              >
                View Flags
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Runs */}
      {pipelineRuns.length > 0 && (
        <>
          <Separator />
          <h2 className="text-lg font-semibold">Runs</h2>
          <div className="space-y-4">
            {pipelineRuns.map((run) => (
              <Card key={run.id}>
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-sm font-mono">
                      {run.id.slice(0, 8)}
                    </CardTitle>
                    <span className="text-xs text-muted-foreground">
                      {new Date(run.created_at).toLocaleString()}
                    </span>
                  </div>
                </CardHeader>
                <CardContent>
                  <PipelineProgress run={run} onUpdate={handleRunUpdate} />
                </CardContent>
              </Card>
            ))}
          </div>
        </>
      )}

      {/* Config preview */}
      <Separator />
      <details className="text-sm">
        <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
          View Configuration
        </summary>
        <pre className="mt-2 p-3 rounded-md bg-muted text-xs overflow-auto">
          {JSON.stringify(hackathon.config, null, 2)}
        </pre>
      </details>
    </div>
  );
}
