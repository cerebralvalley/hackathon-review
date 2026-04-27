"""Endpoint to parse hackathon rules text into structured config via LLM."""

from __future__ import annotations

import json
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/parse-rules", tags=["parse-rules"])

SYSTEM_PROMPT = """You are a hackathon configuration assistant. Given raw hackathon rules/description text, extract structured configuration for an automated review tool.

Return ONLY valid JSON with this exact schema (omit keys if the info isn't in the rules):

{
  "name": "Hackathon Name",
  "hackathon": {
    "name": "Hackathon Name",
    "deadline_utc": "2026-03-08T20:00:00",
    "start_date": "2026-03-07",
    "end_date": "2026-03-08",
    "verify_git_period": true
  },
  "scoring": {
    "criteria": {
      "criterion_key": {
        "weight": 0.25,
        "description": "What this criterion measures"
      }
    }
  },
  "code_review": {
    "prompt_preamble": "One paragraph context about what participants are building"
  },
  "static_analysis": {
    "pattern_preset": "general"
  }
}

Rules for extraction:
- Criterion weights MUST sum to 1.0. If the rules list criteria without weights, distribute evenly.
- For pattern_preset, choose "general" for generic hackathons, "ai_hackathon" for AI/LLM focused, "openenv" for RL/robotics/environment focused.
- The prompt_preamble should be a concise summary of what participants are expected to build, based on the rules.
- For dates, use ISO 8601 format. Convert timezones to UTC if mentioned.
- criterion keys should be snake_case, short, and descriptive.
- Return ONLY the JSON object, no markdown fences or explanation."""


class ParseRulesRequest(BaseModel):
    rules_text: str


@router.post("")
async def parse_rules(body: ParseRulesRequest):
    if not body.rules_text.strip():
        raise HTTPException(400, "Rules text is empty")

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    gemini_key = os.environ.get("GEMINI_API_KEY", "")

    if anthropic_key:
        result = _parse_with_anthropic(body.rules_text, anthropic_key)
    elif gemini_key:
        result = _parse_with_gemini(body.rules_text, gemini_key)
    else:
        raise HTTPException(
            503,
            "No LLM API key configured. Set ANTHROPIC_API_KEY or GEMINI_API_KEY.",
        )

    return result


def _parse_with_anthropic(rules_text: str, api_key: str) -> dict:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": rules_text}],
    )
    return _extract_json(response.content[0].text)


def _parse_with_gemini(rules_text: str, api_key: str) -> dict:
    from google import genai

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-3.1-pro-preview",
        contents=f"{SYSTEM_PROMPT}\n\n---\n\n{rules_text}",
        config={"response_mime_type": "application/json"},
    )
    return _extract_json(response.text)


def _extract_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise HTTPException(422, f"LLM returned invalid JSON: {e}\n\nRaw: {text[:500]}")
