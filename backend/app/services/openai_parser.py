"""Pure helper — parses the OpenAI response text into `(subject, body)`.

The model is instructed to return JSON of shape `{"subject": "...", "text": "..."}`.
This helper is lenient about surrounding prose (LLMs sometimes prepend a preamble): it looks
for the first `{` and last `}` and parses that slice. It rejects oversized bodies to defend
against runaway generations (data-model.md — body max 100 000 chars).
"""
from __future__ import annotations

import json

_MAX_SUBJECT = 500
_MAX_BODY = 100_000


class OpenAIParseError(Exception):
    """OpenAI response did not match the `{subject, text}` schema."""


def parse_openai_response(text: str) -> tuple[str, str]:
    if not text or not text.strip():
        raise OpenAIParseError("OpenAI returned an empty response.")

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise OpenAIParseError("Response does not contain a JSON object.")

    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise OpenAIParseError(f"Response is not valid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise OpenAIParseError("Response JSON is not an object.")

    subject = payload.get("subject")
    body = payload.get("text") or payload.get("body")
    if not isinstance(subject, str) or not subject.strip():
        raise OpenAIParseError("Response is missing a non-empty 'subject'.")
    if not isinstance(body, str) or not body.strip():
        raise OpenAIParseError("Response is missing a non-empty 'text'.")

    if len(subject) > _MAX_SUBJECT:
        raise OpenAIParseError(f"Subject exceeds {_MAX_SUBJECT} characters.")
    if len(body) > _MAX_BODY:
        raise OpenAIParseError(f"Body exceeds {_MAX_BODY} characters.")

    return subject.strip(), body
