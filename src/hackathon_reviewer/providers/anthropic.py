"""Anthropic (Claude) LLM provider for code review."""

from __future__ import annotations

from hackathon_reviewer.providers.base import (
    CodeReviewContext,
    CodeReviewResponse,
    LLMProvider,
)

CODE_REVIEW_PROMPT = """You are an expert hackathon judge reviewing a submission. Write a detailed narrative review.

## Format

Write your review in this exact structure:

**What it does:** [1-2 sentences describing the project]

**Architecture:** [2-3 sentences on the technical architecture, frameworks, key design decisions]

**AI Integration:** [2-4 sentences specifically about how they use AI/LLMs. Be specific — mention extended thinking, MCP, tool use, agent patterns, streaming, etc. Rate as: None / Basic / Competent / Creative / Exceptional]

**Depth & Execution:** [2-3 sentences on engineering quality, iteration evidence, tests, deployment readiness]

**Demo Assessment:** [1-2 sentences based on the transcript — does it show a working product? Is the presenter compelling?]

**Scores:**
- Impact: [1-10] — [one sentence justification]
- AI Use: [1-10] — [one sentence justification]
- Depth: [1-10] — [one sentence justification]
- Demo: [1-10] — [one sentence justification]

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


def _parse_scores(text: str) -> dict[str, float]:
    """Extract scores from the review text."""
    scores: dict[str, float] = {}
    score_mapping = {
        "impact": "impact",
        "ai use": "ai_use",
        "depth": "depth",
        "demo": "demo",
    }

    for line in text.split("\n"):
        line_lower = line.lower().strip()
        for trigger, key in score_mapping.items():
            if line_lower.startswith(f"- {trigger}:"):
                try:
                    score_part = line.split(":", 1)[1].strip()
                    val = int(score_part.split("/")[0].strip().split()[0])
                    scores[key] = max(1, min(10, val))
                except (ValueError, IndexError):
                    pass
    return scores


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "claude-opus-4-6", max_tokens: int = 2000):
        import anthropic
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    def review_code(self, ctx: CodeReviewContext) -> CodeReviewResponse:
        prompt = CODE_REVIEW_PROMPT.format(
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
                scores=_parse_scores(text),
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )
        except Exception as e:
            return CodeReviewResponse(success=False, error=str(e)[:300])
