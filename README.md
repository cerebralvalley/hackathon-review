# hackathon-reviewer

Automated hackathon submission reviewer. Takes a CSV of project submissions, clones repos, downloads demo videos, analyzes both with LLMs, and generates comprehensive per-project reports.

## What it does

1. **Parses** your submission CSV (team name, GitHub URL, video URL, description, etc.)
2. **Clones** all GitHub repositories and extracts metadata (LOC, languages, git history)
3. **Downloads** demo videos and uploads them to Gemini for native video understanding
4. **Analyzes code** via configurable static analysis + LLM-powered deep review
5. **Scores** submissions on configurable criteria (optional)
6. **Generates** per-project markdown reports, a ranked leaderboard, and an issues/flags report

## Quick start

```bash
# Install (requires Python 3.11+)
pip install -e .

# Set up API keys
cp .env.example .env
# Then edit .env and add your keys:
#   ANTHROPIC_API_KEY=sk-ant-...
#   GEMINI_API_KEY=AIza...

# System dependencies
brew install ffmpeg   # needed for video duration/trimming

# Configure for your hackathon
cp config.example.yaml config.yaml
# Edit config.yaml -- see "Setting up a new hackathon" below

# Run the full pipeline
hackathon-reviewer run --csv submissions.csv --config config.yaml --output ./output
```

The `.env` file is auto-loaded on every run -- no need to `export` keys manually. See `.env.example` for the template.

## CLI commands

```bash
# Full pipeline (recommended)
hackathon-reviewer run --csv FILE --output DIR [--config FILE] [--resume]

# Individual stages (useful for re-running specific steps)
hackathon-reviewer parse    --csv FILE --output DIR [--config FILE]
hackathon-reviewer clone    --output DIR [--config FILE] [--resume]
hackathon-reviewer download --csv FILE --output DIR [--config FILE] [--resume]
hackathon-reviewer analyze  --output DIR [--config FILE] [--resume]
hackathon-reviewer report   --output DIR [--config FILE]
```

The `--resume` flag (on by default) skips already-completed work (cloned repos, downloaded videos, reviewed projects).

## Setting up a new hackathon

Everything hackathon-specific lives in `config.yaml`. No source code changes needed. Copy `config.example.yaml` and fill in these sections:

### 1. Column mapping

Map your CSV headers to the expected fields. Only `team_name`, `github_url`, and `video_url` are required:

```yaml
columns:
  team_name: "Team Name"
  github_url: "Public GitHub Repository"
  video_url: "Demo Video"
  description: "Project Description"
  # Extra columns preserved in reports:
  extra:
    - "Problem Statement"
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

Define the judging rubric. Weights should sum to 1.0. These criteria are passed directly to the LLM for scoring:

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

Control what the LLM judge writes about. The `prompt_preamble` gives the LLM hackathon context, and `review_sections` define the narrative structure of each review:

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

Omit `prompt_preamble` and `review_sections` to use generic defaults (What it does, Architecture, AI Integration, Depth & Execution, Demo Assessment).

### 5. Video analysis

Configure which scoring criteria the video analysis should also evaluate (on top of the built-in `demo` score):

```yaml
video_analysis:
  provider: "gemini"
  model: "gemini-3-flash-preview"
  max_video_duration: 120
  score_criteria:             # keys from scoring.criteria
    - "storytelling"
```

### 6. Static analysis patterns

Choose a preset for the static pattern scanner that detects frameworks and integration patterns in source code:

```yaml
static_analysis:
  pattern_preset: "openenv"   # or "general", "ai_hackathon"
```

Available presets:

| Preset | Patterns | Best for |
|--------|----------|----------|
| `general` | SDK detection (OpenAI, Anthropic, Gemini), tool use, streaming, agentic patterns | Generic hackathons |
| `ai_hackathon` | General + extended thinking, MCP, Claude Code, multi-turn | AI/LLM-focused hackathons |
| `openenv` | General + OpenEnv, Unsloth, TRL, GRPO, reward modeling, Gymnasium, HuggingFace Spaces/Hub, multi-agent, training pipelines | RL environment hackathons |

You can also add custom patterns on top of any preset:

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

Code review and video analysis use separate, independently configurable LLM providers.

**Code review** defaults to Claude Opus 4.6 via Anthropic:

```yaml
code_review:
  provider: "anthropic"          # or "gemini"
  model: "claude-opus-4-6"       # any model the provider supports
```

**Video analysis** defaults to Gemini 3 Flash with native video upload:

```yaml
video_analysis:
  provider: "gemini"
  model: "gemini-3-flash-preview"
```

If you use Gemini for both code review and video analysis, you only need a single `GEMINI_API_KEY` -- no Anthropic key required.

## Output

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

## Flagging

The tool automatically flags:
- Repositories that could not be cloned (404, private, invalid URL)
- Videos that could not be downloaded or are inaccessible
- Videos that appear unrelated to the project description
- (With hackathon config) Late submissions, pre-existing code, single-commit dumps

## Requirements

- Python 3.11+
- `ffmpeg` (for video duration detection)
- `yt-dlp` (installed automatically via pip)
- An Anthropic API key (for code review) and/or Google Gemini API key (for video analysis)
