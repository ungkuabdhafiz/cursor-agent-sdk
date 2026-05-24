import json
from pathlib import Path

import pytest

from cursor_agent_sdk.session import (
    SESSION_VERSION,
    ProjectSession,
    SessionCwdMismatchError,
    append_chat_log,
    chat_log_path,
    clear_session,
    home_dir,
    list_projects,
    list_sessions,
    load_session,
    project_key,
    project_store_dir,
    save_session,
    session_file,
    validate_session_cwd,
)


def test_session_roundtrip(isolated_home: Path, tmp_path: Path) -> None:
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
    assert (isolated_home / ".cursor-agent-sdk" / "projects").is_dir()


def test_named_session_path(isolated_home: Path, tmp_path: Path) -> None:
    key = project_key(tmp_path)
    assert session_file(tmp_path, "auth") == (
        isolated_home / ".cursor-agent-sdk" / "projects" / key / "sessions" / "auth.json"
    )


def test_load_corrupt_json(isolated_home: Path, tmp_path: Path) -> None:
    path = session_file(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    assert load_session(tmp_path) is None


def test_load_missing_agent_id(isolated_home: Path, tmp_path: Path) -> None:
    path = session_file(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"cwd": str(tmp_path)}), encoding="utf-8")
    assert load_session(tmp_path) is None


def test_clear_session(isolated_home: Path, tmp_path: Path) -> None:
    session = ProjectSession.create(agent_id="a", cwd=tmp_path)
    save_session(tmp_path, session)
    assert clear_session(tmp_path) is True
    assert load_session(tmp_path) is None
    assert clear_session(tmp_path) is False


def test_list_sessions(isolated_home: Path, tmp_path: Path) -> None:
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


def test_migrate_legacy_repo_dir(isolated_home: Path, tmp_path: Path) -> None:
    legacy = tmp_path / ".cursor-agent"
    legacy.mkdir()
    (legacy / "session.json").write_text(
        json.dumps({"agent_id": "agent-legacy", "cwd": str(tmp_path)}),
        encoding="utf-8",
    )
    loaded = load_session(tmp_path)
    assert loaded is not None
    assert loaded.agent_id == "agent-legacy"
    store = project_store_dir(tmp_path)
    assert store.is_dir()
    assert not legacy.exists()


def test_chat_log(isolated_home: Path, tmp_path: Path) -> None:
    append_chat_log(
        tmp_path,
        prompt="hello",
        mode="plan",
        status="finished",
        agent_id="agent-1",
    )
    log = chat_log_path(tmp_path)
    assert log.is_file()
    line = json.loads(log.read_text(encoding="utf-8").strip())
    assert line["prompt"] == "hello"
    assert line["status"] == "finished"


def test_list_projects(isolated_home: Path, tmp_path: Path) -> None:
    save_session(tmp_path, ProjectSession.create(agent_id="a", cwd=tmp_path))
    projects = list_projects()
    assert len(projects) == 1
    assert projects[0].cwd == str(tmp_path.resolve())


def test_validate_session_cwd_mismatch(isolated_home: Path, tmp_path: Path) -> None:
    other = tmp_path / "other"
    other.mkdir()
    session = ProjectSession.create(agent_id="a", cwd=other)
    with pytest.raises(SessionCwdMismatchError):
        validate_session_cwd(session, tmp_path)


def test_home_dir(isolated_home: Path) -> None:
    assert home_dir() == isolated_home / ".cursor-agent-sdk"
