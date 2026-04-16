export default function AboutPage() {
  return (
    <div className="max-w-3xl space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">
          About Hackathon Reviewer
        </h1>
        <p className="text-muted-foreground mt-1">
          Automated analysis pipeline for hackathon submissions
        </p>
      </div>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">What it does</h2>
        <p className="text-sm text-muted-foreground leading-relaxed">
          Hackathon Reviewer takes a CSV of hackathon submissions and runs an
          8-stage automated pipeline that clones repositories, downloads demo
          videos, performs static code analysis, runs LLM-powered code reviews,
          analyzes videos with AI, scores projects, and generates detailed
          reports for every team.
        </p>
      </section>

      <section className="space-y-4">
        <h2 className="text-lg font-semibold">Pipeline stages</h2>
        <div className="grid gap-3">
          {[
            {
              name: "1. Parse CSV",
              desc: "Reads the submissions CSV and extracts team names, GitHub URLs, video links, and metadata. Auto-detects column mappings from common header aliases.",
            },
            {
              name: "2. Clone Repos",
              desc: "Clones each team's GitHub repository, scans file structure, counts lines of code by language, and analyzes git commit history.",
            },
            {
              name: "3. Download Videos",
              desc: "Downloads demo videos from YouTube, Loom, Google Drive, and other platforms using yt-dlp. Supports parallel downloads with auto-retry.",
            },
            {
              name: "4. Static Analysis",
              desc: "Scans codebases for AI integration patterns, API usage, framework detection, and calculates an integration depth score.",
            },
            {
              name: "5. Code Review",
              desc: "Sends key source files to an LLM (Claude or Gemini) for a structured code review covering architecture, quality, and completeness.",
            },
            {
              name: "6. Video Analysis",
              desc: "Uses Gemini's native video understanding to analyze demo videos — classifies demo quality, checks relevance to the project, and summarizes what's shown.",
            },
            {
              name: "7. Scoring",
              desc: "Combines signals from all prior stages into weighted scores per configurable criteria, producing a ranked leaderboard.",
            },
            {
              name: "8. Reports",
              desc: "Generates per-project markdown reports, a leaderboard CSV, a flags report for issues, and an overall pipeline summary.",
            },
          ].map((stage) => (
            <div
              key={stage.name}
              className="rounded-lg border p-3 space-y-1"
            >
              <h3 className="text-sm font-medium">{stage.name}</h3>
              <p className="text-xs text-muted-foreground leading-relaxed">
                {stage.desc}
              </p>
            </div>
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Key features</h2>
        <ul className="space-y-2 text-sm text-muted-foreground">
          <li className="flex gap-2">
            <span className="text-foreground font-medium shrink-0">Resumable</span>
            — If the server restarts or a run fails, you can resume from the last completed stage without re-doing work.
          </li>
          <li className="flex gap-2">
            <span className="text-foreground font-medium shrink-0">Live progress</span>
            — Each stage streams real-time progress bars and surfaces failures as they happen.
          </li>
          <li className="flex gap-2">
            <span className="text-foreground font-medium shrink-0">Retry</span>
            — Failed items (clone, video download, code review, video analysis) can be retried individually or in bulk from the UI.
          </li>
          <li className="flex gap-2">
            <span className="text-foreground font-medium shrink-0">Auto-retry</span>
            — Clone and video download automatically retry up to 2 extra times with backoff before marking as failed.
          </li>
          <li className="flex gap-2">
            <span className="text-foreground font-medium shrink-0">Configurable</span>
            — LLM providers, scoring criteria, concurrency limits, and hackathon-specific settings are all editable per hackathon.
          </li>
        </ul>
      </section>
    </div>
  );
}
