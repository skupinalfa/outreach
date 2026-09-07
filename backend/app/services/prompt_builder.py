"""Pure helper — substitutes `{domain}`, `{last_name}`, `{gender}`, `{template}` into the active
prompt text. Uses `str.replace` (not `.format`) because template bodies frequently contain their
own curly braces (JSON schema hints, HTML style attributes) that would otherwise be interpreted
as format specifiers.
"""
from __future__ import annotations

from dataclasses import dataclass

REQUIRED_PLACEHOLDERS = ("domain", "last_name", "gender", "template")


class PromptTemplateError(ValueError):
    """Raised when the active prompt is missing a required placeholder."""


@dataclass(frozen=True)
class ContactContext:
    domain: str
    last_name: str
    gender: str | None


def build_prompt(
    prompt_template: str,
    contact: ContactContext,
    template_body: str,
) -> str:
    missing = [
        placeholder
        for placeholder in REQUIRED_PLACEHOLDERS
        if "{" + placeholder + "}" not in prompt_template
    ]
    if missing:
        raise PromptTemplateError(
            "Prompt is missing required placeholders: "
            + ", ".join("{" + p + "}" for p in missing)
        )

    values = {
        "domain": contact.domain,
        "last_name": contact.last_name,
        "gender": contact.gender or "",
        "template": template_body,
    }
    result = prompt_template
    for key, value in values.items():
        result = result.replace("{" + key + "}", value)
    return result
