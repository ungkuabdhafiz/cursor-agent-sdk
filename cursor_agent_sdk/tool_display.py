"""Format tool-call lines for human-readable CLI output."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

_PATH_KEYS = ("path", "target_file", "file", "file_path", "uri", "downloadPath")
_SEARCH_KEYS = ("pattern", "query", "search_term", "glob_pattern", "glob")
_COMMAND_KEYS = ("command", "description")
_TEXT_KEYS = ("old_string", "new_string", "contents", "text")


def format_tool_line(name: str, args: Any, *, status: str = "running") -> str:
    """One-line summary: ``[tool] read src/main.py``."""
    summary = format_tool_summary(name, args)
    if status and status != "running":
        return f"[tool] {summary} ({status})"
    return f"[tool] {summary}"


def format_tool_summary(name: str, args: Any) -> str:
    data = _args_as_dict(args)
    if not data:
        return name

    details = _extract_details(data)
    if not details:
        compact = _compact_dict(data, limit=100)
        return f"{name} {compact}" if compact else name

    return f"{name} {details}"


def _extract_details(data: Mapping[str, Any]) -> str:
    parts: list[str] = []

    path = _first_str(data, _PATH_KEYS)
    if path:
        parts.append(_short_path(path))

    search = _first_str(data, _SEARCH_KEYS)
    if search:
        parts.append(f'pattern={_quote(search)}')

    command = _first_str(data, _COMMAND_KEYS)
    if command:
        parts.append(f"cmd={_quote(_truncate(command, 120))}")

    if not parts:
        # Edit/write helpers often only have path-like keys already handled;
        # surface a few other short scalar fields.
        skip = set(_PATH_KEYS + _SEARCH_KEYS + _COMMAND_KEYS + _TEXT_KEYS)
        extras = _compact_dict(
            {k: v for k, v in data.items() if k not in skip},
            limit=80,
        )
        if extras:
            parts.append(extras)

    return " ".join(parts)


def _args_as_dict(args: Any) -> dict[str, Any]:
    if args is None:
        return {}
    if isinstance(args, Mapping):
        return dict(args)
    if isinstance(args, str):
        try:
            parsed = json.loads(args)
        except json.JSONDecodeError:
            return {"input": args}
        if isinstance(parsed, Mapping):
            return dict(parsed)
        return {"input": args}
    return {}


def _first_str(data: Mapping[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _short_path(path: str) -> str:
    path = path.strip()
    home = _home_prefix()
    if home and path.startswith(home):
        return "~" + path[len(home) :]
    return path


def _home_prefix() -> str | None:
    try:
        from pathlib import Path

        return str(Path.home())
    except RuntimeError:
        return None


def _compact_dict(data: Mapping[str, Any], *, limit: int) -> str:
    parts: list[str] = []
    for key, value in data.items():
        if value is None or value == "":
            continue
        if isinstance(value, (dict, list)):
            rendered = _truncate(json.dumps(value, ensure_ascii=False), 40)
        else:
            rendered = _quote(_truncate(str(value).replace("\n", " "), 50))
        parts.append(f"{key}={rendered}")
    text = " ".join(parts)
    return _truncate(text, limit)


def _quote(value: str) -> str:
    if not value:
        return '""'
    if any(c.isspace() for c in value) or '"' in value:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."
