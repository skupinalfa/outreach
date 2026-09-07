"""VCR configuration for contract tests. Cassettes live under `cassettes/`.

Record mode:
- Default (no env): `once` — recorded cassettes are replayed; new interactions raise.
- `VCR_RECORD=1`: `new_episodes` — new interactions are appended to the cassette.
- `VCR_REWRITE=1`: `all` — every interaction is re-recorded (use to refresh after an API change).

Sensitive headers are stripped before writing to disk.
"""
from __future__ import annotations

import os
import pathlib

import pytest
import vcr

_CASSETTE_DIR = pathlib.Path(__file__).parent / "cassettes"


def _record_mode() -> str:
    if os.environ.get("VCR_REWRITE") == "1":
        return "all"
    if os.environ.get("VCR_RECORD") == "1":
        return "new_episodes"
    return "once"


@pytest.fixture
def cassette(request: pytest.FixtureRequest):
    name = f"{request.node.name}.yaml"
    path = _CASSETTE_DIR / name
    with vcr.use_cassette(
        str(path),
        record_mode=_record_mode(),
        filter_headers=[("authorization", "REDACTED"), ("x-api-key", "REDACTED")],
        filter_query_parameters=[("api_key", "REDACTED")],
        filter_post_data_parameters=[("api_key", "REDACTED")],
        match_on=["method", "scheme", "host", "port", "path", "query"],
    ):
        yield path
