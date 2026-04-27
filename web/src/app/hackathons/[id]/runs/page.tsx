"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { runs as runsApi } from "@/lib/api";
import type { PipelineRun } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { PipelineProgress } from "@/components/pipeline-progress";

function phaseBadgeVariant(phase: string | undefined) {
  if (phase === "acquisition") return "secondary" as const;
  if (phase === "analysis") return "default" as const;
  return "outline" as const;
}

export default function RunsPage() {
  const { id } = useParams<{ id: string }>();
  const [runs, setRuns] = useState<PipelineRun[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await runsApi.list(id);
      setRuns(data);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  function handleRunUpdate(updatedRun: PipelineRun) {
    setRuns((prev) =>
      prev.map((r) => (r.id === updatedRun.id ? updatedRun : r))
    );
  }

  return (
    <div className="space-y-6">
      <Link
        href={`/hackathons/${id}`}
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" />
        Back to hackathon
      </Link>

      <div>
        <h1 className="text-2xl font-bold tracking-tight">Run history</h1>
        <p className="text-muted-foreground text-sm">
          Every pipeline run for this hackathon — newest first
        </p>
      </div>

      {loading ? (
        <p className="text-muted-foreground">Loading...</p>
      ) : runs.length === 0 ? (
        <p className="text-muted-foreground">
          No runs yet. Trigger Acquire Data or Run Analysis from the hackathon
          page.
        </p>
      ) : (
        <div className="space-y-4">
          {runs.map((run) => (
            <Card key={run.id}>
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <div className="flex items-center gap-2">
                    <CardTitle className="text-sm font-mono">
                      {run.id.slice(0, 8)}
                    </CardTitle>
                    {run.phase && (
                      <Badge
                        variant={phaseBadgeVariant(run.phase)}
                        className="text-xs"
                      >
                        {run.phase}
                      </Badge>
                    )}
                  </div>
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
      )}
    </div>
  );
}
