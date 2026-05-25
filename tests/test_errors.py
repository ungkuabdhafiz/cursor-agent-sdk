from cursor_sdk import (
    AuthenticationError,
    CursorAgentError,
    InternalServerError,
    RateLimitError,
)

from cursor_agent_sdk.errors import format_error, format_error_details, format_error_hint


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
    assert format_error(err) == "oops (code: test)"


def test_format_error_details() -> None:
    err = CursorAgentError(
        "internal error",
        code="internal",
        status=200,
        request_id="req-abc",
        proto_error_code="SDK_ERROR_CODE_INTERNAL",
        details=[{"type": "cursor.v1.SdkErrorDetails", "requestId": "req-abc"}],
        is_retryable=True,
        cause=RuntimeError("bridge reset"),
    )
    text = "\n".join(format_error_details(err))
    assert "request_id: req-abc" in text
    assert "proto_error_code: SDK_ERROR_CODE_INTERNAL" in text
    assert "retryable: true" in text
    assert "details:" in text
    assert "req-abc" in text
    assert "RuntimeError: bridge reset" in text


def test_format_error_details_generic_cause() -> None:
    inner = ValueError("bad cwd")
    outer = RuntimeError("session failed")
    outer.__cause__ = inner
    text = "\n".join(format_error_details(outer))
    assert "ValueError: bad cwd" in text


def test_format_error_details_minimal_internal() -> None:
    err = InternalServerError("internal error", code="internal", status=200)
    text = "\n".join(format_error_details(err))
    assert "type: InternalServerError" in text
    assert "request_id: (none)" in text
    assert "details: (none)" in text
    assert "code: internal" in text
