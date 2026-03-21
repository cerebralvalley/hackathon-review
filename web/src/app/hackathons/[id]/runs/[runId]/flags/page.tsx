"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { results as api } from "@/lib/api";
import type { Flag } from "@/lib/types";
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

export default function FlagsPage() {
  const { id, runId } = useParams<{ id: string; runId: string }>();
  const [flags, setFlags] = useState<Flag[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.flags(runId).then(setFlags).finally(() => setLoading(false));
  }, [runId]);

  const grouped = flags.reduce<Record<string, Flag[]>>((acc, f) => {
    (acc[f.flag_type] ??= []).push(f);
    return acc;
  }, {});

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Flags</h1>
          <p className="text-muted-foreground text-sm">
            {flags.length} issue{flags.length !== 1 ? "s" : ""} found
          </p>
        </div>
        <Link
          href={`/hackathons/${id}`}
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          Back to hackathon
        </Link>
      </div>

      {loading ? (
        <p className="text-muted-foreground">Loading...</p>
      ) : flags.length === 0 ? (
        <p className="text-muted-foreground">No flags raised. All clear.</p>
      ) : (
        Object.entries(grouped).map(([type, items]) => (
          <div key={type} className="space-y-2">
            <h2 className="text-base font-semibold flex items-center gap-2">
              {type.replace(/_/g, " ")}
              <Badge variant={severityVariant(items[0].severity)} className="text-xs">
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
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((f, i) => (
                    <TableRow key={`${f.team_number}-${i}`}>
                      <TableCell>{f.team_number}</TableCell>
                      <TableCell className="max-w-[150px] truncate">
                        {f.team_name}
                      </TableCell>
                      <TableCell className="max-w-[150px] truncate">
                        {f.project_name}
                      </TableCell>
                      <TableCell className="text-sm">
                        {f.description}
                      </TableCell>
                      <TableCell>
                        <Badge variant={severityVariant(f.severity)} className="text-xs">
                          {f.severity}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>
        ))
      )}
    </div>
  );
}
