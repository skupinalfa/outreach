"""Pure helper — returns the list of recognised placeholders missing from a template body.

Recognised placeholders are the same four the prompt builder substitutes (`{domain}`,
`{last_name}`, `{gender}`, `{template}`). The templates screen surfaces the missing set as an
inline warning so the operator can add them before the template is used for generation.
"""
from __future__ import annotations

from app.services.prompt_builder import REQUIRED_PLACEHOLDERS


def missing_placeholders(body: str) -> list[str]:
    """Return the recognised placeholders that don't appear in `body`."""
    return [p for p in REQUIRED_PLACEHOLDERS if "{" + p + "}" not in body]
