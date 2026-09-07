"""IMAP boundary — Drafts-folder detection + APPEND with replace-in-place (feature 002 US3).

Uses only stdlib `imaplib`. IMAP is one-off per operator action, so no async or connection
pooling. Retry classification mirrors `integrations/smtp.py`: 3 tries with 200/400/800 ms
backoff on transient failures; authentication and permanent server errors are terminal.

Layout of the public API:
- `connect(settings)`           -> IMAPConnection context manager
- `resolve_drafts_folder(...)`  -> str (three-tier resolver per research R5)
- `append_draft(...)`           -> (folder_path, uid)  — uid may be None on non-UIDPLUS servers
- `replace_previous(...)`       -> deletes+expunges the previous copy (UIDPLUS required)
- `test_credentials(settings)`  -> raises typed errors; used by /settings/test/imap
"""
from __future__ import annotations

import contextlib
import imaplib
import re
import ssl
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from email.message import EmailMessage

from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.logging import get_logger

log = get_logger("imap")


class IMAPError(Exception):
    """Non-retryable IMAP failure (permanent, unexpected protocol error)."""


class IMAPCredentialError(IMAPError):
    """IMAP server rejected auth."""


class IMAPDraftsNotFoundError(IMAPError):
    """No Drafts folder could be resolved by any tier of the resolver."""


class IMAPStoreConflictError(IMAPError):
    """Previous mailbox copy exists but the server does not advertise UIDPLUS,
    so we cannot reliably replace it in-place (FR-049 fallback)."""


class _RetryableIMAPError(Exception):
    """Transient IMAP failure (connection reset, EOF, socket timeout)."""


def _retry():
    return retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.2, min=0.2, max=0.8),
        retry=retry_if_exception_type(_RetryableIMAPError),
    )


# Well-known Drafts-folder names, tried in order when SPECIAL-USE detection returns nothing.
# Order matters: Gmail's IMAP has a plain `Drafts` folder AND `[Gmail]/Drafts`; the plain
# one is a shortcut alias, but the account's "canonical" copy lives under `[Gmail]/`. We try
# the plain name first because it works everywhere Gmail's IMAP does, and fall back to the
# bracketed form for the rare configuration where the plain alias is disabled.
_WELL_KNOWN_DRAFTS = ("Drafts", "[Gmail]/Drafts", "INBOX.Drafts")


@dataclass(frozen=True)
class ImapConnectSettings:
    """Minimal settings shape the IMAP boundary needs — decouples it from ORM types."""

    host: str
    port: int
    username: str
    password: str
    use_tls: bool = True


@contextmanager
def connect(cfg: ImapConnectSettings) -> Iterator[imaplib.IMAP4]:
    """Connect and LOGIN. Yields a live `imaplib.IMAP4` (or `IMAP4_SSL`). Closes cleanly."""
    if not cfg.host or not cfg.port:
        raise IMAPCredentialError("IMAP host/port not configured.")
    if not cfg.username or not cfg.password:
        raise IMAPCredentialError("IMAP credentials not configured.")

    imap: imaplib.IMAP4 | None = None
    try:
        if cfg.use_tls:
            imap = imaplib.IMAP4_SSL(cfg.host, cfg.port, ssl_context=ssl.create_default_context())
        else:
            imap = imaplib.IMAP4(cfg.host, cfg.port)
        try:
            imap.login(cfg.username, cfg.password)
        except imaplib.IMAP4.error as exc:
            # imaplib raises IMAP4.error for LOGIN failures (both auth-reject and protocol).
            # We can't reliably differentiate; treat as auth error.
            raise IMAPCredentialError(f"IMAP authentication failed: {exc}") from exc
        yield imap
    except (TimeoutError, ConnectionError, OSError) as exc:
        raise _RetryableIMAPError(f"IMAP transient: {exc}") from exc
    finally:
        if imap is not None:
            # Logout errors are noise once we're done — nothing useful to do about them.
            with contextlib.suppress(Exception):
                imap.logout()


# ---------------------------------------------------------------------------
# Folder resolver (research R5).
# ---------------------------------------------------------------------------


# Matches a LIST/SPECIAL-USE response line, e.g. `(\HasNoChildren \Drafts) "/" "Drafts"`.
_LIST_LINE = re.compile(rb'\((?P<flags>[^)]*)\)\s+(?:"(?P<sep>[^"]*)"|NIL)\s+(?P<name>"[^"]*"|\S+)')


def resolve_drafts_folder(
    imap: imaplib.IMAP4,
    *,
    operator_override: str | None,
    detected_cache: str | None,
) -> tuple[str, bool]:
    """Return `(folder_name, is_new_detection)`.

    Tier 1: operator override (from settings.imap_drafts_folder).
    Tier 2: SPECIAL-USE `\\Drafts` (RFC 6154).
    Tier 3: well-known fallbacks (`Drafts`, `[Gmail]/Drafts`, `INBOX.Drafts`), first EXAMINE-OK wins.
    Otherwise: raise IMAPDraftsNotFoundError with the folders tried.

    Cached detected value (from `settings.imap_drafts_folder_detected`) short-circuits tier 2/3
    if it still resolves — we EXAMINE it first to verify it still exists.
    """
    if operator_override:
        return operator_override, False

    if detected_cache and _folder_readable(imap, detected_cache):
        return detected_cache, False

    special_use = _detect_via_special_use(imap)
    if special_use is not None:
        return special_use, True

    for candidate in _WELL_KNOWN_DRAFTS:
        if _folder_readable(imap, candidate):
            return candidate, True

    raise IMAPDraftsNotFoundError(
        "No Drafts folder resolved by override, SPECIAL-USE, or well-known names. "
        f"Tried: {list(_WELL_KNOWN_DRAFTS)}."
    )


def _detect_via_special_use(imap: imaplib.IMAP4) -> str | None:
    typ, data = imap.list('""', "*")
    if typ != "OK" or not data:
        return None
    for line in data:
        if not isinstance(line, bytes | bytearray):
            continue
        match = _LIST_LINE.search(bytes(line))
        if match is None:
            continue
        flags = match.group("flags").split()
        if b"\\Drafts" not in flags:
            continue
        raw_name = match.group("name")
        return raw_name.decode().strip('"') if raw_name else None
    return None


def _folder_readable(imap: imaplib.IMAP4, folder: str) -> bool:
    try:
        typ, _ = imap.examine(_encode_folder(folder))
    except imaplib.IMAP4.error:
        return False
    if typ != "OK":
        return False
    with contextlib.suppress(imaplib.IMAP4.error):
        imap.close()
    return True


def _encode_folder(folder: str) -> bytes:
    # IMAP folder names transit as bytes; use ASCII if possible, else UTF-7 modified encoding.
    # In v1 the operator-provided override is validated as printable ASCII, and Well-known
    # names are all ASCII, so a plain encode is safe.
    return f'"{folder}"'.encode("ascii", errors="replace")


# ---------------------------------------------------------------------------
# APPEND + replace-in-place (research R6).
# ---------------------------------------------------------------------------


# Matches `APPENDUID <uidvalidity> <uid>` inside the response, per RFC 4315.
_APPENDUID = re.compile(rb"APPENDUID\s+(\d+)\s+(\d+)")


def append_draft(imap: imaplib.IMAP4, folder: str, msg: EmailMessage) -> int | None:
    """APPEND the message with the `\\Draft` flag. Returns the UID from APPENDUID, or None
    if the server did not advertise UIDPLUS (rare)."""
    raw = bytes(msg)
    typ, data = imap.append(
        _encode_folder(folder),
        r"(\Draft)",
        imaplib.Time2Internaldate(time.time()),
        raw,
    )
    if typ != "OK":
        raise IMAPError(f"IMAP APPEND failed: {typ} {data!r}")

    for line in data:
        if not isinstance(line, bytes | bytearray):
            continue
        match = _APPENDUID.search(bytes(line))
        if match:
            return int(match.group(2))
    return None


def replace_previous(imap: imaplib.IMAP4, folder: str, previous_uid: int) -> None:
    """UID STORE +FLAGS (\\Deleted) then EXPUNGE the specific UID. Silent if the UID is gone."""
    try:
        imap.select(_encode_folder(folder))
        imap.uid("STORE", str(previous_uid).encode(), "+FLAGS", r"(\Deleted)")
        # UID EXPUNGE narrows the expunge to just this UID — RFC 4315 UIDPLUS. Fall back to
        # a plain EXPUNGE on servers that don't understand UID EXPUNGE (imaplib raises).
        try:
            imap.uid("EXPUNGE", str(previous_uid).encode())
        except imaplib.IMAP4.error:
            imap.expunge()
    finally:
        with contextlib.suppress(imaplib.IMAP4.error):
            imap.close()


# ---------------------------------------------------------------------------
# Credential test (used by POST /settings/test/imap).
# ---------------------------------------------------------------------------


def test_credentials(cfg: ImapConnectSettings) -> str:
    """Connect + LOGIN + resolve Drafts folder. Returns the resolved folder name.
    Raises IMAPCredentialError / IMAPError / IMAPDraftsNotFoundError on failure."""

    @_retry()
    def _do() -> str:
        with connect(cfg) as imap:
            folder, _ = resolve_drafts_folder(
                imap, operator_override=None, detected_cache=None
            )
            return folder

    try:
        return _do()
    except RetryError as exc:
        raise IMAPError("IMAP transient failure after retries.") from exc
