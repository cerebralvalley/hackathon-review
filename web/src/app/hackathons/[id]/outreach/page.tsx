"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Copy, Mail } from "lucide-react";
import {
  hackathons as hackathonsApi,
  results as resultsApi,
  runs as runsApi,
} from "@/lib/api";
import type { Hackathon, OutreachTeam, PipelineRun } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

function buildMailto(team: OutreachTeam, hackathonName: string) {
  const emails = team.members
    .map((m) => m.email)
    .filter(Boolean)
    .join(",");
  if (!emails) return null;

  const subject = `[${hackathonName || "Hackathon"}] Issue with your submission – ${
    team.project_name || team.team_name
  }`;

  const issuesBlock = team.issues
    .map((i) => `• ${i.label}: ${i.description}`)
    .join("\n");

  const body = `Hi ${team.team_name},

We hit an issue while reviewing your submission to ${
    hackathonName || "the hackathon"
  }:

${issuesBlock}

The URLs we have on file:
• GitHub: ${team.github_url || "(none)"}
• Video:  ${team.video_url || "(none)"}

Could you take a look and reply with an updated link or fix? We want to
make sure your project gets reviewed.

Thanks!`;

  return `mailto:${emails}?subject=${encodeURIComponent(
    subject
  )}&body=${encodeURIComponent(body)}`;
}

function copyToClipboard(text: string) {
  navigator.clipboard?.writeText(text).catch(() => {});
}

function severityForType(t: string) {
  if (t.startsWith("invalid_")) return "destructive" as const;
  if (t.endsWith("_failed")) return "destructive" as const;
  return "secondary" as const;
}

export default function OutreachPage() {
  const { id } = useParams<{ id: string }>();
  const [hackathon, setHackathon] = useState<Hackathon | null>(null);
  const [run, setRun] = useState<PipelineRun | null>(null);
  const [teams, setTeams] = useState<OutreachTeam[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<number | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    Promise.all([hackathonsApi.get(id), runsApi.list(id)])
      .then(async ([h, runs]) => {
        setHackathon(h);
        const latest = runs.find((r) => r.status === "completed")
          ?? runs.find((r) => r.status === "interrupted")
          ?? runs[0];
        if (!latest) {
          setRun(null);
          setTeams([]);
          return;
        }
        setRun(latest);
        const data = await resultsApi.outreach(latest.id);
        setTeams(data);
      })
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false));
  }, [id]);

  const issueCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const t of teams) {
      for (const i of t.issues) {
        counts[i.type] = (counts[i.type] || 0) + 1;
      }
    }
    return counts;
  }, [teams]);

  const allEmails = useMemo(
    () =>
      teams
        .flatMap((t) => t.members.map((m) => m.email))
        .filter(Boolean),
    [teams]
  );

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
          <h1 className="text-2xl font-bold tracking-tight">
            Teams needing outreach
          </h1>
          <p className="text-muted-foreground text-sm">
            {run ? (
              <>
                {teams.length} team{teams.length === 1 ? "" : "s"} from run{" "}
                <span className="font-mono">{run.id.slice(0, 8)}</span>
                {run.status !== "completed" && (
                  <> · run {run.status}</>
                )}
              </>
            ) : (
              "No run yet"
            )}
          </p>
        </div>
        {allEmails.length > 0 && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              copyToClipboard(allEmails.join(", "));
              setCopied(-1);
              setTimeout(() => setCopied(null), 1500);
            }}
            title="Copy a comma-separated list of every email below"
          >
            <Copy className="size-3.5 mr-1.5" />
            {copied === -1 ? "Copied!" : `Copy all ${allEmails.length} emails`}
          </Button>
        )}
      </div>

      {Object.keys(issueCounts).length > 0 && (
        <div className="flex flex-wrap gap-2 text-xs">
          {Object.entries(issueCounts).map(([type, n]) => (
            <Badge key={type} variant="outline">
              {type.replace(/_/g, " ")}: {n}
            </Badge>
          ))}
        </div>
      )}

      {loading ? (
        <p className="text-muted-foreground">Loading...</p>
      ) : error ? (
        <p className="text-destructive">{error}</p>
      ) : teams.length === 0 ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            No teams currently need outreach. Every submission's repo and video
            were processed successfully.
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {teams.map((team, idx) => {
            const mailto = buildMailto(team, hackathon?.name ?? "");
            const emails = team.members.map((m) => m.email).filter(Boolean);
            return (
              <Card key={team.team_number}>
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <CardTitle className="text-base">
                        <span className="font-mono text-muted-foreground mr-2">
                          #{team.team_number}
                        </span>
                        {team.team_name}
                      </CardTitle>
                      <CardDescription className="mt-0.5">
                        {team.project_name || "(no project name)"}
                      </CardDescription>
                    </div>
                    <div className="flex gap-2 shrink-0">
                      {mailto && (
                        <a
                          href={mailto}
                          className="inline-flex items-center gap-1.5 rounded-md border bg-background px-2.5 py-1 text-xs font-medium hover:bg-muted transition-colors"
                        >
                          <Mail className="size-3.5" />
                          Email team
                        </a>
                      )}
                      {emails.length > 0 && (
                        <button
                          type="button"
                          onClick={() => {
                            copyToClipboard(emails.join(", "));
                            setCopied(idx);
                            setTimeout(() => setCopied(null), 1500);
                          }}
                          className="inline-flex items-center gap-1.5 rounded-md border bg-background px-2.5 py-1 text-xs font-medium hover:bg-muted transition-colors"
                        >
                          <Copy className="size-3.5" />
                          {copied === idx ? "Copied!" : "Copy emails"}
                        </button>
                      )}
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="space-y-3 text-sm">
                  <div className="space-y-1.5">
                    {team.issues.map((issue) => (
                      <div
                        key={issue.type}
                        className="flex items-start gap-2"
                      >
                        <Badge
                          variant={severityForType(issue.type)}
                          className="mt-0.5 shrink-0"
                        >
                          {issue.label}
                        </Badge>
                        <span className="text-xs text-muted-foreground">
                          {issue.description}
                        </span>
                      </div>
                    ))}
                  </div>

                  <div className="grid sm:grid-cols-2 gap-x-4 gap-y-1 text-xs">
                    <div>
                      <div className="text-muted-foreground uppercase tracking-wide text-[10px] mb-0.5">
                        Members
                      </div>
                      {team.members.length === 0 ? (
                        <span className="text-muted-foreground">
                          (no members listed)
                        </span>
                      ) : (
                        <ul className="space-y-0.5">
                          {team.members.map((m, i) => (
                            <li key={i} className="truncate">
                              <span>{m.name}</span>
                              {m.email && (
                                <span className="text-muted-foreground">
                                  {" "}
                                  &lt;{m.email}&gt;
                                </span>
                              )}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                    <div className="space-y-0.5">
                      <div className="text-muted-foreground uppercase tracking-wide text-[10px] mb-0.5">
                        Submitted URLs
                      </div>
                      {team.github_url && (
                        <div className="truncate">
                          <span className="text-muted-foreground">GitHub: </span>
                          <a
                            href={team.github_url}
                            target="_blank"
                            rel="noreferrer"
                            className="hover:underline"
                          >
                            {team.github_url}
                          </a>
                        </div>
                      )}
                      {team.video_url && (
                        <div className="truncate">
                          <span className="text-muted-foreground">Video: </span>
                          <a
                            href={team.video_url}
                            target="_blank"
                            rel="noreferrer"
                            className="hover:underline"
                          >
                            {team.video_url}
                          </a>
                        </div>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
