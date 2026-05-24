"""Token-efficient defaults for cursor-agent-sdk."""

from __future__ import annotations

import sys
from pathlib import Path

from cursor_agent_sdk.codegraph import CodeGraphSettings
from cursor_agent_sdk.config import ToolConfig
from cursor_agent_sdk.session import load_session

LEAN_RULES: tuple[str, ...] = ("project",)

_LEAN_BANNER = """\
Lean mode: project rules only, CodeGraph MCP off (use --codegraph to enable).
Tips: scope with --cwd, use plan then send --mode agent, --new per task to limit context.\
"""


def apply_lean(
    config: ToolConfig,
    *,
    rules_explicit: bool,
    codegraph_explicit: bool,
) -> ToolConfig:
    """Apply token-saving overrides; respect explicit CLI --rules / --codegraph."""
    sources = config.setting_sources if rules_explicit else LEAN_RULES

    codegraph = config.codegraph
    if not codegraph_explicit:
        codegraph = CodeGraphSettings(
            enabled=False,
            command=codegraph.command,
            no_watch=codegraph.no_watch,
        )

    return ToolConfig(
        model_id=config.model_id,
        fast=config.fast,
        show_tools=config.show_tools,
        show_meta=False,
        default_mode="plan",
        session_name=config.session_name,
        setting_sources=sources,
        sandbox_enabled=config.sandbox_enabled,
        mcp_servers=dict(config.mcp_servers),
        codegraph=codegraph,
        lean=True,
    )


def emit_lean_banner(config: ToolConfig) -> None:
    if config.lean:
        print(_LEAN_BANNER, file=sys.stderr)
        print(file=sys.stderr)


def warn_lean_session_resume(
    cwd: Path,
    session_name: str,
    *,
    lean: bool,
    force_new: bool,
) -> None:
    if not lean or force_new:
        return
    session = load_session(cwd, session_name)
    if session is None:
        return
    print(
        "warning: lean mode resumed an existing session — context grows each turn. "
        "Use --new, `cursor-agent-sdk clear`, or /clear in chat for a fresh task.",
        file=sys.stderr,
    )
