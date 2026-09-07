import pytest

from app.services.prompt_builder import (
    ContactContext,
    PromptTemplateError,
    build_prompt,
)

_TEMPLATE = "Body for {last_name}"


def _prompt() -> str:
    return (
        "Domain: {domain}\n"
        "Name: {last_name}\n"
        "Anrede: {gender}\n"
        "Template follows:\n{template}"
    )


def _context() -> ContactContext:
    return ContactContext(domain="acme.com", last_name="Müller", gender="m")


def test_substitutes_all_placeholders():
    result = build_prompt(_prompt(), _context(), _TEMPLATE)
    assert "Domain: acme.com" in result
    assert "Name: Müller" in result
    assert "Anrede: m" in result
    assert _TEMPLATE.replace("{last_name}", "{last_name}") in result


def test_leaves_curly_braces_in_template_alone():
    tmpl = "Preserve {this} and {json_like: 1}"
    result = build_prompt(_prompt(), _context(), tmpl)
    assert "Preserve {this} and {json_like: 1}" in result


def test_none_gender_becomes_empty_string():
    ctx = ContactContext(domain="a.co", last_name="X", gender=None)
    result = build_prompt(_prompt(), ctx, "t")
    assert "Anrede: \n" in result or "Anrede: " in result


def test_missing_placeholder_raises():
    prompt = "No template placeholder at all: {domain} {last_name} {gender}"
    with pytest.raises(PromptTemplateError) as exc:
        build_prompt(prompt, _context(), "t")
    assert "template" in str(exc.value)
