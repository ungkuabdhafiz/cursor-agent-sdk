"""CLI and library for multi-turn Cursor SDK agent sessions."""

from cursor_agent_sdk.config import ToolConfig, load_config
from cursor_agent_sdk.session import (
    ProjectSession,
    SessionCwdMismatchError,
    clear_session,
    list_sessions,
    load_session,
    save_session,
    session_file,
)
from cursor_agent_sdk.tool import AgentTool

__version__ = "0.2.0"

__all__ = [
    "__version__",
    "AgentTool",
    "ProjectSession",
    "SessionCwdMismatchError",
    "ToolConfig",
    "clear_session",
    "list_sessions",
    "load_config",
    "load_session",
    "save_session",
    "session_file",
]
