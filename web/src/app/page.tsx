"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { hackathons as api } from "@/lib/api";
import type { HackathonListItem } from "@/lib/types";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

function statusVariant(status: string | null) {
  switch (status) {
    case "completed":
      return "default" as const;
    case "running":
      return "secondary" as const;
    case "failed":
      return "destructive" as const;
    default:
      return "outline" as const;
  }
}

export default function DashboardPage() {
  const [items, setItems] = useState<HackathonListItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.list().then(setItems).finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground">
          Your hackathon review pipelines
        </p>
      </div>

      {loading ? (
        <p className="text-muted-foreground">Loading...</p>
      ) : items.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <p className="text-muted-foreground mb-4">
              No hackathons yet. Create one to get started.
            </p>
            <Link
              href="/hackathons/new"
              className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
            >
              Create your first hackathon
            </Link>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((h) => (
            <Link key={h.id} href={`/hackathons/${h.id}`}>
              <Card className="hover:border-foreground/20 transition-colors cursor-pointer h-full">
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">{h.name}</CardTitle>
                  <CardDescription>
                    Created{" "}
                    {new Date(h.created_at).toLocaleDateString(undefined, {
                      month: "short",
                      day: "numeric",
                      year: "numeric",
                    })}
                  </CardDescription>
                </CardHeader>
                <CardContent className="flex flex-wrap items-center gap-2">
                  {h.csv_filename ? (
                    <Badge
                      variant="outline"
                      className="max-w-full shrink min-w-0"
                      title={h.csv_filename}
                    >
                      <span className="truncate">{h.csv_filename}</span>
                    </Badge>
                  ) : (
                    <Badge variant="outline">No CSV</Badge>
                  )}
                  {h.latest_run_status && (
                    <Badge variant={statusVariant(h.latest_run_status)}>
                      {h.latest_run_status}
                    </Badge>
                  )}
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
