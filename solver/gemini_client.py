"""
Thin wrapper around the Gemini API (google-genai SDK).

Uses gemini-2.5-flash by default, which sits comfortably in the free tier
(roughly 10 requests/min, 250/day as of mid-2026 -- plenty for one issue-solve
run, which typically needs 1 plan call + 1 call per file).
"""
from __future__ import annotations

import json
import os

from google import genai
from google.genai import types

from solver.prompts import (
    CODE_WRITER_SYSTEM_PROMPT,
    PLANNER_SYSTEM_PROMPT,
    build_code_writer_prompt,
    build_planner_prompt,
)

DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")


class GeminiClient:
    def __init__(self, api_key: str | None = None, model: str = DEFAULT_MODEL):
        self.client = genai.Client(api_key=api_key or os.environ["GEMINI_API_KEY"])
        self.model = model

    def generate_plan(self, issue_title: str, issue_body: str, file_tree: list[str]) -> dict:
        prompt = build_planner_prompt(issue_title, issue_body, file_tree)
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=PLANNER_SYSTEM_PROMPT,
                response_mime_type="application/json",
                temperature=0.2,
            ),
        )
        return _safe_json_parse(response.text)

    def generate_file_content(
        self,
        issue_title: str,
        issue_body: str,
        plan_summary: str,
        plan_approach: str,
        file_path: str,
        action: str,
        original_content: str | None,
    ) -> str:
        prompt = build_code_writer_prompt(
            issue_title, issue_body, plan_summary, plan_approach,
            file_path, action, original_content,
        )
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=CODE_WRITER_SYSTEM_PROMPT,
                temperature=0.1,
            ),
        )
        return _strip_code_fences(response.text)


def _safe_json_parse(text: str) -> dict:
    text = _strip_code_fences(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Gemini did not return valid JSON:\n{text}") from e


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:]  # drop opening fence (possibly with language tag)
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip() + "\n"
