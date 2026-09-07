import pytest

from app.services.openai_parser import OpenAIParseError, parse_openai_response


def test_happy_path():
    subject, body = parse_openai_response('{"subject": "Hallo", "text": "Guten Tag"}')
    assert subject == "Hallo"
    assert body == "Guten Tag"


def test_tolerates_surrounding_prose():
    raw = 'Sure, here you go:\n{"subject": "S", "text": "B"}\nHope it helps.'
    assert parse_openai_response(raw) == ("S", "B")


def test_accepts_body_key_alias():
    subject, body = parse_openai_response('{"subject": "S", "body": "B"}')
    assert subject == "S"
    assert body == "B"


def test_missing_subject_raises():
    with pytest.raises(OpenAIParseError):
        parse_openai_response('{"text": "no subject"}')


def test_missing_body_raises():
    with pytest.raises(OpenAIParseError):
        parse_openai_response('{"subject": "no body"}')


def test_non_json_raises():
    with pytest.raises(OpenAIParseError):
        parse_openai_response("just a paragraph, no braces at all")


def test_empty_string_raises():
    with pytest.raises(OpenAIParseError):
        parse_openai_response("")


def test_oversized_body_raises():
    huge = "x" * 100_001
    payload = '{"subject": "S", "text": "' + huge + '"}'
    with pytest.raises(OpenAIParseError):
        parse_openai_response(payload)
