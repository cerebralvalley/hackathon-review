"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { hackathons as hackathonsApi, parseRules } from "@/lib/api";
import { HackathonForm, type HackathonFormData } from "@/components/hackathon-form";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

export default function NewHackathonPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"paste" | "manual">("paste");
  const [rulesText, setRulesText] = useState("");
  const [parsing, setParsing] = useState(false);
  const [parseError, setParseError] = useState("");
  const [parsedConfig, setParsedConfig] = useState<{
    name: string;
    config: Record<string, unknown>;
  } | null>(null);

  async function handleParseRules() {
    setParsing(true);
    setParseError("");
    try {
      const result = await parseRules(rulesText) as Record<string, Record<string, unknown> | string>;
      const hackathonObj = result.hackathon as Record<string, unknown> | undefined;
      const name = String(result.name || hackathonObj?.name || "My Hackathon");
      const config: Record<string, unknown> = {};
      if (result.hackathon) config.hackathon = result.hackathon;
      if (result.scoring) config.scoring = result.scoring;
      if (result.code_review) config.code_review = result.code_review;
      if (result.video_analysis) config.video_analysis = result.video_analysis;
      if (result.static_analysis) config.static_analysis = result.static_analysis;
      setParsedConfig({ name, config });
    } catch (err) {
      setParseError(String(err));
    } finally {
      setParsing(false);
    }
  }

  // After parsing, show the form pre-filled
  if (parsedConfig) {
    return (
      <div>
        <div className="mb-6">
          <h1 className="text-2xl font-bold tracking-tight">New Hackathon</h1>
          <p className="text-muted-foreground">
            Review the auto-detected settings, then create.
          </p>
        </div>
        <HackathonForm
          initial={parsedConfig}
          submitLabel="Create Hackathon"
          onSubmit={async (data: HackathonFormData) => {
            const h = await hackathonsApi.create(data.name, data.config);
            router.push(`/hackathons/${h.id}`);
          }}
          onCancel={() => setParsedConfig(null)}
        />
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">New Hackathon</h1>
        <p className="text-muted-foreground">
          Paste your hackathon rules or configure manually
        </p>
      </div>

      <div className="flex gap-2">
        <Button
          variant={mode === "paste" ? "default" : "outline"}
          size="sm"
          onClick={() => setMode("paste")}
        >
          Paste Rules
        </Button>
        <Button
          variant={mode === "manual" ? "default" : "outline"}
          size="sm"
          onClick={() => setMode("manual")}
        >
          Manual Setup
        </Button>
      </div>

      {mode === "paste" ? (
        <Card>
          <CardHeader>
            <CardTitle>Hackathon Rules</CardTitle>
            <CardDescription>
              Paste the rules, judging criteria, or details page from your
              hackathon. We&apos;ll extract the name, dates, scoring criteria, and
              review context automatically.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Textarea
              rows={12}
              value={rulesText}
              onChange={(e) => setRulesText(e.target.value)}
              placeholder={"Paste your hackathon rules here...\n\nFor example:\n- Hackathon name and dates\n- Judging criteria and weights\n- What participants are building\n- Submission requirements"}
              className="text-sm"
            />
            {parseError && (
              <p className="text-sm text-destructive">{parseError}</p>
            )}
            <Button
              onClick={handleParseRules}
              disabled={parsing || !rulesText.trim()}
            >
              {parsing ? "Analyzing rules..." : "Auto-Configure"}
            </Button>
          </CardContent>
        </Card>
      ) : (
        <>
          <Separator />
          <HackathonForm
            submitLabel="Create Hackathon"
            onSubmit={async (data: HackathonFormData) => {
              const h = await hackathonsApi.create(data.name, data.config);
              router.push(`/hackathons/${h.id}`);
            }}
            onCancel={() => router.push("/")}
          />
        </>
      )}
    </div>
  );
}
