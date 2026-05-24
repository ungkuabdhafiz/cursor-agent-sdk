from cursor_sdk import AuthenticationError, CursorAgentError, RateLimitError

from cursor_agent_sdk.errors import format_error, format_error_hint


def test_missing_session_hint() -> None:
    err = CursorAgentError("no session", code="missing_session")
    assert "cursor-agent-sdk plan" in (format_error_hint(err) or "")


def test_auth_hint() -> None:
    err = AuthenticationError("bad key", code="unauthorized")
    assert "CURSOR_API_KEY" in (format_error_hint(err) or "")


def test_rate_limit_hint() -> None:
    err = RateLimitError("slow down", retry_after="30")
    hint = format_error_hint(err) or ""
    assert "30" in hint


def test_format_error() -> None:
    err = CursorAgentError("oops", code="test")
    assert format_error(err) == "oops"
