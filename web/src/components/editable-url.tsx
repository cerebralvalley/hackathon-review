"use client";

import { useEffect, useState } from "react";
import { Pencil, Save, X } from "lucide-react";
import { hackathons as hackathonsApi } from "@/lib/api";
import { Input } from "@/components/ui/input";

/**
 * Inline-editable URL field for an outreach team's GitHub or Video URL.
 *
 * On save: PATCHes the canonical CSV + every run's submissions.json,
 * purges stale clone/download artifacts, and re-classifies the new URL.
 * Calls `onSaved()` after a valid save so the parent can re-fetch the
 * outreach list (the team often disappears).
 */
export function EditableUrl({
  hackathonId,
  teamNumber,
  field,
  label,
  initialUrl,
  onSaved,
}: {
  hackathonId: string;
  teamNumber: number;
  field: "github_url" | "video_url";
  label: string;
  initialUrl: string;
  onSaved: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(initialUrl);
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<{
    valid: boolean;
    issues: string[];
  } | null>(null);

  useEffect(() => {
    setValue(initialUrl);
  }, [initialUrl]);

  async function save() {
    setSaving(true);
    setFeedback(null);
    try {
      const resp = await hackathonsApi.updateSubmission(
        hackathonId,
        teamNumber,
        { [field]: value },
      );
      const info = field === "github_url" ? resp.github : resp.video;
      if (info) {
        setFeedback({ valid: info.is_valid, issues: info.issues });
        if (info.is_valid) {
          setTimeout(() => {
            setEditing(false);
            onSaved();
          }, 600);
        }
      }
    } catch (err) {
      alert(String(err));
    } finally {
      setSaving(false);
    }
  }

  function cancel() {
    setValue(initialUrl);
    setFeedback(null);
    setEditing(false);
  }

  if (!editing) {
    return (
      <div className="flex items-start gap-1.5 text-xs">
        <span className="text-muted-foreground shrink-0">{label}:</span>
        <span className="min-w-0 flex-1 truncate">
          {initialUrl ? (
            <a
              href={initialUrl}
              target="_blank"
              rel="noreferrer"
              className="hover:underline"
              onClick={(e) => e.stopPropagation()}
            >
              {initialUrl}
            </a>
          ) : (
            <span className="text-muted-foreground italic">(none)</span>
          )}
        </span>
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            setEditing(true);
          }}
          className="shrink-0 text-muted-foreground hover:text-foreground"
          title={`Edit ${label} URL`}
        >
          <Pencil className="size-3" />
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-1" onClick={(e) => e.stopPropagation()}>
      <div className="flex items-center gap-1">
        <span className="text-muted-foreground shrink-0 text-xs">{label}:</span>
        <Input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !saving) save();
            if (e.key === "Escape") cancel();
          }}
          className="h-7 text-xs flex-1"
          autoFocus
          disabled={saving}
        />
        <button
          type="button"
          onClick={save}
          disabled={saving || value.trim() === initialUrl.trim()}
          className="shrink-0 text-muted-foreground hover:text-foreground disabled:opacity-40"
          title="Save"
        >
          <Save className="size-3" />
        </button>
        <button
          type="button"
          onClick={cancel}
          disabled={saving}
          className="shrink-0 text-muted-foreground hover:text-foreground"
          title="Cancel"
        >
          <X className="size-3" />
        </button>
      </div>
      {feedback && (
        <p
          className={`text-[11px] ${
            feedback.valid
              ? "text-green-600 dark:text-green-500"
              : "text-destructive"
          }`}
        >
          {feedback.valid
            ? "✓ Valid — refreshing…"
            : `✗ ${feedback.issues[0] || "Still invalid"}`}
        </p>
      )}
    </div>
  );
}
