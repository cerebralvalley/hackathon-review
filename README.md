# hackathon-reviewer

Automated hackathon submission reviewer. Takes a CSV of project submissions, clones repos, downloads demo videos, analyzes both with LLMs, and generates comprehensive per-project reports.

## What it does

1. **Parses** your submission CSV (team name, GitHub URL, video URL, description, etc.)
2. **Clones** all GitHub repositories and extracts metadata (LOC, languages, git history)
3. **Downloads** demo videos and uploads them to Gemini for native video understanding
4. **Analyzes code** via static analysis + LLM-powered deep review (default: Claude Opus 4.6)
5. **Scores** submissions on configurable criteria (optional)
6. **Generates** per-project markdown reports, a ranked leaderboard, and an issues/flags report

## Quick start

```bash
# Install (requires Python 3.11+)
pip install -e .

# Set API keys
export ANTHROPIC_API_KEY="your-key"
export GEMINI_API_KEY="your-key"

# System dependencies
brew install ffmpeg   # needed for video duration detection

# Run the full pipeline
hackathon-reviewer run --csv submissions.csv --output ./output

# Or with a config file for custom settings
hackathon-reviewer run --csv submissions.csv --config config.yaml --output ./output
```

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

## Configuration

Copy `config.example.yaml` to `config.yaml` and customize:

- **Column mapping** -- tell the tool which CSV columns map to team name, GitHub URL, etc.
- **Code review model** -- swap between Anthropic and Gemini for code analysis
- **Video analysis** -- uses Gemini's native video understanding by default
- **Hackathon settings** -- optionally enable deadline checking, git period verification
- **Scoring rubric** -- define custom criteria and weights, or omit to skip scoring

### Switching models

Code review and video analysis use separate, independently configurable LLM providers.

**Code review** defaults to Claude Opus 4.6 via Anthropic. To change it, set these fields in your `config.yaml`:

```yaml
code_review:
  provider: "anthropic"          # or "gemini"
  model: "claude-opus-4-6"       # any model the provider supports
```

Examples:

```yaml
# Use Claude Sonnet instead of Opus
code_review:
  provider: "anthropic"
  model: "claude-sonnet-4-20250514"

# Use Gemini for code review (only needs a GEMINI_API_KEY, no Anthropic key)
code_review:
  provider: "gemini"
  model: "gemini-3-flash-preview"
```

**Video analysis** defaults to Gemini 3 Flash with native video upload:

```yaml
video_analysis:
  provider: "gemini"
  model: "gemini-3-flash-preview"    # or "gemini-3.1-pro-preview" for higher quality
```

If you use Gemini for both code review and video analysis, you only need a single `GEMINI_API_KEY` -- no Anthropic key required.

## Output

```
output/
  data/
    submissions.json        # Parsed submissions
    repo_metadata.json      # Clone + git analysis results
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
