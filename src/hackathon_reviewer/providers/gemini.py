"""Google Gemini provider for video analysis and optional code review."""

from __future__ import annotations

import json
import time
from pathlib import Path

from hackathon_reviewer.providers.base import (
    CodeReviewContext,
    CodeReviewResponse,
    LLMProvider,
    ScoringCriterionDef,
    VideoReviewContext,
    VideoReviewResponse,
)

VIDEO_ANALYSIS_PROMPT = """You are reviewing a hackathon demo video. Analyze this video and provide:

1. **Transcript Summary**: A concise summary of what the presenter says and shows (2-3 sentences).

2. **Demo Classification**: Classify the demo as one of:
   - "broken" — video doesn't play, is corrupted, or shows nothing relevant
   - "slides_only" — only slides/mockups, no working product shown
   - "basic_working" — shows a working product but unpolished
   - "polished" — clean, clear demo with real functionality
   - "exceptional" — genuinely impressive, makes you want to use the product

3. **Project Relevance**: Is this video actually demonstrating the project described below? (true/false)
   If the video seems unrelated (e.g., a rickroll, random content, wrong video), mark as false.

4. **Review**: 2-3 sentences assessing the demo quality.

5. **Scores** (1-10 each):
   - demo: Overall demo quality

**Project being reviewed:**
- Name: {project_name}
- Team: {team_name}
- Description: {description}

Respond with ONLY valid JSON:
{{"transcript_summary": "...", "demo_classification": "...", "is_related_to_project": true/false, "review": "...", "scores": {{"demo": N}}}}
"""

DEFAULT_CRITERIA = [
    ScoringCriterionDef(key="impact", weight=0.25, description="Real-world potential, who benefits, product viability"),
    ScoringCriterionDef(key="ai_use", weight=0.25, description="Creativity and depth of AI/LLM integration"),
    ScoringCriterionDef(key="depth", weight=0.20, description="Engineering quality, iteration, craft"),
    ScoringCriterionDef(key="demo", weight=0.30, description="Demo quality, working product, presentation"),
]


def _build_code_review_prompt(criteria: list[ScoringCriterionDef]) -> str:
    criteria_block = ""
    for c in criteria:
        label = c.key.replace("_", " ").title()
        pct = int(c.weight * 100)
        criteria_block += f"**{label} ({pct}%):** {c.description}\n"
        criteria_block += "- 1-3: Poor / 4-6: Average / 7-8: Strong / 9-10: Exceptional\n\n"

    json_keys = ", ".join(f'"{c.key}": N' for c in criteria)
    json_schema = "{" + f"{json_keys}, \"rationale\": \"1-2 sentence summary\"" + "}"

    return f"""You are a hackathon judge. Score this submission on the following criteria, each 1-10. Be discriminating — use the full range.

{criteria_block}
**Project:** {{project_name}}
**Team:** {{team_name}}
**Description:** {{description}}

**Repo Stats:** LOC: {{loc}} | Commits: {{commits}} | Language: {{language}} | Tests: {{has_tests}}
**AI Patterns:** {{patterns}}

**Key Source Files:**
{{source_files}}

**Demo Transcript:**
{{transcript}}

Respond with ONLY valid JSON:
{json_schema}
"""


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gemini-3-flash-preview"):
        from google import genai
        self.client = genai.Client(api_key=api_key)
        self.model = model

    def review_code(self, ctx: CodeReviewContext) -> CodeReviewResponse:
        criteria = ctx.scoring_criteria if ctx.scoring_criteria else DEFAULT_CRITERIA
        prompt_template = _build_code_review_prompt(criteria)

        prompt = prompt_template.format(
            project_name=ctx.project_name,
            team_name=ctx.team_name,
            description=ctx.description[:500],
            loc=ctx.loc,
            commits=ctx.commits,
            language=ctx.primary_language,
            has_tests=ctx.has_tests,
            patterns=ctx.integration_patterns,
            source_files=ctx.source_files,
            transcript=ctx.transcript or "(no transcript available)",
        )

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config={"response_mime_type": "application/json"},
            )
            scores_raw = json.loads(response.text)
            scores = {}
            valid_keys = {c.key for c in criteria}
            for key, val in scores_raw.items():
                if key in valid_keys:
                    scores[key] = max(1, min(10, int(val)))

            return CodeReviewResponse(
                success=True,
                review_text=scores_raw.get("rationale", ""),
                scores=scores,
            )
        except Exception as e:
            return CodeReviewResponse(success=False, error=str(e)[:300])

    def review_video(self, ctx: VideoReviewContext) -> VideoReviewResponse:
        if not ctx.video_path or not ctx.video_path.exists():
            return VideoReviewResponse(success=False, error="video_file_not_found")

        prompt = VIDEO_ANALYSIS_PROMPT.format(
            project_name=ctx.project_name,
            team_name=ctx.team_name,
            description=ctx.description[:500],
        )

        try:
            video_file = self.client.files.upload(
                file=ctx.video_path,
                config={"mime_type": "video/mp4"},
            )

            while video_file.state.name == "PROCESSING":
                time.sleep(2)
                video_file = self.client.files.get(name=video_file.name)

            if video_file.state.name == "FAILED":
                return VideoReviewResponse(
                    success=False,
                    error=f"Video processing failed: {video_file.state.name}",
                )

            response = self.client.models.generate_content(
                model=self.model,
                contents=[video_file, prompt],
                config={"response_mime_type": "application/json"},
            )

            result = json.loads(response.text)

            try:
                self.client.files.delete(name=video_file.name)
            except Exception:
                pass

            scores = {}
            if "scores" in result and isinstance(result["scores"], dict):
                for k, v in result["scores"].items():
                    scores[k] = max(1, min(10, int(v)))

            return VideoReviewResponse(
                success=True,
                transcript_summary=result.get("transcript_summary", ""),
                demo_classification=result.get("demo_classification", "unknown"),
                is_related_to_project=result.get("is_related_to_project", True),
                review_text=result.get("review", ""),
                scores=scores,
            )

        except Exception as e:
            return VideoReviewResponse(success=False, error=str(e)[:300])
