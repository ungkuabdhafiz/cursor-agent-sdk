"""Persist full agent run transcripts to chat.jsonl."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cursor_sdk import RunResult

from cursor_agent_sdk.model import format_model
from cursor_agent_sdk.session import chat_log_path

# Cap very large tool results / thinking blocks in the log file.
_MAX_TEXT_LEN = 32_000


def append_chat_log_event(cwd: Path, entry: dict[str, Any]) -> None:
    """Append one JSON object as a line to the project chat log."""
    path = chat_log_path(cwd)
    path.parent.mkdir(parents=True, exist_ok=True)
    if "timestamp" not in entry:
        entry = {**entry, "timestamp": _now()}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")


def log_user_prompt(
    cwd: Path,
    *,
    prompt: str,
    run_id: str,
    agent_id: str | None,
    mode: str | None,
) -> None:
    append_chat_log_event(
        cwd,
        {
            "role": "user",
            "run_id": run_id,
            "agent_id": agent_id,
            "mode": mode,
            "content": prompt,
        },
    )


def log_run_outcome(
    cwd: Path,
    *,
    run_id: str,
    agent_id: str | None,
    result: RunResult,
    streamed_text: bool,
) -> None:
    append_chat_log_event(
        cwd,
        {
            "role": "run",
            "run_id": run_id,
            "agent_id": agent_id,
            "status": result.status,
            "model": format_model(result.model),
            "duration_ms": result.duration_ms,
            "streamed_text": streamed_text,
            "result": _truncate(result.result) if result.result else None,
        },
    )


def serialize_sdk_message(
    message: Any,
    *,
    run_id: str,
    agent_id: str | None,
) -> dict[str, Any]:
    """Turn an SDK stream message into a JSON-serializable log entry."""
    base: dict[str, Any] = {
        "role": "agent",
        "run_id": run_id,
        "agent_id": agent_id,
        "message_type": message.type,
    }

    if message.type == "assistant":
        base["content"] = _assistant_text(message)
        return base

    if message.type == "thinking":
        base["content"] = _truncate(message.text)
        if getattr(message, "thinking_duration_ms", None):
            base["thinking_duration_ms"] = message.thinking_duration_ms
        return base

    if message.type == "tool_call":
        base.update(
            {
                "tool": message.name,
                "call_id": message.call_id,
                "status": message.status,
                "args": _truncate_value(message.args),
            }
        )
        if message.result is not None:
            base["result"] = _truncate_value(message.result)
        truncated = getattr(message, "truncated", None)
        if truncated:
            base["truncated"] = dict(truncated)
        return base

    if message.type == "status":
        base["status"] = message.status
        base["content"] = message.message
        return base

    if message.type == "system" and getattr(message, "model", None):
        base["model"] = format_model(message.model)
        return base

    if message.type == "task":
        base["status"] = getattr(message, "status", "")
        base["content"] = _truncate(getattr(message, "text", ""))
        return base

    return base


class BufferedChatLogger:
    """Aggregate streaming thinking/assistant chunks into single log lines."""

    def __init__(
        self,
        cwd: Path,
        *,
        run_id: str,
        agent_id: str | None,
    ) -> None:
        self._cwd = cwd
        self._run_id = run_id
        self._agent_id = agent_id
        self._thinking_parts: list[str] = []
        self._assistant_parts: list[str] = []
        self._thinking_duration_ms: int | None = None

    def __call__(self, message: Any) -> None:
        if message.type == "thinking":
            self._flush_assistant()
            if message.text:
                self._thinking_parts.append(message.text)
            duration = getattr(message, "thinking_duration_ms", None)
            if duration is not None:
                self._thinking_duration_ms = duration
            return

        if message.type == "assistant":
            self._flush_thinking()
            text = _assistant_text_raw(message)
            if text:
                self._assistant_parts.append(text)
            return

        self.flush()
        append_chat_log_event(
            self._cwd,
            serialize_sdk_message(
                message,
                run_id=self._run_id,
                agent_id=self._agent_id,
            ),
        )

    def flush(self) -> None:
        self._flush_thinking()
        self._flush_assistant()

    def _flush_thinking(self) -> None:
        if not self._thinking_parts:
            return
        entry: dict[str, Any] = {
            "role": "agent",
            "run_id": self._run_id,
            "agent_id": self._agent_id,
            "message_type": "thinking",
            "content": _truncate("".join(self._thinking_parts)),
        }
        if self._thinking_duration_ms is not None:
            entry["thinking_duration_ms"] = self._thinking_duration_ms
        append_chat_log_event(self._cwd, entry)
        self._thinking_parts.clear()
        self._thinking_duration_ms = None

    def _flush_assistant(self) -> None:
        if not self._assistant_parts:
            return
        append_chat_log_event(
            self._cwd,
            {
                "role": "agent",
                "run_id": self._run_id,
                "agent_id": self._agent_id,
                "message_type": "assistant",
                "content": _truncate("".join(self._assistant_parts)),
            },
        )
        self._assistant_parts.clear()


def make_message_logger(
    cwd: Path,
    *,
    run_id: str,
    agent_id: str | None,
) -> BufferedChatLogger:
    """Return a buffered logger for ``stream_run(..., log_message=...)``."""
    return BufferedChatLogger(cwd, run_id=run_id, agent_id=agent_id)


def append_chat_log(
    cwd: Path,
    *,
    prompt: str,
    mode: str | None,
    status: str,
    agent_id: str | None = None,
) -> None:
    """Backward-compatible minimal log line (prefer full turn logging in tool.send)."""
    append_chat_log_event(
        cwd,
        {
            "role": "user",
            "agent_id": agent_id,
            "mode": mode,
            "content": prompt,
            "legacy_status": status,
        },
    )


def _assistant_text(message: Any) -> str:
    return _truncate(_assistant_text_raw(message))


def _assistant_text_raw(message: Any) -> str:
    parts: list[str] = []
    for block in message.message.content:
        if getattr(block, "type", None) == "text" and block.text:
            parts.append(block.text)
    return "".join(parts)


def _truncate(value: str | None) -> str | None:
    if value is None:
        return None
    if len(value) <= _MAX_TEXT_LEN:
        return value
    return value[: _MAX_TEXT_LEN - 20] + "\n… [truncated]"


def _truncate_value(value: Any) -> Any:
    if isinstance(value, str):
        return _truncate(value)
    if isinstance(value, (dict, list)):
        encoded = json.dumps(value, ensure_ascii=False, default=str)
        if len(encoded) <= _MAX_TEXT_LEN:
            return value
        return _truncate(encoded)
    text = repr(value)
    return _truncate(text) if len(text) > _MAX_TEXT_LEN else value


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
