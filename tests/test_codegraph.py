from pathlib import Path

from cursor_agent_sdk.codegraph import (
    CodeGraphSettings,
    build_codegraph_mcp,
    is_index_initialized,
    prepare_mcp_servers,
    resolve_codegraph_command,
)
from cursor_agent_sdk.config import ToolConfig, build_agent_options


def test_is_index_initialized(tmp_path: Path) -> None:
    assert is_index_initialized(tmp_path) is False
    db_dir = tmp_path / ".codegraph"
    db_dir.mkdir()
    (db_dir / "codegraph.db").write_text("", encoding="utf-8")
    assert is_index_initialized(tmp_path) is True


def test_build_codegraph_mcp_uses_project_cwd(tmp_path: Path) -> None:
    server = build_codegraph_mcp(tmp_path, command="/usr/bin/codegraph", no_watch=True)
    assert server.command == "/usr/bin/codegraph"
    assert server.args == ["serve", "--mcp", "--no-watch"]
    assert server.cwd == str(tmp_path.resolve())


def test_prepare_mcp_servers_injects_codegraph(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "cursor_agent_sdk.codegraph.resolve_codegraph_command",
        lambda override=None: "/usr/bin/codegraph",
    )
    (tmp_path / ".codegraph").mkdir()
    (tmp_path / ".codegraph" / "codegraph.db").write_text("", encoding="utf-8")

    servers, warnings = prepare_mcp_servers(tmp_path, {}, CodeGraphSettings())
    assert "codegraph" in servers
    assert warnings == []


def test_prepare_mcp_servers_skips_when_disabled(tmp_path: Path) -> None:
    servers, warnings = prepare_mcp_servers(
        tmp_path,
        {},
        CodeGraphSettings(enabled=False),
    )
    assert servers == {}
    assert warnings == []


def test_prepare_mcp_servers_respects_existing_entry(tmp_path: Path, monkeypatch) -> None:
    from cursor_sdk import StdioMcpServerConfig

    monkeypatch.setattr(
        "cursor_agent_sdk.codegraph.resolve_codegraph_command",
        lambda override=None: "/usr/bin/codegraph",
    )
    custom = StdioMcpServerConfig(command="custom", args=["serve"])
    servers, _ = prepare_mcp_servers(
        tmp_path,
        {"codegraph": custom},
        CodeGraphSettings(),
    )
    assert servers["codegraph"] is custom


def test_prepare_mcp_servers_warns_when_binary_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "cursor_agent_sdk.codegraph.resolve_codegraph_command",
        lambda override=None: None,
    )
    servers, warnings = prepare_mcp_servers(tmp_path, {}, CodeGraphSettings())
    assert "codegraph" not in servers
    assert len(warnings) == 1


def test_build_agent_options_includes_codegraph(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("CURSOR_API_KEY", "cursor_test")
    monkeypatch.setattr(
        "cursor_agent_sdk.codegraph.resolve_codegraph_command",
        lambda override=None: "/usr/bin/codegraph",
    )
    (tmp_path / ".codegraph").mkdir()
    (tmp_path / ".codegraph" / "codegraph.db").write_text("", encoding="utf-8")

    config = ToolConfig()
    options = build_agent_options(tmp_path, config)
    assert options.mcp_servers is not None
    assert "codegraph" in options.mcp_servers


def test_build_agent_options_respects_no_codegraph(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CURSOR_API_KEY", "cursor_test")
    monkeypatch.setattr(
        "cursor_agent_sdk.codegraph.resolve_codegraph_command",
        lambda override=None: "/usr/bin/codegraph",
    )
    config = ToolConfig(codegraph=CodeGraphSettings(enabled=False))
    options = build_agent_options(tmp_path, config)
    assert options.mcp_servers in (None, {})


def test_resolve_codegraph_command_from_env(tmp_path: Path, monkeypatch) -> None:
    fake = tmp_path / "codegraph"
    fake.write_text("#!/bin/sh\n", encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setenv("CODEGRAPH_BIN", str(fake))
    assert resolve_codegraph_command() == str(fake.resolve())
