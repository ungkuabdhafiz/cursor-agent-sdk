"""Per-project session persistence with locking and named sessions."""

from __future__ import annotations

import contextlib
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

SESSION_DIR = ".cursor-agent"
SESSION_FILE = "session.json"
SESSIONS_SUBDIR = "sessions"
SESSION_VERSION = 1


@dataclass
class ProjectSession:
    agent_id: str
    cwd: str
    created_at: str
    updated_at: str
    last_mode: str = "agent"
    version: int = SESSION_VERSION
    session_name: str = "default"

    @classmethod
    def create(
        cls,
        *,
        agent_id: str,
        cwd: Path,
        mode: str = "agent",
        session_name: str = "default",
    ) -> ProjectSession:
        now = _now()
        return cls(
            agent_id=agent_id,
            cwd=str(cwd.resolve()),
            created_at=now,
            updated_at=now,
            last_mode=mode,
            version=SESSION_VERSION,
            session_name=session_name,
        )

    def touch(self, *, mode: str | None = None) -> None:
        self.updated_at = _now()
        if mode is not None:
            self.last_mode = mode


def session_dir(cwd: Path) -> Path:
    return cwd.resolve() / SESSION_DIR


def session_file(cwd: Path, session_name: str = "default") -> Path:
    base = session_dir(cwd)
    if session_name == "default":
        return base / SESSION_FILE
    return base / SESSIONS_SUBDIR / f"{session_name}.json"


def list_sessions(cwd: Path) -> list[str]:
    names: list[str] = []
    default_path = session_file(cwd, "default")
    if default_path.is_file():
        names.append("default")
    sessions_path = session_dir(cwd) / SESSIONS_SUBDIR
    if sessions_path.is_dir():
        for path in sorted(sessions_path.glob("*.json")):
            names.append(path.stem)
    return names


def load_session(cwd: Path, session_name: str = "default") -> ProjectSession | None:
    path = session_file(cwd, session_name)
    if not path.is_file():
        return None

    with session_lock(path):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    return _session_from_payload(payload, cwd=cwd, session_name=session_name)


def save_session(cwd: Path, session: ProjectSession) -> None:
    path = session_file(cwd, session.session_name)
    session.version = SESSION_VERSION
    payload = asdict(session)

    with session_lock(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        temp.replace(path)


def clear_session(cwd: Path, session_name: str = "default") -> bool:
    path = session_file(cwd, session_name)
    if not path.is_file():
        return False
    with session_lock(path):
        path.unlink()
    return True


def validate_session_cwd(session: ProjectSession, cwd: Path) -> None:
    expected = str(cwd.resolve())
    if session.cwd != expected:
        raise SessionCwdMismatchError(
            f"Saved session belongs to {session.cwd!r}, but --cwd is {expected!r}. "
            "Use the correct --cwd, run `cursor-agent-sdk clear`, or pass --new."
        )


class SessionCwdMismatchError(ValueError):
    pass


class SessionNotFoundError(ValueError):
    pass


@contextlib.contextmanager
def session_lock(path: Path):
    """Exclusive lock for session read/write (best-effort on all platforms)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.touch(exist_ok=True)
    fd = os.open(lock_path, os.O_RDWR)
    try:
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        if sys.platform == "win32":
            import msvcrt

            try:
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _session_from_payload(
    payload: dict,
    *,
    cwd: Path,
    session_name: str,
) -> ProjectSession | None:
    agent_id = payload.get("agent_id")
    if not agent_id:
        return None

    version = int(payload.get("version", 0))
    if version > SESSION_VERSION:
        return None

    return ProjectSession(
        agent_id=str(agent_id),
        cwd=payload.get("cwd", str(cwd.resolve())),
        created_at=payload.get("created_at", ""),
        updated_at=payload.get("updated_at", ""),
        last_mode=payload.get("last_mode", "agent"),
        version=version or SESSION_VERSION,
        session_name=payload.get("session_name", session_name),
    )


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
