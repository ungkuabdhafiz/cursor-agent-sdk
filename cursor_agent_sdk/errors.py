"""User-facing error hints for Cursor SDK exceptions."""

from __future__ import annotations

import json
import sys
import traceback
from collections.abc import Mapping
from typing import Any, TextIO

from cursor_sdk import (
    AgentBusyError,
    AuthenticationError,
    ConfigurationError,
    CursorAgentError,
    CursorSDKError,
    IntegrationNotConnectedError,
    InternalServerError,
    NetworkError,
    NotFoundError,
    RateLimitError,
    UnknownAgentError,
)


def format_error(err: BaseException) -> str:
    if isinstance(err, CursorAgentError):
        return _format_cursor_error(err)
    return str(err)


def format_error_hint(err: BaseException) -> str | None:
    if isinstance(err, CursorAgentError):
        return _hint_for_cursor_error(err)
    return None


def format_error_details(err: BaseException) -> list[str]:
    """Extra fields for debugging (use with --verbose). Always non-empty."""
    if isinstance(err, CursorAgentError):
        return _format_cursor_error_details(err)
    return _format_generic_error_details(err)


def print_error_details(
    err: BaseException,
    *,
    file: TextIO | None = None,
    include_traceback: bool = True,
) -> None:
    from cursor_agent_sdk import __version__

    lines = format_error_details(err)
    out = file or sys.stderr
    print(f"--- error details (cursor-agent-sdk {__version__}) ---", file=out)
    for line in lines:
        print(line, file=out)
    if include_traceback and err.__traceback__ is not None:
        traceback.print_exception(type(err), err, err.__traceback__, file=out)


def _format_cursor_error_details(err: CursorAgentError) -> list[str]:
    lines = [
        f"type: {type(err).__name__}",
        f"repr: {err!r}",
        f"message: {err.message}",
        f"code: {err.code or '(none)'}",
        f"status: {err.status if err.status is not None else '(none)'}",
        f"request_id: {err.request_id or '(none)'}",
        f"proto_error_code: {err.proto_error_code or '(none)'}",
        f"retryable: {str(err.is_retryable).lower()}",
        f"retry_after: {err.retry_after or '(none)'}",
    ]
    if err.details:
        lines.append("details:")
        for index, detail in enumerate(err.details):
            lines.append(f"  [{index}] {_format_detail(detail)}")
    else:
        lines.append("details: (none)")
    if err.cause is not None:
        lines.append(f"cause: {type(err.cause).__name__}: {err.cause}")
    else:
        lines.append("cause: (none)")
    if err.headers:
        lines.append(f"headers: {json.dumps(err.headers, ensure_ascii=False)}")
    else:
        lines.append("headers: (none)")
    return lines


def _format_generic_error_details(err: BaseException) -> list[str]:
    lines = [
        f"type: {type(err).__name__}",
        f"repr: {err!r}",
    ]
    cause = err.__cause__
    if cause is not None and cause is not err:
        lines.append(f"cause: {type(cause).__name__}: {cause}")
    else:
        lines.append("cause: (none)")
    return lines


def _format_detail(detail: Any) -> str:
    if isinstance(detail, Mapping):
        return json.dumps(dict(detail), ensure_ascii=False, indent=2, default=str)
    return repr(detail)


def _format_cursor_error(err: CursorAgentError) -> str:
    parts = [err.message]
    if err.code and err.message.lower() != err.code.replace("_", " "):
        parts.append(f"(code: {err.code})")
    if err.status:
        parts.append(f"(HTTP {err.status})")
    return " ".join(parts)


def _hint_for_cursor_error(err: CursorAgentError) -> str | None:
    if isinstance(err, ConfigurationError) and err.code == "missing_api_key":
        return (
            "Set CURSOR_API_KEY from https://cursor.com/dashboard/integrations\n"
            '  export CURSOR_API_KEY="cursor_..."'
        )

    if isinstance(err, UnknownAgentError) or (
        isinstance(err, NotFoundError) and getattr(err, "code", "") == "missing_session"
    ):
        return (
            "Start a session with:\n"
            "  cursor-agent-sdk plan \"your task\"\n"
            "  cursor-agent-sdk ask \"your task\"\n"
            "Or pass --new to start fresh."
        )

    if isinstance(err, CursorAgentError) and err.code == "missing_session":
        return (
            "No saved session for this project. Run:\n"
            "  cursor-agent-sdk plan \"...\"\n"
            "  cursor-agent-sdk ask \"...\""
        )

    if isinstance(err, AuthenticationError):
        return (
            "Set CURSOR_API_KEY from https://cursor.com/dashboard/integrations\n"
            "  export CURSOR_API_KEY=\"cursor_...\""
        )

    if isinstance(err, RateLimitError):
        hint = "Rate limit exceeded. Wait and retry"
        if err.retry_after:
            hint += f" (retry after {err.retry_after})"
        hint += ", or use --fast for the fast tier."
        return hint

    if isinstance(err, AgentBusyError):
        return (
            "Another run is in progress for this agent. "
            "Wait for it to finish or use --new."
        )

    if isinstance(err, IntegrationNotConnectedError):
        if err.help_url:
            return f"Connect integration ({err.provider}): {err.help_url}"
        return "Connect the required integration in your Cursor dashboard."

    if isinstance(err, InternalServerError):
        return (
            "The Cursor SDK bridge hit an internal error. Try a fresh session:\n"
            "  cursor-agent-sdk chat --new\n"
            "  cursor-agent-sdk clear && cursor-agent-sdk chat\n"
            "If it keeps failing, wait a minute and retry."
        )

    if isinstance(err, NetworkError):
        return "Check your network connection and that the Cursor SDK bridge is running."

    if isinstance(err, UnknownAgentError):
        return (
            "Agent not found. It may have expired. Run `cursor-agent-sdk clear` "
            "and start with plan or ask --new."
        )

    if isinstance(err, CursorSDKError) and err.is_retryable:
        return "This error may be retryable; run the command again."

    return None
