# Contract-test cassettes

Recorded HTTP interactions for `hunter`, `openai`, and `smtp` boundaries.

## Recording

Run once against the real services with live credentials in the environment:

```bash
cd outreach/backend
HUNTER_API_KEY=... OPENAI_API_KEY=... VCR_RECORD=1 uv run pytest tests/contract/test_hunter.py
```

Cassettes end up alongside this README as `<test-name>.yaml`. Commit them.

## Re-recording after an API change

```bash
VCR_REWRITE=1 uv run pytest tests/contract/test_openai.py::test_generate_happy_path
```

## What must NOT be committed

- Any cassette containing an unfiltered `Authorization`, `x-api-key`, or `api_key` query param.
- Cassettes named `*.local.yaml` are gitignored (workspace scratch).

The `cassette` fixture in `tests/contract/conftest.py` already redacts these before writing;
verify before pushing.
