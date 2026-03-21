"use client";

import { useEffect, useRef, useState } from "react";
import { runs as api } from "@/lib/api";
import type { PipelineRun } from "@/lib/types";
import { PIPELINE_STAGES, STAGE_LABELS } from "@/lib/types";
import { Badge } from "@/components/ui/badge";

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
  if (status === "failed") {
    return (
      <div className="w-6 h-6 rounded-full bg-destructive flex items-center justify-center text-destructive-foreground text-xs font-bold">
        ✕
      </div>
    );
  }
  return (
    <div className="w-6 h-6 rounded-full border-2 border-muted" />
  );
}

interface Props {
  run: PipelineRun;
  onUpdate?: (run: PipelineRun) => void;
}

export function PipelineProgress({ run: initialRun, onUpdate }: Props) {
  const [run, setRun] = useState(initialRun);
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

  const progress = run.stage_progress || {};

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
                : "secondary"
          }
        >
          {run.status}
        </Badge>
      </div>

      <div className="space-y-0">
        {PIPELINE_STAGES.map((stage, i) => {
          const status = progress[stage] || "pending";
          return (
            <div key={stage} className="flex items-center gap-3 py-1.5">
              <StageIcon status={status} />
              <div className="flex-1 flex items-center justify-between">
                <span
                  className={`text-sm ${
                    status === "running"
                      ? "font-medium"
                      : status === "pending"
                        ? "text-muted-foreground"
                        : ""
                  }`}
                >
                  {STAGE_LABELS[stage] || stage}
                </span>
                <span className="text-xs text-muted-foreground capitalize">
                  {status === "pending" ? "" : status}
                </span>
              </div>
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
