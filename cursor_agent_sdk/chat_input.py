"""Read user input for interactive chat, including multiline paste."""

from __future__ import annotations

import select
import sys

PASTE_COMMANDS = frozenset({"/paste", "/multiline"})
PASTE_END_MARKER = "."


def read_chat_input(prompt: str = "cursor-agent-sdk> ") -> str | None:
    """Read one chat message.

    Supports:
    - ``/paste`` or ``/multiline`` — enter multiline mode (end with a lone ``.``)
    - Multiline clipboard paste — extra lines buffered after the first ``input()``
      are collected automatically when stdin is a TTY
    """
    try:
        first = input(prompt)
    except EOFError:
        return None

    stripped = first.strip()
    if stripped in PASTE_COMMANDS:
        return read_multiline_paste()

    if not sys.stdin.isatty():
        return first

    extra = _drain_buffered_stdin_lines()
    if extra:
        return "\n".join([first, *extra])

    return first


def read_multiline_paste() -> str | None:
    """Read lines until a lone ``.`` on its own line (email-style end marker)."""
    print(
        "Multiline input — paste your text, then type a lone '.' on its own line to send.",
        file=sys.stderr,
    )
    lines: list[str] = []
    while True:
        try:
            line = input("... ")
        except EOFError:
            break
        if line.strip() == PASTE_END_MARKER:
            break
        lines.append(line)

    text = "\n".join(lines)
    return text if text.strip() else None


def _drain_buffered_stdin_lines() -> list[str]:
    """Collect lines already queued on stdin (e.g. rest of a multiline paste)."""
    lines: list[str] = []
    while True:
        ready, _, _ = select.select([sys.stdin], [], [], 0.01)
        if not ready:
            break
        line = sys.stdin.readline()
        if not line:
            break
        lines.append(line.rstrip("\n"))
    return lines
