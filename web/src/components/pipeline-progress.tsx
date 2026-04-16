"use client";

import { useEffect, useRef, useState } from "react";
import { runs as api } from "@/lib/api";
import type { PipelineRun, StageFailure } from "@/lib/types";
import { PIPELINE_STAGES, STAGE_LABELS } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

const RETRYABLE_STAGES = new Set(["clone", "video_download", "code_review", "video_analysis"]);

function StageIcon({ status }: { status: string }) {
  if (status === "completed") {
    return (
      <div className="w-6 h-6 rounded-full bg-primary flex items-center justify-center text-primary-foreground text-xs font-bold">
        ✓
      </div>
    );
  }
  if (status === "running") {
    return (
      <div className="w-6 h-6 rounded-full border-2 border-primary flex items-center justify-center">
        <div className="w-2 h-2 rounded-full bg-primary animate-pulse" />
      </div>
    );
  }
  if (status === "failed" || status === "interrupted") {
    return (
      <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
        status === "failed"
          ? "bg-destructive text-destructive-foreground"
          : "bg-yellow-600 text-white"
      }`}>
        {status === "failed" ? "✕" : "⏸"}
      </div>
    );
  }
  return (
    <div className="w-6 h-6 rounded-full border-2 border-muted" />
  );
}

function ProgressBar({ done, total }: { done: number; total: number }) {
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  return (
    <div className="flex items-center gap-2 mt-1">
      <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
        <div
          className="h-full rounded-full bg-primary transition-all duration-300"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs tabular-nums text-muted-foreground w-16 text-right">
        {done}/{total}
      </span>
    </div>
  );
}

function FailureList({
  failures,
  stage,
  runId,
  pipelineActive,
  onRetried,
}: {
  failures: StageFailure[];
  stage: string;
  runId: string;
  pipelineActive: boolean;
  onRetried: () => void;
}) {
  const [retrying, setRetrying] = useState<Set<number>>(new Set());
  const canRetry = RETRYABLE_STAGES.has(stage) && !pipelineActive;

  async function handleRetry(teamNumbers: number[]) {
    setRetrying((prev) => new Set([...prev, ...teamNumbers]));
    try {
      await api.retry(runId, stage, teamNumbers);
      setTimeout(onRetried, 2000);
    } catch (err) {
      alert(String(err));
    } finally {
      setRetrying((prev) => {
        const next = new Set(prev);
        teamNumbers.forEach((n) => next.delete(n));
        return next;
      });
    }
  }

  return (
    <div className="ml-9 mt-1.5 space-y-1">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-destructive">
          {failures.length} failed
        </span>
        {canRetry && failures.length > 1 && (
          <Button
            size="sm"
            variant="ghost"
            className="h-5 text-[11px] px-1.5 text-destructive hover:text-destructive"
            onClick={() => handleRetry(failures.map((f) => f.team_number))}
            disabled={retrying.size > 0}
          >
            Retry all
          </Button>
        )}
      </div>
      <div className="space-y-0.5 max-h-32 overflow-y-auto">
        {failures.map((f) => (
          <div
            key={f.team_number}
            className="flex items-center justify-between gap-2 text-xs py-0.5"
          >
            <span className="text-muted-foreground truncate flex-1">
              <span className="font-mono text-destructive/70">#{f.team_number}</span>{" "}
              {f.project_name || f.team_name}
              <span className="text-muted-foreground/60 ml-1">— {f.error}</span>
            </span>
            {canRetry && (
              <Button
                size="sm"
                variant="ghost"
                className="h-5 text-[11px] px-1.5 shrink-0"
                onClick={() => handleRetry([f.team_number])}
                disabled={retrying.has(f.team_number)}
              >
                {retrying.has(f.team_number) ? "..." : "Retry"}
              </Button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

interface Props {
  run: PipelineRun;
  onUpdate?: (run: PipelineRun) => void;
}

export function PipelineProgress({ run: initialRun, onUpdate }: Props) {
  const [run, setRun] = useState(initialRun);
  const [resuming, setResuming] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    setRun(initialRun);
  }, [initialRun]);

  useEffect(() => {
    if (run.status !== "pending" && run.status !== "running") return;

    const es = new EventSource(api.streamUrl(run.id));
    eventSourceRef.current = es;

    es.addEventListener("status", (e) => {
      const data = JSON.parse(e.data) as PipelineRun;
      setRun((prev) => ({ ...prev, ...data }));
      onUpdate?.({ ...run, ...data });
    });

    es.addEventListener("error", () => {
      es.close();
    });

    return () => {
      es.close();
    };
  }, [run.id, run.status]);

  async function handleResume() {
    setResuming(true);
    try {
      const updated = await api.resume(run.id);
      setRun((prev) => ({ ...prev, ...updated }));
      onUpdate?.({ ...run, ...updated });
    } catch (err) {
      alert(String(err));
    } finally {
      setResuming(false);
    }
  }

  function refreshRun() {
    api.get(run.id).then((updated) => {
      setRun((prev) => ({ ...prev, ...updated }));
      onUpdate?.({ ...run, ...updated });
    });
  }

  const progress = run.stage_progress || {};
  const detail = run.stage_detail || {};
  const canResume = run.status === "interrupted" || run.status === "failed";
  const completedStages = Object.values(progress).filter((s) => s === "completed").length;
  const pipelineActive = run.status === "pending" || run.status === "running";

  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-sm font-medium">Pipeline</span>
        <Badge
          variant={
            run.status === "completed"
              ? "default"
              : run.status === "failed"
                ? "destructive"
                : run.status === "interrupted"
                  ? "outline"
                  : "secondary"
          }
        >
          {run.status}
        </Badge>
        {canResume && completedStages > 0 && (
          <Button
            size="sm"
            variant="outline"
            onClick={handleResume}
            disabled={resuming}
            className="ml-auto h-7 text-xs"
          >
            {resuming ? "Resuming..." : "Resume"}
          </Button>
        )}
      </div>

      <div className="space-y-0">
        {PIPELINE_STAGES.map((stage) => {
          const status = progress[stage] || "pending";
          const stageDetail = detail[stage];
          const isRunning = status === "running";
          const failures = stageDetail?.failures ?? [];
          const showFailures = failures.length > 0;
          return (
            <div key={stage} className="py-1.5">
              <div className="flex items-center gap-3">
                <StageIcon status={status} />
                <div className="flex-1 flex items-center justify-between">
                  <span
                    className={`text-sm ${
                      isRunning
                        ? "font-medium"
                        : status === "pending"
                          ? "text-muted-foreground"
                          : ""
                    }`}
                  >
                    {STAGE_LABELS[stage] || stage}
                    {showFailures && status !== "running" && (
                      <span className="ml-1.5 text-xs text-destructive font-normal">
                        ({failures.length} failed)
                      </span>
                    )}
                  </span>
                  <span className="text-xs text-muted-foreground capitalize">
                    {status === "pending" ? "" : status}
                  </span>
                </div>
              </div>
              {isRunning && stageDetail && stageDetail.total > 0 && (
                <div className="ml-9">
                  <ProgressBar done={stageDetail.done} total={stageDetail.total} />
                </div>
              )}
              {showFailures && (
                <FailureList
                  failures={failures}
                  stage={stage}
                  runId={run.id}
                  pipelineActive={pipelineActive}
                  onRetried={refreshRun}
                />
              )}
            </div>
          );
        })}
      </div>

      {run.error && (
        <pre className="mt-3 p-3 rounded-md bg-destructive/10 text-destructive text-xs overflow-auto max-h-40">
          {run.error}
        </pre>
      )}
    </div>
  );
}
