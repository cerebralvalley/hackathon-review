"""Anthropic (Claude) LLM provider for code review."""

from __future__ import annotations

from hackathon_reviewer.providers.base import (
    CodeReviewContext,
    CodeReviewResponse,
    LLMProvider,
)
from hackathon_reviewer.providers.prompts import (
    DEFAULT_CRITERIA,
    build_code_review_prompt,
    parse_scores,
)


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "claude-opus-4-6", max_tokens: int = 2000):
        import anthropic
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    def review_code(self, ctx: CodeReviewContext) -> CodeReviewResponse:
        criteria = ctx.scoring_criteria if ctx.scoring_criteria else DEFAULT_CRITERIA
        prompt = build_code_review_prompt(ctx, criteria)

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
                scores=parse_scores(text, criteria),
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )
        except Exception as e:
            return CodeReviewResponse(success=False, error=str(e)[:300])
