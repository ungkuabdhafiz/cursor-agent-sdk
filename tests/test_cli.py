from pathlib import Path

import pytest

from cursor_agent_sdk.cli import main


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
