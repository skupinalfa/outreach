from app.services.placeholder_validator import missing_placeholders


def test_returns_empty_list_when_all_present():
    body = "Hi {last_name}, salute {gender}, at {domain}. Template: {template}"
    assert missing_placeholders(body) == []


def test_reports_missing_subset_in_declared_order():
    body = "Hi {last_name}, welcome to {domain}."
    assert missing_placeholders(body) == ["gender", "template"]


def test_all_missing_for_empty_body():
    assert missing_placeholders("") == ["domain", "last_name", "gender", "template"]


def test_extra_curly_braces_are_ignored():
    body = "JSON {result: 1} — {domain} {last_name} {gender} {template}"
    assert missing_placeholders(body) == []
