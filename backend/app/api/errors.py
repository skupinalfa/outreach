"""Central helper: convert a typed service error into a `HTTPException` with the taxonomy
shape defined in contracts/api.md.
"""
from __future__ import annotations

from fastapi import HTTPException


def api_error(code: str, message: str, status: int) -> HTTPException:
    return HTTPException(status_code=status, detail={"error": {"code": code, "message": message}})


def not_found(resource: str) -> HTTPException:
    return api_error("not_found", f"{resource} does not exist.", 404)


def conflict(message: str) -> HTTPException:
    return api_error("conflict", message, 409)
