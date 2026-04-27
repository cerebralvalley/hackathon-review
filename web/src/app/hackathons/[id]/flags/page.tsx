"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Undo2, X } from "lucide-react";
import { results as resultsApi, runs as runsApi } from "@/lib/api";
import type { Flag, PipelineRun } from "@/lib/types";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";

function severityVariant(severity: string) {
  switch (severity) {
    case "error":
      return "destructive" as const;
    case "warning":
      return "secondary" as const;
    default:
      return "outline" as const;
  }
}

const flagKey = (f: Flag) => `${f.team_number}:${f.flag_type}`;

export default function HackathonFlagsPage() {
  const { id } = useParams<{ id: string }>();
  const [run, setRun] = useState<PipelineRun | null>(null);
  const [flags, setFlags] = useState<Flag[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<Set<string>>(new Set());
  const [showDismissed, setShowDismissed] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError(null);
    runsApi
      .list(id)
      .then((runs) => {
        const latest =
          runs.find((r) => r.status === "completed") ??
          runs.find((r) => r.status === "interrupted") ??
          runs[0];
        if (!latest) {
          setRun(null);
          setFlags([]);
          return;
        }
        setRun(latest);
        return resultsApi.flags(latest.id).then(setFlags);
      })
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false));
  }, [id]);

  async function toggle(f: Flag, dismiss: boolean) {
    if (!run) return;
    const k = flagKey(f);
    setPending((p) => new Set([...p, k]));
    try {
      if (dismiss) {
        await resultsApi.dismissFlag(run.id, f.team_number, f.flag_type);
      } else {
        await resultsApi.undismissFlag(run.id, f.team_number, f.flag_type);
      }
      setFlags((prev) =>
        prev.map((x) =>
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

  const visibleFlags = useMemo(
    () => (showDismissed ? flags : flags.filter((f) => !f.dismissed)),
    [flags, showDismissed]
  );
  const grouped = useMemo(() => {
    return visibleFlags.reduce<Record<string, Flag[]>>((acc, f) => {
      (acc[f.flag_type] ??= []).push(f);
      return acc;
    }, {});
  }, [visibleFlags]);

  const activeCount = flags.filter((f) => !f.dismissed).length;
  const dismissedCount = flags.length - activeCount;

  return (
    <div className="space-y-6">
      <Link
        href={`/hackathons/${id}`}
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" />
        Back to hackathon
      </Link>

      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Flags</h1>
          <p className="text-muted-foreground text-sm">
            {run ? (
              <>
                {activeCount} active issue{activeCount !== 1 ? "s" : ""}
                {dismissedCount > 0 && <> · {dismissedCount} dismissed</>}
                {" · "}from run{" "}
                <span className="font-mono">{run.id.slice(0, 8)}</span>
                {run.completed_at && (
                  <> · {new Date(run.completed_at).toLocaleString()}</>
                )}
              </>
            ) : (
              "No completed runs yet"
            )}
          </p>
        </div>
        {dismissedCount > 0 && (
          <label className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer">
            <input
              type="checkbox"
              checked={showDismissed}
              onChange={(e) => setShowDismissed(e.target.checked)}
              className="rounded"
            />
            Show dismissed
          </label>
        )}
      </div>

      {loading ? (
        <p className="text-muted-foreground">Loading...</p>
      ) : error ? (
        <p className="text-destructive">{error}</p>
      ) : !run ? (
        <p className="text-muted-foreground">
          Run the pipeline first to see flags.
        </p>
      ) : Object.keys(grouped).length === 0 ? (
        <p className="text-muted-foreground">
          {flags.length === 0
            ? "No flags raised. All clear."
            : "All flags are dismissed. Toggle Show dismissed to view them."}
        </p>
      ) : (
        Object.entries(grouped).map(([type, items]) => (
          <div key={type} className="space-y-2">
            <h2 className="text-base font-semibold flex items-center gap-2">
              {type.replace(/_/g, " ")}
              <Badge
                variant={severityVariant(items[0].severity)}
                className="text-xs"
              >
                {items.length}
              </Badge>
            </h2>
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-12">#</TableHead>
                    <TableHead>Team</TableHead>
                    <TableHead>Project</TableHead>
                    <TableHead>Details</TableHead>
                    <TableHead className="w-20">Severity</TableHead>
                    <TableHead className="w-28 text-right" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((f) => {
                    const k = flagKey(f);
                    const busy = pending.has(k);
                    return (
                      <TableRow
                        key={k}
                        className={f.dismissed ? "opacity-60" : ""}
                      >
                        <TableCell>{f.team_number}</TableCell>
                        <TableCell className="max-w-[150px] truncate">
                          {f.team_name}
                        </TableCell>
                        <TableCell
                          className={`max-w-[150px] truncate ${
                            f.dismissed ? "line-through" : ""
                          }`}
                        >
                          {f.project_name}
                        </TableCell>
                        <TableCell className="text-sm">
                          {f.description}
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant={severityVariant(f.severity)}
                            className="text-xs"
                          >
                            {f.severity}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right">
                          <button
                            type="button"
                            onClick={() => toggle(f, !f.dismissed)}
                            disabled={busy}
                            className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-muted-foreground hover:text-foreground hover:bg-muted disabled:opacity-50"
                          >
                            {f.dismissed ? (
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
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          </div>
        ))
      )}
    </div>
  );
}
