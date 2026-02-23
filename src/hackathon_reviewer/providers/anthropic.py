"""Anthropic (Claude) LLM provider for code review."""

from __future__ import annotations

from hackathon_reviewer.providers.base import (
    CodeReviewContext,
    CodeReviewResponse,
    LLMProvider,
    ScoringCriterionDef,
)

CODE_REVIEW_PROMPT = """You are an expert hackathon judge reviewing a submission. Write a detailed narrative review.

## Format

Write your review in this exact structure:

**What it does:** [1-2 sentences describing the project]

**Architecture:** [2-3 sentences on the technical architecture, frameworks, key design decisions]

**AI Integration:** [2-4 sentences specifically about how they use AI/LLMs. Be specific — mention extended thinking, MCP, tool use, agent patterns, streaming, etc. Rate as: None / Basic / Competent / Creative / Exceptional]

**Depth & Execution:** [2-3 sentences on engineering quality, iteration evidence, tests, deployment readiness]

**Demo Assessment:** [1-2 sentences based on the transcript — does it show a working product? Is the presenter compelling?]

{scores_section}

## Scoring Calibration

Use the full 1-10 range. Target distribution:
- 1-2: ~10% (clearly incomplete or non-functional)
- 3-4: ~20% (basic, boilerplate, minimal customization)
- 5-6: ~40% (solid effort, average quality — most should land here)
- 7-8: ~20% (strong, impressive, stands out)
- 9-10: ~10% (exceptional, wow factor, best-in-class)

## Submission

**Project:** {project_name}
**Team:** {team_name} (Team #{team_number})

**Description:**
{description}

**Repository Stats:**
- LOC: {loc}
- Commits during hackathon: {commits}
- Primary language: {language}
- Has tests: {has_tests}
- Hackathon period flag: {period_flag}
- Single-commit dump: {is_single_dump}

**AI Integration Patterns Found:** {patterns}

**Key Source Files:**
{source_files}

**Demo Video Transcript:**
{transcript}
"""

DEFAULT_CRITERIA = [
    ScoringCriterionDef(key="impact", weight=0.25, description="Real-world potential, who benefits, product viability"),
    ScoringCriterionDef(key="ai_use", weight=0.25, description="Creativity and depth of AI/LLM integration"),
    ScoringCriterionDef(key="depth", weight=0.20, description="Engineering quality, iteration, craft"),
    ScoringCriterionDef(key="demo", weight=0.30, description="Demo quality, working product, presentation"),
]


def _build_scores_section(criteria: list[ScoringCriterionDef]) -> str:
    lines = ["**Scores:**"]
    for c in criteria:
        label = c.key.replace("_", " ").title()
        lines.append(f"- {label}: [1-10] — [one sentence justification] ({c.description})")
    return "\n".join(lines)


def _parse_scores(text: str, criteria: list[ScoringCriterionDef]) -> dict[str, float]:
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


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "claude-opus-4-6", max_tokens: int = 2000):
        import anthropic
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    def review_code(self, ctx: CodeReviewContext) -> CodeReviewResponse:
        criteria = ctx.scoring_criteria if ctx.scoring_criteria else DEFAULT_CRITERIA
        scores_section = _build_scores_section(criteria)

        prompt = CODE_REVIEW_PROMPT.format(
            scores_section=scores_section,
            project_name=ctx.project_name,
            team_name=ctx.team_name,
            team_number=ctx.team_number,
            description=ctx.description[:800],
            loc=ctx.loc,
            commits=ctx.commits,
            language=ctx.primary_language,
            has_tests=ctx.has_tests,
            period_flag=ctx.period_flag,
            is_single_dump=ctx.is_single_dump,
            patterns=ctx.integration_patterns,
            source_files=ctx.source_files,
            transcript=ctx.transcript or "(no transcript available)",
        )

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text
            return CodeReviewResponse(
                success=True,
                review_text=text,
                scores=_parse_scores(text, criteria),
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )
        except Exception as e:
            return CodeReviewResponse(success=False, error=str(e)[:300])
