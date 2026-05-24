"""User-facing error hints for Cursor SDK exceptions."""

from __future__ import annotations

from cursor_sdk import (
    AgentBusyError,
    AuthenticationError,
    CursorAgentError,
    CursorSDKError,
    IntegrationNotConnectedError,
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


def _format_cursor_error(err: CursorAgentError) -> str:
    return err.message


def _hint_for_cursor_error(err: CursorAgentError) -> str | None:
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
