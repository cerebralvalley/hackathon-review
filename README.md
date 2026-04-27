# hackathon-review

Open-source automated reviewer for hackathon submissions. Point it at a CSV of projects, and it clones every repo, downloads every demo video, runs static + LLM-based code review, scores against a configurable rubric, and produces per-project markdown reports plus a ranked leaderboard.

Built for hackathon organizers who want consistent, reviewable, machine-assisted first-pass judging — not to replace human judges, but to give them a structured starting point across hundreds of submissions.

## Two ways to run it

You can use the same pipeline in either of two modes — pick whichever fits your workflow.

| Mode | Best for | What you get |
|------|----------|--------------|
| **CLI** (`hackathon-reviewer`) | One-off runs, scripting, CI, single hackathon | A shell command + `config.yaml` + an `output/` directory of markdown reports |
| **Web app** (FastAPI + Next.js) | Running multiple hackathons, sharing progress with a team, paste-in rubric setup, live progress UI | A web UI where you create hackathons, upload CSVs, watch stage-by-stage progress, and browse leaderboards/reports in the browser |

Both modes share the exact same pipeline code in `src/hackathon_reviewer/`. The web app is just an HTTP wrapper with a database for multi-hackathon state.

## What the pipeline does

1. **Parses** your submission CSV (team name, GitHub URL, video URL, description, ...)
2. **Clones** all GitHub repositories and extracts metadata (LOC, languages, git history)
3. **Downloads** demo videos and uploads them to Gemini for native video understanding
4. **Static analysis** — configurable pattern scanner (frameworks, integration patterns, SDK usage)
5. **Code review** — LLM-powered narrative review per project, structured by your rubric
6. **Video analysis** — LLM-powered review of the demo video itself
7. **Scoring** against your configurable criteria (optional)
8. **Reports** — per-project markdown, ranked leaderboard, issues/flags report

Each stage is resumable: re-runs skip already-completed work.

## Repository layout

```
src/hackathon_reviewer/   # The pipeline (shared by CLI and web app)
  cli.py                  # Click CLI entry point
  stages/                 # parse, clone, video_download, static_analysis,
                          # code_review, video_analysis, scoring, reporting
  providers/              # LLM providers (Anthropic, Gemini)
  config.py               # YAML config loader

api/                      # FastAPI backend (web app mode)
  app/main.py             # API entry point
  app/routes/             # REST endpoints (hackathons, runs, results, parse_rules)
  app/services/pipeline.py # Bridges API to the shared pipeline stages

web/                      # Next.js frontend (web app mode)

config.example.yaml       # Example pipeline config — copy to config.yaml
.env.example              # Template for API keys
```

---

## Mode 1 — CLI

### Install

```bash
# Requires Python 3.11+ and ffmpeg
brew install ffmpeg

git clone https://github.com/<your-fork>/hackathon-review
cd hackathon-review
pip install -e .

# API keys
cp .env.example .env
# Edit .env:
#   ANTHROPIC_API_KEY=sk-ant-...   (for code review)
#   GEMINI_API_KEY=AIza...         (for video analysis, and optional code review)
```

`.env` is auto-loaded on every run — no need to `export` anything.

### Configure

```bash
cp config.example.yaml config.yaml
# Edit config.yaml — see "Configuration" below
```

### Run

```bash
# Full pipeline (recommended)
hackathon-reviewer run --csv submissions.csv --config config.yaml --output ./output

# Or run individual stages (re-runs skip completed work by default)
hackathon-reviewer parse    --csv FILE --output DIR [--config FILE]
hackathon-reviewer clone    --output DIR [--config FILE] [--resume]
hackathon-reviewer download --csv FILE --output DIR [--config FILE] [--resume]
hackathon-reviewer analyze  --output DIR [--config FILE] [--resume]
hackathon-reviewer report   --output DIR [--config FILE]
```

### Output

```
output/
  data/
    submissions.json        # Parsed submissions
    repo_metadata.json      # Clone + git analysis results
    static_analysis.json    # Pattern detection results
    video_analysis.json     # Video understanding results
    code_reviews.json       # LLM code reviews
    scores.json             # Scores (if scoring enabled)
  repos/                    # Cloned repositories
  videos/                   # Downloaded videos
  reports/
    summary.md              # Pipeline summary
    leaderboard.csv         # Ranked leaderboard (if scoring enabled)
    flags.md                # Issues (failed clones, bad videos, etc.)
    projects/               # Per-project deep reports
      001_project_name.md
      ...
```

---

## Mode 2 — Web app

The web app is a self-hosted FastAPI + Next.js stack on top of the same pipeline. It's designed for organizers running multiple hackathons or who want a UI for setup and progress tracking.

### What it adds over the CLI

- A web UI for creating/editing hackathons, uploading CSVs, kicking off runs
- Persistent SQLite database — multiple hackathons, multiple runs each
- Live stage-by-stage progress for in-flight runs
- Browse leaderboards, per-project reports, and flags in the browser
- Paste-in rules text → auto-converted to `config.yaml` via LLM (no YAML editing required)

### Install

You'll need both Python (for the API) and Node.js 20.17+ (for the frontend).

```bash
# 1. Backend
pip install -e .                 # installs the pipeline as a package
pip install -r api/requirements.txt
brew install ffmpeg

# 2. Frontend
cd web
npm install
cd ..

# 3. API keys (same as CLI)
cp .env.example .env
# fill in ANTHROPIC_API_KEY and/or GEMINI_API_KEY
```

### Run

In two terminals (or use a process manager):

```bash
# Terminal 1 — FastAPI backend on :8000
# --reload-dir restricts hot-reload to source code; without it, every
# file the pipeline writes (cloned repos, downloaded videos) would
# trigger a reload and deadlock the worker thread.
uvicorn api.app.main:app --reload --reload-dir api --reload-dir src --port 8000

# Terminal 2 — Next.js frontend on :3000
cd web
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

Then open **http://localhost:3000**.

### How data is stored

| What | Where |
|------|-------|
| Hackathons, runs, stage progress | SQLite DB at `./data/hackathon_review.db` (override with `DATABASE_URL`) |
| Uploaded CSVs | `./data/<hackathon_id>/<filename>.csv` |
| Cloned repos and downloaded videos (shared across runs) | `./data/<hackathon_id>/repos/` and `./data/<hackathon_id>/videos/` |
| Per-run pipeline outputs (JSON, logs, reports) | `./data/<hackathon_id>/runs/<run_id>/` |

Both default to `./data/`, so a single `rm -rf data/` resets the entire app to a clean slate.

### Configuration

| Env var | Default | Purpose |
|---------|---------|---------|
| `DATABASE_URL` | `sqlite:///./data/hackathon_review.db` | Any SQLAlchemy URL. Defaults to a SQLite file inside `DATA_ROOT`. |
| `DATA_ROOT` | `./data` | Where the SQLite DB, uploaded files, and run outputs are stored |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated list of allowed frontend origins |
| `NEXT_PUBLIC_API_URL` (frontend) | empty | URL of the FastAPI backend |

---

## Configuration (both modes)

Everything hackathon-specific lives in a config (a `config.yaml` for CLI mode, or a per-hackathon JSON config in the DB for web mode — both have the same shape). Copy `config.example.yaml` and fill in:

### 1. Column mapping

Map your CSV headers to the expected fields. Only `team_name`, `github_url`, and `video_url` are required:

```yaml
columns:
  team_name: "Team Name"
  github_url: "Public GitHub Repository"
  video_url: "Demo Video"
  description: "Project Description"
  extra:
    - "Problem Statement"   # extra columns are preserved in reports
```

### 2. Hackathon dates and deadlines

```yaml
hackathon:
  name: "My Hackathon"
  deadline_utc: "2026-03-08T20:00:00"
  grace_period_minutes: 15
  start_date: "2026-03-07"
  end_date: "2026-03-08"
  verify_git_period: true    # flag repos with commits outside the hackathon window
```

### 3. Scoring criteria

Define your judging rubric. Weights should sum to 1.0:

```yaml
scoring:
  criteria:
    environment_innovation:
      weight: 0.40
      description: "Is the environment novel, creative, or challenging?"
    storytelling:
      weight: 0.30
      description: "Does the team clearly explain the problem and demo?"
    training_improvement:
      weight: 0.20
      description: "Observable evidence of training progress?"
    reward_pipeline:
      weight: 0.10
      description: "Is the reward logic coherent?"
```

### 4. Code review prompt

Control what the LLM judge writes about. `prompt_preamble` gives the LLM hackathon context; `review_sections` define the narrative structure:

```yaml
code_review:
  provider: "anthropic"
  model: "claude-opus-4-6"
  prompt_preamble: >
    Projects must build RL environments using OpenEnv (0.2.1)
    deployed on HuggingFace Spaces.
  review_sections:
    - name: "What it does"
      instruction: "1-2 sentences describing the project"
    - name: "Environment Design"
      instruction: "2-3 sentences on RL environment architecture"
    - name: "Training & Rewards"
      instruction: "2-4 sentences on reward design and training pipeline"
    - name: "Depth & Execution"
      instruction: "2-3 sentences on engineering quality"
    - name: "Demo Assessment"
      instruction: "1-2 sentences based on the video transcript"
```

Omit `prompt_preamble` and `review_sections` for generic defaults (What it does, Architecture, AI Integration, Depth & Execution, Demo Assessment).

### 5. Video analysis

```yaml
video_analysis:
  provider: "gemini"
  model: "gemini-3.1-pro-preview"
  max_video_duration: 120
  score_criteria:             # keys from scoring.criteria
    - "storytelling"
```

### 6. Static analysis patterns

Pick a preset for the pattern scanner:

```yaml
static_analysis:
  pattern_preset: "openenv"   # or "general", "ai_hackathon"
```

| Preset | Patterns | Best for |
|--------|----------|----------|
| `general` | SDK detection (OpenAI, Anthropic, Gemini), tool use, streaming, agentic patterns | Generic hackathons |
| `ai_hackathon` | General + extended thinking, MCP, Claude Code, multi-turn | AI/LLM-focused hackathons |
| `openenv` | General + OpenEnv, Unsloth, TRL, GRPO, reward modeling, Gymnasium, HuggingFace Spaces/Hub, multi-agent, training pipelines | RL environment hackathons |

Add custom patterns on top of any preset:

```yaml
static_analysis:
  pattern_preset: "general"
  extra_patterns:
    my_framework:
      patterns: ["import my_framework", "from my_framework"]
      weight: 3
      description: "My custom framework usage"
```

## Switching models

Code review and video analysis use independently configurable LLM providers.

```yaml
code_review:
  provider: "anthropic"          # or "gemini"
  model: "claude-opus-4-6"

video_analysis:
  provider: "gemini"
  model: "gemini-3.1-pro-preview"
```

If you use Gemini for both, you only need a `GEMINI_API_KEY` — no Anthropic key required.

## Flagging

The pipeline automatically flags:
- Repositories that could not be cloned (404, private, invalid URL)
- Videos that could not be downloaded or are inaccessible
- Videos that appear unrelated to the project description
- (With hackathon dates configured) Late submissions, pre-existing code, single-commit dumps

## Requirements

- Python 3.11+
- Node.js 20.17+ (web app mode only)
- `ffmpeg` (for video duration detection)
- `yt-dlp` (installed automatically via pip)
- An Anthropic API key (for code review) and/or a Google Gemini API key (for video analysis)

## Contributing

Contributions are welcome — issues, PRs, new pattern presets, additional providers, all of it. The pipeline is intentionally modular: each stage in `src/hackathon_reviewer/stages/` is independent and persists its results to JSON, so adding a new stage or swapping a provider should not require touching the rest of the system.

If you're using this for your own hackathon, we'd love to hear how it went — open an issue with feedback or surprises.
