from pathlib import Path

import pytest

from cursor_agent_sdk.cli import parse_cli_args, main


def test_version(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "cursor-agent-sdk" in capsys.readouterr().out


def test_verbose_global_flag_position() -> None:
    cases = (
        (["--verbose", "--codegraph", "chat"], True),
        (["--codegraph", "--verbose", "chat"], True),
        (["chat", "--verbose"], False),
    )
    for argv, codegraph in cases:
        args = parse_cli_args(argv)
        assert args.verbose is True
        assert args.command == "chat"
        assert args.codegraph is (True if codegraph else None)


def test_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0


def test_completion_bash() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["completion", "bash"])
    assert exc.value.code == 0


def test_invalid_cwd(tmp_path: Path, capsys) -> None:
    missing = tmp_path / "nope"
    with pytest.raises(SystemExit) as exc:
        main(["session", "--cwd", str(missing)])
    assert exc.value.code == 1
    assert "not a directory" in capsys.readouterr().err


def test_codegraph_status_command(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "cursor_agent_sdk.codegraph.resolve_codegraph_command",
        lambda override=None: "/usr/bin/codegraph",
    )
    with pytest.raises(SystemExit) as exc:
        main(["codegraph", "status", "--cwd", str(tmp_path)])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "Enabled: True" in out
    assert "/usr/bin/codegraph" in out
