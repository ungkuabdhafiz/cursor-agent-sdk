"""CLI and library for multi-turn Cursor SDK agent sessions."""

from cursor_agent_sdk.config import ToolConfig, load_config, user_config_path
from cursor_agent_sdk.chat_log import append_chat_log, append_chat_log_event
from cursor_agent_sdk.session import (
    ProjectMeta,
    ProjectSession,
    SessionCwdMismatchError,
    chat_history_path,
    chat_log_path,
    clear_session,
    home_dir,
    list_projects,
    list_sessions,
    load_session,
    project_store_dir,
    save_session,
    session_file,
)
from cursor_agent_sdk.tool import AgentTool

__version__ = "0.2.0"

__all__ = [
    "__version__",
    "AgentTool",
    "ProjectMeta",
    "ProjectSession",
    "SessionCwdMismatchError",
    "ToolConfig",
    "append_chat_log",
    "append_chat_log_event",
    "chat_history_path",
    "chat_log_path",
    "clear_session",
    "home_dir",
    "list_projects",
    "list_sessions",
    "load_config",
    "load_session",
    "project_store_dir",
    "save_session",
    "session_file",
    "user_config_path",
]
