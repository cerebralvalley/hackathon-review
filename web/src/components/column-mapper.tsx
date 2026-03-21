"use client";

import { useEffect, useState } from "react";
import { hackathons as api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const REQUIRED_FIELDS = [
  { key: "team_name", label: "Team Name" },
  { key: "github_url", label: "GitHub URL" },
  { key: "video_url", label: "Video URL" },
] as const;

const OPTIONAL_FIELDS = [
  { key: "project_name", label: "Project Name" },
  { key: "description", label: "Description" },
  { key: "team_members", label: "Team Members" },
  { key: "submitted_at", label: "Submitted At" },
] as const;

const ALL_FIELDS = [...REQUIRED_FIELDS, ...OPTIONAL_FIELDS];

const KNOWN_ALIASES: Record<string, string[]> = {
  team_name: ["team name", "team", "teamname"],
  github_url: ["public github repository", "github", "github url", "repo", "repository"],
  video_url: ["demo video", "video", "video url", "demo", "demo url"],
  project_name: ["project name", "project", "submission name"],
  description: ["project description", "description", "summary", "about"],
  team_members: ["team members", "members", "participants"],
  submitted_at: ["time submitted", "submitted", "timestamp", "submission time"],
};

function autoMap(headers: string[]): Record<string, string> {
  const mapping: Record<string, string> = {};
  const lowerHeaders = headers.map((h) => h.toLowerCase().trim());

  for (const field of ALL_FIELDS) {
    const aliases = KNOWN_ALIASES[field.key] || [];
    const idx = lowerHeaders.findIndex((h) => aliases.includes(h));
    if (idx !== -1) {
      mapping[field.key] = headers[idx];
    }
  }
  return mapping;
}

interface Props {
  hackathonId: string;
  currentConfig: Record<string, unknown>;
  onSave: (config: Record<string, unknown>) => void;
  onSkip: () => void;
}

export function ColumnMapper({ hackathonId, currentConfig, onSave, onSkip }: Props) {
  const [headers, setHeaders] = useState<string[]>([]);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.csvHeaders(hackathonId).then((res) => {
      setHeaders(res.headers);
      setMapping(autoMap(res.headers));
      setLoading(false);
    });
  }, [hackathonId]);

  function handleSave() {
    const columns: Record<string, unknown> = {};
    const extra: string[] = [];
    const mappedValues = new Set(Object.values(mapping));

    for (const field of ALL_FIELDS) {
      if (mapping[field.key]) {
        columns[field.key] = mapping[field.key];
      }
    }

    for (const h of headers) {
      if (!mappedValues.has(h)) {
        extra.push(h);
      }
    }
    if (extra.length > 0) {
      columns.extra = extra;
    }

    onSave({ ...currentConfig, columns });
  }

  if (loading) {
    return <p className="text-muted-foreground text-sm">Reading CSV headers...</p>;
  }

  const selectClass =
    "w-full rounded-md border border-input bg-background px-3 py-2 text-sm";

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Map CSV Columns</CardTitle>
        <CardDescription>
          We auto-detected some columns. Verify or adjust the mapping.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {ALL_FIELDS.map((field) => {
          const isRequired = REQUIRED_FIELDS.some((f) => f.key === field.key);
          return (
            <div key={field.key} className="grid grid-cols-2 gap-3 items-center">
              <Label className="text-sm">
                {field.label}
                {isRequired && <span className="text-destructive ml-1">*</span>}
              </Label>
              <select
                value={mapping[field.key] || ""}
                onChange={(e) =>
                  setMapping((prev) => ({ ...prev, [field.key]: e.target.value }))
                }
                className={selectClass}
              >
                <option value="">-- not mapped --</option>
                {headers.map((h) => (
                  <option key={h} value={h}>
                    {h}
                  </option>
                ))}
              </select>
            </div>
          );
        })}
        <div className="flex gap-2 pt-2">
          <Button
            onClick={handleSave}
            disabled={REQUIRED_FIELDS.some((f) => !mapping[f.key])}
            size="sm"
          >
            Save Mapping
          </Button>
          <Button variant="outline" size="sm" onClick={onSkip}>
            Skip
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
