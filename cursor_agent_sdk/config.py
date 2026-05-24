"""Load defaults from TOML config files and environment."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from cursor_sdk import HttpMcpServerConfig, SandboxOptions, StdioMcpServerConfig
from cursor_sdk.types import McpServerConfig, SettingSource

from cursor_agent_sdk.session import home_dir

SettingSourceInput = SettingSource | str

# Optional per-repo overrides (committed or local); sessions live in home_dir().
PROJECT_CONFIG_DIRNAME = ".cursor-agent-sdk"

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[no-redef]


DEFAULT_MODEL_ID = "composer-2.5"
PROJECT_CONFIG_NAME = "config.toml"


def user_config_path() -> Path:
    return home_dir() / PROJECT_CONFIG_NAME


def project_config_path(cwd: Path) -> Path:
    return cwd.resolve() / PROJECT_CONFIG_DIRNAME / PROJECT_CONFIG_NAME


@dataclass
class ToolConfig:
    model_id: str = DEFAULT_MODEL_ID
    fast: bool | None = None
    show_tools: bool = True
    show_meta: bool = False
    default_mode: Literal["plan", "agent"] = "plan"
    session_name: str = "default"
    setting_sources: tuple[SettingSourceInput, ...] = ()
    sandbox_enabled: bool | None = None
    mcp_servers: dict[str, McpServerConfig] = field(default_factory=dict)

    def merge_cli(
        self,
        *,
        model_id: str | None = None,
        fast: bool | None = None,
        show_tools: bool | None = None,
        show_meta: bool | None = None,
        session_name: str | None = None,
        rules: SequenceSettingSources | None = None,
        sandbox: bool | None = None,
    ) -> ToolConfig:
        sources = self.setting_sources
        if rules is not None:
            sources = tuple(rules)
        return ToolConfig(
            model_id=model_id or self.model_id,
            fast=fast if fast is not None else self.fast,
            show_tools=self.show_tools if show_tools is None else show_tools,
            show_meta=self.show_meta if show_meta is None else show_meta,
            default_mode=self.default_mode,
            session_name=session_name or self.session_name,
            setting_sources=sources,
            sandbox_enabled=sandbox if sandbox is not None else self.sandbox_enabled,
            mcp_servers=dict(self.mcp_servers),
        )


SequenceSettingSources = list[SettingSourceInput] | tuple[SettingSourceInput, ...]


def config_search_paths(cwd: Path) -> list[Path]:
    """Later paths override earlier ones (repo overrides home)."""
    return [
        user_config_path(),
        project_config_path(cwd),
    ]


def load_config(cwd: Path | None = None) -> ToolConfig:
    """Merge project config, user config, then environment."""
    merged: dict[str, Any] = {}
    for path in config_search_paths(cwd or Path.cwd()):
        if path.is_file():
            merged = _deep_merge(merged, _read_toml(path))

    config = _config_from_mapping(merged)
    return _apply_env(config)


def _read_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    return data if isinstance(data, dict) else {}


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _config_from_mapping(data: Mapping[str, Any]) -> ToolConfig:
    defaults = data.get("defaults") or {}
    if not isinstance(defaults, dict):
        defaults = {}

    model_section = data.get("model") or {}
    if not isinstance(model_section, dict):
        model_section = {}

    local_section = data.get("local") or {}
    if not isinstance(local_section, dict):
        local_section = {}

    model_id = str(
        model_section.get("id")
        or defaults.get("model")
        or DEFAULT_MODEL_ID
    )
    fast = _optional_bool(model_section.get("fast", defaults.get("fast")))
    show_tools = bool(defaults.get("show_tools", True))
    show_meta = bool(defaults.get("show_meta", False))
    default_mode = str(defaults.get("mode", "plan"))
    if default_mode not in ("plan", "agent"):
        default_mode = "plan"

    session_name = str(defaults.get("session_name", "default"))
    setting_sources = _parse_setting_sources(local_section.get("setting_sources"))
    sandbox_enabled = _optional_bool(local_section.get("sandbox_enabled"))

    mcp_servers = _parse_mcp_servers(data.get("mcp_servers"))

    return ToolConfig(
        model_id=model_id,
        fast=fast,
        show_tools=show_tools,
        show_meta=show_meta,
        default_mode=default_mode,  # type: ignore[arg-type]
        session_name=session_name,
        setting_sources=setting_sources,
        sandbox_enabled=sandbox_enabled,
        mcp_servers=mcp_servers,
    )


def _apply_env(config: ToolConfig) -> ToolConfig:
    model_id = os.environ.get("CURSOR_AGENT_MODEL", config.model_id)
    fast = config.fast
    if os.environ.get("COMPOSER_FAST") is not None:
        fast = os.environ.get("COMPOSER_FAST", "false").lower() in ("1", "true", "yes")
    return ToolConfig(
        model_id=model_id,
        fast=fast,
        show_tools=config.show_tools,
        show_meta=config.show_meta,
        default_mode=config.default_mode,
        session_name=config.session_name,
        setting_sources=config.setting_sources,
        sandbox_enabled=config.sandbox_enabled,
        mcp_servers=config.mcp_servers,
    )


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("1", "true", "yes", "on")
    return bool(value)


def _parse_setting_sources(value: Any) -> tuple[SettingSourceInput, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value)
    return ()


def _parse_mcp_servers(value: Any) -> dict[str, McpServerConfig]:
    if not isinstance(value, dict):
        return {}
    servers: dict[str, McpServerConfig] = {}
    for name, raw in value.items():
        if not isinstance(raw, dict):
            continue
        servers[str(name)] = _mcp_server_from_dict(raw)
    return servers


def _mcp_server_from_dict(raw: dict[str, Any]) -> McpServerConfig:
    server_type = str(raw.get("type", "stdio")).lower()
    if server_type in ("http", "sse"):
        return HttpMcpServerConfig(
            url=str(raw["url"]),
            type=server_type,  # type: ignore[arg-type]
            headers=dict(raw.get("headers") or {}),
        )
    return StdioMcpServerConfig(
        command=str(raw.get("command", "")),
        args=list(raw.get("args") or ()),
        env=dict(raw.get("env") or {}),
        cwd=raw.get("cwd"),
    )


def build_local_options(cwd: Path, config: ToolConfig):
    from cursor_sdk import LocalAgentOptions

    sandbox = None
    if config.sandbox_enabled is not None:
        sandbox = SandboxOptions(enabled=config.sandbox_enabled)

    sources = config.setting_sources or None
    return LocalAgentOptions(
        cwd=str(cwd.resolve()),
        setting_sources=sources,
        sandbox_options=sandbox,
    )


def build_agent_options(cwd: Path, config: ToolConfig, *, mode: str | None = None):
    from cursor_sdk import AgentOptions

    from cursor_agent_sdk.model import build_model

    return AgentOptions(
        model=build_model(config),
        api_key=resolve_api_key(allow_missing=True),
        local=build_local_options(cwd, config),
        mcp_servers=config.mcp_servers or None,
        mode=mode,  # type: ignore[arg-type]
    )


def resolve_api_key(*, allow_missing: bool = False) -> str | None:
    key = os.environ.get("CURSOR_API_KEY", "").strip()
    if key:
        return key
    if allow_missing:
        return None
    raise RuntimeError(
        "CURSOR_API_KEY is not set. Create a key at "
        "https://cursor.com/dashboard/integrations and run:\n"
        '  export CURSOR_API_KEY="cursor_..."'
    )


def require_api_key() -> str:
    key = resolve_api_key(allow_missing=False)
    assert key is not None
    return key
