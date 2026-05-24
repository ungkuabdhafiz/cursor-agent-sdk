"""CodeGraph MCP integration for cursor-agent-sdk."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from cursor_sdk import StdioMcpServerConfig
from cursor_sdk.types import McpServerConfig

CODEGRAPH_SERVER_NAME = "codegraph"
CODEGRAPH_DB_NAME = "codegraph.db"


@dataclass(frozen=True)
class CodeGraphSettings:
    enabled: bool = True
    command: str | None = None
    no_watch: bool = False

    @classmethod
    def from_mapping(cls, data: dict | None) -> CodeGraphSettings:
        if not data:
            return cls()
        return cls(
            enabled=_bool(data.get("enabled", True), default=True),
            command=_optional_str(data.get("command")),
            no_watch=_bool(data.get("no_watch", False), default=False),
        )


@dataclass(frozen=True)
class CodeGraphStatus:
    enabled: bool
    command: str | None
    index_initialized: bool
    project: Path


def resolve_codegraph_command(override: str | None = None) -> str | None:
    if override:
        path = Path(override).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return str(path.resolve())
        return None

    env_bin = os.environ.get("CODEGRAPH_BIN", "").strip()
    if env_bin:
        path = Path(env_bin).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return str(path.resolve())

    found = shutil.which("codegraph")
    return found


def is_index_initialized(project: Path) -> bool:
    db_path = project.resolve() / ".codegraph" / CODEGRAPH_DB_NAME
    return db_path.is_file()


def build_codegraph_mcp(
    project: Path,
    *,
    command: str,
    no_watch: bool = False,
) -> StdioMcpServerConfig:
    args = ["serve", "--mcp", "--path", str(project.resolve())]
    if no_watch:
        args.append("--no-watch")
    return StdioMcpServerConfig(command=command, args=args)


def prepare_mcp_servers(
    project: Path,
    servers: dict[str, McpServerConfig],
    settings: CodeGraphSettings,
) -> tuple[dict[str, McpServerConfig], list[str]]:
    """Return MCP servers with CodeGraph injected when enabled."""
    merged = dict(servers)
    warnings: list[str] = []

    if not settings.enabled:
        return merged, warnings

    if CODEGRAPH_SERVER_NAME in merged:
        return merged, warnings

    command = resolve_codegraph_command(settings.command)
    if command is None:
        warnings.append(
            "CodeGraph is enabled but the codegraph binary was not found. "
            "Install codegraph, add it to PATH, or set CODEGRAPH_BIN. "
            "Use --no-codegraph to silence this."
        )
        return merged, warnings

    merged[CODEGRAPH_SERVER_NAME] = build_codegraph_mcp(
        project,
        command=command,
        no_watch=settings.no_watch,
    )

    if not is_index_initialized(project):
        warnings.append(
            f"CodeGraph index not found under {project}/.codegraph/. "
            f"Run: cursor-agent-sdk codegraph init --cwd {project}"
        )

    return merged, warnings


def inspect_status(project: Path, settings: CodeGraphSettings) -> CodeGraphStatus:
    return CodeGraphStatus(
        enabled=settings.enabled,
        command=resolve_codegraph_command(settings.command),
        index_initialized=is_index_initialized(project),
        project=project.resolve(),
    )


def run_init(project: Path, settings: CodeGraphSettings) -> int:
    command = resolve_codegraph_command(settings.command)
    if command is None:
        print(
            "error: codegraph binary not found (install codegraph or set CODEGRAPH_BIN)",
            file=sys.stderr,
        )
        return 1

    result = subprocess.run(
        [command, "init", "-i"],
        cwd=str(project.resolve()),
        check=False,
    )
    return result.returncode


def emit_warnings(warnings: list[str]) -> None:
    for message in warnings:
        print(f"warning: {message}", file=sys.stderr)


def _bool(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("1", "true", "yes", "on")
    return bool(value)


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
