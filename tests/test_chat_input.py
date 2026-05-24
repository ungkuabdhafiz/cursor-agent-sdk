from unittest.mock import patch

import pytest

from cursor_agent_sdk import chat_input
from cursor_agent_sdk.chat_input import read_chat_input, read_multiline_paste


def test_read_multiline_paste_collects_until_dot(monkeypatch) -> None:
    lines = iter(["line one", "line two", ".", "ignored"])
    monkeypatch.setattr("builtins.input", lambda _: next(lines))

    assert read_multiline_paste() == "line one\nline two"


def test_read_multiline_paste_empty_returns_none(monkeypatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _: ".")

    assert read_multiline_paste() is None


def test_read_chat_input_paste_command(monkeypatch) -> None:
    calls = iter(["/paste", "hello", "."])
    monkeypatch.setattr("builtins.input", lambda _: next(calls))

    assert read_chat_input() == "hello"


def test_read_chat_input_drains_buffered_lines(monkeypatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _: "first line")
    monkeypatch.setattr(
        chat_input,
        "_drain_buffered_stdin_lines",
        lambda: ["second line", "third line"],
    )

    with patch.object(chat_input.sys.stdin, "isatty", return_value=True):
        assert read_chat_input() == "first line\nsecond line\nthird line"


def test_read_chat_input_eof(monkeypatch) -> None:
    def raise_eof(_: str = "") -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", raise_eof)

    assert read_chat_input() is None


def test_read_chat_input_single_line_non_tty(monkeypatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _: "only line")

    with patch.object(chat_input.sys.stdin, "isatty", return_value=False):
        assert read_chat_input() == "only line"
