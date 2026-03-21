"""Shared prompt-building logic for code review providers."""

from __future__ import annotations

from hackathon_reviewer.providers.base import (
    CodeReviewContext,
    ReviewSectionDef,
    ScoringCriterionDef,
)

DEFAULT_REVIEW_SECTIONS = [
    ReviewSectionDef(
        name="What it does",
        instruction="1-2 sentences describing the project",
    ),
    ReviewSectionDef(
        name="Architecture",
        instruction="2-3 sentences on the technical architecture, frameworks, key design decisions",
    ),
    ReviewSectionDef(
        name="AI Integration",
        instruction="2-4 sentences specifically about how they use AI/LLMs — mention specific patterns, SDKs, or techniques. Rate as: None / Basic / Competent / Creative / Exceptional",
    ),
    ReviewSectionDef(
        name="Depth & Execution",
        instruction="2-3 sentences on engineering quality, iteration evidence, tests, deployment readiness",
    ),
    ReviewSectionDef(
        name="Demo Assessment",
        instruction="1-2 sentences based on the transcript — does it show a working product? Is the presenter compelling?",
    ),
]

DEFAULT_CRITERIA = [
    ScoringCriterionDef(key="impact", weight=0.25, description="Real-world potential, who benefits, product viability"),
    ScoringCriterionDef(key="ai_use", weight=0.25, description="Creativity and depth of AI/LLM integration"),
    ScoringCriterionDef(key="depth", weight=0.20, description="Engineering quality, iteration, craft"),
    ScoringCriterionDef(key="demo", weight=0.30, description="Demo quality, working product, presentation"),
]


def build_sections_block(sections: list[ReviewSectionDef]) -> str:
    lines = []
    for s in sections:
        lines.append(f"**{s.name}:** [{s.instruction}]")
    return "\n\n".join(lines)


def build_scores_section(criteria: list[ScoringCriterionDef]) -> str:
    lines = ["**Scores:**"]
    for c in criteria:
        label = c.key.replace("_", " ").title()
        lines.append(f"- {label}: [1-10] — [one sentence justification] ({c.description})")
    return "\n".join(lines)


def build_code_review_prompt(ctx: CodeReviewContext, criteria: list[ScoringCriterionDef]) -> str:
    sections = ctx.review_sections if ctx.review_sections else DEFAULT_REVIEW_SECTIONS

    preamble = ctx.prompt_preamble or "Write a detailed narrative review."
    sections_block = build_sections_block(sections)
    scores_section = build_scores_section(criteria)

    return f"""You are an expert hackathon judge reviewing a submission. {preamble}

## Format

Write your review in this exact structure:

{sections_block}

{scores_section}

## Scoring Calibration

Use the full 1-10 range. Target distribution:
- 1-2: ~10% (clearly incomplete or non-functional)
- 3-4: ~20% (basic, boilerplate, minimal customization)
- 5-6: ~40% (solid effort, average quality — most should land here)
- 7-8: ~20% (strong, impressive, stands out)
- 9-10: ~10% (exceptional, wow factor, best-in-class)

## Submission

**Project:** {ctx.project_name}
**Team:** {ctx.team_name} (Team #{ctx.team_number})

**Description:**
{ctx.description[:800]}

**Repository Stats:**
- LOC: {ctx.loc}
- Commits during hackathon: {ctx.commits}
- Primary language: {ctx.primary_language}
- Has tests: {ctx.has_tests}
- Hackathon period flag: {ctx.period_flag}
- Single-commit dump: {ctx.is_single_dump}

**Integration Patterns Found:** {ctx.integration_patterns}

**Key Source Files:**
{ctx.source_files}

**Demo Video Transcript:**
{ctx.transcript or "(no transcript available)"}
"""


def parse_scores(text: str, criteria: list[ScoringCriterionDef]) -> dict[str, float]:
    """Extract scores from the review text, matching against configured criteria."""
    scores: dict[str, float] = {}

    label_to_key = {}
    for c in criteria:
        label_to_key[c.key.replace("_", " ").lower()] = c.key
        label_to_key[c.key.lower()] = c.key

    for line in text.split("\n"):
        line_stripped = line.strip()
        if not line_stripped.startswith("- "):
            continue
        line_lower = line_stripped.lower()

        for label, key in label_to_key.items():
            if line_lower.startswith(f"- {label}:"):
                try:
                    score_part = line_stripped.split(":", 1)[1].strip()
                    val = int(score_part.split("/")[0].strip().split()[0])
                    scores[key] = max(1, min(10, val))
                except (ValueError, IndexError):
                    pass
                break

    return scores
