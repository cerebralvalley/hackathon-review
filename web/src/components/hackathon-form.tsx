"use client";

import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { staticAnalysis as staticAnalysisApi } from "@/lib/api";
import type { PatternBundle, PatternPreset } from "@/lib/types";

// Aliases for legacy preset names so existing configs pre-fill correctly.
const PRESET_ALIASES: Record<string, string> = {
  ai_hackathon: "llm-advanced",
  openenv: "rl-training",
};

export interface HackathonFormData {
  name: string;
  config: Record<string, unknown>;
}

interface Props {
  initial?: { name: string; config: Record<string, unknown> };
  submitLabel: string;
  onSubmit: (data: HackathonFormData) => Promise<void>;
  onCancel: () => void;
}

function configVal(config: Record<string, unknown>, ...path: string[]): unknown {
  let cur: unknown = config;
  for (const k of path) {
    if (cur == null || typeof cur !== "object") return undefined;
    cur = (cur as Record<string, unknown>)[k];
  }
  return cur;
}

function criteriaToText(config: Record<string, unknown>): string {
  const criteria = configVal(config, "scoring", "criteria") as
    | Record<string, { weight: number; description: string }>
    | undefined;
  if (!criteria || Object.keys(criteria).length === 0) {
    return `impact: 0.25 | Real-world potential, who benefits
ai_use: 0.25 | Creativity and depth of AI/LLM integration
depth: 0.20 | Engineering quality, iteration, craft
demo: 0.30 | Demo quality, working product, presentation`;
  }
  return Object.entries(criteria)
    .map(([k, v]) => `${k}: ${v.weight} | ${v.description}`)
    .join("\n");
}

export function HackathonForm({ initial, submitLabel, onSubmit, onCancel }: Props) {
  const cfg = initial?.config || {};
  const [saving, setSaving] = useState(false);
  const [name, setName] = useState(initial?.name || "");
  const [deadlineUtc, setDeadlineUtc] = useState(
    String(configVal(cfg, "hackathon", "deadline_utc") || "")
  );
  const [startDate, setStartDate] = useState(
    String(configVal(cfg, "hackathon", "start_date") || "")
  );
  const [endDate, setEndDate] = useState(
    String(configVal(cfg, "hackathon", "end_date") || "")
  );
  const [verifyGitPeriod, setVerifyGitPeriod] = useState(
    Boolean(configVal(cfg, "hackathon", "verify_git_period"))
  );
  const [codeProvider, setCodeProvider] = useState(
    String(configVal(cfg, "code_review", "provider") || "anthropic")
  );
  const [codeModel, setCodeModel] = useState(
    String(configVal(cfg, "code_review", "model") || "claude-opus-4-6")
  );
  const [promptPreamble, setPromptPreamble] = useState(
    String(configVal(cfg, "code_review", "prompt_preamble") || "")
  );
  const [videoProvider, setVideoProvider] = useState(
    String(configVal(cfg, "video_analysis", "provider") || "gemini")
  );
  const [videoModel, setVideoModel] = useState(
    String(configVal(cfg, "video_analysis", "model") || "gemini-3-flash-preview")
  );
  const initialBundles = useMemo<string[]>(() => {
    const explicit = configVal(cfg, "static_analysis", "pattern_bundles");
    if (Array.isArray(explicit) && explicit.every((x) => typeof x === "string")) {
      return explicit as string[];
    }
    // Fall back to preset; bundle list is filled in once the catalog loads.
    return [];
  }, [cfg]);
  const initialPresetId = useMemo(() => {
    const raw = String(configVal(cfg, "static_analysis", "pattern_preset") || "");
    return PRESET_ALIASES[raw] || raw || "general";
  }, [cfg]);
  const [selectedBundles, setSelectedBundles] = useState<Set<string>>(
    () => new Set(initialBundles)
  );
  const [bundles, setBundles] = useState<PatternBundle[]>([]);
  const [presets, setPresets] = useState<PatternPreset[]>([]);
  const [bundlesLoading, setBundlesLoading] = useState(true);
  const [criteriaText, setCriteriaText] = useState(criteriaToText(cfg));

  useEffect(() => {
    let cancelled = false;
    staticAnalysisApi
      .bundles()
      .then(({ bundles, presets }) => {
        if (cancelled) return;
        setBundles(bundles);
        setPresets(presets);
        // If we don't yet have a bundle selection, hydrate from initial preset.
        if (selectedBundles.size === 0) {
          const preset = presets.find((p) => p.id === initialPresetId)
            ?? presets.find((p) => p.id === "general");
          if (preset) setSelectedBundles(new Set(preset.bundles));
        }
      })
      .finally(() => {
        if (!cancelled) setBundlesLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function toggleBundle(id: string) {
    setSelectedBundles((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  function applyPreset(preset: PatternPreset) {
    setSelectedBundles(new Set(preset.bundles));
  }

  const matchingPresetId = useMemo(() => {
    for (const p of presets) {
      if (
        p.bundles.length === selectedBundles.size &&
        p.bundles.every((b) => selectedBundles.has(b))
      ) {
        return p.id;
      }
    }
    return null;
  }, [presets, selectedBundles]);

  function parseCriteria() {
    const criteria: Record<string, { weight: number; description: string }> = {};
    for (const line of criteriaText.split("\n")) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      const [keyWeight, ...descParts] = trimmed.split("|");
      const [key, weightStr] = keyWeight.split(":").map((s) => s.trim());
      if (key && weightStr) {
        criteria[key] = {
          weight: parseFloat(weightStr),
          description: descParts.join("|").trim(),
        };
      }
    }
    return criteria;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);

    const config: Record<string, unknown> = {
      code_review: {
        provider: codeProvider,
        model: codeModel,
        ...(promptPreamble ? { prompt_preamble: promptPreamble } : {}),
      },
      video_analysis: { provider: videoProvider, model: videoModel },
      static_analysis: {
        pattern_bundles: Array.from(selectedBundles),
      },
    };

    if (deadlineUtc || startDate || endDate) {
      config.hackathon = {
        name,
        ...(deadlineUtc ? { deadline_utc: deadlineUtc } : {}),
        ...(startDate ? { start_date: startDate } : {}),
        ...(endDate ? { end_date: endDate } : {}),
        verify_git_period: verifyGitPeriod,
      };
    }

    const criteria = parseCriteria();
    if (Object.keys(criteria).length > 0) {
      config.scoring = { criteria };
    }

    try {
      await onSubmit({ name, config });
    } catch {
      setSaving(false);
    }
  }

  const selectClass =
    "w-full rounded-md border border-input bg-background px-3 py-2 text-sm";

  return (
    <form onSubmit={handleSubmit} className="space-y-6 max-w-2xl">
      <Card>
        <CardHeader>
          <CardTitle>Basics</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="name">Hackathon Name</Label>
            <Input
              id="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="My Hackathon 2026"
              required
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Dates & Deadlines</CardTitle>
          <CardDescription>
            Optional. Used for lateness detection and git period verification.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="start">Start Date</Label>
              <Input
                id="start"
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="end">End Date</Label>
              <Input
                id="end"
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
              />
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="deadline">Submission Deadline (UTC)</Label>
            <Input
              id="deadline"
              type="datetime-local"
              value={deadlineUtc}
              onChange={(e) => setDeadlineUtc(e.target.value)}
            />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={verifyGitPeriod}
              onChange={(e) => setVerifyGitPeriod(e.target.checked)}
              className="rounded"
            />
            Flag repos with commits outside the hackathon window
          </label>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Scoring Criteria</CardTitle>
          <CardDescription>
            One per line: key: weight | description. Weights should sum to 1.0.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Textarea
            rows={6}
            value={criteriaText}
            onChange={(e) => setCriteriaText(e.target.value)}
            className="font-mono text-sm"
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Code Review</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Provider</Label>
              <select
                value={codeProvider}
                onChange={(e) => setCodeProvider(e.target.value)}
                className={selectClass}
              >
                <option value="anthropic">Anthropic</option>
                <option value="gemini">Gemini</option>
              </select>
            </div>
            <div className="space-y-2">
              <Label>Model</Label>
              <Input
                value={codeModel}
                onChange={(e) => setCodeModel(e.target.value)}
              />
            </div>
          </div>
          <div className="space-y-2">
            <Label>Prompt Preamble (optional)</Label>
            <Textarea
              rows={3}
              value={promptPreamble}
              onChange={(e) => setPromptPreamble(e.target.value)}
              placeholder="Projects must build RL environments using OpenEnv..."
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Video Analysis</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Provider</Label>
              <select
                value={videoProvider}
                onChange={(e) => setVideoProvider(e.target.value)}
                className={selectClass}
              >
                <option value="gemini">Gemini</option>
              </select>
            </div>
            <div className="space-y-2">
              <Label>Model</Label>
              <Input
                value={videoModel}
                onChange={(e) => setVideoModel(e.target.value)}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Static Analysis</CardTitle>
          <CardDescription>
            What to look for in submitted code. Pick a starter combo or check
            individual bundles.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          {bundlesLoading ? (
            <p className="text-sm text-muted-foreground">Loading patterns…</p>
          ) : (
            <>
              <div className="space-y-2">
                <Label className="text-xs uppercase tracking-wide text-muted-foreground">
                  Starter combo
                </Label>
                <div className="flex flex-wrap gap-2">
                  {presets.map((p) => {
                    const active = matchingPresetId === p.id;
                    return (
                      <Button
                        key={p.id}
                        type="button"
                        size="sm"
                        variant={active ? "default" : "outline"}
                        onClick={() => applyPreset(p)}
                        title={p.description}
                      >
                        {p.label}
                      </Button>
                    );
                  })}
                </div>
                <p className="text-xs text-muted-foreground">
                  {matchingPresetId
                    ? presets.find((p) => p.id === matchingPresetId)?.description
                    : `Custom selection (${selectedBundles.size} bundle${
                        selectedBundles.size === 1 ? "" : "s"
                      })`}
                </p>
              </div>

              <div className="space-y-2">
                <Label className="text-xs uppercase tracking-wide text-muted-foreground">
                  Pattern bundles
                </Label>
                <div className="grid gap-2 sm:grid-cols-2">
                  {bundles.map((b) => {
                    const checked = selectedBundles.has(b.id);
                    return (
                      <label
                        key={b.id}
                        className={`flex gap-3 p-3 rounded-md border cursor-pointer transition-colors ${
                          checked
                            ? "border-foreground/30 bg-muted/40"
                            : "border-border hover:bg-muted/20"
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleBundle(b.id)}
                          className="mt-0.5 shrink-0"
                        />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-sm font-medium">
                              {b.label}
                            </span>
                            <span className="text-[10px] text-muted-foreground tabular-nums">
                              {b.pattern_count} pattern
                              {b.pattern_count === 1 ? "" : "s"}
                            </span>
                          </div>
                          <p className="text-xs text-muted-foreground mt-0.5">
                            {b.description}
                          </p>
                        </div>
                      </label>
                    );
                  })}
                </div>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <Separator />

      <div className="flex gap-3">
        <Button type="submit" disabled={saving || !name.trim()}>
          {saving ? "Saving..." : submitLabel}
        </Button>
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
