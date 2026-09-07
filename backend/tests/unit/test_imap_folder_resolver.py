"""Unit tests for the IMAP Drafts-folder resolver (research R5).

The resolver is a pure function over the LIST / EXAMINE side of a live IMAP4 client. We
substitute a small fake in place of `imaplib.IMAP4` so the tiers can be exercised
deterministically without any real IMAP server.
"""
from __future__ import annotations

from collections.abc import Iterable

import pytest

from app.integrations.imap import (
    IMAPDraftsNotFoundError,
    resolve_drafts_folder,
)


class _FakeIMAP:
    """Minimal stand-in for `imaplib.IMAP4` — only the two methods the resolver calls."""

    def __init__(
        self,
        list_response: Iterable[bytes] | None = None,
        readable_folders: Iterable[str] = (),
    ) -> None:
        self._list_response = list(list_response) if list_response is not None else []
        self._readable = set(readable_folders)
        self.list_calls: list[tuple[str, str]] = []
        self.examine_calls: list[str] = []

    def list(self, directory: str, pattern: str):
        self.list_calls.append((directory, pattern))
        if not self._list_response:
            return ("NO", [None])
        return ("OK", self._list_response)

    def examine(self, folder: bytes):
        # imaplib passes bytes; the resolver builds them via `"<name>"`.encode('ascii').
        name = folder.decode().strip('"')
        self.examine_calls.append(name)
        return ("OK", [b"0"]) if name in self._readable else ("NO", [b"nope"])

    def close(self) -> None:  # examine + close pairs the way imaplib expects
        pass


def test_operator_override_wins_over_everything():
    imap = _FakeIMAP(
        list_response=[br'(\HasNoChildren \Drafts) "/" "Entwuerfe"'],
        readable_folders=("Drafts",),
    )

    folder, is_new = resolve_drafts_folder(
        imap, operator_override="Meine Entwuerfe", detected_cache=None
    )

    assert folder == "Meine Entwuerfe"
    assert is_new is False
    # No LIST or EXAMINE calls when the override short-circuits tier 1.
    assert imap.list_calls == []
    assert imap.examine_calls == []


def test_detected_cache_short_circuits_when_still_readable():
    imap = _FakeIMAP(readable_folders=("Drafts",))

    folder, is_new = resolve_drafts_folder(
        imap, operator_override=None, detected_cache="Drafts"
    )

    assert folder == "Drafts"
    assert is_new is False
    assert imap.examine_calls == ["Drafts"]
    assert imap.list_calls == []  # cache hit ⇒ never LIST


def test_stale_cache_falls_through_to_next_tier():
    imap = _FakeIMAP(
        list_response=[br'(\HasNoChildren \Drafts) "/" "Drafts"'],
        readable_folders=("Drafts",),
    )

    folder, is_new = resolve_drafts_folder(
        imap, operator_override=None, detected_cache="StaleFolder"
    )

    assert folder == "Drafts"
    assert is_new is True
    # First EXAMINE was the stale cache (miss), then SPECIAL-USE ran.
    assert imap.examine_calls[0] == "StaleFolder"


def test_special_use_wins_over_fallbacks():
    imap = _FakeIMAP(
        list_response=[
            br'(\HasNoChildren) "/" "INBOX"',
            br'(\HasNoChildren \Drafts) "/" "[Gmail]/Drafts"',
            br'(\HasNoChildren \Sent) "/" "[Gmail]/Sent Mail"',
        ],
        readable_folders=("Drafts",),  # a well-known name would also work if we tried it
    )

    folder, is_new = resolve_drafts_folder(
        imap, operator_override=None, detected_cache=None
    )

    assert folder == "[Gmail]/Drafts"
    assert is_new is True
    # SPECIAL-USE short-circuits before tier 3: no EXAMINE against well-known names.
    assert imap.examine_calls == []


def test_falls_back_to_well_known_when_special_use_missing():
    imap = _FakeIMAP(
        list_response=[br'(\HasNoChildren) "/" "INBOX"'],  # no \Drafts flag
        readable_folders=("[Gmail]/Drafts",),  # only the bracketed form exists
    )

    folder, is_new = resolve_drafts_folder(
        imap, operator_override=None, detected_cache=None
    )

    assert folder == "[Gmail]/Drafts"
    assert is_new is True
    # Well-known list is tried in order: Drafts (miss), [Gmail]/Drafts (hit).
    assert imap.examine_calls == ["Drafts", "[Gmail]/Drafts"]


def test_all_miss_raises_with_folders_tried():
    imap = _FakeIMAP(list_response=[br'(\HasNoChildren) "/" "INBOX"'], readable_folders=())

    with pytest.raises(IMAPDraftsNotFoundError) as exc:
        resolve_drafts_folder(imap, operator_override=None, detected_cache=None)

    message = str(exc.value)
    assert "Drafts" in message
    assert "[Gmail]/Drafts" in message
    assert "INBOX.Drafts" in message
