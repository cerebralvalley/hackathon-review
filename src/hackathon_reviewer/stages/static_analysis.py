"""Stage 4: Static code analysis — no LLM calls, pure heuristics."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import click
from tqdm import tqdm

from hackathon_reviewer.config import ReviewConfig
from hackathon_reviewer.models import (
    IntegrationDepth,
    PatternMatch,
    RepoMetadata,
    RepoStructure,
    StaticAnalysisResult,
    Submission,
)

SKIP_DIRS = {
    "node_modules", ".git", "vendor", "venv", ".venv", "__pycache__",
    ".next", "dist", "build", ".cache", "target", "coverage",
    ".idea", ".vscode", "env", ".env", ".tox", "egg-info",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
}

SOURCE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".rs", ".go", ".java",
    ".rb", ".swift", ".kt", ".cpp", ".c", ".cs", ".vue", ".svelte",
    ".dart", ".sh", ".bash", ".zsh",
}

SCANNABLE_EXTENSIONS = SOURCE_EXTENSIONS | {
    ".md", ".txt", ".json", ".yaml", ".yml", ".toml",
    ".cfg", ".ini", ".conf",
}

SCANNABLE_FILENAMES = {
    ".env.example", "Dockerfile", "docker-compose.yml", "Makefile",
    "Procfile", "CLAUDE.md",
}

# ---------------------------------------------------------------------------
# Pattern presets — select via config `static_analysis.pattern_preset`
# ---------------------------------------------------------------------------

COMMON_PATTERNS: dict[str, dict] = {
    "openai_sdk": {
        "patterns": [
            r"import\s+openai", r"from\s+openai",
            r"OpenAI\(", r"OPENAI_API_KEY",
        ],
        "weight": 2,
        "description": "OpenAI SDK usage",
    },
    "anthropic_sdk": {
        "patterns": [
            r"import\s+anthropic", r"from\s+anthropic",
            r"require\(['\"]@anthropic", r"require\(['\"]anthropic",
            r"import\s+Anthropic", r"new\s+Anthropic",
        ],
        "weight": 2,
        "description": "Anthropic SDK import/usage",
    },
    "gemini_sdk": {
        "patterns": [
            r"import\s+google\.genai", r"from\s+google\s+import\s+genai",
            r"genai\.Client", r"GEMINI_API_KEY",
        ],
        "weight": 2,
        "description": "Google Gemini SDK usage",
    },
    "agentic_pattern": {
        "patterns": [
            r"agent.*loop", r"observe.*act", r"autonomous",
            r"self.*correct", r"plan.*execute",
        ],
        "weight": 3,
        "description": "Agentic patterns",
    },
    "tool_use": {
        "patterns": [
            r"tool_use", r"tool_choice", r"function_calling",
            r"tools\s*=\s*\[", r"input_schema",
        ],
        "weight": 3,
        "description": "Tool use / function calling",
    },
    "streaming": {
        "patterns": [
            r"stream.*message", r"with.*stream",
            r"content_block", r"message_stream",
        ],
        "weight": 2,
        "description": "Streaming response handling",
    },
    "system_prompt": {
        "patterns": [
            r"system\s*[=:]\s*['\"]", r"system_prompt",
            r"role.*system",
        ],
        "weight": 1,
        "description": "System prompt usage",
    },
}

_AI_HACKATHON_EXTRA: dict[str, dict] = {
    "claude_model_reference": {
        "patterns": [
            r"claude-opus", r"claude-sonnet", r"claude-haiku",
            r"claude-3", r"claude-4",
            r"opus-4", r"opus4",
        ],
        "weight": 3,
        "description": "Claude model name reference",
    },
    "anthropic_api_key": {
        "patterns": [r"ANTHROPIC_API_KEY", r"sk-ant-"],
        "weight": 2,
        "description": "Anthropic API key reference",
    },
    "extended_thinking": {
        "patterns": [
            r"extended.?thinking", r"thinking.*budget",
            r"think.*tokens", r"budget_tokens",
        ],
        "weight": 4,
        "description": "Extended thinking / chain-of-thought",
    },
    "mcp_server": {
        "patterns": [
            r"mcp.*server", r"model.?context.?protocol",
            r"FastMCP", r"@mcp", r"mcp\.tool", r"MCPServer",
        ],
        "weight": 4,
        "description": "MCP (Model Context Protocol) server",
    },
    "claude_code": {
        "patterns": [
            r"claude.?code", r"CLAUDE\.md", r"\.claude",
            r"claude.*hooks", r"claude.*skills",
        ],
        "weight": 3,
        "description": "Claude Code integration",
    },
    "multi_turn": {
        "patterns": [
            r"conversation.*history", r"messages\s*[\.\[]\s*append",
            r"chat.*history", r"message.*history",
        ],
        "weight": 2,
        "description": "Multi-turn conversation",
    },
}

_OPENENV_EXTRA: dict[str, dict] = {
    "openenv": {
        "patterns": [
            r"import\s+openenv", r"from\s+openenv",
            r"open.?env", r"OpenEnv",
        ],
        "weight": 5,
        "description": "OpenEnv framework usage",
    },
    "unsloth": {
        "patterns": [
            r"import\s+unsloth", r"from\s+unsloth",
            r"unsloth", r"FastLanguageModel",
            r"UnslothTrainer",
        ],
        "weight": 4,
        "description": "Unsloth AI training framework",
    },
    "trl": {
        "patterns": [
            r"import\s+trl", r"from\s+trl",
            r"GRPOTrainer", r"PPOTrainer", r"SFTTrainer",
            r"DPOTrainer", r"RewardTrainer",
        ],
        "weight": 4,
        "description": "HuggingFace TRL (Transformer Reinforcement Learning)",
    },
    "grpo": {
        "patterns": [
            r"GRPO", r"group.?relative.?policy",
            r"grpo_config", r"GRPOConfig",
        ],
        "weight": 4,
        "description": "GRPO (Group Relative Policy Optimization)",
    },
    "reward_modeling": {
        "patterns": [
            r"reward.?function", r"reward.?model", r"reward.?signal",
            r"compute.?reward", r"reward_fn", r"get_reward",
            r"reward.?shaping", r"reward.?curve",
        ],
        "weight": 4,
        "description": "Reward function / reward modeling",
    },
    "rl_environment": {
        "patterns": [
            r"gymnasium", r"import\s+gym", r"from\s+gym",
            r"env\.reset", r"env\.step", r"observation.?space",
            r"action.?space", r"make_env",
        ],
        "weight": 3,
        "description": "RL environment (Gymnasium/Gym) patterns",
    },
    "huggingface_spaces": {
        "patterns": [
            r"gradio", r"import\s+gradio", r"from\s+gradio",
            r"gr\.Interface", r"gr\.Blocks",
            r"huggingface.co/spaces", r"hf\.space",
            r"spaces\.launch",
        ],
        "weight": 3,
        "description": "HuggingFace Spaces / Gradio deployment",
    },
    "huggingface_hub": {
        "patterns": [
            r"from\s+huggingface_hub", r"import\s+huggingface_hub",
            r"from\s+transformers", r"import\s+transformers",
            r"AutoModelFor", r"AutoTokenizer",
            r"push_to_hub", r"HfApi",
        ],
        "weight": 3,
        "description": "HuggingFace Hub / Transformers usage",
    },
    "multi_agent": {
        "patterns": [
            r"multi.?agent", r"agent.*interact", r"agent.*cooperat",
            r"agent.*compet", r"negotiat", r"coalition",
            r"theory.?of.?mind", r"self.?play",
        ],
        "weight": 3,
        "description": "Multi-agent interaction patterns",
    },
    "training_pipeline": {
        "patterns": [
            r"training.?loop", r"train_model", r"trainer\.train",
            r"training.?script", r"training.?config",
            r"epochs?", r"batch.?size", r"learning.?rate",
            r"wandb", r"tensorboard", r"training.?log",
        ],
        "weight": 3,
        "description": "Training pipeline / experiment tracking",
    },
}

PATTERN_PRESETS: dict[str, dict[str, dict]] = {
    "general": COMMON_PATTERNS,
    "ai_hackathon": {**COMMON_PATTERNS, **_AI_HACKATHON_EXTRA},
    "openenv": {**COMMON_PATTERNS, **_OPENENV_EXTRA},
}


def get_patterns(cfg: ReviewConfig) -> dict[str, dict]:
    """Resolve the active pattern set from config preset + extra_patterns."""
    preset_name = cfg.static_analysis.pattern_preset
    patterns = dict(PATTERN_PRESETS.get(preset_name, COMMON_PATTERNS))
    for name, pat_cfg in cfg.static_analysis.extra_patterns.items():
        patterns[name] = pat_cfg
    return patterns

BOILERPLATE_INDICATORS = {
    "create_react_app": {
        "files": ["src/App.test.js", "src/reportWebVitals.js", "src/setupTests.js"],
        "description": "Create React App boilerplate",
    },
    "next_js_default": {
        "files": ["app/page.tsx", "app/layout.tsx", "next.config.ts"],
        "description": "Next.js default template",
    },
    "vite_default": {
        "files": ["vite.config.ts", "src/App.tsx"],
        "description": "Vite default template",
    },
}


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------

def _scan_file(filepath: Path) -> str:
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except OSError:
        return ""


def _detect_ai_integration(
    repo_dir: Path,
    active_patterns: dict[str, dict],
) -> tuple[dict[str, PatternMatch], int, IntegrationDepth]:
    patterns_found: dict[str, PatternMatch] = {}
    total_matches = 0

    if not repo_dir.exists():
        return patterns_found, 0, IntegrationDepth.NONE

    for root, dirs, files in os.walk(repo_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in files:
            fpath = Path(root) / fname
            ext = fpath.suffix.lower()
            if ext not in SCANNABLE_EXTENSIONS and fname not in SCANNABLE_FILENAMES:
                continue

            content = _scan_file(fpath)
            if not content:
                continue

            rel_path = str(fpath.relative_to(repo_dir))

            for pattern_name, config in active_patterns.items():
                for regex in config["patterns"]:
                    matches = re.findall(regex, content, re.IGNORECASE)
                    if matches:
                        if pattern_name not in patterns_found:
                            patterns_found[pattern_name] = PatternMatch(
                                description=config["description"],
                            )
                        patterns_found[pattern_name].files.append(rel_path)
                        patterns_found[pattern_name].match_count += len(matches)
                        total_matches += len(matches)
                        break

    score = 0
    for pname, pdata in patterns_found.items():
        weight = active_patterns[pname]["weight"]
        score += weight * min(pdata.match_count, 5)

    pattern_count = len(patterns_found)
    if pattern_count == 0:
        depth = IntegrationDepth.NONE
    elif pattern_count <= 2 and score < 6:
        depth = IntegrationDepth.BASIC
    elif pattern_count <= 4 and score < 15:
        depth = IntegrationDepth.MODERATE
    elif pattern_count <= 6 and score < 25:
        depth = IntegrationDepth.DEEP
    else:
        depth = IntegrationDepth.EXTENSIVE

    return patterns_found, score, depth


def _detect_boilerplate(repo_dir: Path, total_loc: int) -> tuple[str | None, bool]:
    if not repo_dir.exists():
        return None, False

    for bp_name, config in BOILERPLATE_INDICATORS.items():
        matched = sum(1 for f in config["files"] if (repo_dir / f).exists())
        if matched >= len(config["files"]) * 0.6:
            is_heavy = total_loc < 500
            return config["description"], is_heavy

    return None, False


def _analyze_structure(repo_dir: Path) -> RepoStructure:
    structure = RepoStructure()
    if not repo_dir.exists():
        return structure

    for item in sorted(repo_dir.iterdir()):
        if item.name.startswith(".") and item.name not in {".env.example", ".claude"}:
            continue
        if item.is_dir() and item.name not in SKIP_DIRS:
            structure.top_level_dirs.append(item.name)
        elif item.is_file():
            structure.top_level_files.append(item.name)

    structure.has_docker = any(
        (repo_dir / f).exists()
        for f in ["Dockerfile", "docker-compose.yml", "docker-compose.yaml"]
    )
    structure.has_ci = (repo_dir / ".github" / "workflows").exists()
    structure.has_env_example = any(
        (repo_dir / f).exists()
        for f in [".env.example", ".env.local.example", ".env.sample"]
    )
    structure.has_claude_md = (repo_dir / "CLAUDE.md").exists() or (repo_dir / ".claude").exists()
    structure.has_license = any(
        (repo_dir / f).exists() for f in ["LICENSE", "LICENSE.md", "LICENSE.txt"]
    )

    framework_signals = {
        "package.json": {"next": "Next.js", "react": "React", "vue": "Vue",
                         "express": "Express", "svelte": "Svelte"},
        "requirements.txt": {"flask": "Flask", "fastapi": "FastAPI",
                             "django": "Django", "streamlit": "Streamlit"},
        "pyproject.toml": {"flask": "Flask", "fastapi": "FastAPI", "django": "Django"},
        "Cargo.toml": {},
        "go.mod": {},
    }

    for config_file, detectors in framework_signals.items():
        if (repo_dir / config_file).exists():
            content = _scan_file(repo_dir / config_file).lower()
            detected = False
            for keyword, framework in detectors.items():
                if keyword in content:
                    structure.frameworks_detected.append(framework)
                    detected = True
            if not detected:
                lang_map = {
                    "Cargo.toml": "Rust", "go.mod": "Go",
                    "package.json": "Node.js",
                    "requirements.txt": "Python", "pyproject.toml": "Python",
                }
                if config_file in lang_map:
                    structure.frameworks_detected.append(lang_map[config_file])

    structure.frameworks_detected = list(set(structure.frameworks_detected))
    return structure


# ---------------------------------------------------------------------------
# Process one submission
# ---------------------------------------------------------------------------

def _process_one(
    sub: Submission,
    meta: RepoMetadata,
    cfg: ReviewConfig,
    active_patterns: dict[str, dict],
) -> StaticAnalysisResult:
    result = StaticAnalysisResult(
        team_number=sub.team_number,
        clone_success=meta.clone_success,
    )

    if not meta.clone_success:
        return result

    repo_dir = cfg.repos_dir / sub.sanitized_name

    patterns, score, depth = _detect_ai_integration(repo_dir, active_patterns)
    result.integration_patterns = patterns
    result.integration_score = score
    result.integration_depth = depth

    bp_type, is_heavy = _detect_boilerplate(repo_dir, meta.files.total_loc)
    result.boilerplate_type = bp_type
    result.is_boilerplate_heavy = is_heavy

    result.structure = _analyze_structure(repo_dir)

    return result


# ---------------------------------------------------------------------------
# Stage entry points
# ---------------------------------------------------------------------------

def run_static_analysis(
    cfg: ReviewConfig,
    submissions: list[Submission],
    repo_metadata: list[RepoMetadata],
    progress: "Any | None" = None,
) -> list[StaticAnalysisResult]:
    """Run static analysis on all repos, save to JSON."""
    click.echo("\n--- Stage 4: Static Analysis ---")
    active_patterns = get_patterns(cfg)
    click.echo(f"  Pattern preset: {cfg.static_analysis.pattern_preset} ({len(active_patterns)} patterns)")

    meta_by_team = {m.team_number: m for m in repo_metadata}
    total = len(submissions)
    results: list[StaticAnalysisResult] = []

    for i, sub in enumerate(tqdm(submissions, desc="Static analysis"), 1):
        meta = meta_by_team.get(sub.team_number, RepoMetadata(
            team_number=sub.team_number, team_name=sub.team_name,
            project_name=sub.project_name, sanitized_name=sub.sanitized_name,
        ))
        results.append(_process_one(sub, meta, cfg, active_patterns))
        if progress:
            progress.update(i, total, sub.project_name)

    depths = {}
    for r in results:
        d = r.integration_depth.value
        depths[d] = depths.get(d, 0) + 1
    click.echo("  AI integration depth:")
    for d in ["extensive", "deep", "moderate", "basic", "none"]:
        if depths.get(d, 0) > 0:
            click.echo(f"    {d}: {depths[d]}")

    out_path = cfg.data_dir / "static_analysis.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump([r.model_dump(mode="json") for r in results], f, indent=2, ensure_ascii=False)
    click.echo(f"  Saved to {out_path}")

    return results


def load_static_analysis(cfg: ReviewConfig) -> list[StaticAnalysisResult]:
    """Load previously saved static analysis results."""
    path = cfg.data_dir / "static_analysis.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run the analyze stage first.")
    with open(path) as f:
        return [StaticAnalysisResult(**r) for r in json.load(f)]
