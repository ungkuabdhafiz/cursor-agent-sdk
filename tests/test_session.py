import json
from pathlib import Path

import pytest

from cursor_agent_sdk.session import (
    SESSION_VERSION,
    ProjectSession,
    SessionCwdMismatchError,
    clear_session,
    list_sessions,
    load_session,
    save_session,
    session_file,
    validate_session_cwd,
)


def test_session_roundtrip(tmp_path: Path) -> None:
    session = ProjectSession.create(
        agent_id="agent-123",
        cwd=tmp_path,
        mode="plan",
        session_name="default",
    )
    save_session(tmp_path, session)
    loaded = load_session(tmp_path)
    assert loaded is not None
    assert loaded.agent_id == "agent-123"
    assert loaded.last_mode == "plan"
    assert loaded.version == SESSION_VERSION


def test_named_session_path(tmp_path: Path) -> None:
    assert (
        session_file(tmp_path, "auth")
        == tmp_path / ".cursor-agent-sdk" / "sessions" / "auth.json"
    )


def test_load_corrupt_json(tmp_path: Path) -> None:
    path = session_file(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    assert load_session(tmp_path) is None


def test_load_missing_agent_id(tmp_path: Path) -> None:
    path = session_file(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"cwd": str(tmp_path)}), encoding="utf-8")
    assert load_session(tmp_path) is None


def test_clear_session(tmp_path: Path) -> None:
    session = ProjectSession.create(agent_id="a", cwd=tmp_path)
    save_session(tmp_path, session)
    assert clear_session(tmp_path) is True
    assert load_session(tmp_path) is None
    assert clear_session(tmp_path) is False


def test_list_sessions(tmp_path: Path) -> None:
    save_session(
        tmp_path,
        ProjectSession.create(agent_id="a", cwd=tmp_path, session_name="default"),
    )
    save_session(
        tmp_path,
        ProjectSession.create(agent_id="b", cwd=tmp_path, session_name="auth"),
    )
    names = list_sessions(tmp_path)
    assert "default" in names
    assert "auth" in names


def test_migrate_legacy_session_dir(tmp_path: Path) -> None:
    legacy = tmp_path / ".cursor-agent"
    legacy.mkdir()
    (legacy / "session.json").write_text(
        '{"agent_id": "agent-legacy", "cwd": "' + str(tmp_path) + '"}',
        encoding="utf-8",
    )
    loaded = load_session(tmp_path)
    assert loaded is not None
    assert loaded.agent_id == "agent-legacy"
    assert (tmp_path / ".cursor-agent-sdk").is_dir()
    assert not legacy.exists()


def test_validate_session_cwd_mismatch(tmp_path: Path) -> None:
    other = tmp_path / "other"
    other.mkdir()
    session = ProjectSession.create(agent_id="a", cwd=other)
    with pytest.raises(SessionCwdMismatchError):
        validate_session_cwd(session, tmp_path)
